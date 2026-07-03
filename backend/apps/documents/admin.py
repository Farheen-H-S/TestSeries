from django.contrib import admin
from .models import Document

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        'document_id',
        'title',
        'subject',
        'document_type',
        'paper_year',
        'paper_session',
        'extraction_status',
        'uploaded_at'
    )
    search_fields = ('title',)
    list_filter = ('subject', 'document_type', 'extraction_status')
    readonly_fields = ('uploaded_at',)
