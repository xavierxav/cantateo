from django.test import TestCase, Client
from django.urls import reverse
from django.core import mail
from django.conf import settings


class ContactFormTests(TestCase):
    def setUp(self):
        self.client = Client()
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

    def test_contact_form_mail_sent(self):
        url = reverse('contact')
        resp = self.client.post(url, {
            'nom': 'Test',
            'email': 'test@example.com',
            'message': 'Hello',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Contact Cantateo de Test', mail.outbox[0].subject)

    def test_contact_form_invalid_email(self):
        url = reverse('contact')
        resp = self.client.post(url, {
            'nom': 'Test',
            'email': 'invalid-email',
            'message': 'Hello',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'email', status_code=200)
