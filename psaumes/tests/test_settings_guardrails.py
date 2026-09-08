import importlib
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured


PRODUCTION_MODULE = 'psalm_project.settings.production'


def _set_required_prod_env(monkeypatch):
    monkeypatch.setenv('ALLOWED_HOSTS', 'www.cantateo.fr')
    monkeypatch.setenv('CSRF_TRUSTED_ORIGINS', 'https://www.cantateo.fr')
    monkeypatch.setenv('DJANGO_SECRET_KEY', 'test-secret-key')
    monkeypatch.setenv('CONTACT_EMAIL', 'contact@example.com')
    monkeypatch.setenv('TURNSTILE_SITE_KEY', 'turnstile-site')
    monkeypatch.setenv('TURNSTILE_SECRET_KEY', 'turnstile-secret')


def _reload_production():
    sys.modules.pop(PRODUCTION_MODULE, None)
    return importlib.import_module(PRODUCTION_MODULE)


def test_production_requires_allowed_hosts(monkeypatch):
    _set_required_prod_env(monkeypatch)
    monkeypatch.delenv('ALLOWED_HOSTS', raising=False)

    with pytest.raises(ImproperlyConfigured):
        _reload_production()


def test_production_requires_contact_email(monkeypatch):
    _set_required_prod_env(monkeypatch)
    monkeypatch.delenv('CONTACT_EMAIL', raising=False)

    with pytest.raises(ImproperlyConfigured):
        _reload_production()


def test_production_requires_turnstile_secret(monkeypatch):
    _set_required_prod_env(monkeypatch)
    monkeypatch.delenv('TURNSTILE_SECRET_KEY', raising=False)

    with pytest.raises(ImproperlyConfigured):
        _reload_production()


def test_production_sets_security_flags(monkeypatch):
    _set_required_prod_env(monkeypatch)
    module = _reload_production()

    assert module.SECURE_HSTS_SECONDS == 31536000
    assert module.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
    assert module.SECURE_HSTS_PRELOAD is True
    assert module.X_FRAME_OPTIONS == 'DENY'
    assert module.SECURE_REFERRER_POLICY == 'strict-origin-when-cross-origin'
    assert module.SECURE_CROSS_ORIGIN_OPENER_POLICY == 'same-origin'
    assert module.SESSION_COOKIE_SAMESITE == 'Lax'
    assert module.CSRF_COOKIE_SAMESITE == 'Lax'
    assert "'unsafe-inline'" not in module.CONTENT_SECURITY_POLICY.split('script-src', 1)[1].split(';', 1)[0]
    assert "'nonce-{csp_nonce}'" in module.CONTENT_SECURITY_POLICY
