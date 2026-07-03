from django.db import models
from apps.documents.models import Document

class ExtractionLog(models.Model):
    """
    Model to track the processing status and logs/errors of document extractions.
    """
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    log_id = models.BigAutoField(primary_key=True)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="extraction_logs"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices
    )
    message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Log {self.log_id} - Document {self.document_id} ({self.status})"
