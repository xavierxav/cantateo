# Migration to switch from SearchVector to pg_trgm + unaccent
# This simplifies the search implementation while adding typo tolerance

from django.db import migrations
from django.contrib.postgres.operations import TrigramExtension


class Migration(migrations.Migration):

    dependencies = [
        ('psaumes', '0012_install_unaccent_extension'),
    ]

    operations = [
        # 1. Install pg_trgm extension
        TrigramExtension(),

        # 2. Remove the old GIN index on search_vector
        migrations.RemoveIndex(
            model_name='chant',
            name='chant_search_idx',
        ),

        # 3. Remove the search_vector field
        migrations.RemoveField(
            model_name='chant',
            name='search_vector',
        ),

        # 4. Create an IMMUTABLE wrapper for unaccent (required for indexes)
        # PostgreSQL's built-in unaccent is STABLE, not IMMUTABLE
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION immutable_unaccent(text)
            RETURNS text AS $$
            SELECT unaccent('unaccent', $1)
            $$ LANGUAGE SQL IMMUTABLE PARALLEL SAFE;
            """,
            reverse_sql="DROP FUNCTION IF EXISTS immutable_unaccent(text);",
        ),

        # 5. Create trigram GIN indexes for fast similarity search
        migrations.RunSQL(
            sql=[
                # Index on refrain (most important for search)
                "CREATE INDEX chant_refrain_trgm_idx ON psaumes_chant USING gin (LOWER(immutable_unaccent(COALESCE(refrain, ''))) gin_trgm_ops);",
                # Index on titre
                "CREATE INDEX chant_titre_trgm_idx ON psaumes_chant USING gin (LOWER(immutable_unaccent(COALESCE(titre, ''))) gin_trgm_ops);",
            ],
            reverse_sql=[
                "DROP INDEX IF EXISTS chant_refrain_trgm_idx;",
                "DROP INDEX IF EXISTS chant_titre_trgm_idx;",
            ],
        ),
    ]
