from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('psaumes', '0009_fichieraudio_est_synthetique'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cantique',
            name='reference_biblique',
            field=models.CharField(
                max_length=200,
                db_index=True,
                help_text='Référence biblique (ex: Is 12,1-6, Ap 19,1-8)'
            ),
        ),
    ]
