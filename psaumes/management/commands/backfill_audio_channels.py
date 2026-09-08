import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from psaumes.models import MomentLiturgique, Partition, PartitionAudioTempoVariant
from psaumes.services.audio.channels import (
    NORMALIZABLE_PARTITION_AUDIO_FIELDS,
    file_field_channel_count,
    _persist_partition_channel_count,
    _persist_tempo_variant_channel_count,
)
from psaumes.services.liturgie.calendrier_liturgique import get_moment_liturgique_query_params

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'One-shot backfill of the audio_channels cache for existing R2 files. '
        'Downloads each MP3 once, counts channels via ffprobe, and persists the '
        'result so future scans avoid R2 HEAD/GET requests.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Detect and report channel counts without writing to the database.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Maximum number of audio files to inspect. 0 = no limit.',
        )
        parser.add_argument(
            '--upcoming-days',
            type=int,
            default=0,
            help=(
                'Only inspect partitions used in the next N days of liturgy. '
                '0 = no limit (inspect all partitions and variants).'
            ),
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-inspect files even when audio_channels cache is already set.',
        )

    def handle(self, *args, **options):
        logging.getLogger('botocore').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)

        dry_run = options['dry_run']
        limit = max(options['limit'], 0)
        upcoming_days = max(options['upcoming_days'], 0)
        force = options['force']

        partition_ids = self._upcoming_partition_ids(upcoming_days)

        inspected = 0
        persisted = 0
        missing = 0
        errors = 0

        for partition, field_name in self._partition_field_iter(partition_ids, force):
            if limit and inspected >= limit:
                break
            inspected += 1
            channels = self._inspect_partition_field(partition, field_name)
            status = self._report_partition(
                partition, field_name, channels, dry_run
            )
            if status == 'missing':
                missing += 1
            elif status == 'error':
                errors += 1
            elif status == 'persisted':
                persisted += 1

        for variant in self._variant_iter(partition_ids, force):
            if limit and inspected >= limit:
                break
            inspected += 1
            channels = self._inspect_variant(variant)
            status = self._report_variant(variant, channels, dry_run)
            if status == 'missing':
                missing += 1
            elif status == 'error':
                errors += 1
            elif status == 'persisted':
                persisted += 1

        verb = 'would persist' if dry_run else 'persisted'
        self.stdout.write(self.style.SUCCESS(
            f"backfill_audio_channels: inspected={inspected} "
            f"{verb}={persisted} missing={missing} errors={errors}"
        ))

    def _partition_field_iter(self, partition_ids, force):
        queryset = Partition.objects.order_by('id')
        if partition_ids is not None:
            queryset = queryset.filter(id__in=partition_ids)
        for partition in queryset.iterator():
            for field_name in NORMALIZABLE_PARTITION_AUDIO_FIELDS:
                field = getattr(partition, field_name)
                if not field or not field.name:
                    continue
                if not force and self._partition_cache_has(partition, field_name):
                    continue
                yield partition, field_name

    def _variant_iter(self, partition_ids, force):
        queryset = PartitionAudioTempoVariant.objects.exclude(audio_file='').order_by('id')
        if partition_ids is not None:
            queryset = queryset.filter(partition_id__in=partition_ids)
        for variant in queryset.iterator():
            if not variant.audio_file or not variant.audio_file.name:
                continue
            if not force and variant.audio_channels is not None:
                continue
            yield variant

    def _partition_cache_has(self, partition, field_name):
        cache = partition.audio_channels or {}
        return isinstance(cache, dict) and field_name in cache

    def _inspect_partition_field(self, partition, field_name):
        field = getattr(partition, field_name)
        try:
            channels = file_field_channel_count(field)
        except Exception:
            logger.warning(
                "backfill: ffprobe failed partition=%s field=%s",
                partition.id,
                field_name,
                exc_info=True,
            )
            return None
        if channels is None:
            return None
        return channels

    def _inspect_variant(self, variant):
        try:
            channels = file_field_channel_count(variant.audio_file)
        except Exception:
            logger.warning(
                "backfill: ffprobe failed tempo_variant=%s",
                variant.id,
                exc_info=True,
            )
            return None
        return channels

    def _report_partition(self, partition, field_name, channels, dry_run):
        label = f"partition={partition.id} field={field_name}"
        if channels is None:
            self.stdout.write(f"[skip] {label}: missing or unreadable source")
            return 'missing'
        if dry_run:
            self.stdout.write(f"[dry-run] {label}: channels={channels}")
            return 'dry-run'
        with transaction.atomic():
            _persist_partition_channel_count(partition, field_name, channels)
        self.stdout.write(f"[ok] {label}: channels={channels}")
        return 'persisted'

    def _report_variant(self, variant, channels, dry_run):
        label = (
            f"tempo_variant={variant.id} partition={variant.partition_id} "
            f"voice={variant.voice_type} tempo={variant.tempo}"
        )
        if channels is None:
            self.stdout.write(f"[skip] {label}: missing or unreadable source")
            return 'missing'
        if dry_run:
            self.stdout.write(f"[dry-run] {label}: channels={channels}")
            return 'dry-run'
        with transaction.atomic():
            _persist_tempo_variant_channel_count(variant, channels)
        self.stdout.write(f"[ok] {label}: channels={channels}")
        return 'persisted'

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
