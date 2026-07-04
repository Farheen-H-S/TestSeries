from rest_framework import generics, permissions
from .models import ExtractionLog
from .serializers import ExtractionLogSerializer

class ExtractionLogListView(generics.ListAPIView):
    """
    API view to list all extraction logs, ordered by newest first.
    """
    queryset = ExtractionLog.objects.all().order_by("-created_at")
    serializer_class = ExtractionLogSerializer
    permission_classes = [permissions.AllowAny]
