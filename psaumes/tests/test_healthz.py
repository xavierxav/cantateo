import json
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase

from psalm_project.urls import healthz


class HealthzTests(SimpleTestCase):
    def test_healthz_returns_ok(self):
        request = RequestFactory().get('/healthz/')

        with patch('psalm_project.urls.connections') as connections_mock, patch(
            'psalm_project.urls.caches'
        ) as caches_mock:
            connection = Mock()
            connection.ensure_connection.return_value = None
            connections_mock.__getitem__.return_value = connection

            cache = Mock()
            cache.get.return_value = 'ok'
            caches_mock.__getitem__.return_value = cache

            response = healthz(request)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode())
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['database'], 'ok')
        self.assertEqual(payload['cache'], 'ok')
