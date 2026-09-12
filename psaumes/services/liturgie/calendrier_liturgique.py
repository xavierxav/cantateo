"""
Service principal pour le calendrier liturgique.

Ce module fournit la fonction get_moment_liturgique() qui, pour une date donnée,
retourne un dictionnaire avec les informations nécessaires pour identifier
le MomentLiturgique correspondant dans la base de données.
"""

from datetime import date, timedelta
from typing import Optional

from .calculs_paques import (
    date_paques,
    date_cendres,
    date_rameaux,
    date_jeudi_saint,
    date_pentecote,
    premier_dimanche_avent,
    date_bapteme_seigneur,
    date_epiphanie,
    annee_liturgique,
    parite_annee,
)
from .fetes import get_fete, est_fete_cyclique, get_fete_query_names


def get_temps_liturgique(d: date) -> str:
    """
    Retourne le temps liturgique pour une date donnée.

    Temps possibles : AVENT, NOEL, ORDINAIRE, CAREME, SAINT, PASCAL

    Args:
        d: La date à analyser

    Returns:
        Le code du temps liturgique
    """
    annee = d.year

    # Calculer les bornes des différents temps
    # Note: On doit parfois regarder l'année précédente ou suivante

    # --- Temps de Noël (peut chevaucher deux années civiles) ---
    # Noël de l'année en cours
    noel = date(annee, 12, 25)
    bapteme = date_bapteme_seigneur(annee + 1)  # Baptême en janvier de l'année suivante

    # Noël de l'année précédente (pour les dates en janvier)
    noel_precedent = date(annee - 1, 12, 25)
    bapteme_courant = date_bapteme_seigneur(annee)

    # Vérifier si on est dans le temps de Noël
    if d >= noel:
        # Entre Noël et le 31 décembre
        return "NOEL"
    if d <= bapteme_courant:
        # Entre le 1er janvier et le Baptême du Seigneur
        if d >= date(annee, 1, 1):
            return "NOEL"

    # --- Temps de l'Avent ---
    avent = premier_dimanche_avent(annee)
    if d >= avent and d < noel:
        return "AVENT"

    # --- Temps Pascal ---
    paques = date_paques(annee)
    pentecote = date_pentecote(annee)
    if d >= paques and d <= pentecote:
        return "PASCAL"

    # --- Semaine Sainte (Triduum: Jeudi Saint - Samedi Saint) ---
    jeudi_saint = date_jeudi_saint(annee)
    if d >= jeudi_saint and d < paques:
        return "SAINT"

    # --- Temps de Carême ---
    cendres = date_cendres(annee)
    if d >= cendres and d < jeudi_saint:
        return "CAREME"

    # --- Temps Ordinaire (par défaut) ---
    return "ORDINAIRE"


def get_semaine_liturgique(d: date) -> int:
    """
    Retourne le numéro de semaine dans le temps liturgique.

    Args:
        d: La date à analyser

    Returns:
        Le numéro de semaine (1-34 selon le temps)
    """
    temps = get_temps_liturgique(d)
    annee = d.year

    if temps == "AVENT":
        avent = premier_dimanche_avent(annee)
        jours = (d - avent).days
        return (jours // 7) + 1

    elif temps == "NOEL":
        # Semaine 1: de Noël à avant Épiphanie
        # Semaine 2: de l'Épiphanie au Baptême
        if d.month == 12:
            noel = date(annee, 12, 25)
        else:
            noel = date(annee - 1, 12, 25)

        epiphanie = date_epiphanie(d.year if d.month == 1 else d.year + 1)

        if d < epiphanie:
            return 1
        else:
            return 2

    elif temps == "CAREME":
        cendres = date_cendres(annee)
        jours = (d - cendres).days
        # Les Cendres sont en semaine 0 (avant le 1er dimanche)
        # 1er dimanche de Carême = semaine 1
        return (jours // 7) + 1

    elif temps == "SAINT":
        # La Semaine Sainte est considérée comme une seule semaine
        return 1

    elif temps == "PASCAL":
        paques = date_paques(annee)
        jours = (d - paques).days
        return (jours // 7) + 1

    elif temps == "ORDINAIRE":
        # Le Temps Ordinaire est en deux parties
        return _get_semaine_temps_ordinaire(d)

    return 1


def _get_semaine_temps_ordinaire(d: date) -> int:
    """
    Calcule le numéro de semaine du Temps Ordinaire.

    Le Temps Ordinaire est divisé en deux parties:
    - Partie I: du lendemain du Baptême du Seigneur à la veille des Cendres
    - Partie II: du lendemain de la Pentecôte à la veille de l'Avent

    La numérotation continue de la partie I à la partie II, en ajustant
    pour que la 34ème semaine tombe toujours à Christ-Roi.

    Args:
        d: La date dans le Temps Ordinaire

    Returns:
        Le numéro de semaine (1-34)
    """
    annee = d.year

    bapteme = date_bapteme_seigneur(annee)
    cendres = date_cendres(annee)
    pentecote = date_pentecote(annee)
    avent = premier_dimanche_avent(annee)

    # Partie I : après le Baptême, avant le Carême
    if d > bapteme and d < cendres:
        # Le Baptême du Seigneur est le 1er dimanche du Temps Ordinaire
        # (même si liturgiquement il clôture le temps de Noël)
        # La semaine 2 commence le dimanche suivant
        jours = (d - bapteme).days
        return (jours // 7) + 1

    # Partie II : après la Pentecôte, avant l'Avent
    if d > pentecote and d < avent:
        # Calculer combien de semaines il reste jusqu'à l'Avent
        # La semaine avant l'Avent est la 34ème (Christ-Roi)
        jours_jusqua_avent = (avent - d).days
        return 34 - ((jours_jusqua_avent - 1) // 7)

    return 1


def get_moment_liturgique(d: date) -> dict:
    """
    Retourne les informations du moment liturgique pour une date.

    Cette fonction est le point d'entrée principal du service.
    Elle retourne un dictionnaire qui peut être utilisé pour
    rechercher le MomentLiturgique correspondant en base de données.

    Args:
        d: La date à analyser

    Returns:
        Un dictionnaire avec les clés suivantes:
        - type: "FETE", "DIMANCHE", ou "SEMAINE"
        - nom_fete: (si type=FETE) Le nom de la fête
        - annee: (si type=DIMANCHE ou FETE cyclique) "A", "B", ou "C"
        - temps: (si type=DIMANCHE ou SEMAINE) Le temps liturgique
        - semaine: (si type=DIMANCHE ou SEMAINE) Le numéro de semaine
        - jour: (si type=DIMANCHE ou SEMAINE) 0-6 (0=dimanche)
        - parite: (si type=SEMAINE) "P" ou "I"
    """
    # 1. Vérifier si c'est une fête
    nom_fete = get_fete(d)
    if nom_fete:
        result = {
            "type": "FETE",
            "nom_fete": nom_fete,
        }
        # Ajouter l'année si c'est une fête cyclique
        if est_fete_cyclique(nom_fete):
            result["annee"] = annee_liturgique(d)
        else:
            result["annee"] = None
        return result

    # 2. Calculer les informations de base
    temps = get_temps_liturgique(d)
    semaine = get_semaine_liturgique(d)
    jour_semaine = (d.weekday() + 1) % 7  # Convertir: lundi=0 -> dimanche=0

    # 3. Dimanche ou jour de semaine ?
    if jour_semaine == 0:  # Dimanche
        return {
            "type": "DIMANCHE",
            "temps": temps,
            "semaine": semaine,
            "jour": 0,
            "annee": annee_liturgique(d),
        }
    else:  # Lundi à Samedi
        return {
            "type": "SEMAINE",
            "temps": temps,
            "semaine": semaine,
            "jour": jour_semaine,
            "parite": parite_annee(d),
        }


def get_moment_liturgique_query_params(d: date) -> dict:
    """
    Retourne les paramètres pour une requête Django MomentLiturgique.

    Cette fonction transforme le résultat de get_moment_liturgique()
    en paramètres utilisables directement dans un filtre Django.

    Args:
        d: La date à analyser

    Returns:
        Un dictionnaire de paramètres pour MomentLiturgique.objects.filter()
    """
    moment = get_moment_liturgique(d)

    if moment["type"] == "FETE":
        noms_fete = get_fete_query_names(moment["nom_fete"])
        params = {"nom_fete": noms_fete[0]} if len(noms_fete) == 1 else {"nom_fete__in": noms_fete}
        if moment.get("annee"):
            params["annee"] = moment["annee"]
        return params

    elif moment["type"] == "DIMANCHE":
        return {
            "temps": moment["temps"],
            "semaine": moment["semaine"],
            "jour": 0,
            "annee": moment["annee"],
        }

    else:  # SEMAINE
        return {
            "temps": moment["temps"],
            "semaine": moment["semaine"],
            "jour": moment["jour"],
            "parite": moment["parite"],
        }
