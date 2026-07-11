"""Startup guards for production secrets and checked-in example values."""

import pytest

import config


def _use_production_mode(monkeypatch, secret_key: str, admin_password: str) -> None:
    """Set module and environment values exactly as a non-test process would use them."""
    monkeypatch.delenv('BLOG_TESTING', raising=False)
    monkeypatch.setenv('BLOG_SECRET_KEY', secret_key)
    monkeypatch.setenv('ADMIN_PASSWORD', admin_password)
    monkeypatch.delenv('BLOG_ADMIN_PASSWORD', raising=False)
    monkeypatch.setattr(config, 'SECRET_KEY', secret_key)
    monkeypatch.setattr(config, 'ADMIN_PASSWORD', admin_password)


def test_production_rejects_checked_in_example_credentials(monkeypatch):
    """Copying `.env.example` unchanged cannot start the public application."""
    _use_production_mode(monkeypatch, config.EXAMPLE_SECRET_KEY, config.EXAMPLE_ADMIN_PASSWORD)

    with pytest.raises(RuntimeError, match='BLOG_SECRET_KEY'):
        config.validate_security_config()


def test_production_requires_a_non_default_admin_password(monkeypatch):
    """A valid secret key cannot compensate for the built-in admin password."""
    _use_production_mode(monkeypatch, 'safe-secret-key-for-test', config.INSECURE_ADMIN_PASSWORD)

    with pytest.raises(RuntimeError, match='ADMIN_PASSWORD'):
        config.validate_security_config()


def test_production_accepts_explicit_non_placeholder_credentials(monkeypatch):
    """Explicit non-default deployment credentials keep the normal startup path working."""
    _use_production_mode(monkeypatch, 'safe-secret-key-for-test', 'safe-admin-password-for-test')

    config.validate_security_config()
