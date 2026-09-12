import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from psaumes.models import MomentLiturgique, Partition, PartitionAudioTempoVariant
from psaumes.models.audio_variant import APPLE_GENERATED_TEMPO_VALUES
from psaumes.services.audio import get_missing_voices
from psaumes.services.audio.channels import (
    NORMALIZABLE_PARTITION_AUDIO_FIELDS,
    partition_field_cached_channel_count,
    tempo_variant_cached_channel_count,
)
from psaumes.services.audio.tempo_variants import (
    get_missing_source_voice_types,
    get_missing_tempo_variant_voice_types,
)
from psaumes.services.liturgie.calendrier_liturgique import get_moment_liturgique_query_params
from psaumes.tasks import (
    AUDIO_QUEUE_PRIORITY_BULK,
    enqueue_partition_audio_field_normalization,
    enqueue_partition_audio_generation,
    enqueue_partition_tempo_variant_generation,
    enqueue_tempo_variant_audio_normalization,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Enqueue missing audio generation jobs at low priority."

    def add_arguments(self, parser):
        parser.add_argument(
            '--synthetic',
            action='store_true',
            help='Enqueue missing synthetic MP3 generation from MXL files.',
        )
        parser.add_argument(
            '--normalize-mono',
            action='store_true',
            help='Enqueue stereo-to-mono normalization for non-mix audio files.',
        )
        parser.add_argument(
            '--tempo-variants',
            action='store_true',
            help='Enqueue missing Apple/Safari tempo variants for non-synthetic MP3 files.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=20,
            help='Maximum number of generation jobs to enqueue.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be enqueued without creating jobs.',
        )
        parser.add_argument(
            '--upcoming-days',
            type=int,
            default=21,
            help=(
                'Limit mono normalization and tempo variant backfill to partitions used in the '
                'next N days. Use 0 to disable this limit.'
            ),
        )

    def handle(self, *args, **options):
        include_normalize_mono = options['normalize_mono']
        include_synthetic = options['synthetic']
        include_tempo_variants = options['tempo_variants']
        if not include_normalize_mono and not include_synthetic and not include_tempo_variants:
            include_normalize_mono = True
            include_synthetic = True
            include_tempo_variants = True

        limit = max(options['limit'], 0)
        upcoming_days = max(options['upcoming_days'], 0)
        dry_run = options['dry_run']
        enqueued = 0
        upcoming_partition_ids = self._upcoming_partition_ids(upcoming_days)

        if include_normalize_mono:
            for target in self._normalization_candidates(upcoming_partition_ids):
                if enqueued >= limit:
                    break
                self.stdout.write(
                    f"{'[dry-run] ' if dry_run else ''}normalize {target['label']}"
                )
                if not dry_run:
                    if target['type'] == 'partition':
                        enqueue_partition_audio_field_normalization(
                            target['partition'],
                            target['field_name'],
                            priority=AUDIO_QUEUE_PRIORITY_BULK,
                            detect=target.get('detect', False),
                        )
                    else:
                        enqueue_tempo_variant_audio_normalization(
                            target['variant'],
                            priority=AUDIO_QUEUE_PRIORITY_BULK,
                            detect=target.get('detect', False),
                        )
                enqueued += 1

        if include_tempo_variants:
            for partition, tempo, missing in self._tempo_variant_candidates(upcoming_partition_ids):
                if enqueued >= limit:
                    break
                self.stdout.write(
                    f"{'[dry-run] ' if dry_run else ''}tempo partition={partition.id} "
                    f"tempo={tempo} missing={','.join(missing)}"
                )
                if not dry_run:
                    enqueue_partition_tempo_variant_generation(
                        partition,
                        tempo,
                        priority=AUDIO_QUEUE_PRIORITY_BULK,
                    )
                enqueued += 1

        if include_synthetic:
            for partition in self._synthetic_candidates():
                if enqueued >= limit:
                    break
                missing = get_missing_voices(partition)
                self.stdout.write(
                    f"{'[dry-run] ' if dry_run else ''}synthetic partition={partition.id} "
                    f"missing={','.join(missing)}"
                )
                if not dry_run:
                    enqueue_partition_audio_generation(partition, priority=AUDIO_QUEUE_PRIORITY_BULK)
                enqueued += 1

        action = 'would enqueue' if dry_run else 'enqueued'
        self.stdout.write(self.style.SUCCESS(f"{action}: {enqueued} job(s)"))

    def _synthetic_candidates(self):
        queryset = (
            Partition.objects
            .filter(partition_mxl__isnull=False)
            .exclude(partition_mxl='')
            .order_by('id')
        )
        for partition in queryset.iterator():
            if not get_missing_voices(partition):
                continue
            if not partition.mp3_synthetiques and partition.has_audio():
                continue
            yield partition

    def _normalization_candidates(self, partition_ids=None):
        queryset = Partition.objects.order_by('id')
        if partition_ids is not None:
            queryset = queryset.filter(id__in=partition_ids)
        for partition in queryset.iterator():
            for field_name in NORMALIZABLE_PARTITION_AUDIO_FIELDS:
                if not getattr(partition, field_name):
                    continue
                try:
                    cached = partition_field_cached_channel_count(partition, field_name)
                except Exception:
                    logger.warning(
                        "Unable to read audio_channels cache partition=%s field=%s",
                        partition.id,
                        field_name,
                        exc_info=True,
                    )
                    continue
                if cached is not None:
                    if cached > 1:
                        yield {
                            'type': 'partition',
                            'partition': partition,
                            'field_name': field_name,
                            'detect': False,
                            'label': f"partition={partition.id} field={field_name}",
                        }
                    continue
                # Cache missing: defer detection to the Celery worker, which must
                # download the file anyway, to avoid double R2 GET during scan.
                yield {
                    'type': 'partition',
                    'partition': partition,
                    'field_name': field_name,
                    'detect': True,
                    'label': (
                        f"partition={partition.id} field={field_name} "
                        f"(detect-pending)"
                    ),
                }

        variant_queryset = PartitionAudioTempoVariant.objects.exclude(audio_file='').order_by('id')
        if partition_ids is not None:
            variant_queryset = variant_queryset.filter(partition_id__in=partition_ids)
        for variant in variant_queryset.iterator():
            try:
                cached = tempo_variant_cached_channel_count(variant)
            except Exception:
                logger.warning(
                    "Unable to read audio_channels cache tempo_variant=%s",
                    variant.id,
                    exc_info=True,
                )
                continue
            if cached is not None:
                if cached > 1:
                    yield {
                        'type': 'tempo_variant',
                        'variant': variant,
                        'detect': False,
                        'label': (
                            f"tempo_variant={variant.id} partition={variant.partition_id} "
                            f"voice={variant.voice_type} tempo={variant.tempo}"
                        ),
                    }
                continue
            yield {
                'type': 'tempo_variant',
                'variant': variant,
                'detect': True,
                'label': (
                    f"tempo_variant={variant.id} partition={variant.partition_id} "
                    f"voice={variant.voice_type} tempo={variant.tempo} (detect-pending)"
                ),
            }

    def _tempo_variant_candidates(self, partition_ids=None):
        queryset = (
            Partition.objects
            .filter(mp3_synthetiques=False)
            .order_by('id')
        )
        if partition_ids is not None:
            queryset = queryset.filter(id__in=partition_ids)
        for partition in queryset.iterator():
            if get_missing_source_voice_types(partition):
                continue
            for tempo in APPLE_GENERATED_TEMPO_VALUES:
                missing = get_missing_tempo_variant_voice_types(partition, tempo)
                if missing:
                    yield partition, tempo, missing

    def _upcoming_partition_ids(self, days):
        if days <= 0:
            return None

        today = timezone.localdate()
        partition_ids = set()
        for offset in range(days + 1):
            target_date = today + timedelta(days=offset)
            try:
                moment_params = get_moment_liturgique_query_params(target_date)
            except Exception:
                logger.warning(
                    "Unable to compute liturgical moment for %s",
                    target_date,
                    exc_info=True,
                )
                continue
            moments = (
                MomentLiturgique.objects
                .filter(**moment_params)
                .filter(psaume__isnull=False)
                .prefetch_related('psaume__partitions')
            )
            for moment in moments:
                partition_ids.update(moment.psaume.partitions.values_list('id', flat=True))
        return partition_ids
