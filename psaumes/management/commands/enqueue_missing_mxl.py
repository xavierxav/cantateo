from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from psaumes.models import Partition
from psaumes.tasks import (
    OMR_QUEUE_PRIORITY_BULK,
    OMR_QUEUE_PRIORITY_USER,
    enqueue_partition_omr_generation,
    reset_partition_omr_generation,
)


class Command(BaseCommand):
    help = 'Enqueue OMR jobs for partitions with a PDF but no MXL and no existing MP3.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument(
            '--priority',
            choices=[OMR_QUEUE_PRIORITY_USER, OMR_QUEUE_PRIORITY_BULK],
            default=OMR_QUEUE_PRIORITY_BULK,
        )
        parser.add_argument('--retry-failed', action='store_true')
        parser.add_argument('--max-pages', type=int)

    def handle(self, *args, **options):
        limit = options['limit']
        if limit < 1:
            raise CommandError('--limit must be at least 1.')

        if options['max_pages'] is not None:
            from django.conf import settings

            settings.OMR_MAX_PAGES = options['max_pages']

        queryset = self._candidates(options['retry_failed'])[:limit]
        queued = 0
        for partition in queryset:
            self.stdout.write(
                f"{'[dry-run] ' if options['dry_run'] else ''}omr partition={partition.id} "
                f"pdf={partition.partition_pdf.name}"
            )
            if options['dry_run']:
                continue

            if options['retry_failed']:
                job = reset_partition_omr_generation(partition)
            else:
                job = enqueue_partition_omr_generation(partition, priority=options['priority'])
            if job:
                queued += 1

        suffix = 'would be queued' if options['dry_run'] else 'queued'
        self.stdout.write(self.style.SUCCESS(f'{queued if not options["dry_run"] else len(queryset)} OMR job(s) {suffix}.'))

    def _candidates(self, retry_failed):
        queryset = (
            Partition.objects
            .filter(partition_pdf__isnull=False)
            .exclude(partition_pdf='')
            .filter(Q(partition_mxl='') | Q(partition_mxl__isnull=True))
            .order_by('id')
        )
        for field_name in (
            'audio_soprano',
            'audio_alto',
            'audio_tenor',
            'audio_basse',
            'audio_instrumental',
            'audio_mix',
        ):
            queryset = queryset.filter(Q(**{field_name: ''}) | Q(**{f'{field_name}__isnull': True}))

        if retry_failed:
            return queryset.filter(omr_job__status='failed')
        return queryset.exclude(omr_job__status__in=['queued', 'started'])
