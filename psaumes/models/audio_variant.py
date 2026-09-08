from decimal import Decimal

from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver

from .utils import partition_audio_tempo_variant_path
from .validators import validate_mp3_upload


APPLE_TEMPO_VALUES = (Decimal('0.50'), Decimal('1.00'), Decimal('1.50'))
APPLE_GENERATED_TEMPO_VALUES = (Decimal('0.50'), Decimal('1.50'))
APPLE_TEMPO_CHOICES = (
    (Decimal('0.50'), '0.5x'),
    (Decimal('1.00'), '1.0x'),
    (Decimal('1.50'), '1.5x'),
)
TEMPO_VARIANT_VOICE_CHOICES = (
    ('S', 'Soprano'),
    ('A', 'Alto'),
    ('T', 'Ténor'),
    ('B', 'Basse'),
    ('I', 'Instrumental'),
)


class PartitionAudioTempoVariant(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        QUEUED = 'queued', 'Queued'
        STARTED = 'started', 'Started'
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED = 'failed', 'Failed'

    class QueuePriority(models.TextChoices):
        USER = 'user', 'Utilisateur'
        BULK = 'bulk', 'Basse priorité'

    partition = models.ForeignKey(
        'Partition',
        on_delete=models.CASCADE,
        related_name='tempo_variants',
    )
    voice_type = models.CharField(max_length=1, choices=TEMPO_VARIANT_VOICE_CHOICES)
    tempo = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        choices=APPLE_TEMPO_CHOICES,
        db_index=True,
    )
    audio_file = models.FileField(
        upload_to=partition_audio_tempo_variant_path,
        validators=[validate_mp3_upload],
        blank=True,
        null=True,
        verbose_name='Audio tempo Apple/Safari',
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
    last_error = models.TextField(blank=True, default='')
    audio_channels = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Cache du nombre de canaux audio du fichier. Invalide les "
            "requêtes R2 HEAD/GET lors de la détection mono."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['partition', 'voice_type', 'tempo'],
                name='unique_partition_voice_tempo_variant',
            ),
        ]
        ordering = ['partition_id', 'tempo', 'voice_type']
        verbose_name = 'Variante audio tempo'
        verbose_name_plural = 'Variantes audio tempo'

    def __str__(self):
        return f"Tempo {self.tempo} {self.voice_type} for partition {self.partition_id} ({self.status})"


@receiver(pre_save, sender=PartitionAudioTempoVariant)
def invalidate_tempo_variant_audio_channels_on_file_change(sender, instance, **kwargs):
    """Clear cached channel count when the variant audio file changes."""
    if not instance.pk or instance.audio_channels is None:
        return
    try:
        previous = PartitionAudioTempoVariant.objects.filter(pk=instance.pk).only(
            'audio_file', 'audio_channels'
        ).first()
    except PartitionAudioTempoVariant.DoesNotExist:
        return
    if previous is None:
        return
    new_name = instance.audio_file.name if instance.audio_file else ''
    old_name = previous.audio_file.name if previous.audio_file else ''
    if new_name != old_name:
        instance.audio_channels = None
