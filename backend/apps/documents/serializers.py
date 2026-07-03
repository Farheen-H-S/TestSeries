from rest_framework import serializers
from django.conf import settings
from django.utils import timezone
from .models import Document
from apps.syllabus.models import Subject
import os

class DocumentUploadSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)
    subject_id = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.all(), 
        source='subject', 
        write_only=True
    )

    class Meta:
        model = Document
        fields = ['subject_id', 'title', 'document_type', 'paper_year', 'paper_session', 'file']

    def validate_file(self, value):
        # Validate extension
        ext = os.path.splitext(value.name)[1].lower()
        if ext != '.pdf':
            raise serializers.ValidationError("Only PDF files are allowed.")
        
        # Validate MIME type
        content_type = value.content_type
        if content_type != 'application/pdf':
            raise serializers.ValidationError("Invalid file type. Only application/pdf is allowed.")
        
        # Validate size
        if value.size > settings.MAX_UPLOAD_SIZE:
            max_size_mb = settings.MAX_UPLOAD_SIZE / (1024 * 1024)
            raise serializers.ValidationError(f"File size exceeds the limit of {max_size_mb}MB.")
        
        return value

    def validate_paper_year(self, value):
        # paper_year cannot be negative
        if value < 0:
            raise serializers.ValidationError("Paper year cannot be negative.")
            
        current_year = timezone.now().year
        if value > current_year + 1:
            raise serializers.ValidationError(f"Paper year cannot be more than {current_year + 1}.")
            
        # Optional: Add minimum year check if needed, e.g., 1900 as per previous instructions
        if value < 1900:
            raise serializers.ValidationError("Paper year must be 1900 or later.")
            
        return value


class DocumentListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            'document_id', 
            'title', 
            'document_type', 
            'paper_year', 
            'paper_session', 
            'extraction_status', 
            'uploaded_at'
        ]
