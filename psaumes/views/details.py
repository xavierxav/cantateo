import logging
from django.shortcuts import render, get_object_or_404, redirect
from .utils import trigger_async_audio_generation
from ..models import Psaume

logger = logging.getLogger(__name__)

def psaume_detail(request, pk, slug):
    """Detail view for a single Psaume with canonical URL enforcement."""
    psaume = get_object_or_404(
        Psaume.objects.prefetch_related('moments_liturgiques', 'partitions', 'partitions__compositeur'),
        pk=pk
    )

    # 301 redirect if slug doesn't match (SEO canonical enforcement)
    expected_slug = psaume.slug or 'psaume'
    if slug != expected_slug:
        return redirect('psaume_detail', pk=pk, slug=expected_slug, permanent=True)

    # Current partition (first one by default, or from query param)
    partition_id = request.GET.get('partition')
    if partition_id:
        partition = psaume.partitions.filter(pk=partition_id).first()
    else:
        partition = psaume.partitions.first()

    if partition:
        # Trigger background audio generation if needed
        trigger_async_audio_generation(partition)
        # Check if any non-synthetic audio exists
        has_audio = any([
            partition.audio_soprano, partition.audio_alto, partition.audio_tenor, 
            partition.audio_basse, partition.audio_instrumental, partition.audio_mix
        ])
        has_non_synthetic_audio = has_audio and not partition.mp3_synthetiques
    else:
        has_non_synthetic_audio = False

    # Partitions du même Psaume (hors partition courante)
    # Utilise la prefetch_related déjà chargée pour éviter une requête supplémentaire
    memes_versets = []
    if partition:
        memes_versets = [p for p in psaume.partitions.all() if p.pk != partition.pk]

    # Psaumes de même nom_psaume (autres versets, autres dates)
    autres_versets_psaumes = []
    if psaume.nom_psaume:
        autres_versets_psaumes = list(
            Psaume.objects.filter(nom_psaume=psaume.nom_psaume).exclude(pk=psaume.pk).prefetch_related(
                'partitions__compositeur',
                'moments_liturgiques'
            )
        )

    structured_data = []
    if partition:
        composition = {
            '@context': 'https://schema.org',
            '@type': 'MusicComposition',
            'name': f"{psaume.nom_psaume or ''}{f' - {partition.titre}' if partition.titre else ''}".strip(),
            'description': partition.refrain or 'Chant liturgique',
            'inLanguage': 'fr-FR',
            'genre': 'Musique sacrée',
            'publisher': {
                '@type': 'Organization',
                'name': 'Cantateo',
            },
            'url': request.build_absolute_uri(psaume.get_absolute_url()),
            'hasPart': [],
        }
        if partition.compositeur:
            composition['composer'] = {
                '@type': 'Person',
                'name': str(partition.compositeur),
            }
        moments = list(psaume.moments_liturgiques.all())
        if moments:
            composition['about'] = [str(moment) for moment in moments]
        if partition.partition_pdf:
            composition['hasPart'].append({
                '@type': 'CreativeWork',
                'name': f"Partition PDF - {psaume.nom_psaume}",
                'encodingFormat': 'application/pdf',
                'url': request.build_absolute_uri(partition.partition_pdf.url),
            })
        for audio in partition.get_audio_list():
            composition['hasPart'].append({
                '@type': 'AudioObject',
                'name': f"Audio {audio['label']} - {psaume.nom_psaume}",
                'contentUrl': request.build_absolute_uri(audio['url']),
                'encodingFormat': 'audio/mpeg',
                'description': f"Piste audio pour la voix {audio['label']} du {psaume.nom_psaume}",
            })
        structured_data.append(composition)

    structured_data.append({
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Accueil', 'item': request.build_absolute_uri('/')},
            {
                '@type': 'ListItem',
                'position': 2,
                'name': psaume.nom_psaume or str(psaume),
                'item': request.build_absolute_uri(psaume.get_absolute_url()),
            },
        ],
    })

    return render(request, 'psaume_detail.html', {
        'psaume': psaume,
        'partition': partition,
        'has_non_synthetic_audio': has_non_synthetic_audio,
        'structured_data': structured_data,
        'memes_versets': memes_versets,
        'autres_versets_psaumes': autres_versets_psaumes,
    })

def cantique_detail(request, pk, slug):
    """Legacy redirect to psaume_detail."""
    return redirect('psaume_detail', pk=pk, slug=slug, permanent=True)
