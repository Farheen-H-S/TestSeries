import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

import unittest
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.conf import settings
from pathlib import Path
import tempfile
import shutil
from django.contrib.auth import get_user_model
from apps.documents.models import Document
from apps.syllabus.models import Subject
from apps.extraction.models import ExtractionLog
from apps.extraction.services.extraction_service import ExtractionService
from apps.papers.models import Question

class PipelineErrorHandlingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="testuser_err", password="password")
        self.subject = Subject.objects.create(name="Mathematics", exam_level="Intermediate")

    @patch('apps.extraction.services.extraction_pipeline.load_pdf')
    @patch('apps.extraction.services.extraction_pipeline.extract_text')
    @patch('apps.extraction.services.extraction_pipeline.logger')
    def test_pipeline_error_handling_and_cleanup(self, mock_logger, mock_extract_text, mock_load_pdf):
        from apps.extraction.services.extraction_pipeline import extract_document
        
        # 1. Setup mocks
        mock_pdf = MagicMock()
        mock_load_pdf.return_value = mock_pdf
        
        # Make extract_text raise a clear error to simulate failure
        test_exception = ValueError("Simulated extraction text failure")
        mock_extract_text.side_effect = test_exception
        
        # Create actual Document
        document = Document.objects.create(
            user=self.user,
            subject=self.subject,
            title="FM Nov 2025 Paper",
            document_type=Document.DocumentType.PYQ,
            paper_year=2025,
            storage_path="documents/test_err.pdf"
        )
        
        # 2. Run extraction and assert exception is raised
        with self.assertRaises(ValueError) as context:
            extract_document(document)
            
        self.assertEqual(str(context.exception), "Simulated extraction text failure")
        
        # 3. Verify cleanup: pdf.close() was called
        mock_pdf.close.assert_called_once()
        
        # 4. Verify status updates
        document.refresh_from_db()
        self.assertEqual(document.extraction_status, Document.ExtractionStatus.FAILED)
        
        # ExtractionLog status should be set to FAILED and message should be str(e)
        log = ExtractionLog.objects.filter(document=document).latest('created_at')
        self.assertEqual(log.status, ExtractionLog.Status.FAILED)
        self.assertEqual(log.message, "Simulated extraction text failure")
        
        # 5. Verify single stack trace / no duplicate logging
        mock_logger.exception.assert_called_once_with(
            "Extraction failed | document_id=%s | storage_path=%s",
            document.document_id,
            "documents/test_err.pdf"
        )

    @patch('apps.extraction.services.extraction_pipeline.load_pdf')
    @patch('apps.extraction.services.extraction_pipeline.extract_text')
    @patch('apps.extraction.services.extraction_pipeline.QuestionParser')
    def test_pipeline_fail_fast_duplicate_detection(self, mock_q_parser_cls, mock_extract_text, mock_load_pdf):
        from apps.extraction.services.extraction_pipeline import extract_document
        from apps.extraction.services.exceptions import DuplicateHierarchyError
        from apps.extraction.services.types import ParsedQuestion, QuestionLevel
        
        mock_pdf = MagicMock()
        mock_load_pdf.return_value = mock_pdf
        mock_extract_text.return_value = [{"page_number": 1, "text": "dummy text"}]
        
        # Mock the parser instance
        mock_parser = MagicMock()
        mock_q_parser_cls.return_value = mock_parser
        mock_parser.diagnostics.total_matches = 2
        mock_parser.diagnostics.rejected_headers = []
        mock_parser.diagnostics.validated_count = 2
        
        # Return duplicate ParsedQuestion objects of depth 3
        mock_parser.parse.return_value = [
            ParsedQuestion(
                hierarchy_path=["2", "d", "i"],
                raw_header="Question 2(d)(i)",
                text="First occurrence text",
                start_offset=10,
                end_offset=50,
                start_page=6,
                end_page=6,
                level=QuestionLevel.SUB_SUB
            ),
            ParsedQuestion(
                hierarchy_path=["2", "d", "i"],
                raw_header="Question 2(d)(i)",
                text="Second occurrence text",
                start_offset=60,
                end_offset=100,
                start_page=8,
                end_page=8,
                level=QuestionLevel.SUB_SUB
            ),
        ]
        
        document = Document.objects.create(
            user=self.user,
            subject=self.subject,
            title="Duplicate Test Paper",
            document_type=Document.DocumentType.MOCK,
            paper_year=2026,
            storage_path="documents/test_dup.pdf"
        )
        
        with self.assertRaises(DuplicateHierarchyError) as context:
            extract_document(document)
            
        err_msg = str(context.exception)
        self.assertIn("Duplicate hierarchy key detected", err_msg)
        self.assertIn("Duplicate Test Paper", err_msg)
        self.assertIn("2.d.i", err_msg)
        
        # Assert first occurrence diagnostics
        self.assertIn("First", err_msg)
        self.assertIn("['2', 'd', 'i']", err_msg)
        self.assertIn("Page:\n6", err_msg)
        self.assertIn("First occurrence text", err_msg)
        
        # Assert second occurrence diagnostics
        self.assertIn("Second", err_msg)
        self.assertIn("['2', 'd', 'i']", err_msg)
        self.assertIn("Page:\n8", err_msg)
        self.assertIn("Second occurrence text", err_msg)

    @patch('apps.extraction.services.extraction_pipeline.load_pdf')
    @patch('apps.extraction.services.extraction_pipeline.extract_text')
    def test_pipeline_successful_extraction_integration(self, mock_extract_text, mock_load_pdf):
        """
        Verify the extraction pipeline end-to-end with mock PDF text loading.
        """
        from apps.extraction.services.extraction_pipeline import extract_document
        
        # 1. Setup mocks
        mock_pdf = MagicMock()
        mock_load_pdf.return_value = mock_pdf
        
        # Mock PyMuPDF text loader to return page content
        mock_extract_text.return_value = [
            {
                "page_number": 1,
                "text": (
                    "Question 1\n"
                    "What is the capital of France?\n"
                    "(a)\n"
                    "Option A content.\n"
                    "SUGGESTED ANSWERS\n"
                    "Answer 1\n"
                    "(a)\n"
                    "Paris is the capital of France.\n"
                )
            }
        ]
        
        # Create a document
        document = Document.objects.create(
            user=self.user,
            subject=self.subject,
            title="E2E Integration Test Paper",
            document_type=Document.DocumentType.MOCK,
            paper_year=2026,
            storage_path="documents/e2e_test.pdf"
        )
        
        # Run pipeline
        extract_document(document)
        
        # Verify document status updated to COMPLETED
        document.refresh_from_db()
        self.assertEqual(document.extraction_status, Document.ExtractionStatus.COMPLETED)
        self.assertEqual(document.total_pages, 1)
        
        # Verify questions created in DB
        questions = Question.objects.filter(document=document)
        self.assertTrue(questions.exists())
        
        # Verify extraction log completed
        log = ExtractionLog.objects.filter(document=document).latest('created_at')
        self.assertEqual(log.status, ExtractionLog.Status.COMPLETED)
        self.assertIn("Extracted", log.message)


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
