from django.db import models
from django.conf import settings
from apps.syllabus.models import Subject

class Document(models.Model):
    class DocumentType(models.TextChoices):
        RTP = "RTP", "RTP"
        PYQ = "PYQ", "PYQ"
        MOCK = "MOCK", "MOCK"

    class ExtractionStatus(models.TextChoices):
        PENDING = "PENDING", "PENDING"
        PROCESSING = "PROCESSING", "PROCESSING"
        COMPLETED = "COMPLETED", "COMPLETED"
        FAILED = "FAILED", "FAILED"

    document_id = models.BigAutoField(primary_key=True)
    
    # TODO: Replace with apps.accounts.User once implemented
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name="documents"
    )
    subject = models.ForeignKey(
        Subject, 
        on_delete=models.PROTECT,
        related_name="documents"
    )
    title = models.CharField(max_length=255)
    document_type = models.CharField(
        max_length=10, 
        choices=DocumentType.choices
    )
    paper_year = models.PositiveIntegerField()
    paper_session = models.CharField(
        max_length=20, 
        null=True, 
        blank=True
    )
    storage_path = models.TextField()
    total_pages = models.PositiveIntegerField(null=True, blank=True)
    extraction_status = models.CharField(
        max_length=20,
        choices=ExtractionStatus.choices,
        default=ExtractionStatus.PENDING
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['subject'], name='idx_document_subject'),
            models.Index(fields=['document_type'], name='idx_document_type'),
        ]

    def __str__(self):
        return f"{self.title} ({self.document_type})"
