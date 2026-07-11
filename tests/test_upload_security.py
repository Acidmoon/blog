"""Focused boundary tests for admin and visitor upload handling."""

from __future__ import annotations

import io
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from werkzeug.datastructures import FileStorage

import config
from models import get_db
from services.access_settings import MAX_CHAT_FILE_UPLOAD_MB, save_access_settings
from services.chat_sessions import ChatFileUploadError, create_chat_session, save_chat_upload


PNG_BYTES = (
    b'\x89PNG\r\n\x1a\n'
    b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
)


class NonSeekableBytesIO(io.BytesIO):
    """Exercise the one-pass path instead of relying on a seekable test stream."""

    def seek(self, *args, **kwargs):
        raise OSError('stream is intentionally non-seekable')


def _all_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return [candidate for candidate in path.rglob('*') if candidate.is_file()]


def _create_chat_session_for_upload() -> tuple[int, int]:
    """Create only the rows required by a chat attachment without request auth."""
    connection = get_db()
    username = f'upload{uuid.uuid4().hex[:12]}'
    cursor = connection.execute(
        """
        INSERT INTO visitor_users (username, password_hash, created_at)
        VALUES (?, ?, ?)
        """,
        (username, 'test-only-password-hash', datetime.now().isoformat(timespec='seconds')),
    )
    connection.commit()
    session = create_chat_session(cursor.lastrowid)
    return cursor.lastrowid, session['id']


def _chat_upload_settings(*, max_mb: int = 1) -> dict:
    return {
        'chat_file_upload_enabled': True,
        'chat_file_max_mb': max_mb,
        'chat_user_storage_mb': 100,
        'chat_session_file_limit': 5,
    }


def test_admin_upload_accepts_verified_image_and_rejects_mime_spoof(login, monkeypatch, tmp_path):
    upload_directory = tmp_path / 'admin-images'
    monkeypatch.setattr(config, 'UPLOAD_DIR', str(upload_directory))

    success = login.post(
        '/admin/upload',
        data={'file': (io.BytesIO(PNG_BYTES), 'cover.PNG', 'image/png')},
    )
    assert success.status_code == 200
    payload = success.get_json()
    assert set(payload) == {'url'}
    assert payload['url'].startswith('/static/images/')
    assert len(_all_files(upload_directory)) == 1

    spoofed = login.post(
        '/admin/upload',
        data={'file': (io.BytesIO(PNG_BYTES), 'cover.png', 'application/pdf')},
    )
    assert spoofed.status_code == 400
    assert '图片类型' in spoofed.get_json()['error']
    assert len(_all_files(upload_directory)) == 1


def test_admin_upload_stream_limit_cleans_temporary_file(login, monkeypatch, tmp_path):
    upload_directory = tmp_path / 'admin-images'
    monkeypatch.setattr(config, 'UPLOAD_DIR', str(upload_directory))
    monkeypatch.setattr('services.media_uploads.MAX_ADMIN_IMAGE_BYTES', len(PNG_BYTES) - 1)

    response = login.post(
        '/admin/upload',
        data={'file': (io.BytesIO(PNG_BYTES), 'too-large.png', 'image/png')},
    )

    assert response.status_code == 400
    assert not _all_files(upload_directory)


def test_chat_upload_streams_nonseekable_text_and_normalizes_filename(app, monkeypatch, tmp_path):
    upload_root = tmp_path / 'chat-uploads'
    monkeypatch.setattr(config, 'CHAT_UPLOAD_DIR', str(upload_root))
    monkeypatch.setattr('services.chat_sessions.get_access_settings', lambda: _chat_upload_settings())

    with app.app_context():
        user_id, session_id = _create_chat_session_for_upload()
        uploaded = save_chat_upload(
            user_id,
            session_id,
            FileStorage(
                stream=NonSeekableBytesIO('第一行\n第二行'.encode('utf-8')),
                filename=r'C:\\fakepath\\notes.md',
                content_type='text/markdown',
            ),
        )
        row = get_db().execute(
            "SELECT original_name, stored_path, mime_type, extracted_text FROM chat_files WHERE id=?",
            (uploaded['id'],),
        ).fetchone()

    assert uploaded['name'] == 'notes.md'
    assert uploaded['mime_type'] == 'text/markdown'
    assert uploaded['has_text'] is True
    assert row['original_name'] == 'notes.md'
    assert row['mime_type'] == 'text/markdown'
    assert row['extracted_text'] == '第一行\n第二行'
    assert (upload_root / row['stored_path']).read_text(encoding='utf-8') == '第一行\n第二行'


def test_chat_upload_rejects_mismatched_content_and_cleans_staging(app, monkeypatch, tmp_path):
    upload_root = tmp_path / 'chat-uploads'
    monkeypatch.setattr(config, 'CHAT_UPLOAD_DIR', str(upload_root))
    monkeypatch.setattr('services.chat_sessions.get_access_settings', lambda: _chat_upload_settings())

    with app.app_context():
        user_id, session_id = _create_chat_session_for_upload()
        with pytest.raises(ChatFileUploadError, match='图片内容'):
            save_chat_upload(
                user_id,
                session_id,
                FileStorage(
                    stream=io.BytesIO(b'<svg><script>alert(1)</script></svg>'),
                    filename='pretend.png',
                    content_type='image/png',
                ),
            )
        with pytest.raises(ChatFileUploadError, match='大小限制'):
            save_chat_upload(
                user_id,
                session_id,
                FileStorage(
                    stream=io.BytesIO(b'%PDF-' + b'x' * (1024 * 1024)),
                    filename='too-large.pdf',
                    content_type='application/pdf',
                ),
            )
        row_count = get_db().execute(
            'SELECT COUNT(*) AS total FROM chat_files WHERE session_id=?',
            (session_id,),
        ).fetchone()['total']

    assert row_count == 0
    assert not _all_files(upload_root)


def test_chat_upload_removes_file_when_metadata_insert_fails(app, monkeypatch, tmp_path):
    upload_root = tmp_path / 'chat-uploads'
    monkeypatch.setattr(config, 'CHAT_UPLOAD_DIR', str(upload_root))
    monkeypatch.setattr('services.chat_sessions.get_access_settings', lambda: _chat_upload_settings())
    trigger_name = f'fail_chat_upload_{uuid.uuid4().hex}'

    with app.app_context():
        user_id, session_id = _create_chat_session_for_upload()
        connection = get_db()
        connection.execute(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON chat_files
            BEGIN
                SELECT RAISE(ABORT, 'forced chat upload failure');
            END
            """
        )
        connection.commit()
        try:
            with pytest.raises(ChatFileUploadError, match='元数据保存失败'):
                save_chat_upload(
                    user_id,
                    session_id,
                    FileStorage(
                        stream=io.BytesIO(b'%PDF-1.7\nbody'),
                        filename='safe.pdf',
                        content_type='application/pdf',
                    ),
                )
        finally:
            connection.execute(f'DROP TRIGGER IF EXISTS {trigger_name}')
            connection.commit()
        row_count = connection.execute(
            'SELECT COUNT(*) AS total FROM chat_files WHERE session_id=?',
            (session_id,),
        ).fetchone()['total']

    assert row_count == 0
    assert not _all_files(upload_root)


def test_access_settings_rejects_unbounded_chat_file_limit(app):
    with app.app_context():
        with pytest.raises(ValueError, match='不能超过'):
            save_access_settings({
                'chat_file_max_mb': str(MAX_CHAT_FILE_UPLOAD_MB + 1),
            })
