import re
from django.core.cache import cache
from django.template.loader import render_to_string
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from ..models import Psaume, Partition, MomentLiturgique, Ordinaire
from ..rate_limit import is_rate_limited
from ..services.search import (
    MAX_AUTOCOMPLETE_QUERY_LENGTH,
    annotate_trigram_similarity,
    normalize_search_query,
)
from ..tasks import build_partition_audio_status
from ..tasks import enqueue_partition_tempo_variant_generation, enqueue_partition_tempo_variant_normalizations
from ..services.audio.tempo_variants import (
    build_partition_tempo_variant_status,
    parse_apple_tempo,
)

@require_GET
def audio_status(request, partition_id):
    """API endpoint to check audio generation status for a partition."""
    if is_rate_limited(request, 'audio_status'):
        return JsonResponse({'error': 'Trop de requêtes'}, status=429)

    try:
        partition = Partition.objects.get(id=partition_id)
    except Partition.DoesNotExist:
        return JsonResponse({'error': 'Partition non trouvée'}, status=404)

    return JsonResponse(build_partition_audio_status(partition))


@require_GET
def audio_variants(request, partition_id):
    """API endpoint returning Apple/Safari tempo-variant audio URLs."""
    if is_rate_limited(request, 'audio_variants'):
        return JsonResponse({'error': 'Trop de requêtes'}, status=429)

    try:
        tempo = parse_apple_tempo(request.GET.get('tempo', '1.0'))
    except ValueError:
        return JsonResponse({'error': 'Tempo non supporté'}, status=400)

    try:
        partition = Partition.objects.get(id=partition_id)
    except Partition.DoesNotExist:
        return JsonResponse({'error': 'Partition non trouvée'}, status=404)

    payload = build_partition_tempo_variant_status(partition, tempo)
    if payload['status'] == 'generating':
        payload = enqueue_partition_tempo_variant_generation(partition, tempo)
    elif payload['status'] == 'ready':
        enqueue_partition_tempo_variant_normalizations(partition, tempo)

    return JsonResponse(payload)

@require_GET
def search_autocomplete(request):
    """HTMX autocomplete endpoint returning HTML partial.

    Recherche Psaumes/MomentLiturgiques par trigram sur nom_complet_recherche.
    """
    if is_rate_limited(request, 'search_autocomplete'):
        return HttpResponse('', status=429)

    query = normalize_search_query(request.GET.get('q', ''))
    if len(query) < 2 or len(query) > MAX_AUTOCOMPLETE_QUERY_LENGTH:
        return HttpResponse('')

    cache_key = f"search-autocomplete:v3:{query}"
    cached = cache.get(cache_key)
    if cached is not None:
        return HttpResponse(cached)

    results = []

    # 1. Psaumes
    psaumes = annotate_trigram_similarity(Psaume.objects.all(), query).filter(
        similarity__gt=0.1
    ).prefetch_related('moments_liturgiques').order_by('-similarity')[:10]

    for p in psaumes:
        moment = p.moments_liturgiques.first()
        results.append({
            'similarity': p.similarity,
            'type': 'psaume',
            'title': p.nom_complet,
            'subtitle': moment.nom_complet if moment else None,
            'url': p.get_absolute_url(),
        })

    # 2. MomentLiturgique
    moments = annotate_trigram_similarity(
        MomentLiturgique.objects.filter(psaume__isnull=False),
        query,
    ).filter(similarity__gt=0.1).select_related('psaume').order_by('-similarity')[:10]

    for m in moments:
        results.append({
            'similarity': m.similarity,
            'type': 'moment',
            'title': m.nom_complet,
            'subtitle': str(m.psaume),
            'url': m.psaume.get_absolute_url(),
        })

    # 3. Ordinaires de messe (recherche trigram sur nom_complet_recherche).
    ordinaires = annotate_trigram_similarity(
        Ordinaire.objects.all(), query
    ).filter(similarity__gt=0.1).select_related('compositeur').order_by('-similarity')[:5]
    for o in ordinaires:
        results.append({
            'similarity': o.similarity,
            'type': 'ordinaire',
            'title': o.titre,
            'subtitle': (o.compositeur.nom if o.compositeur else None) or 'Ordinaire de messe',
            'url': o.get_absolute_url(),
        })

    # Sort all results by similarity
    results.sort(key=lambda x: x['similarity'], reverse=True)

    # Deduced deduplication (unique by URL)
    seen_urls = set()
    unique_results = []
    for r in results:
        if r['url'] not in seen_urls:
            unique_results.append(r)
            seen_urls.add(r['url'])

    html = render_to_string('_autocomplete_results.html', {
        'results': unique_results[:10],
        'query': query,
    })
    cache.set(cache_key, html, 60)
    return HttpResponse(html)
