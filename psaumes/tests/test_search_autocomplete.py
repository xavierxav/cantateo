import pytest
from django.test import Client
from django.urls import reverse

from psaumes.models import MomentLiturgique, Psaume, Partition, Compositeur, Ordinaire, PartieMesse


@pytest.mark.django_db
class TestSearchAutocomplete:
    def setup_method(self, method=None):
        self.client = Client()

    def _create_psaume_with_partition(self):
        compositeur = Compositeur.objects.create(nom="Jean Dupont")
        psaume = Psaume.objects.create(
            nom_psaume="Psaume 23",
            titre="Le Seigneur est mon berger",
        )
        Partition.objects.create(
            psaume=psaume,
            compositeur=compositeur,
            refrain="Le Seigneur est mon berger, rien ne saurait me manquer.",
        )
        return psaume

    def test_autocomplete_matches_accented_trinite(self):
        psaume = self._create_psaume_with_partition()
        MomentLiturgique.objects.create(
            psaume=psaume,
            nom_fete="Sainte Trinité",
            annee="C",
        )

        resp = self.client.get(reverse("search_autocomplete"), {"q": "trinité"})

        assert resp.status_code == 200
        assert "Sainte Trinité" in resp.content.decode()

    def test_autocomplete_matches_typo_in_psalm(self):
        psaume = self._create_psaume_with_partition()
        MomentLiturgique.objects.create(
            psaume=psaume,
            nom_fete="Sainte Trinité",
            annee="C",
        )

        resp = self.client.get(reverse("search_autocomplete"), {"q": "bergerr"})

        assert resp.status_code == 200
        assert "Psaume 23" in resp.content.decode()

    def test_autocomplete_rejects_queries_over_length_cap(self):
        resp = self.client.get(reverse("search_autocomplete"), {"q": "a" * 81})

        assert resp.status_code == 200
        assert resp.content == b""

    def test_autocomplete_matches_ordinaire(self):
        Ordinaire.objects.create(titre="Messe de VAN")
        resp = self.client.get(reverse("search_autocomplete"), {"q": "messe van"})
        assert resp.status_code == 200
        assert "Messe de VAN" in resp.content.decode()

    def test_autocomplete_matches_ordinaire_by_party_name(self):
        """Searching 'agnus' finds an ordinaire that has an Agnus Dei partition."""
        compositeur = Compositeur.objects.create(nom="Carlo Acutis")
        ordinaire = Ordinaire.objects.create(
            titre="Messe du Bienheureux Carlo Acutis",
            compositeur=compositeur,
        )
        Partition.objects.create(
            ordinaire=ordinaire,
            partie_messe=PartieMesse.AGNUS_DEI,
            titre="Messe du Bienheureux Carlo Acutis — Agnus Dei",
        )
        Partition.objects.create(
            ordinaire=ordinaire,
            partie_messe=PartieMesse.SANCTUS,
            titre="Messe du Bienheureux Carlo Acutis — Sanctus",
        )

        resp = self.client.get(reverse("search_autocomplete"), {"q": "agnus"})

        assert resp.status_code == 200
        assert "Carlo Acutis" in resp.content.decode()

    def test_autocomplete_matches_ordinaire_by_composer(self):
        """Searching by composer name finds the ordinaire."""
        compositeur = Compositeur.objects.create(nom="Jean Musique")
        ordinaire = Ordinaire.objects.create(
            titre="Messe solennelle",
            compositeur=compositeur,
        )
        Partition.objects.create(
            ordinaire=ordinaire,
            partie_messe=PartieMesse.KYRIE,
            titre="Messe solennelle — Kyrie",
        )

        resp = self.client.get(reverse("search_autocomplete"), {"q": "jean musique"})

        assert resp.status_code == 200
        assert "Messe solennelle" in resp.content.decode()
