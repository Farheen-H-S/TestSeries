import fitz
from typing import List, Dict, Any

def extract_text(doc: fitz.Document) -> List[Dict[str, Any]]:
    """
    Extract raw text from a PDF document page-by-page.

    Args:
        doc: An opened fitz.Document object.

    Returns:
        A list of dictionaries containing page number and extracted text.
        Example: [{"page_number": 1, "text": "..."}, ...]
    """
    extracted_pages = []

    for page in doc:
        page_content = {
            "page_number": page.number + 1,
            "text": page.get_text().strip()
        }
        extracted_pages.append(page_content)

    return extracted_pages
