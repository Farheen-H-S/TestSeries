from rest_framework import serializers
from .models import ExtractionLog

class ExtractionLogSerializer(serializers.ModelSerializer):
    """
    Serializer for the ExtractionLog model.
    """
    class Meta:
        model = ExtractionLog
        fields = [
            "log_id",
            "document",
            "status",
            "message",
            "created_at",
        ]
