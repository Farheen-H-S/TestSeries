import logging
import time
from typing import List, Dict, Any, Tuple, Optional
from django.db import transaction
from apps.documents.models import Document
from apps.extraction.models import ExtractionLog
from apps.papers.models import Question
from .pdf_loader import load_pdf
from .text_extractor import extract_text
from .html_formatter import text_to_html
from .chapter_mapper import map_question_to_chapter, get_prepared_chapters

# Phase 3D Services
from .types import LayoutType, QuestionLevel
from .layout_detector import DocumentLayoutDetector
from .section_splitter import SectionSplitter
from .question_parser import QuestionParser
from .answer_parser import AnswerParser
from .answer_matcher import AnswerMatcher
from .marks_extractor import MarksExtractor
from .question_classifier import QuestionClassifier
from .instruction_detector import InstructionDetector

from .extraction_patterns import get_default_parser_config

# Initialize logger
logger = logging.getLogger(__name__)

# Configurable initial default thresholds for unmatched items, expected to be tuned after testing
UNMATCHED_RATIO_THRESHOLD = 0.20
UNMATCHED_COUNT_THRESHOLD = 5

def extract_document(document: Document):
    """
    Full Phase 3D pipeline to process a Document with industrial-grade correctness.
    """
    logger.info("Starting extraction | document_id=%s | storage_path=%s", document.document_id, document.storage_path)
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
        pdf_doc = load_pdf(document.storage_path)
        try:
            pages_data = extract_text(pdf_doc)
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

        # 4. Parsing with Config and Base Offsets
        q_parser = QuestionParser(config)
        a_parser = AnswerParser(config)
        
        parsed_questions = q_parser.parse(q_part, page_offsets, base_offset=q_base_offset)
        
        # Best-effort Answer Parsing for UNKNOWN layout
        parsed_answers = []
        # UNKNOWN should require actual header signals to avoid false positives (e.g. "Answer the following")
        if layout_res.layout != LayoutType.UNKNOWN:
            parsed_answers = a_parser.parse(a_part, page_offsets, base_offset=a_base_offset)
        else:
            # Best effort: require at least 2 distinct answer headers
            signals = 0
            for p in config.answer_header_patterns:
                signals += len(p.findall(a_part))
                if signals >= 2: break
                
            if signals >= 2:
                parsed_answers = a_parser.parse(a_part, page_offsets, base_offset=a_base_offset)

        # 5. Matching using Canonical Hierarchy Paths
        matcher = AnswerMatcher()
        match_res = matcher.match(parsed_questions, parsed_answers)
        
        # Log diagnostics
        diag = match_res.diagnostics
        logger.info(
            "Matching complete | matched=%d | unmatched_questions=%d | unmatched_answers=%d | time_ms=%.2f",
            diag.matched_count, len(diag.unmatched_questions), 
            len(diag.unmatched_answers), diag.processing_time_ms
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

        # 7. Persistence inside a transaction
        with transaction.atomic():
            document.total_pages = len(pages_data)
            document.save(update_fields=["total_pages"])
            
            prepared_chapters = get_prepared_chapters(document.subject)
            
            # hierarchy_map: tuple(path) -> Question object
            hierarchy_map = {}

            # Sort questions by hierarchy depth then order to ensure parents are created first
            # But the parser already handles them in order.
            for pq in parsed_questions:
                # 7.1 Enrichment
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
                
                instr = None
                try:
                    instr = instr_det.detect(pq.text)
                except Exception:
                    logger.exception("Instruction detection failed for %s", pq.raw_header)
                
                # Answer Matching
                ans = answer_lookup.get(tuple(pq.hierarchy_path))
                ans_text = ans.text if ans else ""
                
                # HTML Formatting
                q_content = text_to_html(pq.text)
                a_content = text_to_html(ans_text) if ans_text else ""
                
                # Chapter Mapping
                matched_chapter = None
                try:
                    matched_chapter = map_question_to_chapter(
                        pq.text,
                        prepared_chapters=prepared_chapters
                    )
                except Exception:
                    logger.exception("Chapter mapping failed for %s", pq.raw_header)

                # 7.2 Resolve Parent deterministically
                parent_q = None
                if len(pq.hierarchy_path) > 1:
                    parent_path = tuple(pq.hierarchy_path[:-1])
                    parent_q = hierarchy_map.get(parent_path)

                # 7.3 Create Record
                q_obj = Question.objects.create(
                    document=document,
                    parent_question=parent_q,
                    chapter=matched_chapter,
                    question_number=pq.hierarchy_path[0],
                    sub_question_label=pq.hierarchy_path[1] if len(pq.hierarchy_path) > 1 else None,
                    question_text=pq.text,
                    question_content=q_content,
                    answer_text=ans_text,
                    answer_content=a_content,
                    question_type=q_type,
                    instruction_type=instr,
                    marks=marks,
                    source_page=pq.start_page
                )
                
                # Keep track for hierarchy resolution
                hierarchy_map[tuple(pq.hierarchy_path)] = q_obj

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
