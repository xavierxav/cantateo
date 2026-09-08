"""
Définitions des fêtes liturgiques fixes et mobiles.

Les fêtes sont classées par priorité pour gérer la préséance.
"""

from datetime import date
from typing import Optional

from .calculs_paques import (
    date_paques,
    date_cendres,
    date_rameaux,
    date_jeudi_saint,
    date_vendredi_saint,
    date_ascension,
    date_pentecote,
    date_trinite,
    date_fete_dieu,
    date_sacre_coeur,
    date_christ_roi,
    date_sainte_famille,
    date_bapteme_seigneur,
    date_epiphanie
)


# Fêtes fixes : (mois, jour) -> nom_fete
# Ces fêtes ont toujours lieu à la même date chaque année.
# Seules les solennités qui ont un psaume propre sont listées.
FETES_FIXES: dict[tuple[int, int], str] = {
    # Solennités du Seigneur et de la Vierge
    (12, 25): "Nativité du Seigneur",
    (1, 1): "Sainte Marie Mère de Dieu",
    (3, 25): "Annonciation du Seigneur",
    (8, 15): "Assomption de la Vierge Marie",
    (12, 8): "Immaculée Conception",

    # Autres solennités
    (11, 1): "Toussaint",
    (6, 24): "Nativité de Saint Jean Baptiste",
    (6, 29): "Saints Pierre et Paul",
    (8, 6): "Transfiguration du Seigneur",
    (9, 14): "Exaltation de la Sainte Croix",
    (11, 2): "Commémoration des fidèles défunts",
}


# Fêtes cycliques : fêtes qui ont des lectures différentes selon l'année A/B/C
# Ces fêtes nécessitent le champ 'annee' dans MomentLiturgique
FETES_CYCLIQUES: set[str] = {
    "Sainte Trinité",
    "Christ-Roi",
    "Sainte Famille",
    "Baptême du Seigneur",
    "Sacré-Cœur",
    "Saint-Sacrement du Corps et du Sang du Christ"
    # Note: Pâques et Pentecôte ont les mêmes lectures chaque année
}

FETE_ALIASES: dict[str, str] = {
    "Trinité": "Sainte Trinité",
    "Saint-Sacrement": "Saint-Sacrement du Corps et du Sang du Christ",
    "Saint-Sacrement du Corps et du sang du Seigneur": "Saint-Sacrement du Corps et du Sang du Christ",
}


def canonicaliser_nom_fete(nom_fete: Optional[str]) -> Optional[str]:
    """Return the canonical feast name used by the application."""
    if not nom_fete:
        return nom_fete
    cleaned = nom_fete.strip()
    return FETE_ALIASES.get(cleaned, cleaned)


def get_fete_query_names(nom_fete: Optional[str]) -> list[str]:
    """Return the canonical name plus accepted aliases for DB lookups."""
    canonical = canonicaliser_nom_fete(nom_fete)
    if not canonical:
        return []

    names = [canonical]
    for alias, target in FETE_ALIASES.items():
        if target == canonical:
            names.append(alias)
    return names


def get_fetes_mobiles(annee: int) -> dict[date, str]:
    """
    Retourne un dictionnaire des fêtes mobiles pour une année civile donnée.

    Args:
        annee: L'année civile (ex: 2024)

    Returns:
        Dict[date, str]: Dictionnaire date -> nom de la fête
    """
    return {
        date_cendres(annee): "Mercredi des Cendres",
        date_rameaux(annee): "Dimanche des Rameaux",
        date_jeudi_saint(annee): "Jeudi Saint",
        date_vendredi_saint(annee): "Vendredi Saint",
        date_paques(annee): "Pâques",
        date_ascension(annee): "Ascension",
        date_pentecote(annee): "Pentecôte",
        date_trinite(annee): "Sainte Trinité",
        date_fete_dieu(annee): "Saint-Sacrement",
        date_sacre_coeur(annee): "Sacré-Cœur",
        date_christ_roi(annee): "Christ-Roi",
        date_sainte_famille(annee): "Sainte Famille",
        date_bapteme_seigneur(annee): "Baptême du Seigneur",
        date_epiphanie(annee): "Épiphanie",
    }


def get_fete_fixe(d: date) -> Optional[str]:
    """
    Retourne le nom de la fête fixe pour une date, ou None.

    Args:
        d: La date à vérifier

    Returns:
        Le nom de la fête fixe ou None si ce n'est pas une fête fixe
    """
    return FETES_FIXES.get((d.month, d.day))


def get_fete_mobile(d: date) -> Optional[str]:
    """
    Retourne le nom de la fête mobile pour une date, ou None.

    Args:
        d: La date à vérifier

    Returns:
        Le nom de la fête mobile ou None si ce n'est pas une fête mobile
    """
    # On vérifie l'année en cours et l'année précédente pour les fêtes
    # qui peuvent chevaucher le changement d'année (Sainte Famille, Baptême)
    for annee in [d.year, d.year - 1, d.year + 1]:
        fetes = get_fetes_mobiles(annee)
        if d in fetes:
            return fetes[d]
    return None


def get_fete(d: date) -> Optional[str]:
    """
    Retourne le nom de la fête (fixe ou mobile) pour une date.

    La priorité est donnée aux fêtes mobiles car elles incluent
    les grandes solennités comme Pâques.

    Args:
        d: La date à vérifier

    Returns:
        Le nom de la fête ou None si ce n'est pas une fête
    """
    # Les fêtes mobiles ont priorité (Pâques > tout)
    fete_mobile = get_fete_mobile(d)
    if fete_mobile:
        return fete_mobile

    return get_fete_fixe(d)


def est_fete_cyclique(nom_fete: str) -> bool:
    """
    Vérifie si une fête est cyclique (lectures A/B/C différentes).

    Args:
        nom_fete: Le nom de la fête

    Returns:
        True si la fête a des lectures différentes selon l'année A/B/C
    """
    return canonicaliser_nom_fete(nom_fete) in FETES_CYCLIQUES
