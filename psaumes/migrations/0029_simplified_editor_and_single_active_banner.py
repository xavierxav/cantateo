from django.db import migrations, models


def keep_only_latest_active_banner(apps, schema_editor):
    SiteBanner = apps.get_model('psaumes', 'SiteBanner')
    active_ids = list(
        SiteBanner.objects.filter(active=True)
        .order_by('-updated_at', '-id')
        .values_list('id', flat=True)
    )
    if len(active_ids) <= 1:
        return
    SiteBanner.objects.filter(id__in=active_ids[1:]).update(active=False)


class Migration(migrations.Migration):

    dependencies = [
        ('psaumes', '0028_alter_sitebanner_text'),
    ]

    operations = [
        migrations.RunPython(keep_only_latest_active_banner, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name='psaume',
            options={
                'ordering': ['nom_psaume'],
                'permissions': [
                    ('use_simplified_editor', 'Peut utiliser la saisie simplifiée Cantateo'),
                ],
                'verbose_name': 'Psaume/Cantique',
                'verbose_name_plural': 'Psaumes et Cantiques',
            },
        ),
        migrations.AddConstraint(
            model_name='sitebanner',
            constraint=models.UniqueConstraint(
                condition=models.Q(('active', True)),
                fields=('active',),
                name='unique_active_site_banner',
            ),
        ),
    ]
