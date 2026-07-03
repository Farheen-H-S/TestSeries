from django.contrib import admin
from .models import ExtractionLog

@admin.register(ExtractionLog)
class ExtractionLogAdmin(admin.ModelAdmin):
    """
    Admin configuration for the ExtractionLog model.
    """
    list_display = ("log_id", "document", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("document__title", "message")
    readonly_fields = ("created_at",)
