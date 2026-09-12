from django.test import SimpleTestCase
from psaumes.services.aelf import extract_psalm_from_messes


class UtilsTests(SimpleTestCase):
    def test_extract_cantique(self):
        messes_data = {
            'messes': [
                {'lectures': [{'type': 'Cantique', 'titre': 'Cantique X', 'contenu': '<p>Content</p>'}]}
            ]
        }
        res = extract_psalm_from_messes(messes_data)
        self.assertIsNotNone(res)
        self.assertEqual(res['kind'], 'cantique')

    def test_extract_psaume(self):
        messes_data = {'messes': [{'lectures': [{'type': 'Lecture du psaume', 'titre': 'Psaume', 'texte': 'xyz'}]}]}
        res = extract_psalm_from_messes(messes_data)
        self.assertIsNotNone(res)
        self.assertEqual(res['kind'], 'psaume')

    def test_extract_psaume_linebreaks(self):
        messes_data = {
            'messes': [
                {'lectures': [{'type': 'Lecture du psaume', 'titre': 'Psaume', 'contenu': 'Ligne X\nLigne Y'}]}
            ]
        }
        res = extract_psalm_from_messes(messes_data)
        self.assertIsNotNone(res)
        # contenue_html should have <br/> injected
        self.assertIn('<br', res['contenu'])

    def test_extract_psaume_sanitizes_html(self):
        messes_data = {
            'messes': [
                {'lectures': [{'type': 'Lecture du psaume', 'titre': 'Psaume', 'contenu': '<p>OK</p><script>alert(1)</script>'}]}
            ]
        }
        res = extract_psalm_from_messes(messes_data)
        self.assertIsNotNone(res)
        # script tag should be removed by sanitization
        self.assertNotIn('<script', res['contenu'])
