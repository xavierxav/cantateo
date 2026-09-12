from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('psaumes', '0022_canonicalize_trinite_and_search_indexes'),
    ]

    operations = [
        migrations.CreateModel(
            name='PartitionAudioGenerationJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('queued', 'Queued'), ('started', 'Started'), ('succeeded', 'Succeeded'), ('failed', 'Failed')], db_index=True, default='pending', max_length=20)),
                ('task_id', models.CharField(blank=True, default='', max_length=255)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('generated_count', models.PositiveSmallIntegerField(default=0)),
                ('total_count', models.PositiveSmallIntegerField(default=0)),
                ('missing_voice_types', models.JSONField(blank=True, default=list)),
                ('last_error', models.TextField(blank=True, default='')),
                ('queued_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('partition', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='audio_generation_job', to='psaumes.partition')),
            ],
            options={
                'verbose_name': 'Job de génération audio',
                'verbose_name_plural': 'Jobs de génération audio',
                'ordering': ['-queued_at', '-id'],
            },
        ),
    ]
