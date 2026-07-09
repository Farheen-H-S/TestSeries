from rest_framework import generics, permissions
from .models import ExtractionLog
from .serializers import ExtractionLogSerializer

class ExtractionLogListView(generics.ListAPIView):
    """
    API view to list all extraction logs, ordered by newest first.
    Supports filtering by document_id via query parameter.
    """
    serializer_class = ExtractionLogSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = ExtractionLog.objects.all().order_by("-created_at")
        document_id = self.request.query_params.get("document_id")
        if document_id:
            queryset = queryset.filter(document_id=document_id)
        return queryset
