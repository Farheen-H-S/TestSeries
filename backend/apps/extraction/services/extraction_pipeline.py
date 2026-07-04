from typing import List, Dict, Any
from .pdf_loader import load_pdf
from .text_extractor import extract_text

def run_extraction_pipeline(file_path: str) -> List[Dict[str, Any]]:
    """
    Orchestrate the extraction of text from a PDF file.
    
    This function handles resource management (opening/closing document)
    and coordinates between loading and extraction services.

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
        # Ensure the document is always closed, even if extraction fails
        doc.close()
