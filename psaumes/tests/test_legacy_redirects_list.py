from django.test import Client, TestCase, override_settings


@override_settings(
    ALLOWED_HOSTS=['testserver', 'www.cantateo.fr', 'media.cantateo.fr'],
)
class LegacyRedirectListTests(TestCase):
    def setUp(self):
        self.client = Client()

    def assert_redirects_root(self, path):
        response = self.client.get(path, HTTP_HOST='www.cantateo.fr')
        self.assertEqual(response.status_code, 301, f'{path} should 301 redirect')
        self.assertEqual(response['Location'], '/', f'{path} should redirect to /')

    def test_psaumes_146_beni_sois_tu_seigneur(self):
        self.assert_redirects_root('/psaumes/146-beni-sois-tu-seigneur/')

    def test_book_online(self):
        self.assert_redirects_root('/book-online')

    def test_psaume_a_4eme_ordinaire(self):
        self.assert_redirects_root('/psaume-a-dimanche-et-fete/4%C3%A8me-ordinaire')

    def test_psaume_c_ordinaire_31(self):
        self.assert_redirects_root('/psaume-c-dimanche-et-fete/ordinaire-31')

    def test_psaume_c_christ_roi(self):
        self.assert_redirects_root('/psaume-c-dimanche-et-fete/christ-roi')

    def test_psaumes_b_ps_125(self):
        self.assert_redirects_root('/psaumes-b-dimanche-fetes/ps-125-(27-10-2024)')

    def test_psaume_c_alleluia_paques(self):
        self.assert_redirects_root('/psaume-c-dimanche-et-fete/alleluia-p%C3%A2ques')

    def test_psaume_c_saint_joseph(self):
        self.assert_redirects_root('/psaume-c-dimanche-et-fete/saint-joseph')

    def test_psaume_a_2_veillee_pascale(self):
        self.assert_redirects_root('/psaume-a-dimanche-et-fete-2/veill%C3%A9e-pascale-2')

    def test_psaume_a_2_ordinaire_11(self):
        self.assert_redirects_root('/psaume-a-dimanche-et-fete-2/ordinaire-11')

    def test_psaume_a_careme_4(self):
        self.assert_redirects_root('/psaume-a-dimanche-et-fete/car%C3%AAme-4')

    def test_psaume_c_ordinaire_14(self):
        self.assert_redirects_root('/psaume-c-dimanche-et-fete/ordinaire-14')

    def test_psaumes_ps_114(self):
        self.assert_redirects_root('/psaumes/ps-114-(15-09-2024)')

    def test_psaumes_ps_145(self):
        self.assert_redirects_root('/psaumes/ps-145-(08-09-2024)')

    def test_psaume_a_2_22eme_ordinaire(self):
        self.assert_redirects_root('/psaume-a-dimanche-et-fete-2/22%C3%A8me-ordinaire')

    def test_psaume_c_avent_4(self):
        self.assert_redirects_root('/psaume-c-dimanche-et-fete/avent-4')

    def test_psaume_a_2_assomption(self):
        self.assert_redirects_root('/psaume-a-dimanche-et-fete-2/assomption')

    def test_psaume_c_ordinaire_6(self):
        self.assert_redirects_root('/psaume-c-dimanche-et-fete/ordinaire-6')

    def test_psaume_c_2_sainte_trinite(self):
        self.assert_redirects_root('/psaume-c-dimanche-et-fete-2/sainte-trinit%C3%A9')

    def test_properties_acu_1(self):
        self.assert_redirects_root('/properties/acu-1')

    def test_psaume_c_2_ordinaire_31(self):
        self.assert_redirects_root('/psaume-c-dimanche-et-fete-2/ordinaire-31')

    def test_psaume_a_20eme_ordinaire(self):
        self.assert_redirects_root('/psaume-a-dimanche-et-fete/20%C3%A8me-ordinaire')

    def test_psaume_c_sequence_pentecote(self):
        self.assert_redirects_root('/psaume-c-dimanche-et-fete/s%C3%A9quence-pentec%C3%B4te')

    def test_properties_root(self):
        self.assert_redirects_root('/properties')

    def test_properties_bapt_4(self):
        self.assert_redirects_root('/properties/bapt-4')

    def test_psaume_a_27eme_ordinaire(self):
        self.assert_redirects_root('/psaume-a-dimanche-et-fete/27eme-ordinaire')

    def test_properties_bapt_5(self):
        self.assert_redirects_root('/properties/bapt-5')

    def test_psaume_a_2_20eme_ordinaire(self):
        self.assert_redirects_root('/psaume-a-dimanche-et-fete-2/20%C3%A8me-ordinaire')

    def test_media_host_is_not_redirected(self):
        response = self.client.get('/this-path-does-not-exist/', HTTP_HOST='media.cantateo.fr')
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('Location', response)
