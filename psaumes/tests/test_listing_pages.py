import pytest
from django.urls import reverse

from psaumes.models import Psaume, Partition, MomentLiturgique

pytestmark = pytest.mark.django_db


class TestToutesLesPartitions:
    def test_status_ok(self, client):
        url = reverse('toutes_les_partitions')
        resp = client.get(url)
        assert resp.status_code == 200

    def test_contains_cantiques_and_psaumes(self, client):
        # Build a cantique with a partition so the "Cantiques" heading renders
        cantique = Psaume.objects.create(
            nom_psaume='Cantique de Moïse',
            psaume_or_cantique='cantique',
        )
        Partition.objects.create(
            psaume=cantique,
            titre='Test',
        )
        # Build a psaume so the "Psaumes" heading renders
        psaume = Psaume.objects.create(
            nom_psaume='Psaume 1',
            psaume_or_cantique='psaume',
        )
        Partition.objects.create(
            psaume=psaume,
            titre='Test',
        )

        url = reverse('toutes_les_partitions')
        resp = client.get(url)
        html = resp.content.decode()
        assert 'Cantiques' in html
        assert 'Psaumes' in html


class TestCalendrierLiturgique:
    def test_status_ok(self, client):
        url = reverse('calendrier_liturgique')
        resp = client.get(url)
        assert resp.status_code == 200

    def test_temps_listed(self, client):
        psaume = Psaume.objects.create(nom_psaume='Psaume 1')
        partition = Partition.objects.create(psaume=psaume, titre='Test')
        moment = MomentLiturgique.objects.create(
            psaume=psaume, nom_fete='Test Fête'
        )

        url = reverse('calendrier_liturgique')
        resp = client.get(url)
        html = resp.content.decode()
        assert 'Test Fête' in html
