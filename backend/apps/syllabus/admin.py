from django.contrib import admin
from .models import Subject, Chapter

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Subject model.
    """
    list_display = ('subject_id', 'name', 'exam_level', 'is_active')
    search_fields = ('name',)
    list_filter = ('exam_level', 'is_active')


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Chapter model.
    """
    list_display = ('chapter_id', 'chapter_name', 'subject', 'chapter_order')
    search_fields = ('chapter_name',)
    list_filter = ('subject',)
