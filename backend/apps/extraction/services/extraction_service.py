import logging
import shutil
import uuid
import tempfile
from pathlib import Path
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.exceptions import SuspiciousFileOperation
from apps.documents.models import Document
from .extraction_pipeline import extract_document

logger = logging.getLogger(__name__)

class ExtractionService:
    @classmethod
    def trigger_extraction(cls, document_id: int):
        """
        Orchestrate document extraction using a temporary working copy.
        Creates a temporary directory, copies the document PDF to it,
        triggers the extraction pipeline, and ensures everything is cleaned up.
        """
        logger.info("Triggering extraction service | document_id=%s", document_id)
        document = Document.objects.get(pk=document_id)

        # Resolve the original absolute path
        try:
            original_path = Path(default_storage.path(document.storage_path))
        except (SuspiciousFileOperation, ValueError):
            original_path = Path(document.storage_path)

        # Define temporary root path (relative to BASE_DIR)
        temp_root = Path(settings.BASE_DIR) / "temp"
        temp_root.mkdir(parents=True, exist_ok=True)

        try:
            # Create unique temporary folder under backend/temp
            with tempfile.TemporaryDirectory(dir=str(temp_root)) as tmp_dir:
                temp_file_name = f"{document.document_id}_{uuid.uuid4()}.pdf"
                temp_file_path = Path(tmp_dir) / temp_file_name

                if original_path.exists():
                    logger.info("Copying original file from %s to temp copy %s", original_path, temp_file_path)
                    shutil.copy2(original_path, temp_file_path)
                    target_path = str(temp_file_path)
                else:
                    # Fallback for testing environments where the storage path is a mock or does not exist on disk
                    logger.warning("Original file does not exist at %s. Skipping copy.", original_path)
                    target_path = str(original_path)

                # Invoke extraction pipeline with the temporary file path
                extract_document(document, temp_file_path=target_path)
        finally:
            # Prune empty parent temp directory if empty after TemporaryDirectory context exits and cleans up its files
            if temp_root.exists() and not any(temp_root.iterdir()):
                try:
                    temp_root.rmdir()
                    logger.info("Pruned empty temp directory: %s", temp_root)
                except Exception as e:
                    logger.warning("Failed to prune temp directory: %s", e)
