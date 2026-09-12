import logging
import re
from collections import defaultdict

from django.shortcuts import render
from ..models import Psaume, MomentLiturgique

logger = logging.getLogger(__name__)


def toutes_les_partitions(request):
    psaumes = Psaume.objects.filter(
        psaume_or_cantique='psaume'
    ).prefetch_related(
        'partitions__compositeur',
        'moments_liturgiques'
    )

    # Sort numerically by extracting the number from nom_psaume
    def psaume_sort_key(p):
        m = re.search(r'(\d+)', p.nom_psaume or '')
        return int(m.group(1)) if m else 0

    psaumes = sorted(psaumes, key=psaume_sort_key)

    cantiques = Psaume.objects.filter(
        psaume_or_cantique='cantique'
    ).prefetch_related(
        'partitions__compositeur',
        'moments_liturgiques'
    ).order_by('nom_psaume')

    return render(request, 'toutes_les_partitions.html', {
        'psaumes': psaumes,
        'cantiques': cantiques,
    })


def calendrier_liturgique(request):
    moments = MomentLiturgique.objects.filter(
        psaume__isnull=False
    ).select_related(
        'psaume'
    ).prefetch_related(
        'psaume__partitions__compositeur'
    )

    TEMPS_DISPLAY = {
        'ORDINAIRE': 'Temps Ordinaire',
        'AVENT': "Temps de l'Avent",
        'NOEL': 'Temps de Noël',
        'CAREME': 'Temps de Carême',
        'SAINT': 'Semaine Sainte',
        'PASCAL': 'Temps Pascal',
    }
    TEMPS_ORDER = {t: i for i, t in enumerate(TEMPS_DISPLAY.keys())}

    sections = []

    # 1. Fêtes fixes (no year)
    fetes_fixes = sorted(
        [m for m in moments if m.nom_fete and not m.annee],
        key=lambda m: m.nom_fete
    )
    if fetes_fixes:
        sections.append({'title': 'Fêtes', 'subsections': [{'title': None, 'moments': fetes_fixes}]})

    # 2. Year A, B, C
    for annee_code in ['A', 'B', 'C']:
        annee_label = dict(MomentLiturgique.ANNEE_CHOICES).get(annee_code, f'Année {annee_code}')
        year_moments = [m for m in moments if m.annee == annee_code]
        if not year_moments:
            continue

        subsections = []

        # Fêtes cycliques within this year
        fetes = sorted(
            [m for m in year_moments if m.nom_fete],
            key=lambda m: m.nom_fete
        )
        if fetes:
            subsections.append({'title': 'Fêtes', 'moments': fetes})

        # Group regular moments by temps
        temps_groups = defaultdict(list)
        for m in year_moments:
            if not m.nom_fete and m.temps:
                temps_groups[m.temps].append(m)

        for temps in sorted(temps_groups.keys(), key=lambda t: TEMPS_ORDER.get(t, 99)):
            temps_moments = sorted(temps_groups[temps], key=lambda m: (m.semaine or 0, m.jour or 0))
            subsections.append({
                'title': TEMPS_DISPLAY.get(temps, temps),
                'moments': temps_moments
            })

        sections.append({'title': annee_label, 'subsections': subsections})

    return render(request, 'calendrier_liturgique.html', {
        'sections': sections,
    })
