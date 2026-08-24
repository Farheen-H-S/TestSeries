from rest_framework import serializers
from django.conf import settings
from django.utils import timezone
from .models import Document
from apps.syllabus.models import Subject
from apps.syllabus.serializers import SubjectSerializer
import os

import re

MONTH_MAP = {
    'january': Document.ExamMonth.JANUARY, 'jan': Document.ExamMonth.JANUARY,
    'february': Document.ExamMonth.FEBRUARY, 'feb': Document.ExamMonth.FEBRUARY,
    'march': Document.ExamMonth.MARCH, 'mar': Document.ExamMonth.MARCH,
    'april': Document.ExamMonth.APRIL, 'apr': Document.ExamMonth.APRIL,
    'may': Document.ExamMonth.MAY,
    'june': Document.ExamMonth.JUNE, 'jun': Document.ExamMonth.JUNE,
    'july': Document.ExamMonth.JULY, 'jul': Document.ExamMonth.JULY,
    'august': Document.ExamMonth.AUGUST, 'aug': Document.ExamMonth.AUGUST,
    'september': Document.ExamMonth.SEPTEMBER, 'sept': Document.ExamMonth.SEPTEMBER, 'sep': Document.ExamMonth.SEPTEMBER,
    'october': Document.ExamMonth.OCTOBER, 'oct': Document.ExamMonth.OCTOBER,
    'november': Document.ExamMonth.NOVEMBER, 'nov': Document.ExamMonth.NOVEMBER,
    'december': Document.ExamMonth.DECEMBER, 'dec': Document.ExamMonth.DECEMBER,
}

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
            target_title = f"{subject.name} - {document_type} - {exam_month} {paper_year}"
        else:
            target_title = title.strip()
            # Smart alignment: if title explicitly mentions a specific month keyword, ensure exam_month aligns
            t_lower = target_title.lower()
            for kw, m_enum in MONTH_MAP.items():
                if re.search(rf'\b{kw}\b', t_lower):
                    if exam_month != m_enum:
                        attrs['exam_month'] = m_enum
                        exam_month = m_enum
                    break
            
        # Case-insensitive title uniqueness validation
        if Document.objects.filter(title__iexact=target_title).exists():
            raise serializers.ValidationError({
                "title": f"A paper titled '{target_title}' already exists. Please enter a unique title."
            })

        attrs['title'] = target_title
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


class DocumentUpdateSerializer(serializers.ModelSerializer):
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.filter(is_active=True), required=False)
    exam_month = serializers.ChoiceField(choices=Document.ExamMonth.choices, required=False)
    title = serializers.CharField(required=False, allow_blank=True)
    paper_year = serializers.IntegerField(required=False)
    document_type = serializers.ChoiceField(choices=Document.DocumentType.choices, required=False)

    class Meta:
        model = Document
        fields = ['subject', 'title', 'document_type', 'paper_year', 'exam_month']


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
