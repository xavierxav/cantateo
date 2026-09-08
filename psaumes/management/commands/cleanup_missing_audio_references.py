import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from psaumes.models import Partition, PartitionAudioTempoVariant
from psaumes.models.partition import VOICE_FIELD_MAP

logger = logging.getLogger(__name__)

PARTITION_AUDIO_FIELDS = tuple(VOICE_FIELD_MAP.values())


class Command(BaseCommand):
    help = 'Remove audio references whose storage objects are missing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned without modifying the database',
        )

    def handle(self, *args, **options):
        logging.getLogger('botocore').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        dry_run = options['dry_run']

        partition_updates = []
        variant_updates = []

        for partition in Partition.objects.order_by('id').iterator():
            for field_name in PARTITION_AUDIO_FIELDS:
                field = getattr(partition, field_name)
                if not field or not field.name:
                    continue
                if self._storage_exists(field):
                    continue
                partition_updates.append((partition, field_name, field.name))

        for variant in PartitionAudioTempoVariant.objects.exclude(audio_file='').order_by('id').iterator():
            field = variant.audio_file
            if not field or not field.name:
                continue
            if self._storage_exists(field):
                continue
            variant_updates.append((variant, field.name))

        if not partition_updates and not variant_updates:
            self.stdout.write(self.style.SUCCESS('No missing audio references found.'))
            return

        self.stdout.write(
            f'Found {len(partition_updates)} partition audio reference(s) and '
            f'{len(variant_updates)} tempo variant reference(s) missing from storage.'
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('\n[DRY RUN] Would clean up:'))
            for partition, field_name, file_name in partition_updates:
                self.stdout.write(
                    f'- partition={partition.id} field={field_name} file={file_name}'
                )
            for variant, file_name in variant_updates:
                self.stdout.write(
                    f'- tempo_variant={variant.id} partition={variant.partition_id} '
                    f'voice={variant.voice_type} tempo={variant.tempo} file={file_name}'
                )
            return

        cleared_partition_fields = 0
        cleared_variant_fields = 0

        with transaction.atomic():
            for partition, field_name, file_name in partition_updates:
                setattr(partition, field_name, None)
                update_fields = [field_name]
                if partition.mp3_synthetiques and not self._partition_has_audio(partition):
                    partition.mp3_synthetiques = False
                    update_fields.append('mp3_synthetiques')
                partition.save(update_fields=update_fields)
                cleared_partition_fields += 1
                logger.info(
                    "Cleared missing audio reference partition=%s field=%s file=%s",
                    partition.id,
                    field_name,
                    file_name,
                )

            for variant, file_name in variant_updates:
                variant.audio_file = None
                variant.status = PartitionAudioTempoVariant.Status.PENDING
                variant.last_error = 'Missing file in storage; cleared by cleanup.'
                variant.save(update_fields=['audio_file', 'status', 'last_error', 'updated_at'])
                cleared_variant_fields += 1
                logger.info(
                    "Cleared missing tempo variant audio reference variant=%s file=%s",
                    variant.id,
                    file_name,
                )

        self.stdout.write(self.style.SUCCESS(
            f'Cleared {cleared_partition_fields} partition audio reference(s) '
            f'and {cleared_variant_fields} tempo variant reference(s).'
        ))

    def _storage_exists(self, field):
        try:
            return bool(field.name and field.storage.exists(field.name))
        except Exception:
            logger.warning(
                "Unable to verify storage presence for %s",
                field.name,
                exc_info=True,
            )
            return True

    def _partition_has_audio(self, partition):
        return any(getattr(partition, field_name) for field_name in PARTITION_AUDIO_FIELDS)
