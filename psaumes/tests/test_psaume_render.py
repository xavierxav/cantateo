from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from psaumes.models import Compositeur, Psaume, Partition, MomentLiturgique
from django.core.cache import cache
import re


from django.test import override_settings


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class PsaumeRenderTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_index_page_loads(self):
        """Test that the index page loads successfully."""
        resp = self.client.get(reverse('index'), follow=True)
        self.assertEqual(resp.status_code, 200)

    def test_compositeur_creation(self):
        """Test creating a composer."""
        compositeur = Compositeur.objects.create(nom='Jean Dupont')
        self.assertEqual(str(compositeur), 'Jean Dupont')

    def test_psaume_with_compositeur(self):
        """Test creating a psalm with a composer."""
        compositeur = Compositeur.objects.create(nom='Jean Dupont')
        psaume = Psaume.objects.create(
            nom_psaume="Psaume 23",
            titre='Le Seigneur est mon berger'
        )
        partition = Partition.objects.create(
            psaume=psaume,
            compositeur=compositeur,
            refrain='Le Seigneur est mon berger, rien ne saurait me manquer.'
        )
        self.assertEqual(partition.compositeur.nom, 'Jean Dupont')

    def test_moment_dimanche(self):
        """Test creating a Sunday liturgical moment."""
        psaume = Psaume.objects.create(nom_psaume="Psaume 23", titre='Test')
        moment = MomentLiturgique.objects.create(
            psaume=psaume,
            temps='CAREME',
            semaine=4,
            jour=0,  # Dimanche
            annee='A'
        )
        self.assertIn('dimanche', str(moment))
        self.assertIn('Carême', str(moment))
        self.assertIn("l'année A", str(moment))

    def test_moment_semaine(self):
        """Test creating a weekday liturgical moment."""
        psaume = Psaume.objects.create(nom_psaume="Psaume 85", titre='Test')
        moment = MomentLiturgique.objects.create(
            psaume=psaume,
            temps='AVENT',
            semaine=2,
            jour=3,  # Mercredi
            parite='P'
        )
        self.assertIn('Mercredi', str(moment))
        self.assertIn('Avent', str(moment))
        self.assertIn('paire', str(moment))

    def test_moment_fete(self):
        """Test creating a feast liturgical moment."""
        psaume = Psaume.objects.create(nom_psaume="Psaume 96", titre='Test')
        moment = MomentLiturgique.objects.create(
            psaume=psaume,
            nom_fete='Nativité du Seigneur'
        )
        self.assertEqual(str(moment), 'Nativité du Seigneur')

    def test_moment_dimanche_validation_rejects_jour(self):
        """Test that Sunday moments reject jour field."""
        psaume = Psaume.objects.create(nom_psaume="Psaume 23", titre='Test')
        moment = MomentLiturgique(
            psaume=psaume,
            temps='CAREME',
            semaine=4,
            annee='A',
            jour=1  # Should not be set for Sunday
        )
        with self.assertRaises(ValidationError):
            moment.full_clean()

    def test_moment_semaine_validation_rejects_annee(self):
        """Test that weekday moments reject annee field."""
        psaume = Psaume.objects.create(nom_psaume="Psaume 85", titre='Test')
        moment = MomentLiturgique(
            psaume=psaume,
            temps='AVENT',
            semaine=2,
            jour=3,
            parite='P',
            annee='A'  # Should not be set for weekday
        )
        with self.assertRaises(ValidationError):
            moment.full_clean()

    def test_moment_fete_validation_rejects_other_fields(self):
        """Test that feast moments reject other fields."""
        psaume = Psaume.objects.create(nom_psaume="Psaume 96", titre='Test')
        moment = MomentLiturgique(
            psaume=psaume,
            nom_fete='Nativité du Seigneur',
            temps='NOEL'  # Should not be set for feast
        )
        with self.assertRaises(ValidationError):
            moment.full_clean()

    def test_index_shows_aelf_psaume_linebreaks(self):
        """Test AELF psalm display with line breaks."""
        today = timezone.now().date()
        ref = 'Ref P. 1'
        data = {
            'messes': [
                {'lectures': [{'type': 'Lecture du psaume', 'titre': 'Psaume', 'contenu': 'Ligne A\nLigne B\nLigne C', 'ref': ref}]}
            ]
        }
        # Le cache utilisera maintenant LocMemCache grâce au décorateur
        cache.set(f'aelf_messes_{today}', data, 60)
        cache.set(f'aelf_infos_{today}', {}, 60)
        resp = self.client.get(reverse('index'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '<br', html=False)

    def test_search_by_numero(self):
        """Test searching psalms by number via autocomplete API instead of index."""
        psaume = Psaume.objects.create(
            nom_psaume='Psaume 150',
            titre='Louez le Seigneur'
        )
        Partition.objects.create(psaume=psaume, refrain='Alléluia !')
        # Utilisation du chemin direct car le nom de l'URL est introuvable
        url = '/api/search-autocomplete/'
        resp = self.client.get(url, {'q': '150'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '150')

    def test_search_by_refrain(self):
        """Test searching psalms by refrain text via autocomplete API."""
        psaume = Psaume.objects.create(
            nom_psaume='Psaume 23',
            titre='Le Seigneur est mon berger'
        )
        Partition.objects.create(psaume=psaume, refrain='Rien ne saurait me manquer')
        url = '/api/search-autocomplete/'
        resp = self.client.get(url, {'q': 'manquer'})
        self.assertEqual(resp.status_code, 200)
        # On vérifie la présence du numéro ou du titre dans le fragment renvoyé par HTMX
        self.assertContains(resp, '23')
