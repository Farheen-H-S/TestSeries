from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.syllabus.models import Subject
from apps.documents.models import Document
from unittest.mock import patch
import tempfile
import shutil

TEMP_MEDIA_ROOT = tempfile.mkdtemp()

@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class DocumentUploadTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        # Clean up any existing users/subjects/documents to ensure pure test state
        User.objects.all().delete()
        Subject.objects.all().delete()
        Document.objects.all().delete()
        
        self.user = User.objects.create_user(username="testuser", password="password")
        
        # Start celery task mock patcher to avoid connection attempts to Redis
        self.patcher = patch('apps.extraction.tasks.extract_document_task.delay')
        self.mock_delay = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()
        
    def test_document_upload_flow(self):
        # Create subjects
        subject_inter = Subject.objects.create(name='Financial Management', exam_level='Intermediate')
        subject_final = Subject.objects.create(name='Financial Management', exam_level='Final')

        # Create a dummy PDF file
        pdf_file = SimpleUploadedFile(
            "test_paper.pdf",
            b"%PDF-1.4 ... dummy content ...",
            content_type="application/pdf"
        )
        
        # 1. Upload a document with a subject reference and custom title
        url = reverse('document-upload')
        data = {
            'subject': subject_inter.subject_id,
            'title': 'FM Nov 2025 Paper',
            'document_type': 'PYQ',
            'paper_year': 2025,
            'exam_month': 'November',
            'file': pdf_file
        }
        
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify response structure
        res_data = response.json()
        self.assertIn('document_id', res_data)
        self.assertEqual(res_data['title'], 'FM Nov 2025 Paper')
        self.assertEqual(res_data['status'], 'PENDING')
        self.assertEqual(res_data['subject']['subject_id'], subject_inter.subject_id)
        self.assertEqual(res_data['subject']['name'], 'Financial Management')
        self.assertEqual(res_data['subject']['exam_level'], 'Intermediate')
        self.assertIn('uploaded_at', res_data)
        
        # 2. Upload another document without custom title (verifies auto-title fallback)
        pdf_file_2 = SimpleUploadedFile(
            "test_paper_2.pdf",
            b"%PDF-1.4 ... dummy content 2 ...",
            content_type="application/pdf"
        )
        data_2 = {
            'subject': subject_inter.subject_id,
            'document_type': 'PYQ',
            'paper_year': 2025,
            'exam_month': 'May',
            'file': pdf_file_2
        }
        
        response_2 = self.client.post(url, data_2, format='multipart')
        self.assertEqual(response_2.status_code, status.HTTP_201_CREATED)
        
        # Verify subject is correct and title was auto-generated
        res_data_2 = response_2.json()
        self.assertEqual(res_data_2['title'], 'Financial Management - PYQ - May 2025')
        self.assertEqual(res_data_2['subject']['subject_id'], subject_inter.subject_id)
        
        # 3. Upload another document with a different exam level subject
        pdf_file_3 = SimpleUploadedFile(
            "test_paper_3.pdf",
            b"%PDF-1.4 ... dummy content 3 ...",
            content_type="application/pdf"
        )
        data_3 = {
            'subject': subject_final.subject_id,
            'title': 'FM Final May 2025 Paper',
            'document_type': 'PYQ',
            'paper_year': 2025,
            'exam_month': 'May',
            'file': pdf_file_3
        }
        
        response_3 = self.client.post(url, data_3, format='multipart')
        self.assertEqual(response_3.status_code, status.HTTP_201_CREATED)
        
        # Verify subject final was linked
        res_data_3 = response_3.json()
        self.assertEqual(res_data_3['subject']['subject_id'], subject_final.subject_id)
        self.assertIn('uploaded_at', res_data_3)

        # Verify Celery delay task was called for each successful upload
        self.assertEqual(self.mock_delay.call_count, 3)
        self.assertEqual(self.mock_delay.call_args_list[0][0][0], res_data['document_id'])

    def test_document_upload_celery_queue_failure(self):
        # Setup mock delay to raise a connection/broker exception
        self.mock_delay.side_effect = RuntimeError("Broker connection refused")
        
        subject_inter = Subject.objects.create(name='Financial Management', exam_level='Intermediate')
        pdf_file = SimpleUploadedFile(
            "test_paper_fail.pdf",
            b"%PDF-1.4 ... dummy content ...",
            content_type="application/pdf"
        )
        
        url = reverse('document-upload')
        data = {
            'subject': subject_inter.subject_id,
            'title': 'FM Queue Fail Paper',
            'document_type': 'PYQ',
            'paper_year': 2025,
            'exam_month': 'November',
            'file': pdf_file
        }
        
        response = self.client.post(url, data, format='multipart')
        # The upload view should handle broker failure gracefully, returning 201 Created
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        res_data = response.json()
        doc_id = res_data['document_id']
        
        # Verify document status is still PENDING
        document = Document.objects.get(pk=doc_id)
        self.assertEqual(document.extraction_status, Document.ExtractionStatus.PENDING)
        
        # Verify an ExtractionLog is created with FAILED status and message about the queue failure
        from apps.extraction.models import ExtractionLog
        log = ExtractionLog.objects.filter(document=document).latest('created_at')
        self.assertEqual(log.status, ExtractionLog.Status.FAILED)
        self.assertIn("Failed to queue background extraction task", log.message)
        self.assertIn("Broker connection refused", log.message)

    def test_document_upload_missing_subject(self):
        url = reverse('document-upload')
        pdf_file = SimpleUploadedFile(
            "test_paper.pdf",
            b"%PDF-1.4 ... dummy content ...",
            content_type="application/pdf"
        )
        
        # Test request without subject reference
        data = {
            'title': 'FM Nov 2025 Paper',
            'document_type': 'PYQ',
            'paper_year': 2025,
            'exam_month': 'November',
            'file': pdf_file
        }
        
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('subject', response.json())

    def test_document_stats_and_delete_cascade(self):
        from apps.papers.models import Question
        from apps.extraction.models import ExtractionLog

        subject = Subject.objects.create(name='Taxation', exam_level='Intermediate')
        doc = Document.objects.create(
            user=self.user,
            subject=subject,
            title='Taxation Paper 2024',
            document_type='PYQ',
            paper_year=2024,
            storage_path='documents/test_tax.pdf'
        )

        # Create child extracted questions and logs
        Question.objects.create(
            document=doc,
            question_number='Q1',
            question_content='<p>Question 1</p>',
            question_text='Question 1',
            answer_content='<p>Answer 1</p>',
            answer_text='Answer 1'
        )
        Question.objects.create(
            document=doc,
            question_number='Q2',
            question_content='<p>Question 2</p>',
            question_text='Question 2',
            answer_content='<p>Answer 2</p>',
            answer_text='Answer 2'
        )
        ExtractionLog.objects.create(
            document=doc,
            status=ExtractionLog.Status.COMPLETED,
            message='Extraction done'
        )

        # 1. Verify Stats API Endpoint
        stats_url = reverse('document-stats', kwargs={'pk': doc.pk})
        stats_resp = self.client.get(stats_url)
        self.assertEqual(stats_resp.status_code, status.HTTP_200_OK)
        stats_data = stats_resp.json()
        self.assertEqual(stats_data['questions_count'], 2)
        self.assertEqual(stats_data['logs_count'], 1)

        # 2. Verify Delete API Endpoint
        detail_url = reverse('document-detail', kwargs={'pk': doc.pk})
        delete_resp = self.client.delete(detail_url)
        self.assertEqual(delete_resp.status_code, status.HTTP_204_NO_CONTENT)

        # 3. Assert Cascading Deletion from Database
        self.assertFalse(Document.objects.filter(pk=doc.pk).exists())
        self.assertEqual(Question.objects.filter(document_id=doc.pk).count(), 0)
        self.assertEqual(ExtractionLog.objects.filter(document_id=doc.pk).count(), 0)

