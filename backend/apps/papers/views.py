from rest_framework import generics
from rest_framework.permissions import AllowAny
from .models import Question, GeneratedPaper, GeneratedPaperQuestion
from .serializers import QuestionSerializer, GeneratedPaperSerializer, GeneratedPaperQuestionSerializer

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
