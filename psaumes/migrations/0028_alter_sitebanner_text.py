from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('psaumes', '0027_partitionaudiotempovariant'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sitebanner',
            name='text',
            field=models.TextField(
                help_text=(
                    'Markdown sécurisé autorisé : **gras**, *italique*, liens [texte](/url), '
                    'et icônes :info:, :warning:, :music:, :calendar:, :check:. '
                    'Le HTML dangereux est supprimé.'
                ),
                verbose_name='Texte de la bannière',
            ),
        ),
    ]
