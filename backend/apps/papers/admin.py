from django.contrib import admin
from .models import Question, GeneratedPaper, GeneratedPaperQuestion

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        'question_id', 
        'question_number', 
        'sub_question_label', 
        'document', 
        'chapter', 
        'question_type', 
        'marks'
    )
    list_filter = ('question_type', 'document', 'chapter')
    search_fields = ('question_number', 'question_text', 'document__title')
    readonly_fields = ('created_at',)

@admin.register(GeneratedPaper)
class GeneratedPaperAdmin(admin.ModelAdmin):
    list_display = ('paper_id', 'user', 'subject', 'chapter', 'paper_type', 'generated_at')
    list_filter = ('paper_type', 'subject', 'chapter')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('generated_at',)

@admin.register(GeneratedPaperQuestion)
class GeneratedPaperQuestionAdmin(admin.ModelAdmin):
    list_display = ('generated_paper_question_id', 'paper', 'question', 'question_order')
    list_filter = ('paper',)
    search_fields = ('paper__paper_id', 'question__question_number')
