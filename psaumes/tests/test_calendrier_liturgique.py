"""
Tests pour le calendrier liturgique.

Ces tests vérifient:
- Les calculs de dates (Pâques, dates mobiles)
- Les temps liturgiques
- Les numéros de semaine
- La fonction principale get_moment_liturgique()
"""

import pytest
from datetime import date

from psaumes.models import MomentLiturgique, Psaume
from psaumes.services.liturgie.calculs_paques import (
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
    premier_dimanche_avent,
    date_epiphanie,
    date_bapteme_seigneur,
    date_christ_roi,
    date_sainte_famille,
    annee_liturgique,
    parite_annee,
)
from psaumes.services.liturgie.fetes import (
    get_fete,
    get_fete_fixe,
    get_fete_mobile,
    est_fete_cyclique,
    canonicaliser_nom_fete,
    get_fete_query_names,
)
from psaumes.services.liturgie.calendrier_liturgique import (
    get_temps_liturgique,
    get_semaine_liturgique,
    get_moment_liturgique,
    get_moment_liturgique_query_params,
)


class TestDatePaques:
    """Tests pour le calcul de la date de Pâques."""

    def test_paques_2024(self):
        """Pâques 2024 = 31 mars."""
        assert date_paques(2024) == date(2024, 3, 31)

    def test_paques_2025(self):
        """Pâques 2025 = 20 avril."""
        assert date_paques(2025) == date(2025, 4, 20)

    def test_paques_2026(self):
        """Pâques 2026 = 5 avril."""
        assert date_paques(2026) == date(2026, 4, 5)

    def test_paques_2027(self):
        """Pâques 2027 = 28 mars."""
        assert date_paques(2027) == date(2027, 3, 28)

    def test_paques_2030(self):
        """Pâques 2030 = 21 avril."""
        assert date_paques(2030) == date(2030, 4, 21)


class TestDatesMobiles:
    """Tests pour les dates mobiles dérivées de Pâques."""

    def test_cendres_2024(self):
        """Cendres 2024 = 14 février (Pâques - 46 jours)."""
        assert date_cendres(2024) == date(2024, 2, 14)

    def test_rameaux_2024(self):
        """Rameaux 2024 = 24 mars (Pâques - 7 jours)."""
        assert date_rameaux(2024) == date(2024, 3, 24)

    def test_jeudi_saint_2024(self):
        """Jeudi Saint 2024 = 28 mars."""
        assert date_jeudi_saint(2024) == date(2024, 3, 28)

    def test_vendredi_saint_2024(self):
        """Vendredi Saint 2024 = 29 mars."""
        assert date_vendredi_saint(2024) == date(2024, 3, 29)

    def test_ascension_2024(self):
        """Ascension 2024 = 9 mai (Pâques + 39 jours, jeudi)."""
        assert date_ascension(2024) == date(2024, 5, 9)
        assert date_ascension(2024).weekday() == 3  # Jeudi

    def test_pentecote_2024(self):
        """Pentecôte 2024 = 19 mai (Pâques + 49 jours)."""
        assert date_pentecote(2024) == date(2024, 5, 19)
        assert date_pentecote(2024).weekday() == 6  # Dimanche

    def test_trinite_2024(self):
        """Sainte Trinité 2024 = 26 mai (Pâques + 56 jours)."""
        assert date_trinite(2024) == date(2024, 5, 26)
        assert date_trinite(2024).weekday() == 6  # Dimanche

    def test_fete_dieu_2024(self):
        """Fête-Dieu 2024 = 2 juin (dimanche après Sainte Trinité en France)."""
        assert date_fete_dieu(2024) == date(2024, 6, 2)
        assert date_fete_dieu(2024).weekday() == 6  # Dimanche

    def test_sacre_coeur_2024(self):
        """Sacré-Cœur 2024 = 7 juin (vendredi après Fête-Dieu)."""
        assert date_sacre_coeur(2024) == date(2024, 6, 7)
        assert date_sacre_coeur(2024).weekday() == 4  # Vendredi


class TestAvent:
    """Tests pour le premier dimanche de l'Avent."""

    def test_avent_2024(self):
        """Premier dimanche de l'Avent 2024 = 1er décembre."""
        assert premier_dimanche_avent(2024) == date(2024, 12, 1)
        assert premier_dimanche_avent(2024).weekday() == 6  # Dimanche

    def test_avent_2025(self):
        """Premier dimanche de l'Avent 2025 = 30 novembre."""
        assert premier_dimanche_avent(2025) == date(2025, 11, 30)
        assert premier_dimanche_avent(2025).weekday() == 6  # Dimanche

    def test_avent_2022(self):
        """Premier dimanche de l'Avent 2022 = 27 novembre."""
        # Noël 2022 = dimanche, donc Avent = 4 semaines avant
        assert premier_dimanche_avent(2022) == date(2022, 11, 27)

    def test_christ_roi_2024(self):
        """Christ-Roi 2024 = 24 novembre (dimanche avant l'Avent)."""
        assert date_christ_roi(2024) == date(2024, 11, 24)
        assert date_christ_roi(2024).weekday() == 6  # Dimanche


class TestEpiphanieFrance:
    """Tests pour l'Épiphanie en France (dimanche 2-8 janvier)."""

    def test_epiphanie_2024(self):
        """Épiphanie 2024 = 7 janvier (1er janvier = lundi)."""
        # 1er janvier 2024 = lundi, premier dimanche = 7 janvier
        assert date_epiphanie(2024) == date(2024, 1, 7)
        assert date_epiphanie(2024).weekday() == 6  # Dimanche

    def test_epiphanie_2023(self):
        """Épiphanie 2023 = 8 janvier (1er janvier = dimanche)."""
        # 1er janvier 2023 = dimanche, donc Épiphanie = 8 janvier
        assert date_epiphanie(2023) == date(2023, 1, 8)
        assert date_epiphanie(2023).weekday() == 6  # Dimanche

    def test_epiphanie_2025(self):
        """Épiphanie 2025 = 5 janvier (1er janvier = mercredi)."""
        # 1er janvier 2025 = mercredi, premier dimanche = 5 janvier
        assert date_epiphanie(2025) == date(2025, 1, 5)
        assert date_epiphanie(2025).weekday() == 6  # Dimanche

    def test_epiphanie_2028(self):
        """Épiphanie 2028 = 2 janvier (1er janvier = samedi)."""
        # 1er janvier 2028 = samedi, premier dimanche = 2 janvier
        assert date_epiphanie(2028) == date(2028, 1, 2)
        assert date_epiphanie(2028).weekday() == 6  # Dimanche


class TestBapteme:
    """Tests pour le Baptême du Seigneur."""

    def test_bapteme_2024(self):
        """Baptême 2024 = 8 janvier (lendemain de l'Épiphanie le 7)."""
        # Épiphanie 2024 = 7 janvier, donc Baptême = lundi 8
        assert date_bapteme_seigneur(2024) == date(2024, 1, 8)
        assert date_bapteme_seigneur(2024).weekday() == 0  # Lundi

    def test_bapteme_2023(self):
        """Baptême 2023 = 9 janvier (lendemain de l'Épiphanie le 8)."""
        # Épiphanie 2023 = 8 janvier, donc Baptême = lundi 9
        assert date_bapteme_seigneur(2023) == date(2023, 1, 9)
        assert date_bapteme_seigneur(2023).weekday() == 0  # Lundi

    def test_bapteme_2025(self):
        """Baptême 2025 = 12 janvier (dimanche après Épiphanie le 5)."""
        # Épiphanie 2025 = 5 janvier, donc Baptême = dimanche 12
        assert date_bapteme_seigneur(2025) == date(2025, 1, 12)
        assert date_bapteme_seigneur(2025).weekday() == 6  # Dimanche

    def test_bapteme_2028(self):
        """Baptême 2028 = 9 janvier (dimanche après Épiphanie le 2)."""
        # Épiphanie 2028 = 2 janvier, donc Baptême = dimanche 9
        assert date_bapteme_seigneur(2028) == date(2028, 1, 9)
        assert date_bapteme_seigneur(2028).weekday() == 6  # Dimanche


class TestSainteFamille:
    """Tests pour la fête de la Sainte Famille."""

    def test_sainte_famille_2024(self):
        """Sainte Famille 2024 = 29 décembre (dimanche après Noël)."""
        # Noël 2024 = mercredi, dimanche suivant = 29 décembre
        assert date_sainte_famille(2024) == date(2024, 12, 29)
        assert date_sainte_famille(2024).weekday() == 6  # Dimanche

    def test_sainte_famille_2022(self):
        """Sainte Famille 2022 = 30 décembre (Noël = dimanche)."""
        # Noël 2022 = dimanche, donc Sainte Famille = 30 décembre
        assert date_sainte_famille(2022) == date(2022, 12, 30)


class TestAnneeLiturgique:
    """Tests pour le calcul de l'année liturgique A/B/C."""

    def test_annee_2024_avant_avent(self):
        """Novembre 2024 (avant Avent) = année B."""
        # L'Avent 2024 commence le 1er décembre
        # Novembre 2024 est dans l'année liturgique B (Pâques 2024)
        assert annee_liturgique(date(2024, 11, 15)) == "B"

    def test_annee_2024_apres_avent(self):
        """Décembre 2024 (après Avent) = année C."""
        # Après le 1er décembre 2024, on est dans l'année C (Pâques 2025)
        assert annee_liturgique(date(2024, 12, 15)) == "C"

    def test_annee_2025(self):
        """2025 = année C."""
        assert annee_liturgique(date(2025, 3, 15)) == "C"

    def test_annee_2026(self):
        """2026 = année A."""
        assert annee_liturgique(date(2026, 3, 15)) == "A"

    def test_annee_2027(self):
        """2027 = année B."""
        assert annee_liturgique(date(2027, 3, 15)) == "B"


class TestParite:
    """Tests pour la parité de l'année."""

    def test_parite_2024(self):
        """2024 = année paire."""
        assert parite_annee(date(2024, 6, 15)) == "P"

    def test_parite_2025(self):
        """2025 = année impaire."""
        assert parite_annee(date(2025, 6, 15)) == "I"


class TestTempsLiturgique:
    """Tests pour la détermination du temps liturgique."""

    def test_temps_avent(self):
        """Décembre avant Noël = AVENT."""
        assert get_temps_liturgique(date(2024, 12, 15)) == "AVENT"

    def test_temps_noel_decembre(self):
        """25-31 décembre = NOEL."""
        assert get_temps_liturgique(date(2024, 12, 25)) == "NOEL"
        assert get_temps_liturgique(date(2024, 12, 31)) == "NOEL"

    def test_temps_noel_janvier(self):
        """Janvier jusqu'au Baptême = NOEL."""
        assert get_temps_liturgique(date(2025, 1, 5)) == "NOEL"
        # Baptême 2025 = 12 janvier, donc le 11 est encore Noël
        assert get_temps_liturgique(date(2025, 1, 11)) == "NOEL"

    def test_temps_ordinaire_janvier(self):
        """Après le Baptême = ORDINAIRE."""
        # Baptême 2025 = 12 janvier
        assert get_temps_liturgique(date(2025, 1, 13)) == "ORDINAIRE"

    def test_temps_careme(self):
        """Après les Cendres = CAREME."""
        # Cendres 2025 = 5 mars
        assert get_temps_liturgique(date(2025, 3, 5)) == "CAREME"
        assert get_temps_liturgique(date(2025, 3, 15)) == "CAREME"

    def test_temps_semaine_sainte(self):
        """Jeudi Saint à Samedi Saint = SAINT."""
        # Pâques 2025 = 20 avril
        # Jeudi Saint = 17 avril
        assert get_temps_liturgique(date(2025, 4, 17)) == "SAINT"
        assert get_temps_liturgique(date(2025, 4, 18)) == "SAINT"
        assert get_temps_liturgique(date(2025, 4, 19)) == "SAINT"

    def test_temps_pascal(self):
        """Pâques à Pentecôte = PASCAL."""
        # Pâques 2025 = 20 avril
        assert get_temps_liturgique(date(2025, 4, 20)) == "PASCAL"
        # Pentecôte 2025 = 8 juin
        assert get_temps_liturgique(date(2025, 6, 8)) == "PASCAL"

    def test_temps_ordinaire_ete(self):
        """Après Pentecôte = ORDINAIRE."""
        # Pentecôte 2025 = 8 juin
        assert get_temps_liturgique(date(2025, 6, 15)) == "ORDINAIRE"
        assert get_temps_liturgique(date(2025, 10, 15)) == "ORDINAIRE"


class TestFetes:
    """Tests pour l'identification des fêtes."""

    def test_fete_fixe_noel(self):
        """25 décembre = Nativité du Seigneur."""
        assert get_fete_fixe(date(2024, 12, 25)) == "Nativité du Seigneur"

    def test_fete_fixe_toussaint(self):
        """1er novembre = Toussaint."""
        assert get_fete_fixe(date(2024, 11, 1)) == "Toussaint"

    def test_fete_mobile_paques(self):
        """Pâques 2025 = 20 avril."""
        assert get_fete_mobile(date(2025, 4, 20)) == "Pâques"

    def test_fete_mobile_ascension(self):
        """Ascension 2025 = 29 mai."""
        assert get_fete_mobile(date(2025, 5, 29)) == "Ascension"

    def test_fete_mobile_pentecote(self):
        """Pentecôte 2025 = 8 juin."""
        assert get_fete_mobile(date(2025, 6, 8)) == "Pentecôte"

    def test_fete_cyclique(self):
        """Sainte Trinité et Christ-Roi sont des fêtes cycliques."""
        assert est_fete_cyclique("Sainte Trinité")
        assert est_fete_cyclique("Trinité")
        assert est_fete_cyclique("Christ-Roi")
        assert est_fete_cyclique("Sainte Famille")
        assert not est_fete_cyclique("Pâques")
        assert not est_fete_cyclique("Toussaint")

    def test_trinite_alias_helpers(self):
        """The legacy alias Trinité remains accepted for imports/search."""
        assert canonicaliser_nom_fete("Trinité") == "Sainte Trinité"
        assert get_fete_query_names("Trinité") == ["Sainte Trinité", "Trinité"]

    def test_sacrement_alias_helpers(self):
        """All variations of Saint-Sacrement are mapped to the canonical name and cyclique check works."""
        assert est_fete_cyclique("Saint-Sacrement")
        assert est_fete_cyclique("Saint-Sacrement du Corps et du sang du Seigneur")
        assert canonicaliser_nom_fete("Saint-Sacrement") == "Saint-Sacrement du Corps et du Sang du Christ"
        assert canonicaliser_nom_fete("Saint-Sacrement du Corps et du sang du Seigneur") == "Saint-Sacrement du Corps et du Sang du Christ"
        query_names = get_fete_query_names("Saint-Sacrement")
        assert "Saint-Sacrement" in query_names
        assert "Saint-Sacrement du Corps et du Sang du Christ" in query_names
        assert "Saint-Sacrement du Corps et du sang du Seigneur" in query_names

    def test_get_fete_priorite_mobile(self):
        """Les fêtes mobiles ont priorité sur les fixes."""
        # Ce test vérifie la logique de priorité
        assert get_fete(date(2025, 4, 20)) == "Pâques"


class TestMomentLiturgique:
    """Tests pour la fonction principale get_moment_liturgique()."""

    def test_moment_fete_fixe(self):
        """Noël retourne un moment de type FETE."""
        moment = get_moment_liturgique(date(2024, 12, 25))
        assert moment["type"] == "FETE"
        assert moment["nom_fete"] == "Nativité du Seigneur"
        assert moment["annee"] is None  # Fête non cyclique

    def test_moment_fete_mobile(self):
        """Pâques retourne un moment de type FETE."""
        moment = get_moment_liturgique(date(2025, 4, 20))
        assert moment["type"] == "FETE"
        assert moment["nom_fete"] == "Pâques"

    def test_moment_fete_cyclique(self):
        """Sainte Trinité retourne un moment avec année A/B/C."""
        # Sainte Trinité 2025 = 15 juin (année C)
        moment = get_moment_liturgique(date(2025, 6, 15))
        assert moment["type"] == "FETE"
        assert moment["nom_fete"] == "Sainte Trinité"
        assert moment["annee"] == "C"

    @pytest.mark.django_db
    def test_moment_query_params_accept_legacy_trinite_alias(self):
        """The query params still find legacy rows stored as Trinité."""
        psaume = Psaume.objects.create(nom_psaume="Psaume 8", titre="Test")
        legacy = MomentLiturgique.objects.create(
            psaume=psaume,
            nom_fete="Trinité",
            annee="C",
        )

        params = get_moment_liturgique_query_params(date(2025, 6, 15))
        result = MomentLiturgique.objects.filter(**params).first()

        assert result == legacy

    @pytest.mark.django_db
    def test_moment_query_params_accept_sacrement_aliases(self):
        """The query params find rows stored as either Saint-Sacrement du Corps et du Sang du Christ or other variations."""
        psaume_a = Psaume.objects.create(nom_psaume="Psaume 147", titre="A")
        psaume_b = Psaume.objects.create(nom_psaume="Psaume 115", titre="B")
        
        m_a = MomentLiturgique.objects.create(
            psaume=psaume_a,
            nom_fete="Saint-Sacrement du Corps et du Sang du Christ",
            annee="A",
        )
        m_b = MomentLiturgique.objects.create(
            psaume=psaume_b,
            nom_fete="Saint-Sacrement du Corps et du sang du Seigneur",
            annee="B",
        )

        # Fête-Dieu 2026 is June 7, 2026 (Year A)
        params_2026 = get_moment_liturgique_query_params(date(2026, 6, 7))
        result_2026 = MomentLiturgique.objects.filter(**params_2026).first()
        assert result_2026 == m_a

        # Fête-Dieu 2027 is May 30, 2027 (Year B) (Easter 2027 is Mar 28 -> Pentecost May 16 -> Trinity May 23 -> Fete-Dieu May 30)
        params_2027 = get_moment_liturgique_query_params(date(2027, 5, 30))
        result_2027 = MomentLiturgique.objects.filter(**params_2027).first()
        assert result_2027 == m_b

    def test_moment_dimanche_ordinaire(self):
        """Un dimanche ordinaire retourne le bon format."""
        # 16 février 2025 = dimanche (6ème dimanche du temps ordinaire, année C)
        moment = get_moment_liturgique(date(2025, 2, 16))
        assert moment["type"] == "DIMANCHE"
        assert moment["temps"] == "ORDINAIRE"
        assert moment["jour"] == 0
        assert moment["annee"] == "C"
        assert "semaine" in moment

    def test_moment_dimanche_avent(self):
        """Un dimanche de l'Avent retourne le bon format."""
        # 1er décembre 2024 = 1er dimanche de l'Avent
        moment = get_moment_liturgique(date(2024, 12, 1))
        assert moment["type"] == "DIMANCHE"
        assert moment["temps"] == "AVENT"
        assert moment["semaine"] == 1
        assert moment["jour"] == 0
        assert moment["annee"] == "C"  # Année liturgique C (Pâques 2025)

    def test_moment_semaine(self):
        """Un jour de semaine retourne le bon format."""
        # 17 février 2025 = lundi (année impaire)
        moment = get_moment_liturgique(date(2025, 2, 17))
        assert moment["type"] == "SEMAINE"
        assert moment["temps"] == "ORDINAIRE"
        assert moment["jour"] == 1  # Lundi
        assert moment["parite"] == "I"  # 2025 = impaire

    def test_moment_semaine_careme(self):
        """Un jour de semaine en Carême."""
        # 6 mars 2025 = jeudi après les Cendres
        moment = get_moment_liturgique(date(2025, 3, 6))
        assert moment["type"] == "SEMAINE"
        assert moment["temps"] == "CAREME"
        assert moment["jour"] == 4  # Jeudi


class TestSemainesLiturgiques:
    """Tests pour les numéros de semaines."""

    def test_semaine_avent(self):
        """Semaines de l'Avent (1-4)."""
        # 2024: Avent commence le 1er décembre
        assert get_semaine_liturgique(date(2024, 12, 1)) == 1
        assert get_semaine_liturgique(date(2024, 12, 8)) == 2
        assert get_semaine_liturgique(date(2024, 12, 15)) == 3
        assert get_semaine_liturgique(date(2024, 12, 22)) == 4

    def test_semaine_noel(self):
        """Semaines de Noël (1-2)."""
        # Semaine 1: Noël jusqu'à Épiphanie
        assert get_semaine_liturgique(date(2024, 12, 26)) == 1
        # Semaine 2: Épiphanie jusqu'à Baptême
        # Épiphanie 2025 = 5 janvier
        assert get_semaine_liturgique(date(2025, 1, 6)) == 2

    def test_semaine_careme(self):
        """Semaines de Carême (1-6)."""
        # 2025: Cendres = 5 mars, Rameaux = 13 avril
        # La semaine des Cendres est la semaine 1
        assert get_semaine_liturgique(date(2025, 3, 5)) == 1  # Cendres
        # 1er dimanche de Carême = 9 mars = semaine 1
        assert get_semaine_liturgique(date(2025, 3, 9)) == 1

    def test_semaine_pascal(self):
        """Semaines du temps pascal (1-8)."""
        # 2025: Pâques = 20 avril
        assert get_semaine_liturgique(date(2025, 4, 20)) == 1  # Pâques
        assert get_semaine_liturgique(date(2025, 4, 27)) == 2  # 2ème dim
        # Pentecôte = 49 jours après Pâques = semaine 8
        assert get_semaine_liturgique(date(2025, 6, 8)) == 8
