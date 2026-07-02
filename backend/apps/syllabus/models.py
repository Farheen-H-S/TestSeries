from django.db import models

class Subject(models.Model):
    """
    Represents a subject in the syllabus, categorized by exam level.
    """
    subject_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=150, unique=True, null=False)
    exam_level = models.CharField(max_length=30, null=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Chapter(models.Model):
    """
    Represents a chapter belonging to a specific subject.
    """
    chapter_id = models.BigAutoField(primary_key=True)
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="chapters"
    )
    chapter_name = models.CharField(max_length=100)
    chapter_order = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['subject', 'chapter_name'],
                name='unique_subject_chapter'
            )
        ]

    def __str__(self):
        return f"{self.subject.name} - {self.chapter_name}"
