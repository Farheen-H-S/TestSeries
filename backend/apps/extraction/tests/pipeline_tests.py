import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

import unittest
from unittest.mock import patch, MagicMock

class PipelineErrorHandlingTests(unittest.TestCase):
    @patch('apps.extraction.services.extraction_pipeline.load_pdf')
    @patch('apps.extraction.services.extraction_pipeline.extract_text')
    @patch('apps.extraction.services.extraction_pipeline.logger')
    @patch('apps.extraction.services.extraction_pipeline.ExtractionLog')
    def test_pipeline_error_handling_and_cleanup(self, mock_extraction_log_cls, mock_logger, mock_extract_text, mock_load_pdf):
        from apps.extraction.services.extraction_pipeline import extract_document
        from apps.documents.models import Document
        
        # 1. Setup mocks
        mock_pdf = MagicMock()
        mock_load_pdf.return_value = mock_pdf
        
        # Make extract_text raise a clear error to simulate failure
        test_exception = ValueError("Simulated extraction text failure")
        mock_extract_text.side_effect = test_exception
        
        # Mock document
        mock_document = MagicMock()
        mock_document.document_id = "doc_123"
        mock_document.storage_path = "/path/to/test.pdf"
        
        # Mock log object returned by create
        mock_log = MagicMock()
        mock_extraction_log_cls.objects.create.return_value = mock_log
        
        # 2. Run extraction and assert exception is raised
        with self.assertRaises(ValueError) as context:
            extract_document(mock_document)
            
        self.assertEqual(str(context.exception), "Simulated extraction text failure")
        
        # 3. Verify cleanup: pdf.close() was called
        mock_pdf.close.assert_called_once()
        
        # 4. Verify status updates
        # Document status should be set to PROCESSING then FAILED
        self.assertEqual(mock_document.extraction_status, Document.ExtractionStatus.FAILED)
        mock_document.save.assert_any_call(update_fields=["extraction_status"])
        
        # ExtractionLog status should be set to FAILED and message should be str(e)
        self.assertEqual(mock_log.status, mock_extraction_log_cls.Status.FAILED)
        self.assertEqual(mock_log.message, "Simulated extraction text failure")
        mock_log.save.assert_called_with(update_fields=["status", "message"])
        
        # 5. Verify single stack trace / no duplicate logging
        # We expect logger.exception to be called once with context
        mock_logger.exception.assert_called_once_with(
            "Extraction failed | document_id=%s | storage_path=%s",
            "doc_123",
            "/path/to/test.pdf"
        )


if __name__ == "__main__":
    import django
    # Ensure TestSeries is importable when run directly
    sys.path.append(os.path.join(os.getcwd(), 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TestSeries.settings')
    try:
        django.setup()
    except Exception:
        pass
    unittest.main()
