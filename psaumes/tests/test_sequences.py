from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from psaumes.models import MomentLiturgique, Psaume
from psaumes.services.liturgie.calculs_paques import (
    date_fete_dieu,
    date_trinite,
    annee_liturgique,
)


class SequenceSpecialFeastTests(TestCase):
    """Tests for Séquence rendering on Saint-Sacrement and Sainte Trinité."""

    @classmethod
    def setUpTestData(cls):
        cls.annee = annee_liturgique(date_fete_dieu(2026))

        cls.ss_psaume = Psaume.objects.create(
            nom_psaume='Psaume 147',
            titre='Glorifie le Seigneur, Jérusalem',
            slug='psaume-147-test',
        )
        MomentLiturgique.objects.update_or_create(
            nom_fete='Saint-Sacrement du Corps et du Sang du Christ',
            annee=cls.annee,
            defaults={'psaume': cls.ss_psaume},
        )

        cls.seq_psaume = Psaume.objects.create(
            nom_psaume='Cantique Séquence du Saint Sacrement',
            titre='Le voici, le pain des anges',
            slug='le-voici-le-pain-des-anges',
        )
        MomentLiturgique.objects.update_or_create(
            nom_fete='Séquence Saint-Sacrement',
            annee=cls.annee,
            defaults={'psaume': cls.seq_psaume},
        )

        cls.tr_psaume = Psaume.objects.create(
            nom_psaume='Psaume 8',
            titre='Qu\'elle est grande ta majesté',
            slug='psaume-8-test',
        )
        MomentLiturgique.objects.update_or_create(
            nom_fete='Sainte Trinité',
            annee=cls.annee,
            defaults={'psaume': cls.tr_psaume},
        )

    def _get(self, target_date):
        with patch('psaumes.views.base.get_aelf_data', return_value={'info': {}, 'psalm': None}):
            return self.client.get(reverse('index'), {'date': target_date.isoformat()})

    def test_saint_sacrement_shows_gradual_and_clickable_sequence(self):
        response = self._get(date_fete_dieu(2026))
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('Saint-Sacrement', html)
        self.assertIn('Séquence', html)
        self.assertIn('Psaume', html)
        self.assertIn(reverse('psaume_detail', kwargs={
            'pk': self.seq_psaume.pk,
            'slug': self.seq_psaume.slug,
        }), html)
        self.assertIn('Glorifie le Seigneur', html)

    def test_trinite_shows_gradual_and_placeholder_sequence(self):
        response = self._get(date_trinite(2026))
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('Sainte Trinité', html)
        self.assertIn('Séquence', html)
        self.assertIn('À venir', html)
        self.assertIn('ta majesté', html)
