from django.urls import path
from .views import QuestionListView, GeneratedPaperListView, GeneratedPaperQuestionListView

urlpatterns = [
    path('questions/', QuestionListView.as_view(), name='question-list'),
    path('generated-papers/', GeneratedPaperListView.as_view(), name='generated-paper-list'),
    path('generated-paper-questions/', GeneratedPaperQuestionListView.as_view(), name='generated-paper-question-list'),
]
