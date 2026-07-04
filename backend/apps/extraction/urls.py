from django.urls import path
from .views import ExtractionLogListView

urlpatterns = [
    path("extraction-logs/", ExtractionLogListView.as_view(), name="extraction-log-list"),
]
