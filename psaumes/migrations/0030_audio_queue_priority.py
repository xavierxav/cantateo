from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('psaumes', '0029_simplified_editor_and_single_active_banner'),
    ]

    operations = [
        migrations.AddField(
            model_name='partitionaudiogenerationjob',
            name='queue_priority',
            field=models.CharField(
                choices=[
                    ('user', 'Utilisateur'),
                    ('bulk', 'Basse priorité'),
                ],
                db_index=True,
                default='user',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='partitionaudiotempovariant',
            name='queue_priority',
            field=models.CharField(
                choices=[
                    ('user', 'Utilisateur'),
                    ('bulk', 'Basse priorité'),
                ],
                db_index=True,
                default='user',
                max_length=10,
            ),
        ),
    ]
