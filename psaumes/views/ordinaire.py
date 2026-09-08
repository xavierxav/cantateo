from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify

from ..models import Ordinaire, PartieMesse

ORDRE_MESSE = {'KYRIE': 0, 'GLORIA': 1, 'ALLELUIA': 2, 'PRIERE_UNIVERSELLE': 3, 'SANCTUS': 4, 'ANAMNESE': 5, 'AGNUS_DEI': 6}
PARTIE_CODE_TO_SLUG = {code: slugify(label) for code, label in PartieMesse.choices}
PARTIE_SLUG_TO_CODE = {slug: code for code, slug in PARTIE_CODE_TO_SLUG.items()}


def _build_ordinaire_detail_structured_data(request, ordinaire, partitions):
    composition = {
        '@context': 'https://schema.org',
        '@type': 'MusicComposition',
        'name': ordinaire.titre,
        'description': ordinaire.description or f"Ordinaire de messe « {ordinaire.titre} »",
        'inLanguage': 'fr-FR',
        'genre': 'Musique sacrée',
        'publisher': {'@type': 'Organization', 'name': 'Cantateo'},
        'url': request.build_absolute_uri(ordinaire.get_absolute_url()),
    }
    if ordinaire.compositeur:
        composition['composer'] = {'@type': 'Person', 'name': str(ordinaire.compositeur)}
    if partitions:
        composition['hasPart'] = []
        for p in partitions:
            part = {
                '@type': 'MusicComposition',
                'name': f"{p.get_partie_messe_display()} - {ordinaire.titre}",
            }
            if ordinaire.compositeur:
                part['composer'] = {'@type': 'Person', 'name': str(ordinaire.compositeur)}
            if p.partition_pdf:
                part['hasPart'] = [{
                    '@type': 'CreativeWork',
                    'name': f"Partition PDF - {p.get_partie_messe_display()} - {ordinaire.titre}",
                    'encodingFormat': 'application/pdf',
                    'url': request.build_absolute_uri(p.partition_pdf.url),
                }]
            composition['hasPart'].append(part)

    breadcrumb = {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Accueil', 'item': request.build_absolute_uri('/')},
            {'@type': 'ListItem', 'position': 2, 'name': 'Ordinaires de messe', 'item': request.build_absolute_uri(reverse('ordinaire_list'))},
            {'@type': 'ListItem', 'position': 3, 'name': ordinaire.titre, 'item': request.build_absolute_uri(ordinaire.get_absolute_url())},
        ],
    }
    return [composition, breadcrumb]


def _build_ordinaire_partie_structured_data(request, ordinaire, partition, code, partie_slug, partie_label):
    structured_data = []
    if partition:
        composition = {
            '@context': 'https://schema.org',
            '@type': 'MusicComposition',
            'name': f"{partie_label} - {ordinaire.titre}",
            'description': f"{partie_label} de la messe « {ordinaire.titre} »",
            'inLanguage': 'fr-FR',
            'genre': 'Musique sacrée',
            'publisher': {'@type': 'Organization', 'name': 'Cantateo'},
            'url': request.build_absolute_uri(reverse('ordinaire_partie_detail', kwargs={
                'pk': ordinaire.pk, 'slug': ordinaire.slug, 'partie': partie_slug,
            })),
            'hasPart': [],
        }
        if ordinaire.compositeur:
            composition['composer'] = {'@type': 'Person', 'name': str(ordinaire.compositeur)}
        if partition.partition_pdf:
            composition['hasPart'].append({
                '@type': 'CreativeWork',
                'name': f"Partition PDF - {partie_label} - {ordinaire.titre}",
                'encodingFormat': 'application/pdf',
                'url': request.build_absolute_uri(partition.partition_pdf.url),
            })
        for audio in partition.get_audio_list():
            composition['hasPart'].append({
                '@type': 'AudioObject',
                'name': f"Audio {audio['label']} - {partie_label} - {ordinaire.titre}",
                'contentUrl': request.build_absolute_uri(audio['url']),
                'encodingFormat': 'audio/mpeg',
                'description': f"Piste audio pour la voix {audio['label']} du {partie_label} de la messe {ordinaire.titre}",
            })
        structured_data.append(composition)

    structured_data.append({
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Accueil', 'item': request.build_absolute_uri('/')},
            {'@type': 'ListItem', 'position': 2, 'name': 'Ordinaires de messe', 'item': request.build_absolute_uri(reverse('ordinaire_list'))},
            {'@type': 'ListItem', 'position': 3, 'name': ordinaire.titre, 'item': request.build_absolute_uri(ordinaire.get_absolute_url())},
            {'@type': 'ListItem', 'position': 4, 'name': partie_label, 'item': request.build_absolute_uri(reverse('ordinaire_partie_detail', kwargs={
                'pk': ordinaire.pk, 'slug': ordinaire.slug, 'partie': partie_slug,
            }))},
        ],
    })
    return structured_data


def _ordered_parties(ordinaire):
    """Liste (code, slug, label) des parties présentes, ordre liturgique."""
    present = set(ordinaire.partitions_messe.values_list('partie_messe', flat=True))
    out = []
    for code, _ in sorted(ORDRE_MESSE.items(), key=lambda x: x[1]):
        if code in present:
            out.append((code, PARTIE_CODE_TO_SLUG[code], PartieMesse(code).label))
    return out


def ordinaire_list(request):
    ordinaires = Ordinaire.objects.all().prefetch_related('compositeur', 'partitions_messe')
    for o in ordinaires:
        o.parties_ordonnees = sorted(
            o.partitions_messe.all(), key=lambda p: ORDRE_MESSE.get(p.partie_messe or '', 99))
    return render(request, 'ordinaire_list.html', {'ordinaires': ordinaires})


def ordinaire_detail(request, pk, slug):
    ordinaire = get_object_or_404(
        Ordinaire.objects.prefetch_related('partitions_messe', 'partitions_messe__compositeur'), pk=pk)
    expected_slug = ordinaire.slug or 'ordinaire'
    if slug != expected_slug:
        return redirect('ordinaire_detail', pk=pk, slug=expected_slug, permanent=True)
    partitions = sorted(ordinaire.partitions_messe.all(),
                        key=lambda p: ORDRE_MESSE.get(p.partie_messe or '', 99))

    structured_data = _build_ordinaire_detail_structured_data(request, ordinaire, partitions)

    return render(request, 'ordinaire_detail.html', {
        'ordinaire': ordinaire,
        'partitions': partitions,
        'structured_data': structured_data,
    })


def ordinaire_partie_detail(request, pk, slug, partie):
    ordinaire = get_object_or_404(Ordinaire, pk=pk)
    expected_slug = ordinaire.slug or 'ordinaire'
    if slug != expected_slug:
        return redirect('ordinaire_partie_detail', pk=pk, slug=expected_slug, partie=partie, permanent=True)
    code = PARTIE_SLUG_TO_CODE.get(partie)
    if code is None:
        raise Http404('Partie de messe inconnue')
    partitions = list(ordinaire.partitions_messe.filter(partie_messe=code).order_by('titre'))
    if not partitions:
        raise Http404('Aucune partition pour cette partie')
    for p in partitions:
        p.has_non_synthetic_audio = p.has_audio() and not p.mp3_synthetiques
    ordered = _ordered_parties(ordinaire)
    labels = {c: lbl for c, s, lbl in ordered}
    codes_in_order = [c for c, s, lbl in ordered]
    idx = codes_in_order.index(code)
    prev_part = next_part = None
    if idx > 0:
        pc = codes_in_order[idx - 1]
        prev_part = {'slug': PARTIE_CODE_TO_SLUG[pc], 'label': labels[pc]}
    if idx < len(codes_in_order) - 1:
        nc = codes_in_order[idx + 1]
        next_part = {'slug': PARTIE_CODE_TO_SLUG[nc], 'label': labels[nc]}
    return render(request, 'ordinaire_partie_detail.html', {
        'ordinaire': ordinaire, 'partitions': partitions, 'partition': partitions[0],
        'partie_code': code, 'partie_slug': partie, 'partie_label': PartieMesse(code).label,
        'prev_part': prev_part, 'next_part': next_part,
        'structured_data': _build_ordinaire_partie_structured_data(
            request, ordinaire, partitions[0], code, partie, PartieMesse(code).label),
    })
