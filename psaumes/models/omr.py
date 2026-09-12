from django.db import models

from .utils import partition_omr_source_path


class PartitionOmrJob(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        QUEUED = 'queued', 'Queued'
        STARTED = 'started', 'Started'
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED = 'failed', 'Failed'

    class QueuePriority(models.TextChoices):
        USER = 'user', 'Utilisateur'
        BULK = 'bulk', 'Basse priorité'

    class SourceType(models.TextChoices):
        PARTITION_PDF = 'partition_pdf', 'Partition PDF'
        UPLOADED_IMAGE = 'uploaded_image', 'Image importée'

    partition = models.OneToOneField(
        'Partition',
        on_delete=models.CASCADE,
        related_name='omr_job',
    )
    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        default=SourceType.PARTITION_PDF,
        db_index=True,
    )
    source_file = models.FileField(
        upload_to=partition_omr_source_path,
        blank=True,
        null=True,
        verbose_name='Source OMR',
    )
    source_name = models.CharField(max_length=500, blank=True, default='')
    source_sha256 = models.CharField(max_length=64, blank=True, default='')
    backend = models.CharField(max_length=80, blank=True, default='')
    backend_version = models.CharField(max_length=120, blank=True, default='')
    model_profile = models.CharField(max_length=120, blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    queue_priority = models.CharField(
        max_length=10,
        choices=QueuePriority.choices,
        default=QueuePriority.USER,
        db_index=True,
    )
    task_id = models.CharField(max_length=255, blank=True, default='')
    attempts = models.PositiveSmallIntegerField(default=0)
    page_count = models.PositiveSmallIntegerField(default=0)
    processed_pages = models.PositiveSmallIntegerField(default=0)
    generated_file_name = models.CharField(max_length=500, blank=True, default='')
    last_error = models.TextField(blank=True, default='')
    queued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Job de reconnaissance OMR'
        verbose_name_plural = 'Jobs de reconnaissance OMR'
        ordering = ['-queued_at', '-id']

    def __str__(self):
        return f"OMR job #{self.pk} for partition {self.partition_id} ({self.status})"
