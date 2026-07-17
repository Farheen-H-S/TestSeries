from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.syllabus.models import Subject, Chapter
from apps.documents.models import Document
from apps.papers.models import Question
from django.contrib.auth import get_user_model

class SyllabusTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        # Clean up database tables to ensure clean test state
        User.objects.all().delete()
        Subject.objects.all().delete()
        Document.objects.all().delete()
        
        self.user = User.objects.create_user(username="testuser", password="password")
        
    def test_subject_uniqueness(self):
        # Create a subject
        Subject.objects.create(name="Financial Reporting", exam_level="Intermediate")
        
        # Try creating another one with same name and level (case-insensitive, space-padded)
        url = reverse('subject-list-create')
        data = {
            "name": "   financial  reporting   ",
            "exam_level": "Intermediate"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.json())
        
        # Creating same subject name in different level should succeed
        data_diff_level = {
            "name": "Financial Reporting",
            "exam_level": "Final"
        }
        response = self.client.post(url, data_diff_level, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_chapter_uniqueness_and_reorder(self):
        subject = Subject.objects.create(name="Audit", exam_level="Intermediate")
        
        # Create two chapters
        url = reverse('chapter-list-create', kwargs={"subject_id": subject.subject_id})
        
        res1 = self.client.post(url, {"chapter_name": "Intro to Audit"}, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res1.json()['chapter_order'], 1)
        
        res2 = self.client.post(url, {"chapter_name": "Audit Procedures"}, format='json')
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res2.json()['chapter_order'], 2)
        
        # Try duplicate chapter name in same subject
        res_dup = self.client.post(url, {"chapter_name": "   intro to audit   "}, format='json')
        self.assertEqual(res_dup.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Test Reordering
        chapter1 = Chapter.objects.get(pk=res1.json()['chapter_id'])
        chapter2 = Chapter.objects.get(pk=res2.json()['chapter_id'])
        
        reorder_url = reverse('chapter-reorder', kwargs={"chapter_id": chapter1.chapter_id})
        
        # Swap chapter 1 down
        res_reorder = self.client.post(reorder_url, {"direction": "down"}, format='json')
        self.assertEqual(res_reorder.status_code, status.HTTP_200_OK)
        
        chapter1.refresh_from_db()
        chapter2.refresh_from_db()
        self.assertEqual(chapter1.chapter_order, 2)
        self.assertEqual(chapter2.chapter_order, 1)

    def test_subject_stats_and_cascade_delete(self):
        subject = Subject.objects.create(name="Law", exam_level="Intermediate")
        chapter = Chapter.objects.create(subject=subject, chapter_name="Company Law", chapter_order=1)
        
        doc = Document.objects.create(
            user=self.user,
            subject=subject,
            title="Law RTP 2026",
            document_type="RTP",
            paper_year=2026,
            exam_month="May",
            storage_path="documents/dummy.pdf"
        )
        
        Question.objects.create(
            document=doc,
            chapter=chapter,
            question_number="1",
            question_text="What is company law?",
            answer_text="It rules."
        )
        
        # Check stats API
        stats_url = reverse('subject-stats', kwargs={"subject_id": subject.subject_id})
        res_stats = self.client.get(stats_url)
        self.assertEqual(res_stats.status_code, status.HTTP_200_OK)
        self.assertEqual(res_stats.json()['chapters_count'], 1)
        self.assertEqual(res_stats.json()['documents_count'], 1)
        self.assertEqual(res_stats.json()['questions_count'], 1)
        
        # Perform cascade delete
        delete_url = reverse('subject-detail', kwargs={"subject_id": subject.subject_id})
        res_delete = self.client.delete(delete_url)
        self.assertEqual(res_delete.status_code, status.HTTP_204_NO_CONTENT)
        
        # Verify everything was deleted Cascade
        self.assertFalse(Subject.objects.filter(pk=subject.subject_id).exists())
        self.assertFalse(Chapter.objects.filter(pk=chapter.chapter_id).exists())
        self.assertFalse(Document.objects.filter(pk=doc.document_id).exists())
        self.assertFalse(Question.objects.filter(document=doc).exists())

    def test_chapter_delete_validation(self):
        subject = Subject.objects.create(name="Tax", exam_level="Intermediate")
        chapter = Chapter.objects.create(subject=subject, chapter_name="Direct Tax", chapter_order=1)
        doc = Document.objects.create(
            user=self.user,
            subject=subject,
            title="Tax RTP 2026",
            document_type="RTP",
            paper_year=2026,
            exam_month="May",
            storage_path="documents/dummy.pdf"
        )
        
        question = Question.objects.create(
            document=doc,
            chapter=chapter,
            question_number="1",
            question_text="What is direct tax?",
            answer_text="Tax on income."
        )
        
        # Try deleting chapter (should be blocked because question references it)
        delete_url = reverse('chapter-detail', kwargs={"chapter_id": chapter.chapter_id})
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot delete chapter because 1 extracted questions reference it", response.json()['detail'])
        
        # Delete question first
        question.delete()
        
        # Now try deleting chapter again (should succeed)
        response2 = self.client.delete(delete_url)
        self.assertEqual(response2.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Chapter.objects.filter(pk=chapter.chapter_id).exists())

    def test_subject_rename_casing_and_whitespace(self):
        # 1. Test whitespace normalization
        url_create = reverse('subject-list-create')
        res_create = self.client.post(url_create, {
            "name": "  Financial    Reporting  ",
            "exam_level": "Intermediate"
        }, format='json')
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_create.json()['name'], 'Financial Reporting') # Whitespace collapsed

        # Create another subject
        sub2 = Subject.objects.create(name="Audit", exam_level="Intermediate")
        
        # 2. Test renaming to a duplicate of another subject (case-insensitive & whitespace check)
        url_update = reverse('subject-detail', kwargs={"subject_id": sub2.subject_id})
        res_update = self.client.patch(url_update, {
            "name": "   financial   reporting   "
        }, format='json')
        self.assertEqual(res_update.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", res_update.json())

        # 3. Test renaming to its own name is allowed
        res_self_update = self.client.patch(url_update, {
            "name": "Audit"
        }, format='json')
        self.assertEqual(res_self_update.status_code, status.HTTP_200_OK)

    def test_inactive_subject_uniqueness(self):
        # Create an inactive subject
        Subject.objects.create(name="Audit", exam_level="Intermediate", is_active=False)

        # Try to create an active subject with same name and level (should fail duplicate check)
        url = reverse('subject-list-create')
        data = {
            "name": "Audit",
            "exam_level": "Intermediate"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue("name" in response.json() or "non_field_errors" in response.json())

    def test_chapter_reorder_bounds(self):
        subject = Subject.objects.create(name="Law", exam_level="Intermediate")
        ch1 = Chapter.objects.create(subject=subject, chapter_name="Chapter 1", chapter_order=1)
        ch2 = Chapter.objects.create(subject=subject, chapter_name="Chapter 2", chapter_order=2)

        # 1. Try to move first item up (should be a no-op/have no effect on ordering)
        reorder_url_1 = reverse('chapter-reorder', kwargs={"chapter_id": ch1.chapter_id})
        res1 = self.client.post(reorder_url_1, {"direction": "up"}, format='json')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        ch1.refresh_from_db()
        ch2.refresh_from_db()
        self.assertEqual(ch1.chapter_order, 1)
        self.assertEqual(ch2.chapter_order, 2)

        # 2. Try to move last item down (should be a no-op/have no effect on ordering)
        reorder_url_2 = reverse('chapter-reorder', kwargs={"chapter_id": ch2.chapter_id})
        res2 = self.client.post(reorder_url_2, {"direction": "down"}, format='json')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        ch1.refresh_from_db()
        ch2.refresh_from_db()
        self.assertEqual(ch1.chapter_order, 1)
        self.assertEqual(ch2.chapter_order, 2)

    def test_invalid_month_upload(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        subject = Subject.objects.create(name='Tax', exam_level='Intermediate')
        pdf_file = SimpleUploadedFile(
            "test_paper.pdf",
            b"%PDF-1.4 ... dummy content ...",
            content_type="application/pdf"
        )
        url = reverse('document-upload')
        data = {
            'subject': subject.subject_id,
            'title': 'FM Nov 2025 Paper',
            'document_type': 'PYQ',
            'paper_year': 2025,
            'exam_month': 'Decemberr', # Invalid month value
            'file': pdf_file
        }
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('exam_month', response.json())
