from django.db import models


class PartitionAudioGenerationJob(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        QUEUED = 'queued', 'Queued'
        STARTED = 'started', 'Started'
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED = 'failed', 'Failed'

    class QueuePriority(models.TextChoices):
        USER = 'user', 'Utilisateur'
        BULK = 'bulk', 'Basse priorité'

    partition = models.OneToOneField(
        'Partition',
        on_delete=models.CASCADE,
        related_name='audio_generation_job',
    )
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
    generated_count = models.PositiveSmallIntegerField(default=0)
    total_count = models.PositiveSmallIntegerField(default=0)
    missing_voice_types = models.JSONField(default=list, blank=True)
    last_error = models.TextField(blank=True, default='')
    queued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Job de génération audio'
        verbose_name_plural = 'Jobs de génération audio'
        ordering = ['-queued_at', '-id']

    def __str__(self):
        return f"Audio job #{self.pk} for partition {self.partition_id} ({self.status})"
