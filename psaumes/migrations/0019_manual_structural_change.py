# Generated manually for robust structural change
import django.db.models.deletion
import psaumes.models.utils
from django.db import migrations, models

# Global buffer to keep data in memory during structural change
_migration_data_buffer = {}

def backup_data(apps, schema_editor):
    """Saves data from old structure to memory."""
    # Use apps.get_model to avoid importing models directly
    try:
        Chant = apps.get_model('psaumes', 'Chant')
        Psaume = apps.get_model('psaumes', 'Psaume')
        Cantique = apps.get_model('psaumes', 'Cantique')
        MomentLiturgique = apps.get_model('psaumes', 'MomentLiturgique')
        FichierAudio = apps.get_model('psaumes', 'FichierAudio')
    except LookupError:
        # Models might already be deleted if migration is re-run or partially failed
        return

    # Backup Psaumes (which inherit from Chant)
    ps_data = []
    for p in Psaume.objects.all():
        ps_data.append({
            'id': p.id,
            'numero': p.numero,
            'titre': p.titre,
            'compositeur_id': p.compositeur_id,
            'refrain': p.refrain,
            'versets': p.versets,
            'partition_pdf': p.partition_pdf.name if p.partition_pdf else None,
            'partition_mxl': p.partition_mxl.name if p.partition_mxl else None,
            'slug': p.slug,
        })
    _migration_data_buffer['psaumes'] = ps_data

    # Backup Cantiques
    cant_data = []
    for c in Cantique.objects.all():
        cant_data.append({
            'id': c.id,
            'reference_biblique': c.reference_biblique,
            'titre': c.titre,
            'compositeur_id': c.compositeur_id,
            'refrain': c.refrain,
            'versets': c.versets,
            'partition_pdf': c.partition_pdf.name if c.partition_pdf else None,
            'partition_mxl': c.partition_mxl.name if c.partition_mxl else None,
            'slug': c.slug,
        })
    _migration_data_buffer['cantiques'] = cant_data

    # Backup Relations
    _migration_data_buffer['moments'] = list(MomentLiturgique.objects.values())
    _migration_data_buffer['audios'] = list(FichierAudio.objects.values())

def restore_data(apps, schema_editor):
    """Restores data to new structure from memory."""
    if not _migration_data_buffer:
        return

    Psaume = apps.get_model('psaumes', 'Psaume')
    Partition = apps.get_model('psaumes', 'Partition')
    MomentLiturgique = apps.get_model('psaumes', 'MomentLiturgique')
    FichierAudio = apps.get_model('psaumes', 'FichierAudio')

    # Mapping to keep track of old IDs
    old_to_new_psaume = {}
    old_to_new_partition = {}

    # 1. Create Psaumes and Partitions from old Psaumes
    for data in _migration_data_buffer.get('psaumes', []):
        p = Psaume.objects.create(
            psaume_or_cantique='psaume',
            numero=data['numero'],
            titre=data['titre'],
            slug=data['slug'],
            nom_psaume=f"Psaume {data['numero']}" if data['numero'] else f"Psaume (ID {data['id']})"
        )
        old_to_new_psaume[data['id']] = p
        
        part = Partition.objects.create(
            psaume=p,
            titre=data['titre'],
            refrain=data['refrain'],
            versets=data['versets'],
            partition_pdf=data['partition_pdf'],
            partition_mxl=data['partition_mxl'],
            compositeur_id=data['compositeur_id'],
            slug=data['slug']
        )
        old_to_new_partition[data['id']] = part

    # 2. Create Psaumes and Partitions from old Cantiques
    for data in _migration_data_buffer.get('cantiques', []):
        p = Psaume.objects.create(
            psaume_or_cantique='cantique',
            reference_biblique=data['reference_biblique'],
            titre=data['titre'],
            slug=data['slug'],
            nom_psaume=f"Cantique {data['reference_biblique']}" or f"Cantique (ID {data['id']})"
        )
        old_to_new_psaume[data['id']] = p

        part = Partition.objects.create(
            psaume=p,
            titre=data['titre'],
            refrain=data['refrain'],
            versets=data['versets'],
            partition_pdf=data['partition_pdf'],
            partition_mxl=data['partition_mxl'],
            compositeur_id=data['compositeur_id'],
            slug=data['slug']
        )
        old_to_new_partition[data['id']] = part

    # 3. Update MomentLiturgique (already exist in DB but chant_id column dropped)
    # Re-link via psaume field
    for m_data in _migration_data_buffer.get('moments', []):
        old_chant_id = m_data.get('chant_id')
        if old_chant_id in old_to_new_psaume:
            MomentLiturgique.objects.filter(id=m_data['id']).update(
                psaume=old_to_new_psaume[old_chant_id]
            )

    # 4. Update FichierAudio
    for a_data in _migration_data_buffer.get('audios', []):
        old_chant_id = a_data.get('chant_id')
        if old_chant_id in old_to_new_partition:
            FichierAudio.objects.filter(id=a_data['id']).update(
                partition=old_to_new_partition[old_chant_id]
            )


class Migration(migrations.Migration):

    dependencies = [
        ('psaumes', '0018_sitebanner_end_date_sitebanner_start_date'),
    ]

    operations = [
        migrations.RunPython(backup_data, reverse_code=migrations.RunPython.noop),

        # 1. Clear database structure manually using CASCADE to avoid constraint issues
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL("ALTER TABLE psaumes_momentliturgique DROP COLUMN IF EXISTS chant_id CASCADE"),
                migrations.RunSQL("ALTER TABLE psaumes_fichieraudio DROP COLUMN IF EXISTS chant_id CASCADE"),
                migrations.RunSQL("DROP TABLE IF EXISTS psaumes_cantique CASCADE"),
                migrations.RunSQL("DROP TABLE IF EXISTS psaumes_psaume CASCADE"),
                migrations.RunSQL("DROP TABLE IF EXISTS psaumes_chant CASCADE"),
            ],
            state_operations=[
                migrations.AlterUniqueTogether(
                    name='fichieraudio',
                    unique_together=set(),
                ),
                migrations.RemoveField(
                    model_name='momentliturgique',
                    name='chant',
                ),
                migrations.RemoveField(
                    model_name='fichieraudio',
                    name='chant',
                ),
                migrations.DeleteModel(
                    name='Cantique',
                ),
                migrations.DeleteModel(
                    name='Psaume',
                ),
                migrations.DeleteModel(
                    name='Chant',
                ),
            ],
        ),

        # 2. Re-create new standalone models in the state and database
        migrations.CreateModel(
            name='Psaume',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('psaume_or_cantique', models.CharField(choices=[('psaume', 'Psaume'), ('cantique', 'Cantique')], default='psaume', max_length=10)),
                ('nom_psaume', models.CharField(blank=True, db_index=True, help_text="Ex: 'Psaume 23' ou 'Cantique AT 41'", max_length=250, null=True)),
                ('numero', models.IntegerField(blank=True, db_index=True, null=True)),
                ('reference_biblique', models.CharField(blank=True, db_index=True, help_text='Référence biblique (ex: Is 12,1-6, Ap 19,1-8)', max_length=200, null=True)),
                ('titre', models.CharField(blank=True, max_length=200)),
                ('slug', models.SlugField(blank=True, max_length=250)),
                ('nom_complet_recherche', models.TextField(blank=True, db_index=True, help_text='Auto-généré pour recherche trigram (Titre + Refrain)')),
            ],
            options={
                'verbose_name': 'Psaume/Cantique',
                'verbose_name_plural': 'Psaumes et Cantiques',
                'ordering': ['nom_psaume'],
            },
        ),
        migrations.CreateModel(
            name='Partition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titre', models.CharField(blank=True, max_length=200)),
                ('refrain', models.TextField(blank=True, help_text="Refrain chanté par l'assemblée")),
                ('versets', models.TextField(blank=True)),
                ('partition_pdf', models.FileField(blank=True, null=True, upload_to=psaumes.models.utils.partition_pdf_path, verbose_name='Partition PDF')),
                ('partition_mxl', models.FileField(blank=True, null=True, upload_to=psaumes.models.utils.partition_mxl_path, verbose_name='Partition MXL')),
                ('slug', models.SlugField(blank=True, max_length=250)),
                ('compositeur', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='partitions', to='psaumes.compositeur')),
                ('psaume', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='partitions', to='psaumes.psaume')),
            ],
            options={
                'verbose_name': 'Partition',
                'verbose_name_plural': 'Partitions',
                'ordering': ['titre'],
            },
        ),

        # 3. Add new FKs
        migrations.AddField(
            model_name='momentliturgique',
            name='psaume',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='moments_liturgiques', to='psaumes.psaume'),
        ),
        migrations.AddField(
            model_name='fichieraudio',
            name='partition',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='audios', to='psaumes.partition'),
        ),
        migrations.AlterUniqueTogether(
            name='fichieraudio',
            unique_together={('partition', 'type_voix')},
        ),
        migrations.RunPython(restore_data, reverse_code=migrations.RunPython.noop),
    ]
