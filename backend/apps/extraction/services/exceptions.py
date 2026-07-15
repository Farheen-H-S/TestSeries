"""
Custom exceptions for extraction services.
"""

class ExtractionError(Exception):
    """Base exception for all extraction-related errors."""
    pass


class PDFLoadError(ExtractionError):
    """Raised when a PDF cannot be loaded or is invalid."""
    pass


class DuplicateHierarchyError(ExtractionError):
    """Raised when duplicate hierarchy keys are produced during extraction."""
    pass

