from django.test import SimpleTestCase
from psaumes.services.aelf import extract_psalm_from_messes


class UtilsTests(SimpleTestCase):
    def test_extract_psalm_from_messes_with_cantique(self):
        messes_data = {
        'messes': [
            {
                'lectures': [
                    {
                        'type': 'Cantique',
                        'titre': 'Cantique X',
                        'contenu': '<p>Content</p>',
                        'refrain_psalmique': 'Refrain',
                        'ref': 'Ref1',
                    }
                ]
            }
        ]
    }
        res = extract_psalm_from_messes(messes_data)
        self.assertIsNotNone(res)
        self.assertEqual(res['kind'], 'cantique')
        self.assertIn('contenu', res)


    def test_extract_psalm_from_messes_with_psaume(self):
        messes_data = {
        'messes': [
            {
                'lectures': [
                    {
                        'type': 'Lecture du Psaume',
                        'titre': 'Psaume 1',
                        'texte': 'This is a psaume',
                    }
                ]
            }
        ]
    }
        res = extract_psalm_from_messes(messes_data)
        self.assertIsNotNone(res)
        self.assertEqual(res['kind'], 'psaume')
        self.assertIn('contenu', res)

    def test_extract_psalm_preserve_newlines_plain_text(self):
        messes_data = {
            'messes': [
                {
                    'lectures': [
                        {
                            'type': 'Lecture du Psaume',
                            'titre': 'Psaume 1',
                            'texte': 'Line1\nLine2',
                        }
                    ]
                }
            ]
        }
        res = extract_psalm_from_messes(messes_data)
        self.assertIsNotNone(res)
        self.assertIn('contenu', res)
        # Because texte was plain text with newlines, our function should convert it
        # to HTML containing <br> (linebreaksbr) to preserve line breaks in rendering.
        self.assertIn('<br', res['contenu'])

    def test_extract_psalm_preserve_html_content(self):
        messes_data = {
            'messes': [
                {
                    'lectures': [
                        {
                            'type': 'Lecture du Psaume',
                            'titre': 'Psaume 2',
                            'contenu': '<p>Some <em>html</em> content<br/>Line2</p>',
                        }
                    ]
                }
            ]
        }
        res = extract_psalm_from_messes(messes_data)
        self.assertIsNotNone(res)
        self.assertIn('contenu', res)
        self.assertIn('<p>', res['contenu'])


    def test_extract_psalm_from_messes_fallback_refrain(self):
        messes_data = {
        'messes': [
            {
                'lectures': [
                    {
                        'type': 'Lecture',
                        'titre': 'Lecture X',
                        'refrain_psalmique': 'Refrain text',
                    }
                ]
            }
        ]
    }
        res = extract_psalm_from_messes(messes_data)
        self.assertIsNotNone(res)
        self.assertEqual(res['kind'], 'psaume')
        self.assertIn('refrain_psalmique', res)


    def test_extract_psalm_from_messes_none(self):
        res = extract_psalm_from_messes({'messes': []})
        self.assertIsNone(res)
