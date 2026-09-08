"""
Management command to clean up synthetic audio from database and storage.

This command removes references to synthetic audio files in Partition records
where mp3_synthetiques=True, along with their associated files in storage.

Use this after migrating to on-the-fly audio generation.
"""

from django.core.management.base import BaseCommand
from psaumes.models import Partition


class Command(BaseCommand):
    help = 'Remove all synthetic audio files from database and storage'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--no-files',
            action='store_true',
            help='Only delete file references, not the actual files',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        delete_files_from_storage = not options['no_files']

        # Find all partitions with synthetic audio
        partitions = Partition.objects.filter(mp3_synthetiques=True)
        count = partitions.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS('No synthetic audio files found.'))
            return

        self.stdout.write(f'Found {count} partitions with synthetic audio to clean up.')

        audio_fields = [
            'audio_soprano', 'audio_alto', 'audio_tenor', 
            'audio_basse', 'audio_instrumental', 'audio_mix'
        ]

        if dry_run:
            self.stdout.write(self.style.WARNING('\n[DRY RUN] Would clean up:'))
            for part in partitions:
                self.stdout.write(f"- {part}")
            return

        deleted_files_count = 0
        for part in partitions:
            for field_name in audio_fields:
                field = getattr(part, field_name)
                if field and field.name:
                    if delete_files_from_storage:
                        try:
                            field.delete(save=False)
                            deleted_files_count += 1
                        except Exception as e:
                            self.stderr.write(f"Error deleting file {field.name}: {e}")
                    else:
                        setattr(part, field_name, None)
            
            part.mp3_synthetiques = False
            part.save()

        self.stdout.write(self.style.SUCCESS(f'Successfully cleaned up {count} partitions.'))
        if delete_files_from_storage:
            self.stdout.write(f'Deleted {deleted_files_count} files from storage.')
        else:
            self.stdout.write('File references removed from database (files kept in storage).')
