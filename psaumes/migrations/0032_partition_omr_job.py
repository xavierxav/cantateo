import django.db.models.deletion
import psaumes.models.utils
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('psaumes', '0031_partition_audio_normalization_job'),
    ]

    operations = [
        migrations.CreateModel(
            name='PartitionOmrJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_type', models.CharField(choices=[('partition_pdf', 'Partition PDF'), ('uploaded_image', 'Image importée')], db_index=True, default='partition_pdf', max_length=20)),
                ('source_file', models.FileField(blank=True, null=True, upload_to=psaumes.models.utils.partition_omr_source_path, verbose_name='Source OMR')),
                ('source_name', models.CharField(blank=True, default='', max_length=500)),
                ('source_sha256', models.CharField(blank=True, default='', max_length=64)),
                ('backend', models.CharField(blank=True, default='', max_length=80)),
                ('backend_version', models.CharField(blank=True, default='', max_length=120)),
                ('model_profile', models.CharField(blank=True, default='', max_length=120)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('queued', 'Queued'), ('started', 'Started'), ('succeeded', 'Succeeded'), ('failed', 'Failed')], db_index=True, default='pending', max_length=20)),
                ('queue_priority', models.CharField(choices=[('user', 'Utilisateur'), ('bulk', 'Basse priorité')], db_index=True, default='user', max_length=10)),
                ('task_id', models.CharField(blank=True, default='', max_length=255)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('page_count', models.PositiveSmallIntegerField(default=0)),
                ('processed_pages', models.PositiveSmallIntegerField(default=0)),
                ('generated_file_name', models.CharField(blank=True, default='', max_length=500)),
                ('last_error', models.TextField(blank=True, default='')),
                ('queued_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('partition', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='omr_job', to='psaumes.partition')),
            ],
            options={
                'verbose_name': 'Job de reconnaissance OMR',
                'verbose_name_plural': 'Jobs de reconnaissance OMR',
                'ordering': ['-queued_at', '-id'],
            },
        ),
    ]
