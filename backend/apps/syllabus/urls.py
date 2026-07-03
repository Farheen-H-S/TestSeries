from django.urls import path
from .views import SubjectListView, ChapterListView

urlpatterns = [
    path('subjects/', SubjectListView.as_view(), name='subject-list'),
    path('subjects/<int:subject_id>/chapters/', ChapterListView.as_view(), name='chapter-list'),
]
