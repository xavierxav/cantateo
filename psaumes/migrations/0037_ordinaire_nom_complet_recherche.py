# Add nom_complet_recherche to Ordinaire for trigram search + GIN index + backfill.

from django.db import migrations, models


PARTIE_MESSE_LABELS = {
    'KYRIE': 'Kyrie',
    'GLORIA': 'Gloria',
    'SANCTUS': 'Sanctus',
    'AGNUS_DEI': 'Agnus Dei',
    'ALLELUIA': 'Alléluia',
    'ANAMNESE': 'Anamnèse',
    'PRIERE_UNIVERSELLE': 'Prière Universelle',
}


def backfill_ordinaire_search(apps, schema_editor):
    Ordinaire = apps.get_model("psaumes", "Ordinaire")

    for o in Ordinaire.objects.all().iterator():
        parts = []
        if o.titre:
            parts.append(str(o.titre))
        if o.compositeur_id and o.compositeur and o.compositeur.nom:
            parts.append(str(o.compositeur.nom))
        for p in o.partitions_messe.only('titre', 'partie_messe', 'refrain', 'versets'):
            label = PARTIE_MESSE_LABELS.get(p.partie_messe)
            if label:
                parts.append(label)
            if p.titre:
                parts.append(str(p.titre))
            if p.refrain:
                parts.append(str(p.refrain))
            if p.versets:
                parts.append(str(p.versets))
        o.nom_complet_recherche = " - ".join(parts)
        o.save(update_fields=["nom_complet_recherche"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("psaumes", "0036_alter_partition_partie_messe"),
    ]

    operations = [
        migrations.AddField(
            model_name="ordinaire",
            name="nom_complet_recherche",
            field=models.TextField(
                blank=True,
                db_index=True,
                help_text="Auto-généré pour recherche trigram (Titre + Compositeur + Partitions)",
            ),
        ),
        migrations.RunPython(backfill_ordinaire_search, noop),
        migrations.RunSQL(
            sql=[
                """
                CREATE INDEX IF NOT EXISTS ordinaire_nom_complet_recherche_trgm_idx
                ON psaumes_ordinaire
                USING gin (LOWER(immutable_unaccent(COALESCE(nom_complet_recherche, ''))) gin_trgm_ops);
                """,
            ],
            reverse_sql=[
                "DROP INDEX IF EXISTS ordinaire_nom_complet_recherche_trgm_idx;",
            ],
        ),
    ]
