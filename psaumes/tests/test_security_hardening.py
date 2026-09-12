import json
import re

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from psalm_project.security import ContentSecurityPolicyMiddleware
from psaumes.models import Partition, Psaume
from psaumes.models.validators import validate_mp3_upload, validate_pdf_upload


def test_csp_middleware_adds_nonce_header():
    request = RequestFactory().get('/')
    middleware = ContentSecurityPolicyMiddleware(lambda req: HttpResponse('ok'))

    with override_settings(CONTENT_SECURITY_POLICY="script-src 'self' 'nonce-{csp_nonce}';"):
        response = middleware(request)

    assert hasattr(request, 'csp_nonce')
    assert f"'nonce-{request.csp_nonce}'" in response['Content-Security-Policy']


def test_upload_validators_reject_wrong_content():
    with pytest.raises(ValidationError):
        validate_pdf_upload(SimpleUploadedFile('partition.pdf', b'not a pdf'))

    with pytest.raises(ValidationError):
        validate_mp3_upload(SimpleUploadedFile('audio.mp3', b'not an mp3'))


@pytest.mark.django_db
def test_search_autocomplete_rate_limit():
    cache.clear()
    client = Client(REMOTE_ADDR='198.51.100.10')

    with override_settings(RATE_LIMITS={'search_autocomplete': (1, 60)}):
        first = client.get(reverse('search_autocomplete'), {'q': 'psaume'})
        second = client.get(reverse('search_autocomplete'), {'q': 'psaume'})

    assert first.status_code == 200
    assert second.status_code == 429


class StructuredDataTests(TestCase):
    def test_psaume_detail_structured_data_is_valid_json(self):
        psaume = Psaume.objects.create(nom_psaume='Psaume 23', titre='Berger')
        partition = Partition.objects.create(psaume=psaume, titre='Le Seigneur')

        response = self.client.get(psaume.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        scripts = re.findall(
            r'<script type="application/ld\+json"[^>]*>\s*(.*?)\s*</script>',
            response.content.decode(),
            flags=re.S,
        )
        self.assertGreaterEqual(len(scripts), 1)
        for payload in scripts:
            json.loads(payload)
