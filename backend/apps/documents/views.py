from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from django.core.files.storage import default_storage
from .models import Document
from .serializers import DocumentUploadSerializer, DocumentListSerializer

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
        
        # Temporarily use the first available user as a development placeholder
        from django.contrib.auth import get_user_model
        from rest_framework.exceptions import ValidationError
        
        User = get_user_model()
        user = User.objects.first()

        if user is None:
            raise ValidationError(
                {"detail": "No user exists. Create a user before uploading documents."}
            )
        
        # Save document record with business logic fields
        serializer.save(
            user=user,
            storage_path=file_path,
            extraction_status=Document.ExtractionStatus.PENDING
        )

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
        # Base queryset ordered by newest first
        queryset = Document.objects.all().order_by('-uploaded_at')
        
        # Ready for future filtering:
        # if self.request.user.is_authenticated:
        #     queryset = queryset.filter(user=self.request.user)
        
        return queryset
