import os
import fitz
from .exceptions import PDFLoadError

def load_pdf(file_path: str) -> fitz.Document:
    """
    Load a PDF document using PyMuPDF.

    Args:
        file_path: The absolute path to the PDF file.

    Returns:
        A fitz.Document object.

    Raises:
        FileNotFoundError: If the file does not exist at the given path.
        PDFLoadError: If the file is not a valid PDF or is corrupted.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF file not found at: {file_path}")

    try:
        doc = fitz.open(file_path)
        if not doc.is_pdf:
            doc.close()
            raise PDFLoadError(f"File at {file_path} is not a valid PDF.")
        return doc
    except PDFLoadError:
        raise
    except Exception as e:
        raise PDFLoadError(f"Failed to load PDF from {file_path}: {str(e)}") from e
