import logging
import time
from typing import List, Dict, Any, Tuple, Optional
from django.db import transaction
from apps.documents.models import Document
from apps.extraction.models import ExtractionLog
from apps.papers.models import Question
from .pdf_loader import load_pdf
from .text_extractor import extract_text
from .html_formatter import text_to_html, format_question_content, format_answer_content, clean_stored_html_tables
from .chapter_mapper import map_question_to_chapter, get_prepared_chapters


# Phase 3D Services
from .types import LayoutType, QuestionLevel, ParsingContext
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
from .exceptions import DuplicateHierarchyError
from .constants import UNMATCHED_RATIO_THRESHOLD, UNMATCHED_COUNT_THRESHOLD

# Initialize logger
logger = logging.getLogger(__name__)

def extract_document(document: Document, temp_file_path: str = None):
    """
    Full Phase 3D pipeline to process a Document with industrial-grade correctness.
    """
    pdf_path = temp_file_path or document.storage_path
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
        enable_semantic = True
        if q_start_relative is not None:
            logger.info("Optimizing question region start boundary: relative_offset=%d", q_start_relative)
            q_part = q_part[q_start_relative:]
            q_base_offset += q_start_relative
            enable_semantic = False
            
        # 4. Parsing with Config and Base Offsets
        context = ParsingContext()
        q_parser = QuestionParser(config)
        a_parser = AnswerParser(config)
        
        parsed_questions = q_parser.parse(q_part, page_offsets, base_offset=q_base_offset, enable_semantic_validation=enable_semantic, context=context)
        
        valid_question_paths = {tuple(q.hierarchy_path) for q in parsed_questions}
        
        # Best-effort Answer Parsing for UNKNOWN layout
        parsed_answers = []
        # UNKNOWN should require actual header signals to avoid false positives (e.g. "Answer the following")
        if layout_res.layout != LayoutType.UNKNOWN:
            parsed_answers = a_parser.parse(a_part, page_offsets, base_offset=a_base_offset, context=context, valid_question_paths=valid_question_paths)
        else:
            # Best effort: require at least 2 distinct answer headers
            signals = 0
            for p in config.answer_header_patterns:
                signals += len(p.findall(a_part))
                if signals >= 2: break
                
            if signals >= 2:
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
        
        # Build lookup for matched answers based on canonical path tuple
        answer_lookup = {tuple(q.hierarchy_path): a for q, a in match_res.matches}

        # Duplicate detection/logging before persistence
        seen_questions = {}
        # Cache uses id(pq) because the same ParsedQuestion instance is reused throughout the pipeline.
        # This avoids recomputing hierarchy_key without relying on hierarchy content as a lookup key.
        hierarchy_keys = {}
        for pq in parsed_questions:
            h_key = build_hierarchy_key(pq.hierarchy_path)
            if h_key in seen_questions:
                prev_q = seen_questions[h_key]
                raise DuplicateHierarchyError(
                    f"Duplicate hierarchy key detected\n\n"
                    f"Document:\n"
                    f"{document.title} (ID: {document.document_id})\n\n"
                    f"Hierarchy key:\n"
                    f"{h_key}\n\n"
                    f"First\n"
                    f"-----\n"
                    f"Raw path:\n"
                    f"{prev_q.hierarchy_path}\n\n"
                    f"Page:\n"
                    f"{prev_q.start_page}\n\n"
                    f"Preview:\n"
                    f"'{prev_q.text[:80]}...'\n\n"
                    f"Second\n"
                    f"------\n"
                    f"Raw path:\n"
                    f"{pq.hierarchy_path}\n\n"
                    f"Page:\n"
                    f"{pq.start_page}\n\n"
                    f"Preview:\n"
                    f"'{pq.text[:80]}...'"
                )
            seen_questions[h_key] = pq
            hierarchy_keys[id(pq)] = h_key

        # 7. Persistence inside a transaction
        with transaction.atomic():
            document.total_pages = len(pages_data)
            document.save(update_fields=["total_pages"])
            
            # NOTE (FUTURE SCOPE): Automatic chapter mapping currently runs for all documents
            # processed by the extraction pipeline. If a future release restricts automatic chapter
            # mapping strictly to RTP document uploads, check: if getattr(document, 'document_type', None) == 'RTP':
            prepared_chapters = get_prepared_chapters(document.subject)
            
            # hierarchy_map: tuple(path) -> Question object
            hierarchy_map = {}
            active_chapter = None

            for idx, pq in enumerate(parsed_questions):
                # 7.1 Enrichment
                candidate_header_text = ""
                if idx > 0:
                    prev_pq = parsed_questions[idx-1]
                    gap_text = q_part[prev_pq.end_offset:pq.start_offset].strip()
                    trailing_prev = prev_pq.text[-250:] if prev_pq.text else ""
                    candidate_header_text = gap_text + "\n" + trailing_prev
                else:
                    candidate_header_text = q_part[:pq.start_offset]

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
                if not matched_chapter and prepared_chapters:
                    q_full = (pq.shared_context or "") + "\n" + pq.text
                    matched_chapter = map_question_to_chapter(q_full, prepared_chapters)

                marks = None
                try:
                    # Provide larger context to marks extractor
                    marks = marks_ext.extract(pq.text)
                except Exception:
                    logger.exception("Marks extraction failed for %s", pq.raw_header)
                
                q_type = "UNIDENTIFIED"
                try:
                    q_type = classifier.classify(pq.text)
                except Exception:
                    logger.exception("Classification failed for %s", pq.raw_header)
                
                # ... rest of loop
                instr = None
                try:
                    instr = instr_det.detect(pq.text)
                except Exception:
                    logger.exception("Instruction detection failed for %s", pq.raw_header)
                
                # Answer Matching
                ans = answer_lookup.get(tuple(pq.hierarchy_path))
                ans_text = ans.text if ans else ""
                
                # HTML Formatting
                q_content = format_question_content(pq.text, shared_context=pq.shared_context)
                ans_working_notes = ans.working_notes if ans else []
                a_content = format_answer_content(ans_text, working_notes=ans_working_notes) if (ans_text or ans_working_notes) else ""


                # 7.2 Resolve Parent deterministically
                parent_q = None
                if len(pq.hierarchy_path) > 1:
                    parent_path = tuple(pq.hierarchy_path[:-1])
                    parent_q = hierarchy_map.get(parent_path)

                if not matched_chapter and parent_q and parent_q.chapter:
                    matched_chapter = parent_q.chapter

                # 7.3 Create Record
                sub_label_raw = ".".join(pq.hierarchy_path[1:]) if len(pq.hierarchy_path) > 1 else None
                sub_question_label = None
                if sub_label_raw:
                    sub_question_label = sub_label_raw[:10]
                    if len(sub_label_raw) > 10:
                        logger.warning(
                            "Sub-question label truncated from '%s' to '%s' for question %s (Document ID: %d)",
                            sub_label_raw, sub_question_label, pq.hierarchy_path[0], document.document_id
                        )

                clean_q = clean_stored_html_tables(q_content) if '<table' in q_content else q_content
                clean_a = clean_stored_html_tables(a_content) if '<table' in a_content else a_content

                q_obj = Question.objects.create(
                    document=document,
                    parent_question=parent_q,
                    chapter=matched_chapter,
                    question_number=pq.hierarchy_path[0],
                    sub_question_label=sub_question_label,
                    hierarchy_key=hierarchy_keys[id(pq)],
                    question_text=pq.text,
                    question_content=clean_q,
                    answer_text=ans_text,
                    answer_content=clean_a,
                    question_type=q_type,
                    instruction_type=instr,
                    marks=marks,
                    source_page=pq.start_page
                )
                
                # Keep track for hierarchy resolution
                hierarchy_map[tuple(pq.hierarchy_path)] = q_obj

            # Inherit chapter across questions in the same shared_context block
            context_groups = {}
            for h_path, q_obj in hierarchy_map.items():
                if q_obj.question_content and 'shared-context' in q_obj.question_content:
                    ctx_key = q_obj.question_content.split('shared-context', 1)[1][:200]
                    context_groups.setdefault(ctx_key, []).append(q_obj)

            for group_qs in context_groups.values():
                grp_ch = next((q.chapter for q in group_qs if q.chapter), None)
                if grp_ch:
                    for q in group_qs:
                        if not q.chapter:
                            q.chapter = grp_ch
                            q.save(update_fields=['chapter'])

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
