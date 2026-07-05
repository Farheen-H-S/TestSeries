from typing import List, Dict, Any
from django.db import transaction
from apps.documents.models import Document
from apps.extraction.models import ExtractionLog
from apps.papers.models import Question
from .pdf_loader import load_pdf
from .text_extractor import extract_text
from .question_parser import parse_questions
from .html_formatter import text_to_html

def run_extraction_pipeline(file_path: str) -> List[Dict[str, Any]]:
    """
    Orchestrate the extraction of text from a PDF file.
    
    Args:
        file_path: The absolute path to the PDF file.

    Returns:
        A list of dictionaries containing page number and extracted text.
    """
    doc = load_pdf(file_path)
    
    try:
        pages = extract_text(doc)
        return pages
    finally:
        doc.close()

def extract_document(document: Document):
    """
    Full pipeline to process a Document: extract text, parse questions, and persist to DB.
    
    This function handles status updates, logging, and database transactions.
    """
    # 1. Initialize Status and Log
    document.extraction_status = Document.ExtractionStatus.PROCESSING
    document.save(update_fields=["extraction_status"])
    
    log = ExtractionLog.objects.create(
        document=document,
        status=ExtractionLog.Status.PROCESSING
    )
    
    try:
        # 2. Run Python Extraction Logic
        # We perform extraction outside the transaction to minimize lock time
        pages_data = run_extraction_pipeline(document.storage_path)
        
        # 3. Persistence inside a transaction
        with transaction.atomic():
            # Update document page count
            document.total_pages = len(pages_data)
            document.save(update_fields=["total_pages"])
            
            # Parse questions
            questions_data = parse_questions(pages_data)
            
            # TODO: Reprocessing the same document will currently violate the 
            # unique_question_per_document constraint. This will be handled in 
            # a later phase (e.g., delete existing questions or implement update logic).
            # Create Question records
            for q_data in questions_data:
                Question.objects.create(
                    document=document,
                    chapter=None,  # Not implemented in Phase 3B
                    question_number=q_data["question_number"],
                    question_text=q_data["question_text"],
                    question_content=text_to_html(q_data["question_text"]),
                    source_page=q_data["source_page"],
                    question_type="UNIDENTIFIED",
                    answer_text="",
                    answer_content="",
                    marks=None
                )
            
        # 4. Finalize Success
        document.extraction_status = Document.ExtractionStatus.COMPLETED
        document.save(update_fields=["extraction_status"])
        
        log.status = ExtractionLog.Status.COMPLETED
        log.save(update_fields=["status"])
        
    except Exception as e:
        # 5. Handle Failures
        document.extraction_status = Document.ExtractionStatus.FAILED
        document.save(update_fields=["extraction_status"])
        
        log.status = ExtractionLog.Status.FAILED
        log.message = str(e)
        log.save(update_fields=["status", "message"])
        
        # Re-raise to allow caller to handle if needed
        raise
