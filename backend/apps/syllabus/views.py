from django.shortcuts import get_object_or_404
from django.db.models import F, Count, Max
from django.db import transaction, models
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Subject, Chapter
from .serializers import SubjectSerializer, ChapterSerializer
from apps.documents.models import Document
from apps.papers.models import Question


class SubjectViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Subject CRUD operations.
    """
    serializer_class = SubjectSerializer
    lookup_field = 'subject_id'

    def get_queryset(self):
        queryset = Subject.objects.filter(is_active=True).annotate(
            chapters_count=Count('chapters')
        ).order_by("name")

        exam_level = self.request.query_params.get('exam_level')
        if exam_level:
            queryset = queryset.filter(exam_level=exam_level)

        return queryset

    @action(detail=True, methods=['get'])
    def stats(self, request, subject_id=None):
        """
        Returns stats about a subject (chapters, documents, and questions counts)
        to preview before deletion.
        """
        subject = self.get_object()
        chapters_count = subject.chapters.count()
        documents_count = subject.documents.count()
        questions_count = Question.objects.filter(document__subject=subject).count()

        return Response({
            "chapters_count": chapters_count,
            "documents_count": documents_count,
            "questions_count": questions_count
        })

    def destroy(self, request, *args, **kwargs):
        """
        Performs a cascade delete of the subject and all related data in an atomic transaction.
        """
        subject = self.get_object()

        with transaction.atomic():
            # Delete generated papers referencing this subject
            if hasattr(subject, 'generated_papers'):
                subject.generated_papers.all().delete()

            # Delete all documents referencing this subject.
            # This will automatically cascade-delete ExtractionLogs and Questions.
            subject.documents.all().delete()

            # Delete all chapters of this subject.
            subject.chapters.all().delete()

            # Delete the subject itself.
            subject.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class ChapterViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Chapter CRUD operations.
    """
    serializer_class = ChapterSerializer
    lookup_field = 'chapter_id'

    def get_queryset(self):
        subject_id = self.kwargs.get("subject_id")
        queryset = Chapter.objects.all()

        if subject_id:
            get_object_or_404(Subject, pk=subject_id, is_active=True)
            queryset = queryset.filter(subject_id=subject_id)

        search_query = self.request.query_params.get('q')
        if search_query:
            search_query = search_query.strip()
            if search_query:
                queryset = queryset.filter(chapter_name__icontains=search_query)

        return queryset.order_by(F("chapter_order").asc(nulls_last=True))

    def perform_create(self, serializer):
        subject_id = self.kwargs.get("subject_id")
        subject = get_object_or_404(Subject, pk=subject_id, is_active=True)

        # Get next available contiguous order value
        max_order = Chapter.objects.filter(subject=subject).aggregate(Max('chapter_order'))['chapter_order__max']
        next_order = (max_order or 0) + 1

        serializer.save(subject=subject, chapter_order=next_order)

    @action(detail=True, methods=['post'])
    def reorder(self, request, chapter_id=None):
        """
        Atomically shifts a chapter up or down in the ordering sequence.
        """
        chapter = self.get_object()
        direction = request.data.get('direction')

        if direction not in ('up', 'down'):
            return Response(
                {"detail": "Invalid direction. Must be 'up' or 'down'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        subject = chapter.subject
        chapters = list(Chapter.objects.filter(subject=subject).order_by(
            F('chapter_order').asc(nulls_last=True), 'created_at'
        ))

        # Check if safe-healing is needed (if orders are not 1, 2, ..., N)
        needs_healing = False
        for idx, ch in enumerate(chapters):
            if ch.chapter_order != idx + 1:
                needs_healing = True
                break

        # Locate the chapter index in the list
        curr_idx = -1
        for idx, ch in enumerate(chapters):
            if ch.chapter_id == chapter.chapter_id:
                curr_idx = idx
                break

        if curr_idx == -1:
            return Response(
                {"detail": "Chapter not found in subject."},
                status=status.HTTP_404_NOT_FOUND
            )

        if needs_healing:
            # Safe-heal: re-assign contiguous orders from 1 to N
            if direction == 'up' and curr_idx > 0:
                chapters[curr_idx], chapters[curr_idx - 1] = chapters[curr_idx - 1], chapters[curr_idx]
            elif direction == 'down' and curr_idx < len(chapters) - 1:
                chapters[curr_idx], chapters[curr_idx + 1] = chapters[curr_idx + 1], chapters[curr_idx]

            for idx, ch in enumerate(chapters):
                ch.chapter_order = idx + 1

            with transaction.atomic():
                Chapter.objects.bulk_update(chapters, ['chapter_order'])
        else:
            # No gaps/duplicates: just swap the order values of the two affected chapters and bulk_update them
            to_update = []
            if direction == 'up' and curr_idx > 0:
                chapters[curr_idx].chapter_order, chapters[curr_idx - 1].chapter_order = \
                    chapters[curr_idx - 1].chapter_order, chapters[curr_idx].chapter_order
                to_update = [chapters[curr_idx], chapters[curr_idx - 1]]
            elif direction == 'down' and curr_idx < len(chapters) - 1:
                chapters[curr_idx].chapter_order, chapters[curr_idx + 1].chapter_order = \
                    chapters[curr_idx + 1].chapter_order, chapters[curr_idx].chapter_order
                to_update = [chapters[curr_idx], chapters[curr_idx + 1]]

            if to_update:
                with transaction.atomic():
                    Chapter.objects.bulk_update(to_update, ['chapter_order'])

        return Response({"detail": "Chapter reordered successfully."})

    def destroy(self, request, *args, **kwargs):
        """
        Deletes a chapter. Blocks deletion if questions reference it.
        """
        chapter = self.get_object()
        questions_count = chapter.questions.count()

        if questions_count > 0:
            return Response(
                {"detail": f"Cannot delete chapter because {questions_count} extracted questions reference it."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Proceed with deletion and re-indexing within a single transaction boundary
        subject = chapter.subject
        with transaction.atomic():
            chapter.delete()

            # Re-index remaining chapters to keep contiguous ordering, but only update modified ones
            remaining = list(Chapter.objects.filter(subject=subject).order_by(
                F('chapter_order').asc(nulls_last=True), 'created_at'
            ))
            to_update = []
            for idx, ch in enumerate(remaining):
                expected_order = idx + 1
                if ch.chapter_order != expected_order:
                    ch.chapter_order = expected_order
                    to_update.append(ch)
                
            if to_update:
                Chapter.objects.bulk_update(to_update, ['chapter_order'])

        return Response(status=status.HTTP_204_NO_CONTENT)