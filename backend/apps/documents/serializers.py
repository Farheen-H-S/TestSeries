from rest_framework import serializers
from django.conf import settings
from django.utils import timezone
from .models import Document
from apps.syllabus.models import Subject
from apps.syllabus.serializers import SubjectSerializer
import os

class DocumentUploadSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(write_only=True)
    exam_level = serializers.ChoiceField(choices=Subject.ExamLevel.choices, write_only=True)
    file = serializers.FileField(write_only=True)

    class Meta:
        model = Document
        fields = ['subject_name', 'exam_level', 'title', 'document_type', 'paper_year', 'paper_session', 'file']

    def validate(self, attrs):
        subject_name = attrs.pop('subject_name')
        exam_level = attrs.pop('exam_level')
        attrs.pop('file', None)  # Pop write-only file field as it is handled by the view
        
        # Normalize: trim, collapse spaces, Title Case
        normalized_name = " ".join(subject_name.strip().split()).title()
        
        if not normalized_name:
            raise serializers.ValidationError(
                {"subject_name": "Subject name cannot be blank."}
            )
        
        # Atomically get or create Subject using normalized name and exam_level
        subject, created = Subject.objects.get_or_create(
            name=normalized_name,
            exam_level=exam_level
        )
            
        attrs['subject'] = subject
        return attrs

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
        current_year = timezone.now().year
        
        if not (1900 <= value <= current_year + 1):
            raise serializers.ValidationError(
                f"Paper year must be between 1900 and {current_year + 1}."
            )
            
        return value


class DocumentListSerializer(serializers.ModelSerializer):
    subject = SubjectSerializer(read_only=True)

    class Meta:
        model = Document
        fields = [
            'document_id', 
            'title', 
            'subject',
            'document_type', 
            'paper_year', 
            'paper_session', 
            'extraction_status', 
            'uploaded_at',
            'total_pages'
        ]
