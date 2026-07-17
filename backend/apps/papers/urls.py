from django.urls import path
from .views import QuestionListView, GeneratedPaperListView, GeneratedPaperQuestionListView, QuestionDetailView

urlpatterns = [
    path('questions/', QuestionListView.as_view(), name='question-list'),
    path('questions/<int:question_id>/', QuestionDetailView.as_view(), name='question-detail'),
    path('generated-papers/', GeneratedPaperListView.as_view(), name='generated-paper-list'),
    path('generated-paper-questions/', GeneratedPaperQuestionListView.as_view(), name='generated-paper-question-list'),
]
