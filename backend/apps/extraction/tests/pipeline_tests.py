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


import tempfile
import shutil
from pathlib import Path
from django.test import TestCase, override_settings
from django.conf import settings
from apps.documents.models import Document
from apps.extraction.services.extraction_service import ExtractionService
from apps.syllabus.models import Subject
from django.contrib.auth import get_user_model

class ExtractionServiceTests(TestCase):
    def setUp(self):
        # Create user & subject
        User = get_user_model()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.subject = Subject.objects.create(name="Accountancy", exam_level="Intermediate")
        
        # Setup temporary directories for base_dir and media
        self.test_dir = tempfile.mkdtemp()
        self.temp_media_root = Path(self.test_dir) / "media"
        self.temp_media_root.mkdir(parents=True, exist_ok=True)
        
        # Create a dummy source PDF file
        self.pdf_content = b"%PDF-1.4 ... dummy content ..."
        self.doc_dir = self.temp_media_root / "documents"
        self.doc_dir.mkdir(parents=True, exist_ok=True)
        self.source_pdf = self.doc_dir / "test_paper.pdf"
        self.source_pdf.write_bytes(self.pdf_content)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch('apps.extraction.services.extraction_service.extract_document')
    def test_extraction_service_copies_and_cleans_up_on_success(self, mock_extract_document):
        # Create Document instance
        document = Document.objects.create(
            user=self.user,
            subject=self.subject,
            title="Accountancy Mock Paper",
            document_type=Document.DocumentType.MOCK,
            paper_year=2026,
            storage_path="documents/test_paper.pdf"
        )
        
        # Mock default_storage.path to point to our test source file
        with patch('django.core.files.storage.default_storage.path', return_value=str(self.source_pdf)), \
             override_settings(BASE_DIR=self.test_dir, MEDIA_ROOT=str(self.temp_media_root)):
             
            # Verify temp root doesn't contain extraction files yet
            temp_root = Path(self.test_dir) / "temp"
            self.assertFalse(temp_root.exists())
            
            # Execute service trigger
            ExtractionService.trigger_extraction(document.document_id)
            
            # Assert extract_document was called
            mock_extract_document.assert_called_once()
            passed_doc = mock_extract_document.call_args[0][0]
            passed_temp_path = Path(mock_extract_document.call_args[1]['temp_file_path'])
            
            # Verify the document was passed correctly
            self.assertEqual(passed_doc, document)
            
            # Verify the temporary file path format: <document_id>_<uuid>.pdf
            self.assertEqual(passed_temp_path.parent.parent, temp_root)
            self.assertTrue(passed_temp_path.name.startswith(f"{document.document_id}_"))
            self.assertTrue(passed_temp_path.name.endswith(".pdf"))
            
            # Verify the temp file and its parent unique folder are deleted
            self.assertFalse(passed_temp_path.exists())
            self.assertFalse(passed_temp_path.parent.exists())
            
            # Verify the parent temp_root directory itself is also pruned/deleted (since it is empty)
            self.assertFalse(temp_root.exists())
            
            # Verify original source PDF remains untouched
            self.assertTrue(self.source_pdf.exists())
            self.assertEqual(self.source_pdf.read_bytes(), self.pdf_content)

    @patch('apps.extraction.services.extraction_service.extract_document')
    def test_extraction_service_cleans_up_on_failure(self, mock_extract_document):
        # Simulate extraction failure by throwing an error from pipeline
        mock_extract_document.side_effect = RuntimeError("Simulated pipeline failure")
        
        document = Document.objects.create(
            user=self.user,
            subject=self.subject,
            title="Accountancy Failure Paper",
            document_type=Document.DocumentType.MOCK,
            paper_year=2026,
            storage_path="documents/test_paper.pdf"
        )
        
        captured_temp_path = None
        
        # Mock default_storage.path
        with patch('django.core.files.storage.default_storage.path', return_value=str(self.source_pdf)), \
             override_settings(BASE_DIR=self.test_dir, MEDIA_ROOT=str(self.temp_media_root)):
             
            # Capture the temporary path passed to extract_document before it is deleted
            def extract_side_effect(doc, temp_file_path=None):
                nonlocal captured_temp_path
                captured_temp_path = Path(temp_file_path)
                # Verify that temp file exists and has correct content during execution
                self.assertTrue(captured_temp_path.exists())
                self.assertEqual(captured_temp_path.read_bytes(), self.pdf_content)
                raise RuntimeError("Simulated pipeline failure")
                
            mock_extract_document.side_effect = extract_side_effect
            
            # Verify triggering the service propagates the error
            with self.assertRaises(RuntimeError) as context:
                ExtractionService.trigger_extraction(document.document_id)
            self.assertEqual(str(context.exception), "Simulated pipeline failure")
            
            # Verify that cleanup still executed
            self.assertIsNotNone(captured_temp_path)
            self.assertFalse(captured_temp_path.exists())
            self.assertFalse(captured_temp_path.parent.exists())
            self.assertFalse((Path(self.test_dir) / "temp").exists())
            
            # Verify original source PDF is untouched
            self.assertTrue(self.source_pdf.exists())


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
