from django.test import Client, TestCase, override_settings


@override_settings(
    ALLOWED_HOSTS=['testserver', 'www.cantateo.fr', 'media.cantateo.fr'],
)
class RedirectTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_legacy_psaume_url_redirects_to_root(self):
        response = self.client.get(
            '/psaumes/145-beni-sois-tu-seigneur/',
            HTTP_HOST='www.cantateo.fr',
        )

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/')

    def test_dev_host_redirects_to_canonical_site_preserving_path_and_query(self):
        response = self.client.get(
            '/blog/?x=1',
            HTTP_HOST='dev.cantateo.fr',
        )

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], 'https://www.cantateo.fr/blog/?x=1')

    def test_media_host_is_not_redirected(self):
        response = self.client.get(
            '/this-path-does-not-exist/',
            HTTP_HOST='media.cantateo.fr',
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn('Location', response)
