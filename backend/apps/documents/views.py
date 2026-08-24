import logging
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.core.files.storage import default_storage
from .models import Document
from .serializers import DocumentUploadSerializer, DocumentListSerializer, DocumentUpdateSerializer

logger = logging.getLogger(__name__)

class DocumentUploadView(generics.CreateAPIView):
    queryset = Document.objects.all()
    serializer_class = DocumentUploadSerializer
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        file_obj = self.request.FILES.get('file')
        
        # Save file using Django's storage system
        file_path = default_storage.save(f'documents/{file_obj.name}', file_obj)
        
        # TODO: When JWT authentication is added, this should become:
        # permission_classes = [IsAuthenticated]
        # user = self.request.user
        
        # Temporarily use the first available user or fallback user for Document FK requirement
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        user = User.objects.first()
        if user is None:
            user, _ = User.objects.get_or_create(
                username="system_user",
                defaults={"email": "system@example.com"}
            )
        
        # Save document record with business logic fields
        instance = serializer.save(
            user=user,
            storage_path=file_path,
            extraction_status=Document.ExtractionStatus.PENDING
        )

        # Trigger background Celery extraction task resiliently
        try:
            from apps.extraction.tasks import extract_document_task
            extract_document_task.delay(instance.document_id)
            logger.info("Successfully queued extraction task for document_id=%s", instance.document_id)
        except Exception as e:
            logger.exception("Failed to queue extraction task for document_id=%s", instance.document_id)
            try:
                from apps.extraction.models import ExtractionLog
                ExtractionLog.objects.create(
                    document=instance,
                    status=ExtractionLog.Status.FAILED,
                    message=f"Failed to queue background extraction task: {str(e)}"
                )
            except Exception as log_err:
                logger.exception("Also failed to create ExtractionLog for document_id=%s: %s", instance.document_id, log_err)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        instance = serializer.instance
        return Response({
            "document_id": instance.document_id,
            "title": instance.title,
            "subject": {
                "subject_id": instance.subject.subject_id,
                "name": instance.subject.name,
                "exam_level": instance.subject.exam_level
            },
            "status": instance.extraction_status,
            "uploaded_at": instance.uploaded_at
        }, status=status.HTTP_201_CREATED)


class DocumentListView(generics.ListAPIView):
    serializer_class = DocumentListSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        # Base queryset ordered by newest first with select_related for subjects
        queryset = Document.objects.all().select_related('subject').order_by('-uploaded_at')
        
        # Filter query parameters
        search = self.request.query_params.get('search')
        subject_id = self.request.query_params.get('subject')
        doc_type = self.request.query_params.get('document_type')
        year = self.request.query_params.get('paper_year')
        month = self.request.query_params.get('exam_month')
        
        if search and search.strip():
            queryset = queryset.filter(title__icontains=search.strip())
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        if doc_type:
            queryset = queryset.filter(document_type__iexact=doc_type.strip())
        if year:
            queryset = queryset.filter(paper_year=year)
        if month:
            queryset = queryset.filter(exam_month__iexact=month.strip())
            
        return queryset


class DocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve document detail and current status, update metadata, or delete a specific uploaded document.
    """
    queryset = Document.objects.all()
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return DocumentUpdateSerializer
        return DocumentListSerializer

    def destroy(self, request, *args, **kwargs):
        """
        Performs a cascade delete of the document and all related questions and logs inside an atomic transaction.
        Physical file cleanup is executed post DB transaction commit.
        """
        instance = self.get_object()
        storage_path = instance.storage_path

        with transaction.atomic():
            # Delete database instance (cascades to questions & extraction logs)
            instance.delete()

            # Schedule physical storage cleanup after DB commit
            if storage_path:
                def cleanup_file():
                    try:
                        if default_storage.exists(storage_path):
                            default_storage.delete(storage_path)
                    except Exception as e:
                        logger.warning("Failed to delete storage file %s post-commit: %s", storage_path, e)
                
                transaction.on_commit(cleanup_file)

        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentStatsView(generics.RetrieveAPIView):
    """
    Returns stats about a document (extracted questions & logs counts) to preview before deletion.
    """
    queryset = Document.objects.all()
    serializer_class = DocumentListSerializer
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        questions_count = instance.questions.count()
        logs_count = instance.extraction_logs.count()
        return Response({
            "document_id": instance.document_id,
            "title": instance.title,
            "questions_count": questions_count,
            "logs_count": logs_count
        }, status=status.HTTP_200_OK)

