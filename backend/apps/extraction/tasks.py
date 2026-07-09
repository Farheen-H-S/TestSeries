import logging
from celery import shared_task
from django.db.utils import OperationalError
from .services.extraction_service import ExtractionService

logger = logging.getLogger(__name__)

@shared_task(
    name="documents.extract_document",
    acks_late=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=5,
)
def extract_document_task(document_id: int):
    """
    Celery task to trigger document extraction.
    Using acks_late=True ensures tasks are acknowledged only after execution completes,
    facilitating safe redelivery if the worker crashes mid-run.
    """
    logger.info("Celery task started | document_id=%s", document_id)
    try:
        ExtractionService.trigger_extraction(document_id)
    except Exception:
        logger.exception("Failed to run extraction task for document %s", document_id)
        raise
