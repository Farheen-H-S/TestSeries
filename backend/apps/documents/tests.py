from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.syllabus.models import Subject
from apps.documents.models import Document

class DocumentUploadTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        # Clean up any existing users/subjects/documents to ensure pure test state
        User.objects.all().delete()
        Subject.objects.all().delete()
        Document.objects.all().delete()
        
        self.user = User.objects.create_user(username="testuser", password="password")
        
    def test_document_upload_flow(self):
        # Create a dummy PDF file
        pdf_file = SimpleUploadedFile(
            "test_paper.pdf",
            b"%PDF-1.4 ... dummy content ...",
            content_type="application/pdf"
        )
        
        # 1. Upload a document with a new subject and level
        url = reverse('document-upload')
        data = {
            'subject_name': '   financial   management  ',
            'exam_level': 'Intermediate',
            'title': 'FM Nov 2025 Paper',
            'document_type': 'PYQ',
            'paper_year': 2025,
            'paper_session': 'November',
            'file': pdf_file
        }
        
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify Subject was created and normalized to Title Case
        subject = Subject.objects.get(name='Financial Management', exam_level='Intermediate')
        self.assertEqual(subject.name, 'Financial Management')
        self.assertEqual(subject.exam_level, 'Intermediate')
        
        # Verify response structure
        res_data = response.json()
        self.assertIn('document_id', res_data)
        self.assertEqual(res_data['title'], 'FM Nov 2025 Paper')
        self.assertEqual(res_data['status'], 'PENDING')
        self.assertEqual(res_data['subject']['subject_id'], subject.subject_id)
        self.assertEqual(res_data['subject']['name'], 'Financial Management')
        self.assertEqual(res_data['subject']['exam_level'], 'Intermediate')
        
        # 2. Upload another document with the same subject name (different casing/spacing) and same level
        pdf_file_2 = SimpleUploadedFile(
            "test_paper_2.pdf",
            b"%PDF-1.4 ... dummy content 2 ...",
            content_type="application/pdf"
        )
        data_2 = {
            'subject_name': 'FINANCIAL   management',
            'exam_level': 'Intermediate',
            'title': 'FM May 2025 Paper',
            'document_type': 'PYQ',
            'paper_year': 2025,
            'paper_session': 'May',
            'file': pdf_file_2
        }
        
        response_2 = self.client.post(url, data_2, format='multipart')
        self.assertEqual(response_2.status_code, status.HTTP_201_CREATED)
        
        # Verify no duplicate subject was created (still 1 Subject)
        self.assertEqual(Subject.objects.filter(name='Financial Management').count(), 1)
        res_data_2 = response_2.json()
        self.assertEqual(res_data_2['subject']['subject_id'], subject.subject_id)
        
        # 3. Upload another document with the same subject name but different exam level
        pdf_file_3 = SimpleUploadedFile(
            "test_paper_3.pdf",
            b"%PDF-1.4 ... dummy content 3 ...",
            content_type="application/pdf"
        )
        data_3 = {
            'subject_name': 'financial management',
            'exam_level': 'Final',
            'title': 'FM Final May 2025 Paper',
            'document_type': 'PYQ',
            'paper_year': 2025,
            'paper_session': 'May',
            'file': pdf_file_3
        }
        
        response_3 = self.client.post(url, data_3, format='multipart')
        self.assertEqual(response_3.status_code, status.HTTP_201_CREATED)
        
        # Verify a new subject was created for Final
        self.assertEqual(Subject.objects.filter(name='Financial Management').count(), 2)
        subject_final = Subject.objects.get(name='Financial Management', exam_level='Final')
        res_data_3 = response_3.json()
        self.assertEqual(res_data_3['subject']['subject_id'], subject_final.subject_id)
