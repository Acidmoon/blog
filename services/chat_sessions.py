"""Visitor-owned AI chat sessions, messages, and attachments."""

from __future__ import annotations

import mimetypes
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from werkzeug.utils import secure_filename

import config
from models import get_db
from services.access_settings import get_access_settings
from services.ai_chat import MAX_CHAT_MESSAGES, MAX_USER_MESSAGE_CHARS, ChatValidationError, render_chat_markdown


ALLOWED_UPLOAD_EXTENSIONS = {'txt', 'md', 'pdf', 'docx', 'png', 'jpg', 'jpeg', 'webp'}
TEXT_UPLOAD_EXTENSIONS = {'txt', 'md'}
MAX_FILE_TEXT_CHARS = 12000


class ChatSessionError(ValueError):
    pass


class ChatFileUploadError(ValueError):
    pass


def _now_text() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _row_to_session(row) -> dict:
    return {
        'id': row['id'],
        'title': row['title'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
    }


def _row_to_message(row) -> dict:
    return {
        'id': row['id'],
        'role': row['role'],
        'content': row['content'],
        'html': row['rendered_html'] or '',
        'created_at': row['created_at'],
    }


def _row_to_file(row) -> dict:
    return {
        'id': row['id'],
        'name': row['original_name'],
        'mime_type': row['mime_type'] or '',
        'size_bytes': row['size_bytes'],
        'has_text': bool(row['extracted_text']),
        'created_at': row['created_at'],
    }


def build_session_title(content: str) -> str:
    title = ' '.join(str(content or '').strip().split())
    if not title:
        return '新的对话'
    return title[:32]


def create_chat_session(user_id: int, title: str = '新的对话') -> dict:
    now = _now_text()
    conn = get_db()
    cur = conn.execute(
        """
        INSERT INTO chat_sessions (user_id, title, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, title or '新的对话', now, now),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, title, created_at, updated_at FROM chat_sessions WHERE id=?",
        (cur.lastrowid,),
    ).fetchone()
    return _row_to_session(row)


def list_chat_sessions(user_id: int) -> list[dict]:
    rows = get_db().execute(
        """
        SELECT id, title, created_at, updated_at
        FROM chat_sessions
        WHERE user_id=?
        ORDER BY updated_at DESC, id DESC
        """,
        (user_id,),
    ).fetchall()
    return [_row_to_session(row) for row in rows]


def get_chat_session(user_id: int, session_id: int) -> dict | None:
    row = get_db().execute(
        """
        SELECT id, title, created_at, updated_at
        FROM chat_sessions
        WHERE user_id=? AND id=?
        """,
        (user_id, session_id),
    ).fetchone()
    return _row_to_session(row) if row else None


def require_chat_session(user_id: int, session_id: int) -> dict:
    session = get_chat_session(user_id, session_id)
    if not session:
        raise ChatSessionError('对话不存在')
    return session


def delete_chat_session(user_id: int, session_id: int) -> None:
    require_chat_session(user_id, session_id)
    conn = get_db()
    cur = conn.execute(
        "DELETE FROM chat_sessions WHERE user_id=? AND id=?",
        (user_id, session_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        raise ChatSessionError('对话不存在')
    shutil.rmtree(_upload_root() / str(user_id) / str(session_id), ignore_errors=True)


def list_chat_messages(user_id: int, session_id: int) -> list[dict]:
    require_chat_session(user_id, session_id)
    rows = get_db().execute(
        """
        SELECT id, role, content, rendered_html, created_at
        FROM chat_messages
        WHERE session_id=?
        ORDER BY created_at ASC, id ASC
        """,
        (session_id,),
    ).fetchall()
    return [_row_to_message(row) for row in rows]


def list_chat_files(user_id: int, session_id: int) -> list[dict]:
    require_chat_session(user_id, session_id)
    rows = get_db().execute(
        """
        SELECT id, original_name, mime_type, size_bytes, extracted_text, created_at
        FROM chat_files
        WHERE session_id=?
        ORDER BY created_at ASC, id ASC
        """,
        (session_id,),
    ).fetchall()
    return [_row_to_file(row) for row in rows]


def ensure_session_for_message(user_id: int, session_id: int | None, content: str) -> dict:
    if session_id:
        return require_chat_session(user_id, session_id)
    return create_chat_session(user_id, build_session_title(content))


def append_chat_message(session_id: int, role: str, content: str) -> dict:
    role = str(role or '').strip()
    content = str(content or '').strip()
    if role not in {'user', 'assistant'}:
        raise ChatValidationError('消息角色无效')
    if not content:
        raise ChatValidationError('消息内容不能为空')
    if role == 'user' and len(content) > MAX_USER_MESSAGE_CHARS:
        raise ChatValidationError(f'单条用户消息不能超过 {MAX_USER_MESSAGE_CHARS} 字符')
    html = render_chat_markdown(content) if role == 'assistant' else ''
    now = _now_text()
    conn = get_db()
    cur = conn.execute(
        """
        INSERT INTO chat_messages (session_id, role, content, rendered_html, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, role, content, html, now),
    )
    conn.execute(
        "UPDATE chat_sessions SET updated_at=? WHERE id=?",
        (now, session_id),
    )
    conn.commit()
    return {
        'id': cur.lastrowid,
        'role': role,
        'content': content,
        'html': html,
        'created_at': now,
    }


def recent_model_messages(session_id: int) -> list[dict[str, str]]:
    rows = get_db().execute(
        """
        SELECT role, content
        FROM chat_messages
        WHERE session_id=?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (session_id, MAX_CHAT_MESSAGES),
    ).fetchall()
    messages = [{'role': row['role'], 'content': row['content']} for row in reversed(rows)]
    if not messages or messages[-1]['role'] != 'user':
        raise ChatValidationError('最后一条消息必须来自用户')
    if len(messages) > MAX_CHAT_MESSAGES:
        messages = messages[-MAX_CHAT_MESSAGES:]
    return messages


def session_file_context(session_id: int) -> str:
    rows = get_db().execute(
        """
        SELECT original_name, extracted_text
        FROM chat_files
        WHERE session_id=? AND extracted_text!=''
        ORDER BY created_at ASC, id ASC
        """,
        (session_id,),
    ).fetchall()
    parts: list[str] = []
    for row in rows:
        text = str(row['extracted_text'] or '').strip()
        if not text:
            continue
        parts.append(f"文件《{row['original_name']}》片段：\n{text[:MAX_FILE_TEXT_CHARS]}")
    return '\n\n'.join(parts)


def _upload_root() -> Path:
    return Path(getattr(config, 'CHAT_UPLOAD_DIR', Path(config.DATA_DIR) / 'chat_uploads'))


def _extension(filename: str) -> str:
    if '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[-1].lower()


def _read_text_upload(stream: BinaryIO, ext: str) -> str:
    if ext not in TEXT_UPLOAD_EXTENSIONS:
        return ''
    raw = stream.read(MAX_FILE_TEXT_CHARS + 1)
    stream.seek(0)
    return raw.decode('utf-8', errors='ignore')[:MAX_FILE_TEXT_CHARS]


def _user_storage_bytes(user_id: int) -> int:
    row = get_db().execute(
        """
        SELECT COALESCE(SUM(cf.size_bytes), 0) AS total
        FROM chat_files cf
        JOIN chat_sessions cs ON cs.id = cf.session_id
        WHERE cs.user_id=?
        """,
        (user_id,),
    ).fetchone()
    return int(row['total'] or 0)


def save_chat_upload(user_id: int, session_id: int, file_storage) -> dict:
    require_chat_session(user_id, session_id)
    settings = get_access_settings()
    if not settings['chat_file_upload_enabled']:
        raise ChatFileUploadError('文件上传未启用')
    if not file_storage or not file_storage.filename:
        raise ChatFileUploadError('请选择文件')

    original_name = file_storage.filename
    ext = _extension(original_name)
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ChatFileUploadError('不支持的文件类型')

    file_storage.stream.seek(0, os.SEEK_END)
    size_bytes = file_storage.stream.tell()
    file_storage.stream.seek(0)
    max_file_bytes = settings['chat_file_max_mb'] * 1024 * 1024
    if size_bytes > max_file_bytes:
        raise ChatFileUploadError(f'单个文件不能超过 {settings["chat_file_max_mb"]}MB')

    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) AS total FROM chat_files WHERE session_id=?",
        (session_id,),
    ).fetchone()
    if int(row['total'] or 0) >= settings['chat_session_file_limit']:
        raise ChatFileUploadError(f'单个对话最多上传 {settings["chat_session_file_limit"]} 个文件')

    if _user_storage_bytes(user_id) + size_bytes > settings['chat_user_storage_mb'] * 1024 * 1024:
        raise ChatFileUploadError(f'当前用户文件空间不能超过 {settings["chat_user_storage_mb"]}MB')

    upload_dir = _upload_root() / str(user_id) / str(session_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_original = secure_filename(original_name) or f'upload.{ext}'
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    stored_path = upload_dir / stored_name
    extracted_text = _read_text_upload(file_storage.stream, ext)
    file_storage.save(stored_path)
    mime_type = file_storage.mimetype or mimetypes.guess_type(safe_original)[0] or ''
    rel_path = str(stored_path.relative_to(_upload_root()))
    now = _now_text()
    cur = conn.execute(
        """
        INSERT INTO chat_files (session_id, original_name, stored_path, mime_type, size_bytes, extracted_text, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, original_name, rel_path, mime_type, size_bytes, extracted_text, now),
    )
    conn.execute(
        "UPDATE chat_sessions SET updated_at=? WHERE id=?",
        (now, session_id),
    )
    conn.commit()
    return {
        'id': cur.lastrowid,
        'name': original_name,
        'mime_type': mime_type,
        'size_bytes': size_bytes,
        'has_text': bool(extracted_text),
        'created_at': now,
    }
