import os
import re
import logging
import time
from typing import List, Dict, Any, Tuple, Optional
from django.db import transaction
from apps.documents.models import Document
from apps.extraction.models import ExtractionLog
from apps.papers.models import Question
from .pdf_loader import load_pdf
from .text_extractor import extract_text
from .html_formatter import format_question_content, format_answer_content, clean_stored_html_tables, clean_metadata_text
from .chapter_mapper import map_question_to_chapter, get_prepared_chapters


# Phase 3D Services
from .types import LayoutType, ParsingContext
from .layout_detector import DocumentLayoutDetector
from .section_splitter import SectionSplitter
from .question_parser import QuestionParser
from .answer_parser import AnswerParser
from .answer_matcher import AnswerMatcher
from .marks_extractor import MarksExtractor
from .question_classifier import QuestionClassifier
from .instruction_detector import InstructionDetector

from .extraction_patterns import get_default_parser_config
from .hierarchy_utils import build_hierarchy_key
from .exceptions import ExtractionError
from .constants import UNMATCHED_RATIO_THRESHOLD, UNMATCHED_COUNT_THRESHOLD

# Initialize logger
logger = logging.getLogger(__name__)

def extract_document(document: Document, temp_file_path: str = None):
    """
    Full Phase 3D pipeline to process a Document with industrial-grade correctness.
    """
    raw_path = temp_file_path or (document.storage_path.path if hasattr(document.storage_path, 'path') else str(document.storage_path))
    if not os.path.isabs(raw_path) and not os.path.exists(raw_path):
        from django.conf import settings
        raw_path = os.path.join(settings.MEDIA_ROOT, raw_path)
    pdf_path = raw_path
    logger.info("Starting extraction | document_id=%s | storage_path=%s | pdf_path=%s", document.document_id, document.storage_path, pdf_path)
    document.extraction_status = Document.ExtractionStatus.PROCESSING
    document.save(update_fields=["extraction_status"])
    
    log = ExtractionLog.objects.create(
        document=document,
        status=ExtractionLog.Status.PROCESSING
    )
    
    start_time = time.time()
    config = get_default_parser_config()
    
    try:
        # 1. Load and Extract Raw Text
        pdf_doc = load_pdf(pdf_path)
        try:
            pages_data = extract_text(pdf_doc, document_id=document.document_id)
            logger.info("Loaded document | pages=%d", len(pages_data))
        finally:
            pdf_doc.close()

        # Prepare full text and page offsets for the parsers
        full_text = ""
        page_offsets: List[Tuple[int, int]] = []
        current_offset = 0
        for p in pages_data:
            page_offsets.append((current_offset, p["page_number"]))
            full_text += p["text"] + "\n"
            current_offset += len(p["text"]) + 1

        # 2. Layout Detection
        from .normalizer import Normalizer
        normalized_full_text = Normalizer.pre_normalize_ocr(full_text)
        
        # Count OCR corrections passively for threshold check
        ocr_corrections = sum(1 for c1, c2 in zip(full_text, normalized_full_text) if c1 != c2)
        char_threshold = Normalizer.OCR_ANOMALY_CHAR_PERCENTAGE_THRESHOLD
        page_threshold = Normalizer.OCR_ANOMALY_PER_PAGE_THRESHOLD
        text_len = len(full_text)
        num_pages = len(pages_data)
        corrections_ratio = ocr_corrections / text_len if text_len > 0 else 0.0
        corrections_per_page = ocr_corrections / num_pages if num_pages > 0 else 0.0
        
        if corrections_ratio > char_threshold or corrections_per_page > page_threshold:
            logger.warning(
                "OCR anomalies detected | total_corrections=%d | corrections_ratio=%.4f | corrections_per_page=%.2f",
                ocr_corrections, corrections_ratio, corrections_per_page
            )
            
        detector = DocumentLayoutDetector(config)
        layout_res = detector.detect_layout(normalized_full_text)
        logger.info("Layout detected | layout=%s | reason=%s", layout_res.layout.value, layout_res.reason)
        if layout_res.layout == LayoutType.UNKNOWN:
            logger.warning("Unknown layout detected | reason=%s", layout_res.reason)

        # 3. Text Slicing
        splitter = SectionSplitter()
        if layout_res.layout == LayoutType.SECTION_WISE:
            q_part, a_part = splitter.split(full_text, layout_res.boundary_position)
            q_base_offset = 0
            a_base_offset = layout_res.boundary_position
        else:
            q_part, a_part = full_text, full_text
            q_base_offset = 0
            a_base_offset = 0

        # Optimization: Detect start of actual question region if possible
        q_start_relative = None
        for pattern in config.question_start_patterns:
            m = pattern.search(q_part)
            if m:
                q_start_relative = m.start()
                break
        enable_semantic = (q_start_relative is None)
        if q_start_relative is not None:
            logger.info("Optimizing question region start boundary: relative_offset=%d", q_start_relative)
            q_part = q_part[q_start_relative:]
            q_base_offset += q_start_relative
            
        # 4. Parsing with Config and Base Offsets
        context = ParsingContext()
        q_parser = QuestionParser(config)
        a_parser = AnswerParser(config)
        
        parsed_answers = []
        if layout_res.layout != LayoutType.UNKNOWN:
            parsed_answers = a_parser.parse(a_part, page_offsets, base_offset=a_base_offset, context=context)
            if parsed_answers:
                context.valid_question_paths = {tuple(a.hierarchy_path) for a in parsed_answers if a.hierarchy_path}

        parsed_questions = q_parser.parse(q_part, page_offsets, base_offset=q_base_offset, enable_semantic_validation=enable_semantic, context=context)
        
        valid_question_paths = {tuple(q.hierarchy_path) for q in parsed_questions}
        
        if not parsed_answers and layout_res.layout == LayoutType.UNKNOWN:
            signals = 0
            for p in config.answer_header_patterns:
                signals += len(p.findall(a_part))
                if signals >= 2: break
                
            if signals >= 2:
                parsed_answers = a_parser.parse(a_part, page_offsets, base_offset=a_base_offset, context=context, valid_question_paths=valid_question_paths)
        elif parsed_answers:
            parsed_answers = a_parser.parse(a_part, page_offsets, base_offset=a_base_offset, context=context, valid_question_paths=valid_question_paths)

        # 5. Matching using Canonical Hierarchy Paths
        logger.info(
            "Pipeline parsing summary | layout=%s | q_part_len=%d | a_part_len=%d | parsed_questions=%d | parsed_answers=%d",
            layout_res.layout.value, len(q_part), len(a_part), len(parsed_questions), len(parsed_answers)
        )
        matcher = AnswerMatcher()
        match_res = matcher.match(parsed_questions, parsed_answers)

        # Log diagnostics
        diag = match_res.diagnostics
        logger.info("All Parsed Questions hierarchy paths: %s", [".".join(q.hierarchy_path) for q in parsed_questions])
        logger.info("All Parsed Answers hierarchy paths: %s", [".".join(a.hierarchy_path) for a in parsed_answers])
        logger.info(
            "Matched pairs: %s",
            [(".".join(q.hierarchy_path), ".".join(a.hierarchy_path)) for q, a in match_res.matches]
        )
        logger.info("Unmatched Questions: %s", diag.unmatched_questions)
        logger.info("Unmatched Answers: %s", diag.unmatched_answers)
        logger.info("Ambiguous matches: %s", diag.ambiguous_matches)

        logger.info(
            "Matching complete | matched=%d | unmatched_questions=%d | unmatched_answers=%d | ambiguous_matches=%d | time_ms=%.2f",
            diag.matched_count, len(diag.unmatched_questions), 
            len(diag.unmatched_answers), len(diag.ambiguous_matches), diag.processing_time_ms
        )
        
        unmatched_q_count = len(diag.unmatched_questions)
        unmatched_a_count = len(diag.unmatched_answers)
        total_q_count = len(parsed_questions)
        total_a_count = len(parsed_answers)
        
        q_ratio = unmatched_q_count / total_q_count if total_q_count > 0 else 0.0
        a_ratio = unmatched_a_count / total_a_count if total_a_count > 0 else 0.0
        
        # Log individual unmatched details at DEBUG level
        for unmatched_q in diag.unmatched_questions:
            logger.debug("Unmatched question hierarchy path: %s", unmatched_q)
        for unmatched_a in diag.unmatched_answers:
            logger.debug("Unmatched answer hierarchy path: %s", unmatched_a)
            
        # Escalate to WARNING if threshold breached
        if unmatched_q_count > UNMATCHED_COUNT_THRESHOLD or q_ratio > UNMATCHED_RATIO_THRESHOLD:
            logger.warning(
                "High unmatched questions rate | unmatched_count=%d | unmatched_ratio=%.4f | threshold_count=%d | threshold_ratio=%.2f",
                unmatched_q_count, q_ratio, UNMATCHED_COUNT_THRESHOLD, UNMATCHED_RATIO_THRESHOLD
            )
        if unmatched_a_count > UNMATCHED_COUNT_THRESHOLD or a_ratio > UNMATCHED_RATIO_THRESHOLD:
            logger.warning(
                "High unmatched answers rate | unmatched_count=%d | unmatched_ratio=%.4f | threshold_count=%d | threshold_ratio=%.2f",
                unmatched_a_count, a_ratio, UNMATCHED_COUNT_THRESHOLD, UNMATCHED_RATIO_THRESHOLD
            )
            
        # Check for malformed/corrupted document structure warning (suspicious hierarchy)
        total_q_matches = q_parser.diagnostics.total_matches
        rejected_q_headers_count = len(q_parser.diagnostics.rejected_headers)
        if total_q_matches >= 5 and (rejected_q_headers_count / total_q_matches) > 0.80:
            logger.warning(
                "Potential corrupt/malformed document layout | rejected_headers_count=%d | total_matches=%d | ratio=%.4f",
                rejected_q_headers_count, total_q_matches, rejected_q_headers_count / total_q_matches
            )
            
        # Diagnostics Summary
        logger.debug(
            "Diagnostics Summary | Q_total=%d Q_valid=%d Q_rejected=%d | A_total=%d A_valid=%d A_rejected=%d | matched_pairs=%d unmatched_Q=%d unmatched_A=%d",
            q_parser.diagnostics.total_matches, q_parser.diagnostics.validated_count, len(q_parser.diagnostics.rejected_headers),
            a_parser.diagnostics.total_matches, a_parser.diagnostics.validated_count, len(a_parser.diagnostics.rejected_headers),
            diag.matched_count, unmatched_q_count, unmatched_a_count
        )

        # 6. Enrichment Hooks
        marks_ext = MarksExtractor(config)
        classifier = QuestionClassifier() # Uses CLASSIFICATION_RULES internally
        instr_det = InstructionDetector(config.instruction_priority)
        
        # Build lookup for all parsed answers
        all_answers_lookup = {tuple(a.hierarchy_path): a for a in parsed_answers if a.hierarchy_path}

        # Duplicate detection/deduplication before persistence
        seen_questions = {}
        hierarchy_keys = {}
        for pq in parsed_questions:
            h_key = build_hierarchy_key(pq.hierarchy_path)
            if h_key in seen_questions:
                prev_q = seen_questions[h_key]
                suffix = 2
                dedup_key = f"{h_key}.{suffix}"
                while dedup_key in seen_questions:
                    suffix += 1
                    dedup_key = f"{h_key}.{suffix}"
                logger.warning(
                    "Duplicate hierarchy key '%s' detected between p.%d and p.%d; deduplicating to '%s'",
                    h_key, prev_q.start_page, pq.start_page, dedup_key
                )
                pq.hierarchy_path = pq.hierarchy_path + [str(suffix)]
                h_key = dedup_key
            seen_questions[h_key] = pq
            hierarchy_keys[id(pq)] = h_key
        # Guard against zero-question empty extractions
        if not parsed_questions:
            raise ExtractionError(
                f"Zero questions extracted from document '{document.title}' (ID: {document.document_id}). "
                f"Total potential matches evaluated: {q_parser.diagnostics.total_matches}."
            )

        # Group parsed_questions by primary question key
        grouped_questions: Dict[str, List[ParsedQuestion]] = {}
        for pq in parsed_questions:
            if not pq.hierarchy_path:
                continue
            if len(pq.hierarchy_path) >= 2 and pq.hierarchy_path[0].isdigit() and pq.hierarchy_path[1].isdigit():
                key = f"{pq.hierarchy_path[0]}.{pq.hierarchy_path[1]}"
            else:
                key = pq.hierarchy_path[0]
            grouped_questions.setdefault(key, []).append(pq)

        # 7. Persistence inside a transaction
        with transaction.atomic():
            Question.objects.filter(document=document).delete()
            document.total_pages = len(pages_data)
            document.save(update_fields=["total_pages"])
            
            prepared_chapters = get_prepared_chapters(document.subject)
            subj_name = document.subject.name if (document and document.subject) else None
            active_chapter = None

            for idx, (q_key, pqs) in enumerate(grouped_questions.items()):
                first_pq = pqs[0]
                last_pq = pqs[-1]

                # 7.1 Sequential Chapter Mapping
                candidate_header_text = ""
                if idx > 0:
                    prev_pqs = list(grouped_questions.values())[idx-1]
                    prev_last_pq = prev_pqs[-1]
                    gap_text = q_part[prev_last_pq.end_offset:first_pq.start_offset].strip()
                    trailing_prev = prev_last_pq.text[-250:] if prev_last_pq.text else ""
                    candidate_header_text = gap_text + "\n" + trailing_prev
                else:
                    candidate_header_text = q_part[max(0, first_pq.start_offset - 500):first_pq.start_offset].strip()

                if candidate_header_text:
                    temp_chapter = None
                    try:
                        temp_chapter = map_question_to_chapter(
                            candidate_header_text,
                            prepared_chapters=prepared_chapters
                        )
                    except Exception:
                        logger.exception("Sequential chapter mapping failed at index %d", idx)
                    
                    if temp_chapter:
                        active_chapter = temp_chapter
                        logger.info("Sequential chapter state updated | chapter=%s | index=%d", active_chapter.chapter_name, idx)

                matched_chapter = active_chapter

                # 7.2 Consolidate Question Text and HTML Content
                q_text_parts = []
                shared_contexts = []
                
                for sub in pqs:
                    sub_label = ".".join(sub.hierarchy_path[1:]) if len(sub.hierarchy_path) > 1 else None
                    clean_text = clean_metadata_text(sub.text, subject_name=subj_name, prepared_chapters=prepared_chapters)
                    if sub.shared_context:
                        clean_ctx = clean_metadata_text(sub.shared_context, subject_name=subj_name, prepared_chapters=prepared_chapters)
                        if clean_ctx and clean_ctx not in shared_contexts:
                            shared_contexts.append(clean_ctx)
                            
                    if sub_label and sub.raw_header:
                        q_text_parts.append(f"{sub.raw_header.strip()} {clean_text}".strip())
                    else:
                        q_text_parts.append(clean_text)
                        
                consolidated_q_text = "\n\n".join(filter(None, q_text_parts))
                consolidated_shared_ctx = "\n\n".join(shared_contexts) if shared_contexts else None
                q_content = format_question_content(consolidated_q_text, shared_context=consolidated_shared_ctx)

                # 7.3 Consolidate Answer Text and HTML Content in Natural Document Order
                answer_segments = []
                seen_ans_keys = set()
                
                # Direct matching sub-answers
                for sub in pqs:
                    h_tuple = tuple(sub.hierarchy_path)
                    if h_tuple in all_answers_lookup and h_tuple not in seen_ans_keys:
                        seen_ans_keys.add(h_tuple)
                        ans = all_answers_lookup[h_tuple]
                        sub_label = ".".join(sub.hierarchy_path[1:]) if len(sub.hierarchy_path) > 1 else None
                        if ans.text and ans.text.strip():
                            if sub_label and sub.raw_header and not ans.text.strip().startswith(sub.raw_header.strip()):
                                answer_segments.append((ans.start_offset, f"{sub.raw_header.strip()} {ans.text.strip()}"))
                            else:
                                answer_segments.append((ans.start_offset, ans.text.strip()))
                        for wn_idx, wn in enumerate(ans.working_notes or []):
                            if isinstance(wn, dict):
                                title = wn.get("title", "")
                                content = wn.get("content", "")
                                wn_str = f"{title}\n{content}".strip() if title else content.strip()
                            elif hasattr(wn, "content"):
                                title = getattr(wn, "title", "") or ""
                                content = getattr(wn, "content", "") or ""
                                wn_str = f"{title}\n{content}".strip() if title else content.strip()
                            elif isinstance(wn, str):
                                wn_str = wn.strip()
                            else:
                                wn_str = str(wn).strip()
                            if wn_str:
                                answer_segments.append((ans.start_offset + 0.1 + wn_idx * 0.01, wn_str))
                                
                # Also check any child answers under this primary question key (e.g. answer key has (a), (b) under question 10)
                for p, ans in all_answers_lookup.items():
                    if p and p[0] == q_key and p not in seen_ans_keys:
                        seen_ans_keys.add(p)
                        if ans.text and ans.text.strip():
                            answer_segments.append((ans.start_offset, ans.text.strip()))
                        for wn_idx, wn in enumerate(ans.working_notes or []):
                            if isinstance(wn, dict):
                                title = wn.get("title", "")
                                content = wn.get("content", "")
                                wn_str = f"{title}\n{content}".strip() if title else content.strip()
                            elif hasattr(wn, "content"):
                                title = getattr(wn, "title", "") or ""
                                content = getattr(wn, "content", "") or ""
                                wn_str = f"{title}\n{content}".strip() if title else content.strip()
                            elif isinstance(wn, str):
                                wn_str = wn.strip()
                            else:
                                wn_str = str(wn).strip()
                            if wn_str:
                                answer_segments.append((ans.start_offset + 0.1 + wn_idx * 0.01, wn_str))

                # Order all answer segments in natural document sequence
                answer_segments.sort(key=lambda x: x[0])
                full_ans_text = "\n\n".join([s[1] for s in answer_segments if s[1]])

                # Universal Rupee normalization: map all backtick characters to ₹
                clean_q_raw = consolidated_q_text.replace("`", "₹").replace("\u0060", "₹")
                clean_ans_raw = full_ans_text.replace("`", "₹").replace("\u0060", "₹")
                
                clean_q_text = clean_metadata_text(clean_q_raw, subject_name=subj_name, prepared_chapters=prepared_chapters)
                clean_ans_text = clean_metadata_text(clean_ans_raw, subject_name=subj_name, prepared_chapters=prepared_chapters)
                
                q_content = format_question_content(clean_q_text, shared_context=consolidated_shared_ctx)
                a_content = format_answer_content(clean_ans_text) if clean_ans_text else ""

                # 7.4 Marks Extraction
                marks = None
                sub_marks = []
                for sub in pqs:
                    m = marks_ext.extract(sub.text)
                    if m:
                        sub_marks.append(m)
                if sub_marks:
                    marks = sum(sub_marks) if len(sub_marks) > 1 else sub_marks[0]

                # 7.5 Classification & Instruction
                q_type = "UNIDENTIFIED"
                try:
                    q_type = classifier.classify(consolidated_q_text)
                except Exception:
                    logger.exception("Classification failed for %s", q_key)

                instr = None
                try:
                    instr = instr_det.detect(consolidated_q_text)
                except Exception:
                    logger.exception("Instruction detection failed for %s", q_key)

                clean_q = clean_stored_html_tables(q_content) if '<table' in q_content else q_content
                clean_a = clean_stored_html_tables(a_content) if '<table' in a_content else a_content

                Question.objects.create(
                    document=document,
                    parent_question=None,
                    chapter=matched_chapter,
                    question_number=q_key,
                    sub_question_label=None,
                    hierarchy_key=build_hierarchy_key([q_key]),
                    question_text=clean_q_text,
                    question_content=clean_q,
                    answer_text=clean_ans_text,
                    answer_content=clean_a,
                    question_type=q_type,
                    instruction_type=instr,
                    marks=marks,
                    source_page=first_pq.start_page
                )

        # 8. Finalize Success
        document.extraction_status = Document.ExtractionStatus.COMPLETED
        document.save(update_fields=["extraction_status"])
        
        # Build diagnostic summary for the log
        reject_summary = ""
        if q_parser.diagnostics.rejected_headers:
            reasons = {}
            for r in q_parser.diagnostics.rejected_headers:
                reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
            reject_summary = " Rejections: " + ", ".join([f"{k} ({v})" for k, v in reasons.items()])

        duration = time.time() - start_time
        logger.info(
            "Extraction completed | document_id=%s | pages=%d | questions=%d | answers=%d | matches=%d | duration_seconds=%.2f",
            document.document_id, len(pages_data), len(parsed_questions), len(parsed_answers), diag.matched_count, duration
        )

        log.status = ExtractionLog.Status.COMPLETED
        log.message = (
            f"Extracted {len(parsed_questions)} questions in {duration:.2f}s."
            f" Matches: {diag.matched_count}.{reject_summary}"
        )
        log.save(update_fields=["status", "message"])
        
    except Exception as e:
        logger.exception(
            "Extraction failed | document_id=%s | storage_path=%s",
            document.document_id,
            document.storage_path
        )
        document.extraction_status = Document.ExtractionStatus.FAILED
        document.save(update_fields=["extraction_status"])
        
        log.status = ExtractionLog.Status.FAILED
        log.message = str(e)
        log.save(update_fields=["status", "message"])
        raise
