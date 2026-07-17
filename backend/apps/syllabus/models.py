from django.db import models

class Subject(models.Model):
    """
    Represents a subject in the syllabus, categorized by exam level.
    """
    class ExamLevel(models.TextChoices):
        FOUNDATION = "Foundation", "Foundation"
        INTERMEDIATE = "Intermediate", "Intermediate"
        FINAL = "Final", "Final"

    subject_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=150)
    exam_level = models.CharField(
        max_length=30, 
        choices=ExamLevel.choices
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'exam_level'],
                name='unique_subject_name_exam_level'
            )
        ]

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
        return self.chapter_name


class ChapterKeyword(models.Model):
    """
    Stores deterministic keywords for a chapter used during extraction mapping.
    One record per chapter. Store keywords one per line.
    """
    chapter_keyword_id = models.BigAutoField(primary_key=True)
    chapter = models.OneToOneField(
        Chapter,
        on_delete=models.CASCADE,
        related_name="keyword_record"
    )
    keywords = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Keywords for {self.chapter.chapter_name}"
