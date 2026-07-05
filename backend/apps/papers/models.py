from django.db import models
from django.conf import settings
from apps.syllabus.models import Subject, Chapter
from apps.documents.models import Document

class Question(models.Model):
    """
    Represents an individual question extracted from a document.
    """
    question_id = models.BigAutoField(primary_key=True)
    parent_question = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sub_questions"
    )
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="questions"
    )
    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.PROTECT,
        related_name="questions",
        null=True,
        blank=True
    )
    question_number = models.CharField(max_length=20)
    sub_question_label = models.CharField(max_length=10, null=True, blank=True)
    question_content = models.TextField()  # Formatted HTML
    question_text = models.TextField()     # Plain text
    answer_content = models.TextField()    # Formatted HTML
    answer_text = models.TextField()       # Plain text
    
    # Store question_type as a normal CharField without TextChoices.
    # Choices are intentionally not used because supported types are expected to evolve.
    # Default is "UNIDENTIFIED", used when the extraction pipeline cannot determine the type.
    question_type = models.CharField(
        max_length=30,
        default="UNIDENTIFIED"
    )
    
    marks = models.PositiveIntegerField(null=True, blank=True)
    source_page = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['document', 'question_number', 'sub_question_label'],
                name='unique_question_per_document'
            )
        ]
        indexes = [
            models.Index(fields=['document'], name='idx_question_document'),
            models.Index(fields=['chapter'], name='idx_question_chapter'),
            models.Index(fields=['parent_question'], name='idx_question_parent'),
            models.Index(fields=['question_type'], name='idx_question_type'),
        ]

    def __str__(self):
        return f"Q{self.question_number} ({self.document.title})"


class GeneratedPaper(models.Model):
    """
    Represents a paper generated for a user based on selected criteria.
    """
    class PaperType(models.TextChoices):
        RTP = "RTP", "RTP"
        PYQ = "PYQ", "PYQ"
        MOCK = "MOCK", "MOCK"

    paper_id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="generated_papers"
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="generated_papers"
    )
    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.PROTECT,
        related_name="generated_papers"
    )
    paper_type = models.CharField(
        max_length=20,
        choices=PaperType.choices
    )
    total_questions = models.PositiveIntegerField()
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user'], name='idx_generated_paper_user'),
        ]

    def __str__(self):
        return f"{self.paper_type} Paper #{self.paper_id}"


class GeneratedPaperQuestion(models.Model):
    """
    Mapping between a generated paper and the questions it contains.
    """
    generated_paper_question_id = models.BigAutoField(primary_key=True)
    paper = models.ForeignKey(
        GeneratedPaper,
        on_delete=models.CASCADE,
        related_name="paper_questions"
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.PROTECT,
        related_name="paper_mappings"
    )
    question_order = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['paper', 'question_order'],
                name='unique_paper_question_order'
            )
        ]

    def __str__(self):
        return f"Paper {self.paper.paper_id} - Q{self.question_order}"
