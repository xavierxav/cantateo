from django.db import models
from django.db.models import Q


class PartitionAudioNormalizationJob(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        QUEUED = 'queued', 'Queued'
        STARTED = 'started', 'Started'
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED = 'failed', 'Failed'

    class QueuePriority(models.TextChoices):
        USER = 'user', 'Utilisateur'
        BULK = 'bulk', 'Basse priorité'

    class TargetType(models.TextChoices):
        PARTITION = 'partition', 'Partition'
        TEMPO_VARIANT = 'tempo_variant', 'Variante tempo'

    target_type = models.CharField(max_length=20, choices=TargetType.choices, db_index=True)
    partition = models.ForeignKey(
        'Partition',
        on_delete=models.CASCADE,
        related_name='audio_normalization_jobs',
        null=True,
        blank=True,
    )
    tempo_variant = models.ForeignKey(
        'PartitionAudioTempoVariant',
        on_delete=models.CASCADE,
        related_name='audio_normalization_jobs',
        null=True,
        blank=True,
    )
    field_name = models.CharField(max_length=40)
    source_name = models.CharField(max_length=500, blank=True, default='')
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
    last_error = models.TextField(blank=True, default='')
    queued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['partition', 'field_name'],
                condition=Q(partition__isnull=False),
                name='unique_partition_audio_normalization_job',
            ),
            models.UniqueConstraint(
                fields=['tempo_variant'],
                condition=Q(tempo_variant__isnull=False),
                name='unique_tempo_variant_audio_normalization_job',
            ),
        ]
        verbose_name = 'Job de normalisation audio'
        verbose_name_plural = 'Jobs de normalisation audio'
        ordering = ['-queued_at', '-id']

    def __str__(self):
        if self.partition_id:
            return f"Mono job partition {self.partition_id} {self.field_name} ({self.status})"
        return f"Mono job tempo variant {self.tempo_variant_id} ({self.status})"
