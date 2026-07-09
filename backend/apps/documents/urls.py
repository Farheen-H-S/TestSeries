from django.urls import path
from .views import DocumentUploadView, DocumentListView, DocumentDetailView

urlpatterns = [
    path('documents/', DocumentListView.as_view(), name='document-list'),
    path('documents/upload/', DocumentUploadView.as_view(), name='document-upload'),
    path('documents/<int:pk>/', DocumentDetailView.as_view(), name='document-detail'),
]
