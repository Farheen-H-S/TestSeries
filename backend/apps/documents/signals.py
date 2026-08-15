import logging
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.core.files.storage import default_storage
from .models import Document

logger = logging.getLogger(__name__)

@receiver(post_delete, sender=Document)
def delete_document_file(sender, instance, **kwargs):
    """
    Safely delete the physical PDF file associated with the Document
    upon deletion, ONLY if no other Document references the same storage_path.
    """
    if not instance.storage_path:
        return

    # Check if any other Document record references the same storage path
    other_refs = Document.objects.filter(storage_path=instance.storage_path).exclude(pk=instance.pk).exists()
    if not other_refs:
        try:
            if default_storage.exists(instance.storage_path):
                default_storage.delete(instance.storage_path)
                logger.info("Deleted physical file %s associated with deleted document_id=%s", instance.storage_path, instance.document_id)
        except Exception as e:
            logger.warning("Failed to delete physical file %s during document cleanup: %s", instance.storage_path, e)


@receiver(post_delete, sender=Document)
def delete_document_table_crops(sender, instance, **kwargs):
    """
    Deletes all generated table crop PNG files associated with the Document upon deletion.
    """
    import glob, os
    if not instance.document_id:
        return
    crop_dir = os.path.abspath("media/table_crops")
    pattern = os.path.join(crop_dir, f"doc{instance.document_id}_*.png")
    for fpath in glob.glob(pattern):
        try:
            if os.path.exists(fpath):
                os.remove(fpath)
                logger.info("Deleted table crop file %s associated with document_id=%s", fpath, instance.document_id)
        except Exception as e:
            logger.warning("Failed to delete table crop file %s: %s", fpath, e)

