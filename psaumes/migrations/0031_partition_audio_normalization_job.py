from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('psaumes', '0030_audio_queue_priority'),
    ]

    operations = [
        migrations.CreateModel(
            name='PartitionAudioNormalizationJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('target_type', models.CharField(choices=[('partition', 'Partition'), ('tempo_variant', 'Variante tempo')], db_index=True, max_length=20)),
                ('field_name', models.CharField(max_length=40)),
                ('source_name', models.CharField(blank=True, default='', max_length=500)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('queued', 'Queued'), ('started', 'Started'), ('succeeded', 'Succeeded'), ('failed', 'Failed')], db_index=True, default='pending', max_length=20)),
                ('queue_priority', models.CharField(choices=[('user', 'Utilisateur'), ('bulk', 'Basse priorité')], db_index=True, default='user', max_length=10)),
                ('task_id', models.CharField(blank=True, default='', max_length=255)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('last_error', models.TextField(blank=True, default='')),
                ('queued_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('partition', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='audio_normalization_jobs', to='psaumes.partition')),
                ('tempo_variant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='audio_normalization_jobs', to='psaumes.partitionaudiotempovariant')),
            ],
            options={
                'verbose_name': 'Job de normalisation audio',
                'verbose_name_plural': 'Jobs de normalisation audio',
                'ordering': ['-queued_at', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='partitionaudionormalizationjob',
            constraint=models.UniqueConstraint(condition=Q(('partition__isnull', False)), fields=('partition', 'field_name'), name='unique_partition_audio_normalization_job'),
        ),
        migrations.AddConstraint(
            model_name='partitionaudionormalizationjob',
            constraint=models.UniqueConstraint(condition=Q(('tempo_variant__isnull', False)), fields=('tempo_variant',), name='unique_tempo_variant_audio_normalization_job'),
        ),
    ]
