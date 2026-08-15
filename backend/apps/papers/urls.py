from django.urls import path
from .views import (
    QuestionListView,
    GeneratedPaperListView,
    GeneratedPaperQuestionListView,
    QuestionDetailView,
    GeneratePreviewView,
    GenerateQuestionPaperView,
    GenerateAnswerSheetView,
)

urlpatterns = [
    # Existing question endpoints
    path('questions/', QuestionListView.as_view(), name='question-list'),
    path('questions/<int:question_id>/', QuestionDetailView.as_view(), name='question-detail'),
    path('generated-papers/', GeneratedPaperListView.as_view(), name='generated-paper-list'),
    path('generated-paper-questions/', GeneratedPaperQuestionListView.as_view(), name='generated-paper-question-list'),

    # Paper generation endpoints
    path('generate/preview/', GeneratePreviewView.as_view(), name='generate-preview'),
    path('generate/question-paper/', GenerateQuestionPaperView.as_view(), name='generate-question-paper'),
    path('generate/answer-sheet/', GenerateAnswerSheetView.as_view(), name='generate-answer-sheet'),
]
