from rest_framework import serializers
from django.conf import settings
from django.utils import timezone
from .models import Document
from apps.syllabus.models import Subject
from apps.syllabus.serializers import SubjectSerializer
import os

class DocumentUploadSerializer(serializers.ModelSerializer):
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.filter(is_active=True))
    exam_month = serializers.ChoiceField(choices=Document.ExamMonth.choices)
    title = serializers.CharField(required=False, allow_blank=True)
    file = serializers.FileField(write_only=True)

    class Meta:
        model = Document
        fields = ['subject', 'title', 'document_type', 'paper_year', 'exam_month', 'file']

    def validate(self, attrs):
        attrs.pop('file', None)  # Pop write-only file field as it is handled by the view
        
        subject = attrs.get('subject')
        document_type = attrs.get('document_type')
        exam_month = attrs.get('exam_month')
        paper_year = attrs.get('paper_year')
        title = attrs.get('title')
        
        if not title or not title.strip():
            attrs['title'] = f"{subject.name} - {document_type} - {exam_month} {paper_year}"
        else:
            attrs['title'] = title.strip()
            
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
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            'document_id', 
            'title', 
            'subject',
            'document_type', 
            'paper_year', 
            'exam_month', 
            'extraction_status', 
            'uploaded_at',
            'total_pages',
            'file_url'
        ]

    def get_file_url(self, obj):
        return f"{settings.MEDIA_URL}{obj.storage_path}"
