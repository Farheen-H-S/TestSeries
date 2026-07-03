from django.shortcuts import get_object_or_404
from django.db.models import F
from rest_framework.generics import ListAPIView

from .models import Subject, Chapter
from .serializers import SubjectSerializer, ChapterSerializer


class SubjectListView(ListAPIView):
    """
    API view to list all active subjects sorted alphabetically by name.
    """
    serializer_class = SubjectSerializer

    def get_queryset(self):
        return Subject.objects.filter(is_active=True).order_by("name")


class ChapterListView(ListAPIView):
    """
    API view to list chapters for a specific subject,
    ordered by chapter_order with NULL values appearing last.
    """
    serializer_class = ChapterSerializer

    def get_queryset(self):
        subject_id = self.kwargs["subject_id"]

        # Ensure the subject exists, otherwise return 404.
        get_object_or_404(Subject, pk=subject_id)

        return Chapter.objects.filter(subject_id=subject_id).order_by(
            F("chapter_order").asc(nulls_last=True)
        )