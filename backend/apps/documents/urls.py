from django.urls import path
from .views import DocumentUploadView, DocumentListView, DocumentDetailView, DocumentStatsView

urlpatterns = [
    path('documents/', DocumentListView.as_view(), name='document-list'),
    path('documents/upload/', DocumentUploadView.as_view(), name='document-upload'),
    path('documents/<int:pk>/', DocumentDetailView.as_view(), name='document-detail'),
    path('documents/<int:pk>/stats/', DocumentStatsView.as_view(), name='document-stats'),
]

