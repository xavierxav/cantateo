"""
Calculs des dates liturgiques mobiles basées sur Pâques.

Utilise dateutil.easter pour le calcul de la date de Pâques.
Toutes les autres dates mobiles sont dérivées de Pâques.
"""

from datetime import date, timedelta
from dateutil.easter import easter


def date_paques(annee: int) -> date:
    """Retourne la date de Pâques pour une année donnée."""
    return easter(annee)


def date_cendres(annee: int) -> date:
    """Mercredi des Cendres : Pâques - 46 jours."""
    return date_paques(annee) - timedelta(days=46)


def date_rameaux(annee: int) -> date:
    """Dimanche des Rameaux : Pâques - 7 jours."""
    return date_paques(annee) - timedelta(days=7)


def date_jeudi_saint(annee: int) -> date:
    """Jeudi Saint : Pâques - 3 jours."""
    return date_paques(annee) - timedelta(days=3)


def date_vendredi_saint(annee: int) -> date:
    """Vendredi Saint : Pâques - 2 jours."""
    return date_paques(annee) - timedelta(days=2)


def date_ascension(annee: int) -> date:
    """Ascension : Pâques + 39 jours (jeudi en France)."""
    return date_paques(annee) + timedelta(days=39)


def date_pentecote(annee: int) -> date:
    """Pentecôte : Pâques + 49 jours."""
    return date_paques(annee) + timedelta(days=49)


def date_trinite(annee: int) -> date:
    """Sainte Trinité : Pâques + 56 jours (dimanche après Pentecôte)."""
    return date_paques(annee) + timedelta(days=56)


def date_fete_dieu(annee: int) -> date:
    """
    Fête-Dieu (Saint-Sacrement) : dimanche après la Sainte Trinité en France.

    Note: Dans d'autres pays, c'est le jeudi après la Sainte Trinité (Pâques + 60).
    En France, c'est reporté au dimanche suivant.
    """
    return date_paques(annee) + timedelta(days=63)


def date_sacre_coeur(annee: int) -> date:
    """Sacré-Cœur : vendredi après Fête-Dieu (19 jours après Pentecôte)."""
    return date_paques(annee) + timedelta(days=68)


def premier_dimanche_avent(annee: int) -> date:
    """
    Premier dimanche de l'Avent : 4ème dimanche avant Noël.

    C'est le dimanche le plus proche du 30 novembre (entre 27 nov et 3 déc).
    """
    noel = date(annee, 12, 25)
    # Trouver le dimanche avant ou égal à Noël
    # weekday(): 0=lundi, 6=dimanche
    jours_depuis_dimanche = (noel.weekday() + 1) % 7
    dimanche_avant_noel = noel - timedelta(days=jours_depuis_dimanche)
    # Le 4ème dimanche avant Noël = 3 semaines avant le dimanche précédent Noël
    # Si Noël est un dimanche, on compte 4 dimanches avant
    if noel.weekday() == 6:  # Noël est un dimanche
        return noel - timedelta(weeks=4)
    else:
        return dimanche_avant_noel - timedelta(weeks=3)


def date_epiphanie(annee: int) -> date:
    """
    Épiphanie en France : dimanche entre le 2 et le 8 janvier.

    - Si le 1er janvier est un dimanche → Épiphanie = 8 janvier
    - Sinon → premier dimanche après le 1er janvier
    """
    premier_janvier = date(annee, 1, 1)

    if premier_janvier.weekday() == 6:  # 1er janvier est dimanche
        # Épiphanie = dimanche suivant = 8 janvier
        return date(annee, 1, 8)
    else:
        # Premier dimanche après le 1er janvier
        jours_jusqua_dimanche = (6 - premier_janvier.weekday()) % 7
        if jours_jusqua_dimanche == 0:
            jours_jusqua_dimanche = 7
        return premier_janvier + timedelta(days=jours_jusqua_dimanche)


def date_bapteme_seigneur(annee: int) -> date:
    """
    Baptême du Seigneur : normalement le dimanche après l'Épiphanie.

    Exception : si l'Épiphanie tombe le 7 ou 8 janvier (dimanche),
    le Baptême est célébré le lundi suivant.
    """
    epiphanie = date_epiphanie(annee)

    if epiphanie.day >= 7:  # Épiphanie le 7 ou 8 janvier
        # Baptême = lundi suivant
        return epiphanie + timedelta(days=1)
    else:
        # Baptême = dimanche suivant
        return epiphanie + timedelta(days=7)


def date_christ_roi(annee: int) -> date:
    """
    Christ-Roi : dernier dimanche du Temps Ordinaire (34ème dimanche).

    C'est le dimanche qui précède le 1er dimanche de l'Avent.
    """
    return premier_dimanche_avent(annee) - timedelta(weeks=1)


def date_sainte_famille(annee: int) -> date:
    """
    Sainte Famille : dimanche dans l'octave de Noël.

    Si Noël (25 déc) tombe un dimanche, la Sainte Famille est le 30 décembre.
    Sinon, c'est le dimanche entre le 26 et le 31 décembre.
    """
    noel = date(annee, 12, 25)

    if noel.weekday() == 6:  # Noël est un dimanche
        return date(annee, 12, 30)
    else:
        # Premier dimanche après Noël
        jours_jusqua_dimanche = (6 - noel.weekday()) % 7
        if jours_jusqua_dimanche == 0:
            jours_jusqua_dimanche = 7
        return noel + timedelta(days=jours_jusqua_dimanche)


def annee_liturgique(d: date) -> str:
    """
    Retourne l'année liturgique (A, B, ou C) pour une date donnée.

    L'année liturgique commence au 1er dimanche de l'Avent.
    - Année A : quand (année civile de Pâques) % 3 == 1 (ex: 2023, 2026, 2029)
    - Année B : quand (année civile de Pâques) % 3 == 2 (ex: 2024, 2027, 2030)
    - Année C : quand (année civile de Pâques) % 3 == 0 (ex: 2025, 2028, 2031)
    """
    # Déterminer l'année liturgique en cours
    avent = premier_dimanche_avent(d.year)

    if d >= avent:
        # On est dans la nouvelle année liturgique (qui se termine à Pâques de l'année suivante)
        annee_paques = d.year + 1
    else:
        # On est encore dans l'année liturgique précédente
        annee_paques = d.year

    # Calcul du cycle A/B/C
    cycle = annee_paques % 3
    if cycle == 1:
        return 'A'
    elif cycle == 2:
        return 'B'
    else:  # cycle == 0
        return 'C'


def parite_annee(d: date) -> str:
    """
    Retourne la parité de l'année civile (P=paire, I=impaire).

    Utilisé pour les lectures des jours de semaine.
    """
    if d.year % 2 == 0:
        return 'P'
    else:
        return 'I'
