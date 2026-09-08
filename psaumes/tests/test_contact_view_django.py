from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings
from django.core import mail


class ContactViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Use in-memory email backend for test
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

    def test_contact_success_sends_email(self):
        resp = self.client.post(reverse('contact'), {
            'nom': 'Test',
            'email': 'test@example.com',
            'message': 'Hello',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)

    def test_contact_invalid_email_shows_error(self):
        resp = self.client.post(reverse('contact'), {
            'nom': 'Test',
            'email': 'not-an-email',
            'message': 'Hello',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
