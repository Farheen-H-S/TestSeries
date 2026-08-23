from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from apps.syllabus.models import Subject, Chapter
from apps.documents.models import Document
from apps.papers.models import Question

User = get_user_model()

class QuestionAPITests(APITestCase):
    def setUp(self):
        # 1. Create a user
        self.user = User.objects.create_user(username="testuser", password="password")
        self.client.force_authenticate(user=self.user)

        # 2. Create subjects
        self.subject_a = Subject.objects.create(name="Subject A", exam_level="Foundation")
        self.subject_b = Subject.objects.create(name="Subject B", exam_level="Foundation")

        # 3. Create chapters
        self.chapter_a1 = Chapter.objects.create(chapter_name="Chapter A1", subject=self.subject_a, chapter_order=1)
        self.chapter_b1 = Chapter.objects.create(chapter_name="Chapter B1", subject=self.subject_b, chapter_order=1)

        # 4. Create document
        self.document = Document.objects.create(
            user=self.user,
            subject=self.subject_a,
            title="Document A",
            document_type="RTP",
            paper_year=2026,
            exam_month="May",
            storage_path="documents/test_file.pdf"
        )

        # 5. Create question
        self.question = Question.objects.create(
            document=self.document,
            chapter=self.chapter_a1,
            question_number="1(a)",
            question_text="Original question text.",
            question_content="<p>Original question text.</p>",
            answer_text="Original answer text.",
            answer_content="<p>Original answer text.</p>"
        )

        self.url = reverse('question-detail', kwargs={'question_id': self.question.question_id})

    def test_get_question_detail(self):
        """Verify fetching details of a question."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['question_number'], "1(a)")

    def test_question_patch_partial_update(self):
        """PATCH only updates supplied fields, leaving others intact."""
        payload = {"question_number": "1(b)"}
        response = self.client.patch(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify question_number was updated
        self.assertEqual(response.data['question_number'], "1(b)")
        # Verify other fields remain unchanged
        self.assertEqual(response.data['question_text'], "Original question text.")
        self.assertEqual(response.data['answer_text'], "Original answer text.")
        self.assertEqual(response.data['chapter'], self.chapter_a1.chapter_id)

    def test_question_patch_validation_whitespace(self):
        """Validation fails if values resolve to blank strings after normalization."""
        payload = {"question_number": "    "}
        response = self.client.patch(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("question_number", response.data)

        payload = {"question_text": "\n   \n"}
        response = self.client.patch(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("question_text", response.data)

    def test_question_patch_validation_chapter_subject_mismatch(self):
        """Validation fails if chapter belongs to another subject."""
        payload = {"chapter": self.chapter_b1.chapter_id}
        response = self.client.patch(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("chapter", response.data)

    def test_html_content_regeneration_only_on_change(self):
        """HTML formatted content is regenerated only when text updates are supplied."""
        # 1. Update only chapter
        payload = {"chapter": self.chapter_a1.chapter_id}
        response = self.client.patch(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['question_content'], "<p>Original question text.</p>")

        # 2. Update question text and verify regeneration
        payload = {"question_text": "Updated line 1.\n\nUpdated line 2."}
        response = self.client.patch(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['question_content'],
            "<p>Updated line 1.</p>\n<p>Updated line 2.</p>"
        )
        self.assertEqual(response.data['answer_content'], "<p>Original answer text.</p>")

    def test_pdf_renderer_show_source_option(self):
        from apps.papers.services.question_selector import QuestionGroup
        from apps.papers.services.pdf_renderer import render_question_paper, render_answer_sheet

        group = QuestionGroup(
            root_question_id=self.question.pk,
            question_html="<p>Test question</p>",
            answer_html="<p>Test answer</p>",
            sub_questions=[],
            total_marks=5,
            shared_context_html=None,
            subject_name=self.subject_a.name,
            exam_level=self.subject_a.exam_level,
            module="RTP",
            document_title=self.document.title
        )

        qp_bytes = render_question_paper([group], "Test Paper", show_source=True)
        self.assertTrue(len(qp_bytes) > 0)

        ans_bytes = render_answer_sheet([group], "Test Paper", show_source=True)
        self.assertTrue(len(ans_bytes) > 0)

    def test_pdf_renderer_show_chapter_option(self):
        from apps.papers.services.question_selector import QuestionGroup
        from apps.papers.services.pdf_renderer import render_question_paper, render_answer_sheet

        group = QuestionGroup(
            root_question_id=self.question.pk,
            question_html="<p>Test question</p>",
            answer_html="<p>Test answer</p>",
            sub_questions=[],
            total_marks=5,
            shared_context_html=None,
            subject_name=self.subject_a.name,
            exam_level=self.subject_a.exam_level,
            module="RTP",
            document_title=self.document.title,
            chapter_name="Ind AS 1: Presentation of Financial Statements"
        )

        qp_bytes = render_question_paper([group], "Test Paper", show_chapter=True)
        self.assertTrue(len(qp_bytes) > 0)

        ans_bytes = render_answer_sheet([group], "Test Paper", show_source=True, show_chapter=True)
        self.assertTrue(len(ans_bytes) > 0)

    def test_prerender_html_content_preserves_images_and_formulas(self):
        from apps.papers.services.question_selector import _prerender_html_content

        input_html = (
            '<p>Calculate the beta:</p>\n'
            '[STRUCTURED_START]\n'
            '<div class="formula-container" data-is-complex="true" data-crop-path="/media/formula_crops/test.png">\n'
            '<div class="formula-visual-region" style="text-align:center; margin: 0.5em 0;">\n'
            '<img src="/media/formula_crops/test.png" style="max-width: 100%; width: 500px; height: auto;" />\n'
            '</div></div>\n'
            '[STRUCTURED_END]\n'
            '<p>End of problem.</p>'
        )

        prerendered = _prerender_html_content(input_html)
        self.assertIn('<img src="/media/formula_crops/test.png"', prerendered)
        self.assertIn('formula-container', prerendered)
        self.assertNotIn('[STRUCTURED_START]', prerendered)
        self.assertNotIn('[STRUCTURED_END]', prerendered)

    def test_pdf_renderer_embeds_images_properly(self):
        import os
        from django.conf import settings
        from apps.papers.services.question_selector import QuestionGroup
        from apps.papers.services.pdf_renderer import render_question_paper, render_answer_sheet

        # Create dummy image in media directory
        crops_dir = os.path.join(str(settings.MEDIA_ROOT), "table_crops")
        os.makedirs(crops_dir, exist_ok=True)
        test_img_path = os.path.join(crops_dir, "unit_test_crop.png")
        
        # 1x1 PNG bytes
        tiny_png = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00'
            b'\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        with open(test_img_path, 'wb') as f:
            f.write(tiny_png)

        try:
            group = QuestionGroup(
                root_question_id=self.question.pk,
                question_html='<p>Question with visual table:</p><div class="table-container"><img src="/media/table_crops/unit_test_crop.png" width="500" /></div>',
                answer_html='<p>Answer with formula:</p><div class="formula-container"><img src="/media/table_crops/unit_test_crop.png" width="500" /></div>',
                sub_questions=[],
                total_marks=10,
                shared_context_html=None,
                subject_name=self.subject_a.name,
                exam_level=self.subject_a.exam_level,
                module="RTP",
                document_title=self.document.title
            )

            qp_bytes = render_question_paper([group], "Test QP Image Paper")
            self.assertTrue(len(qp_bytes) > 1000)

            ans_bytes = render_answer_sheet([group], "Test QP Image Paper")
            self.assertTrue(len(ans_bytes) > 1000)
        finally:
            if os.path.exists(test_img_path):
                os.remove(test_img_path)



