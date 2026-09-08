"""Seed Séquence MomentLiturgique rows for Saint-Sacrement and Sainte Trinité."""
from django.db import migrations


def _nom_complet_recherche(nom_fete, annee):
    if annee:
        return f"{nom_fete} de l'année {annee}"
    return nom_fete


def create_sequences(apps, schema_editor):
    MomentLiturgique = apps.get_model('psaumes', 'MomentLiturgique')
    Psaume = apps.get_model('psaumes', 'Psaume')

    sequence_psaume = Psaume.objects.filter(slug='le-voici-le-pain-des-anges').first()

    rows = [
        ('Séquence Saint-Sacrement', 'A', sequence_psaume),
        ('Séquence Saint-Sacrement', 'B', sequence_psaume),
        ('Séquence Saint-Sacrement', 'C', sequence_psaume),
        ('Séquence Sainte Trinité', 'A', None),
        ('Séquence Sainte Trinité', 'B', None),
        ('Séquence Sainte Trinité', 'C', None),
    ]

    for nom_fete, annee, psaume in rows:
        obj, created = MomentLiturgique.objects.get_or_create(
            nom_fete=nom_fete,
            annee=annee,
            defaults={
                'psaume': psaume,
                'nom_complet_recherche': _nom_complet_recherche(nom_fete, annee),
            },
        )
        if not created and not obj.nom_complet_recherche:
            obj.nom_complet_recherche = _nom_complet_recherche(nom_fete, annee)
            obj.save()


def remove_sequences(apps, schema_editor):
    MomentLiturgique = apps.get_model('psaumes', 'MomentLiturgique')
    MomentLiturgique.objects.filter(
        nom_fete__in=['Séquence Saint-Sacrement', 'Séquence Sainte Trinité']
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('psaumes', '0033_audio_channels_cache'),
    ]
    operations = [
        migrations.RunPython(create_sequences, remove_sequences),
    ]
