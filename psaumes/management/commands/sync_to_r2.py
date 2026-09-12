"""
Command to sync local media files to Cloudflare R2.

Usage:
    python manage.py sync_to_r2
    python manage.py sync_to_r2 --dry-run  # Preview without uploading
"""
import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
import boto3
from botocore.exceptions import ClientError


class Command(BaseCommand):
    help = 'Sync local media files to Cloudflare R2'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview files that would be uploaded without actually uploading',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Upload files even if they already exist in R2',
        )

    def handle(self, *args, **options):
        # Check R2 configuration
        bucket_name = os.environ.get('CLOUDFLARE_R2_BUCKET_NAME')
        access_key = os.environ.get('CLOUDFLARE_R2_ACCESS_KEY_ID')
        secret_key = os.environ.get('CLOUDFLARE_R2_SECRET_ACCESS_KEY')
        endpoint_url = os.environ.get('CLOUDFLARE_R2_ENDPOINT_URL')

        if not all([bucket_name, access_key, secret_key, endpoint_url]):
            self.stdout.write(
                self.style.ERROR(
                    '❌ Cloudflare R2 configuration missing in .env\n'
                    'Required: CLOUDFLARE_R2_BUCKET_NAME, CLOUDFLARE_R2_ACCESS_KEY_ID, '
                    'CLOUDFLARE_R2_SECRET_ACCESS_KEY, CLOUDFLARE_R2_ENDPOINT_URL'
                )
            )
            return

        # Initialize S3 client for R2
        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name='auto'
        )

        # Get media root
        media_root = Path(settings.MEDIA_ROOT)
        if not media_root.exists():
            self.stdout.write(
                self.style.WARNING(f'⚠️ Media directory not found: {media_root}')
            )
            return

        dry_run = options['dry_run']
        force = options['force']

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No files will be uploaded\n'))

        # Find all files in media directory
        files_to_sync = []
        for file_path in media_root.rglob('*'):
            if file_path.is_file():
                # Get relative path from media_root and convert to forward slashes for R2
                relative_path = file_path.relative_to(media_root)
                r2_key = str(relative_path).replace('\\', '/')  # R2 uses forward slashes
                files_to_sync.append((file_path, r2_key))

        if not files_to_sync:
            self.stdout.write(self.style.WARNING('⚠️ No files found in media directory'))
            return

        self.stdout.write(f'📁 Found {len(files_to_sync)} files to sync\n')

        uploaded = 0
        skipped = 0
        errors = 0

        for local_path, r2_key in files_to_sync:
            try:
                # Check if file already exists in R2
                if not force:
                    try:
                        s3_client.head_object(Bucket=bucket_name, Key=r2_key)
                        if not dry_run:
                            self.stdout.write(f'⏭️  Skipped (exists): {r2_key}')
                        skipped += 1
                        continue
                    except ClientError as e:
                        if e.response['Error']['Code'] != '404':
                            raise

                if dry_run:
                    file_size = local_path.stat().st_size
                    self.stdout.write(f'📤 Would upload: {r2_key} ({file_size:,} bytes)')
                    uploaded += 1
                else:
                    # Upload file
                    with open(local_path, 'rb') as f:
                        s3_client.upload_fileobj(
                            f,
                            bucket_name,
                            r2_key,
                            ExtraArgs={'ContentType': self._get_content_type(local_path)}
                        )
                    file_size = local_path.stat().st_size
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Uploaded: {r2_key} ({file_size:,} bytes)')
                    )
                    uploaded += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error uploading {r2_key}: {str(e)}')
                )
                errors += 1

        # Summary
        self.stdout.write('\n' + '='*50)
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN SUMMARY:'))
        else:
            self.stdout.write(self.style.SUCCESS('SYNC SUMMARY:'))
        self.stdout.write(f'  ✅ Uploaded: {uploaded}')
        self.stdout.write(f'  ⏭️  Skipped: {skipped}')
        if errors > 0:
            self.stdout.write(self.style.ERROR(f'  ❌ Errors: {errors}'))

    def _get_content_type(self, file_path):
        """Get content type based on file extension."""
        ext = file_path.suffix.lower()
        content_types = {
            '.pdf': 'application/pdf',
            '.mxl': 'application/vnd.recordare.musicxml+xml',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.ogg': 'audio/ogg',
            '.m4a': 'audio/mp4',
        }
        return content_types.get(ext, 'application/octet-stream')

