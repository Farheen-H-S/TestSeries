"""
Paper generation API views.

Three endpoints:
  POST /api/papers/generate/preview/          — validate filters, run selection, return metadata
  POST /api/papers/generate/question-paper/   — fetch groups by IDs, render question paper PDF
  POST /api/papers/generate/answer-sheet/     — fetch groups by IDs, render answer sheet PDF

No database writes. PDFs are generated on demand and discarded after download.
"""
import logging

from django.http import HttpResponse
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from .models import Question, GeneratedPaper, GeneratedPaperQuestion
from .serializers import (
    QuestionSerializer,
    GeneratedPaperSerializer,
    GeneratedPaperQuestionSerializer,
    GenerationFilterSerializer,
    PDFGenerationSerializer,
)
from .services.question_selector import select_question_groups, fetch_groups_by_ids
from .services.pdf_renderer import render_question_paper, render_answer_sheet
from .services.filename_utils import sanitize_filename

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Existing views (unchanged)
# ---------------------------------------------------------------------------

class QuestionListView(generics.ListAPIView):
    """
    API view to list all questions.
    Ordered by question_id ascending.
    Supports filtering by document_id via query parameter.
    """
    serializer_class = QuestionSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        # Order by source_page and question_id as a sequential fallback.
        # This assumes sequential parsing insertion order preserves correct document sequence.
        queryset = Question.objects.all().select_related('chapter').order_by('source_page', 'question_id')
        document_id = self.request.query_params.get('document_id')
        if document_id:
            queryset = queryset.filter(document_id=document_id)
        return queryset


class GeneratedPaperListView(generics.ListAPIView):
    """
    API view to list generated papers.
    Ordered by newest first.
    """
    queryset = GeneratedPaper.objects.all().order_by('-generated_at')
    serializer_class = GeneratedPaperSerializer
    permission_classes = [AllowAny]


class GeneratedPaperQuestionListView(generics.ListAPIView):
    """
    API view to list questions within generated papers.
    Ordered by question_order.
    """
    queryset = GeneratedPaperQuestion.objects.all().order_by('question_order')
    serializer_class = GeneratedPaperQuestionSerializer
    permission_classes = [AllowAny]


class QuestionDetailView(generics.RetrieveUpdateAPIView):
    """
    API view to retrieve and update (PATCH only) an individual question.
    """
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    permission_classes = [AllowAny]
    lookup_field = 'question_id'
    http_method_names = ['get', 'patch']


# ---------------------------------------------------------------------------
# Generation views
# ---------------------------------------------------------------------------

def _validate_root_question_ids(root_question_ids: list) -> tuple:
    """
    Validate that the submitted root_question_ids are safe to render.

    Returns (questions_qs, error_response) where error_response is None on success.
    Checks:
      - All IDs exist in the database
      - All are root questions (parent_question is NULL)
      - All belong to the same subject
      - All belong to the same module (document_type)
    """
    found = Question.objects.filter(
        question_id__in=root_question_ids
    ).select_related('document__subject')

    found_ids = {q.question_id for q in found}
    missing = [qid for qid in root_question_ids if qid not in found_ids]
    if missing:
        return None, Response(
            {'root_question_ids': f"IDs not found: {missing}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # All must be root questions
    sub_questions = [q for q in found if q.parent_question_id is not None]
    if sub_questions:
        bad_ids = [q.question_id for q in sub_questions]
        return None, Response(
            {'root_question_ids': f"IDs {bad_ids} are sub-questions, not root questions."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # All must share the same subject
    subject_ids = {q.document.subject_id for q in found}
    if len(subject_ids) > 1:
        return None, Response(
            {'root_question_ids': "All questions must belong to the same subject."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # All must share the same module (document_type)
    modules = {q.document.document_type for q in found}
    if len(modules) > 1:
        return None, Response(
            {'root_question_ids': "All questions must belong to the same module."},
            status=status.HTTP_400_BAD_REQUEST
        )

    return found, None


class GeneratePreviewView(APIView):
    """
    POST /api/papers/generate/preview/

    Validates generation filters, runs best-fit randomized selection once,
    and returns availability metadata plus the ordered list of selected root
    question IDs.

    The frontend caches root_question_ids and passes them to the PDF endpoints.
    This ensures both PDFs are generated from the identical question set.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GenerationFilterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        filters = serializer.validated_data
        result = select_question_groups(filters)

        warning = None
        selection_quality = None

        if result.available_questions == 0:
            return Response({
                'available_questions': 0,
                'available_marks': 0,
                'selected_question_count': 0,
                'selected_total_marks': 0,
                'selection_quality': None,
                'root_question_ids': [],
                'warning': None,
            })

        total_marks_requested = filters.get('total_marks')
        if total_marks_requested:
            # Marks-constrained: check if requested exceeds available
            if total_marks_requested > result.available_marks:
                warning = (
                    f"Requested {total_marks_requested} marks. "
                    f"Only {result.available_marks} marks are available using the selected filters. "
                    f"The generated paper will contain {result.total_marks_selected} marks."
                )
            # Selection quality: how close did best-fit get to requested?
            if total_marks_requested > 0:
                pct = round((result.total_marks_selected / total_marks_requested) * 100)
                selection_quality = f"{min(pct, 100)}%"

        return Response({
            'available_questions': result.available_questions,
            'available_marks': result.available_marks,
            'selected_question_count': result.total_questions_selected,
            'selected_total_marks': result.total_marks_selected,
            'selection_quality': selection_quality,
            'root_question_ids': [g.root_question_id for g in result.groups],
            'warning': warning,
        })


class GenerateQuestionPaperView(APIView):
    """
    POST /api/papers/generate/question-paper/

    Accepts { paper_title, root_question_ids } — no re-selection, no randomness.
    Validates the IDs, fetches QuestionGroup DTOs, renders a question paper PDF,
    and returns it as a streaming attachment.

    Nothing is stored. The PDF is discarded after download.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PDFGenerationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        paper_title = serializer.validated_data['paper_title']
        root_question_ids = serializer.validated_data['root_question_ids']
        show_source = serializer.validated_data.get('show_source', False)

        _, error = _validate_root_question_ids(root_question_ids)
        if error:
            return error

        groups = fetch_groups_by_ids(root_question_ids)
        if not groups:
            return Response(
                {'detail': "No valid question groups found for the provided IDs."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            pdf_bytes = render_question_paper(groups, paper_title, show_source=show_source)
        except Exception:
            logger.exception("Question paper render failed | title=%r", paper_title)
            return Response(
                {'detail': "PDF generation failed. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        filename = sanitize_filename(paper_title)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class GenerateAnswerSheetView(APIView):
    """
    POST /api/papers/generate/answer-sheet/

    Identical request shape as GenerateQuestionPaperView.
    Produces a suggested answer sheet PDF in the same question order.

    Nothing is stored.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PDFGenerationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        paper_title = serializer.validated_data['paper_title']
        root_question_ids = serializer.validated_data['root_question_ids']
        show_source = serializer.validated_data.get('show_source', False)

        _, error = _validate_root_question_ids(root_question_ids)
        if error:
            return error

        groups = fetch_groups_by_ids(root_question_ids)
        if not groups:
            return Response(
                {'detail': "No valid question groups found for the provided IDs."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            pdf_bytes = render_answer_sheet(groups, paper_title, show_source=show_source)
        except Exception:
            logger.exception("Answer sheet render failed | title=%r", paper_title)
            return Response(
                {'detail': "PDF generation failed. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        filename = sanitize_filename(paper_title, suffix='_Answer_Sheet')
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
