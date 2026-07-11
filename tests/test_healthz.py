"""Read-only readiness coverage for the container health endpoint."""

from pathlib import Path

import config
from services.site_settings import delete_settings, set_settings


def test_healthz_reports_only_a_ready_status(client):
    """A healthy runtime returns a stable response without implementation details."""
    response = client.get('/healthz')

    assert response.status_code == 200
    assert response.get_json() == {'status': 'ok'}


def test_healthz_bypasses_public_visitor_login_requirement(client):
    """Container probes stay available when the public site is visitor-gated."""
    with client.application.app_context():
        set_settings({'public_site_login_required': '1'})
    try:
        response = client.get('/healthz')

        assert response.status_code == 200
        assert response.get_json() == {'status': 'ok'}
    finally:
        with client.application.app_context():
            delete_settings(['public_site_login_required'])


def test_healthz_hides_database_failure_details(client, monkeypatch, tmp_path):
    """A missing SQLite file marks the service unhealthy without leaking its path."""
    missing_database = Path(tmp_path) / 'missing.sqlite3'
    monkeypatch.setattr(config, 'DATABASE', str(missing_database))

    response = client.get('/healthz')

    assert response.status_code == 503
    assert response.get_json() == {'status': 'unhealthy'}
    assert str(missing_database) not in response.get_data(as_text=True)


def test_healthz_rejects_missing_runtime_content_path(client, monkeypatch, tmp_path):
    """A missing mounted content directory also fails readiness without details."""
    missing_upload_directory = Path(tmp_path) / 'missing-chat-uploads'
    monkeypatch.setattr(config, 'CHAT_UPLOAD_DIR', str(missing_upload_directory))

    response = client.get('/healthz')

    assert response.status_code == 503
    assert response.get_json() == {'status': 'unhealthy'}
    assert str(missing_upload_directory) not in response.get_data(as_text=True)
