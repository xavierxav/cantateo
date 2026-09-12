from datetime import date
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse

from psaumes.models import Psaume, Partition


class ViewsTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_blog_renders(self):
        resp = self.client.get(reverse('blog'), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'blog.html')

    def test_index_uses_localdate_for_daily_context(self):
        target = date(2026, 1, 1)
        with patch('psaumes.views.base.timezone.localdate', return_value=target), patch(
            'psaumes.views.base.get_aelf_data',
            return_value={'info': None, 'psalm': None},
        ):
            resp = self.client.get(reverse('index'))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['date'], target.isoformat())


class EcouteAleatoireTests(TestCase):
    """Écoute aléatoire must only surface chants with a real mix (non-synthetic)."""

    def setUp(self):
        self.client = Client()
        self.psaume = Psaume.objects.create(
            nom_psaume='Psaume 23', titre='Le Seigneur est mon berger'
        )

    def _partition(self, *, synthetique):
        return Partition.objects.create(
            psaume=self.psaume,
            titre='Synth' if synthetique else 'Réel',
            audio_mix='audios/test/mix.mp3',
            mp3_synthetiques=synthetique,
        )

    def test_excludes_synthetic_partitions(self):
        real = self._partition(synthetique=False)
        self._partition(synthetique=True)
        # Only one eligible (non-synth) partition -> deterministic pick.
        for _ in range(5):
            resp = self.client.get(reverse('ecoute_aleatoire'))
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.context['partition'].pk, real.pk)

    def test_only_synthetic_shows_empty_state(self):
        self._partition(synthetique=True)
        resp = self.client.get(reverse('ecoute_aleatoire'))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.context['psaume'])
        self.assertIn(b'Aucun mix audio disponible', resp.content)

    def test_mix_required(self):
        # Non-synth but no mix -> excluded.
        Partition.objects.create(psaume=self.psaume, titre='Sans mix')
        resp = self.client.get(reverse('ecoute_aleatoire'))
        self.assertIsNone(resp.context['psaume'])
