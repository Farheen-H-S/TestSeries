from django.db import models
from django.core.exceptions import ValidationError

ACRONYM_MAP = {
    "as": "AS", "ind": "Ind", "caro": "CARO", "gst": "GST",
    "tds": "TDS", "tcs": "TCS", "llp": "LLP", "nbfc": "NBFC",
    "rbi": "RBI", "sebi": "SEBI", "dt": "DT", "idt": "IDT",
    "emh": "EMH", "npv": "NPV", "irr": "IRR", "eva": "EVA",
    "wacc": "WACC", "nav": "NAV", "eps": "EPS", "per": "PER",
    "pe": "PE", "it": "IT", "itl": "ITL", "aa": "AA", "fr": "FR",
    "afm": "AFM", "ibs": "IBS"
}

def normalize_syllabus_name(val: str) -> str:
    """
    Normalizes subject and chapter names:
    - Trims and collapses whitespace.
    - Applies canonical Title Case while preserving standard accounting/tax acronyms.
    - Fixes typo casing (e.g. 'RIsk' -> 'Risk').
    """
    if not val:
        return ""
    cleaned = " ".join(val.strip().split())
    words = cleaned.split(" ")
    formatted = []
    for w in words:
        lower_w = w.lower().strip(":,.;-()[]")
        if lower_w in ACRONYM_MAP:
            # Preserve surrounding punctuation
            prefix = w[:w.lower().find(lower_w)]
            suffix = w[w.lower().find(lower_w) + len(lower_w):]
            formatted.append(f"{prefix}{ACRONYM_MAP[lower_w]}{suffix}")
        elif lower_w in ["and", "or", "of", "in", "for", "with", "to", "on", "at", "by", "from", "&"]:
            formatted.append(w.lower() if w != "&" else "&")
        else:
            # Title case word, fixing interior caps like 'RIsk' -> 'Risk'
            if w.isupper() and len(w) > 4:
                formatted.append(w.capitalize())
            elif any(c.isupper() for c in w[1:]) and not w.isupper():
                formatted.append(w.capitalize())
            else:
                formatted.append(w[0].upper() + w[1:] if len(w) > 0 else "")
    res = " ".join(formatted)
    if res and res[0].islower():
        res = res[0].upper() + res[1:]
    return res


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

    def clean(self):
        super().clean()
        if self.name:
            self.name = normalize_syllabus_name(self.name)
            # Case-insensitive duplicate check
            qs = Subject.objects.filter(name__iexact=self.name, exam_level=self.exam_level)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(f"A subject with name '{self.name}' already exists for {self.exam_level}.")

    def save(self, *args, **kwargs):
        if self.name:
            self.name = normalize_syllabus_name(self.name)
        self.clean()
        super().save(*args, **kwargs)

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

    def clean(self):
        super().clean()
        if self.chapter_name:
            self.chapter_name = normalize_syllabus_name(self.chapter_name)
            if self.subject_id:
                qs = Chapter.objects.filter(subject_id=self.subject_id, chapter_name__iexact=self.chapter_name)
                if self.pk:
                    qs = qs.exclude(pk=self.pk)
                if qs.exists():
                    raise ValidationError(f"A chapter with name '{self.chapter_name}' already exists in {self.subject.name}.")

    def save(self, *args, **kwargs):
        if self.chapter_name:
            self.chapter_name = normalize_syllabus_name(self.chapter_name)
        self.clean()
        super().save(*args, **kwargs)

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
