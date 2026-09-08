import unicodedata

from django.db.models import F, Func, Value, TextField, QuerySet
from django.db.models.functions import Coalesce, Lower
from django.contrib.postgres.search import TrigramWordSimilarity

MAX_AUTOCOMPLETE_QUERY_LENGTH = 80


def normalize_search_query(query: str) -> str:
    """Normalize a search query for accent-insensitive trigram matching."""
    if query is None:
        return ""

    normalized = " ".join(str(query).split()).strip().lower()
    if not normalized:
        return ""

    decomposed = unicodedata.normalize("NFKD", normalized)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalized_trigram_expression(field_name: str):
    """Return the DB expression used by the trigram index/search."""
    return Lower(
        Func(
            Coalesce(F(field_name), Value("")),
            function="immutable_unaccent",
            output_field=TextField(),
        )
    )


def annotate_trigram_similarity(
    queryset: QuerySet,
    query: str,
    field_name: str = "nom_complet_recherche",
    similarity_alias: str = "similarity",
) -> QuerySet:
    """Annotate a queryset with trigram similarity on a normalized field."""
    normalized_query = normalize_search_query(query)
    if not normalized_query:
        return queryset.none()

    expression = normalized_trigram_expression(field_name)
    return queryset.annotate(
        **{
            similarity_alias: TrigramWordSimilarity(
                normalized_query,
                expression,
            )
        }
    )
