# Canonicalize Sainte Trinité and add trigram indexes on consolidated search fields.

from django.db import migrations


def canonicalize_trinite(apps, schema_editor):
    MomentLiturgique = apps.get_model("psaumes", "MomentLiturgique")

    for moment in MomentLiturgique.objects.filter(nom_fete="Trinité").iterator():
        moment.nom_fete = "Sainte Trinité"
        moment.save(update_fields=["nom_fete", "nom_complet_recherche"])


def uncanonicalize_trinite(apps, schema_editor):
    MomentLiturgique = apps.get_model("psaumes", "MomentLiturgique")

    for moment in MomentLiturgique.objects.filter(nom_fete="Sainte Trinité").iterator():
        moment.nom_fete = "Trinité"
        moment.save(update_fields=["nom_fete", "nom_complet_recherche"])


class Migration(migrations.Migration):

    dependencies = [
        ("psaumes", "0021_remove_psaume_numero_and_more"),
    ]

    operations = [
        migrations.RunPython(canonicalize_trinite, uncanonicalize_trinite),
        migrations.RunSQL(
            sql=[
                """
                CREATE INDEX IF NOT EXISTS psaume_nom_complet_recherche_trgm_idx
                ON psaumes_psaume
                USING gin (LOWER(immutable_unaccent(COALESCE(nom_complet_recherche, ''))) gin_trgm_ops);
                """,
                """
                CREATE INDEX IF NOT EXISTS moment_nom_complet_recherche_trgm_idx
                ON psaumes_momentliturgique
                USING gin (LOWER(immutable_unaccent(COALESCE(nom_complet_recherche, ''))) gin_trgm_ops);
                """,
            ],
            reverse_sql=[
                "DROP INDEX IF EXISTS psaume_nom_complet_recherche_trgm_idx;",
                "DROP INDEX IF EXISTS moment_nom_complet_recherche_trgm_idx;",
            ],
        ),
    ]
