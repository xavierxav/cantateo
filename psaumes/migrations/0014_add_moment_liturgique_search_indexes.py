# Add trigram GIN indexes on MomentLiturgique for search
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('psaumes', '0013_switch_to_trigram_search'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "CREATE INDEX moment_temps_trgm_idx ON psaumes_momentliturgique USING gin (LOWER(immutable_unaccent(COALESCE(temps, ''))) gin_trgm_ops);",
                "CREATE INDEX moment_nom_fete_trgm_idx ON psaumes_momentliturgique USING gin (LOWER(immutable_unaccent(COALESCE(nom_fete, ''))) gin_trgm_ops);",
            ],
            reverse_sql=[
                "DROP INDEX IF EXISTS moment_temps_trgm_idx;",
                "DROP INDEX IF EXISTS moment_nom_fete_trgm_idx;",
            ],
        ),
    ]
