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

# Initialize logger
logger = logging.getLogger(__name__)

def extract_document(document: Document):
    """
    Full Phase 3D pipeline to process a Document.
    """
    document.extraction_status = Document.ExtractionStatus.PROCESSING
    document.save(update_fields=["extraction_status"])
    
    log = ExtractionLog.objects.create(
        document=document,
        status=ExtractionLog.Status.PROCESSING
    )
    
    start_time = time.time()
    
    try:
        # 1. Load and Extract Raw Text
        pdf_doc = load_pdf(document.storage_path)
        try:
            pages_data = extract_text(pdf_doc)
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
        detector = DocumentLayoutDetector()
        layout_res = detector.detect_layout(full_text)
        logger.info("Detected layout: %s. Reason: %s", layout_res.layout, layout_res.reason)

        # 3. Text Slicing (if SECTION_WISE)
        splitter = SectionSplitter()
        if layout_res.layout == LayoutType.SECTION_WISE:
            q_part, a_part = splitter.split(full_text, layout_res.boundary_position)
        else:
            q_part, a_part = full_text, full_text

        # 4. Parsing
        q_parser = QuestionParser()
        a_parser = AnswerParser()
        
        parsed_questions = q_parser.parse(q_part, page_offsets)
        
        # Best-effort Answer Parsing
        parsed_answers = []
        if layout_res.layout != LayoutType.UNKNOWN or "ANSWER" in a_part.upper():
            parsed_answers = a_parser.parse(a_part, page_offsets)

        # 5. Matching
        matcher = AnswerMatcher()
        match_res = matcher.match(parsed_questions, parsed_answers)
        
        # Log diagnostics
        diag = match_res.diagnostics
        logger.info(
            "Matching complete: %d matched, %d unmatched Q, %d unmatched A. Time: %.2fms",
            diag.matched_count, len(diag.unmatched_questions), 
            len(diag.unmatched_answers), diag.processing_time_ms
        )

        # 6. Enrichment Hooks
        marks_ext = MarksExtractor()
        classifier = QuestionClassifier()
        instr_det = InstructionDetector()
        
        # Build lookup for matched answers
        answer_lookup = {id(q): a for q, a in match_res.matches}

        # 7. Persistence inside a transaction
        with transaction.atomic():
            document.total_pages = len(pages_data)
            document.save(update_fields=["total_pages"])
            
            prepared_chapters = get_prepared_chapters(document.subject)
            
            # hierarchy_map: tuple(path) -> Question object
            hierarchy_map = {}

            for pq in parsed_questions:
                # 7.1 Enrichment
                marks = None
                try:
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
                ans = answer_lookup.get(id(pq))
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

                # 7.2 Resolve Parent
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
                
                # Keep track for hierarchy
                hierarchy_map[tuple(pq.hierarchy_path)] = q_obj

        # 8. Finalize Success
        document.extraction_status = Document.ExtractionStatus.COMPLETED
        document.save(update_fields=["extraction_status"])
        
        log.status = ExtractionLog.Status.COMPLETED
        log.message = f"Extracted {len(parsed_questions)} questions in {time.time() - start_time:.2f}s"
        log.save(update_fields=["status", "message"])
        
    except Exception as e:
        logger.exception("Extraction failed for document %s", document.document_id)
        document.extraction_status = Document.ExtractionStatus.FAILED
        document.save(update_fields=["extraction_status"])
        
        log.status = ExtractionLog.Status.FAILED
        log.message = str(e)
        log.save(update_fields=["status", "message"])
        raise
