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
        return Subject.objects.filter(is_active=True).order_by('name')


class ChapterListView(ListAPIView):
    """
    API view to list chapters for a specific subject.
    Ordered by chapter_order (NULLs last).
    """
    serializer_class = ChapterSerializer

    def get_queryset(self):
        subject_id = self.kwargs.get('subject_id')
        # Ensure subject exists, else raise 404
        subject = get_object_or_404(Subject, pk=subject_id)
        
        # Order by chapter_order ascending, placing NULLs at the end
        return Chapter.objects.filter(subject=subject).order_by(
            F('chapter_order').asc(nulls_last=True)
        )
