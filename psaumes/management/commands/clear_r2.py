"""
Command to delete all media files from Cloudflare R2.

Usage:
    python manage.py clear_r2 --dry-run  # Preview without deleting
    python manage.py clear_r2             # Delete all files
"""
import os
from django.core.management.base import BaseCommand
import boto3
from botocore.exceptions import ClientError


class Command(BaseCommand):
    help = 'Delete all media files from Cloudflare R2'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview files that would be deleted without actually deleting',
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

        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No files will be deleted\n'))
        else:
            self.stdout.write(self.style.WARNING('⚠️  WARNING: This will delete ALL files in R2 bucket!\n'))

        # List all objects in the bucket
        try:
            paginator = s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket_name)
            
            objects_to_delete = []
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects_to_delete.append({'Key': obj['Key']})

            if not objects_to_delete:
                self.stdout.write(self.style.WARNING('⚠️  No files found in R2 bucket'))
                return

            self.stdout.write(f'📁 Found {len(objects_to_delete)} files in R2 bucket\n')

            if dry_run:
                for obj in objects_to_delete:
                    self.stdout.write(f'🗑️  Would delete: {obj["Key"]}')
            else:
                # Delete objects in batches of 1000 (S3 limit)
                deleted = 0
                errors = 0
                
                for i in range(0, len(objects_to_delete), 1000):
                    batch = objects_to_delete[i:i+1000]
                    try:
                        response = s3_client.delete_objects(
                            Bucket=bucket_name,
                            Delete={
                                'Objects': batch,
                                'Quiet': False
                            }
                        )
                        
                        if 'Deleted' in response:
                            deleted += len(response['Deleted'])
                            # Only show first 10 deletions to avoid spam
                            for obj in response['Deleted'][:10]:
                                self.stdout.write(
                                    self.style.SUCCESS(f'✅ Deleted: {obj["Key"]}')
                                )
                            if len(response['Deleted']) > 10:
                                self.stdout.write(
                                    f'... and {len(response["Deleted"]) - 10} more files'
                                )
                        
                        if 'Errors' in response:
                            for error in response['Errors']:
                                self.stdout.write(
                                    self.style.ERROR(
                                        f'❌ Error deleting {error["Key"]}: {error["Message"]}'
                                    )
                                )
                                errors += 1
                        
                        # If no Deleted or Errors in response, assume all were deleted
                        if 'Deleted' not in response and 'Errors' not in response:
                            deleted += len(batch)
                            self.stdout.write(
                                self.style.SUCCESS(f'✅ Deleted batch of {len(batch)} files')
                            )
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'❌ Error deleting batch: {str(e)}')
                        )
                        errors += 1

                # Summary
                self.stdout.write('\n' + '='*50)
                self.stdout.write(self.style.SUCCESS('DELETE SUMMARY:'))
                self.stdout.write(f'  ✅ Deleted: {deleted}')
                if errors > 0:
                    self.stdout.write(self.style.ERROR(f'  ❌ Errors: {errors}'))

        except ClientError as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error accessing R2 bucket: {str(e)}')
            )

