"""Visitor-owned AI chat sessions, messages, and attachments."""

from __future__ import annotations

import codecs
import shutil
import sqlite3
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

import config
from models import get_db
from services.access_settings import MAX_CHAT_FILE_UPLOAD_MB, get_access_settings
from services.ai_chat import MAX_CHAT_MESSAGES, MAX_USER_MESSAGE_CHARS, ChatValidationError, render_chat_markdown
from services.upload_validation import (
    UploadStorageError,
    UploadValidationError,
    cleanup_upload_file,
    normalize_upload_filename,
    sniff_image_mime_type,
    stage_upload,
    validate_reported_mime,
)


ALLOWED_UPLOAD_EXTENSIONS = {'txt', 'md', 'pdf', 'docx', 'png', 'jpg', 'jpeg', 'webp'}
TEXT_UPLOAD_EXTENSIONS = {'txt', 'md'}
MAX_FILE_TEXT_CHARS = 12000
MAX_FILE_TEXT_CAPTURE_BYTES = MAX_FILE_TEXT_CHARS * 4 + 4
CHAT_UPLOAD_MULTIPART_OVERHEAD_BYTES = 64 * 1024
DEFAULT_CHAT_MESSAGE_PAGE_SIZE = 100
MAX_CHAT_MESSAGE_PAGE_SIZE = 200
CHAT_UPLOAD_MIME_TYPES = {
    'txt': {'text/plain'},
    'md': {'text/plain', 'text/markdown', 'text/x-markdown'},
    'pdf': {'application/pdf'},
    'docx': {'application/vnd.openxmlformats-officedocument.wordprocessingml.document'},
    'png': {'image/png'},
    'jpg': {'image/jpeg'},
    'jpeg': {'image/jpeg'},
    'webp': {'image/webp'},
}


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


def update_chat_session_title(user_id: int, session_id: int, title: str) -> dict:
    require_chat_session(user_id, session_id)
    cleaned_title = ' '.join(str(title or '').strip().split())[:32]
    if not cleaned_title:
        raise ChatSessionError('对话标题不能为空')
    now = _now_text()
    conn = get_db()
    conn.execute(
        """
        UPDATE chat_sessions
        SET title=?, updated_at=?
        WHERE user_id=? AND id=?
        """,
        (cleaned_title, now, user_id, session_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, title, created_at, updated_at FROM chat_sessions WHERE id=?",
        (session_id,),
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


def list_chat_message_page(
    user_id: int,
    session_id: int,
    *,
    before_id: int | None = None,
    limit: int = DEFAULT_CHAT_MESSAGE_PAGE_SIZE,
) -> dict:
    """Return one chronological history page without loading an unbounded session."""
    require_chat_session(user_id, session_id)
    if not isinstance(limit, int) or not 1 <= limit <= MAX_CHAT_MESSAGE_PAGE_SIZE:
        raise ValueError(f'消息数量必须在 1 到 {MAX_CHAT_MESSAGE_PAGE_SIZE} 之间')
    if before_id is not None and (not isinstance(before_id, int) or before_id < 1):
        raise ValueError('消息游标无效')

    conn = get_db()
    if before_id is None:
        rows = conn.execute(
            """
            SELECT id, role, content, rendered_html, created_at
            FROM chat_messages
            WHERE session_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit + 1),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, role, content, rendered_html, created_at
            FROM chat_messages
            WHERE session_id=? AND id < ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, before_id, limit + 1),
        ).fetchall()
    has_more = len(rows) > limit
    page_rows = list(reversed(rows[:limit]))
    messages = [_row_to_message(row) for row in page_rows]
    return {
        'messages': messages,
        'has_more': has_more,
        'next_before_id': messages[0]['id'] if has_more and messages else None,
    }


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
    return create_chat_session(user_id)


def _prepare_chat_message(role: str, content: str) -> tuple[str, str, str]:
    """Validate a message before a transaction acquires the SQLite writer lock."""
    role = str(role or '').strip()
    content = str(content or '').strip()
    if role not in {'user', 'assistant'}:
        raise ChatValidationError('消息角色无效')
    if not content:
        raise ChatValidationError('消息内容不能为空')
    if role == 'user' and len(content) > MAX_USER_MESSAGE_CHARS:
        raise ChatValidationError(f'单条用户消息不能超过 {MAX_USER_MESSAGE_CHARS} 字符')
    html = render_chat_markdown(content) if role == 'assistant' else ''
    return role, content, html


def _insert_chat_message(
    conn,
    session_id: int,
    role: str,
    content: str,
    html: str,
    created_at: str,
) -> dict:
    """Insert one already-validated message without committing its transaction."""
    cur = conn.execute(
        """
        INSERT INTO chat_messages (session_id, role, content, rendered_html, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, role, content, html, created_at),
    )
    return {
        'id': cur.lastrowid,
        'role': role,
        'content': content,
        'html': html,
        'created_at': created_at,
    }


def append_chat_message(session_id: int, role: str, content: str) -> dict:
    """Append one message for legacy callers and update the session timestamp."""
    role, content, html = _prepare_chat_message(role, content)
    now = _now_text()
    conn = get_db()
    message = _insert_chat_message(conn, session_id, role, content, html, now)
    conn.execute(
        "UPDATE chat_sessions SET updated_at=? WHERE id=?",
        (now, session_id),
    )
    conn.commit()
    return message


def persist_chat_exchange(
    user_id: int,
    session_id: int | None,
    user_content: str,
    assistant_content: str,
    initial_title: str | None = None,
) -> tuple[dict, dict, dict]:
    """Commit a completed model turn without exposing a partial chat exchange.

    The caller performs all network work first.  This function then creates a
    session when necessary, writes both messages, and updates an initial title
    inside one short SQLite write transaction.
    """
    user_role, user_content, user_html = _prepare_chat_message('user', user_content)
    assistant_role, assistant_content, assistant_html = _prepare_chat_message(
        'assistant', assistant_content,
    )
    cleaned_title = None
    if initial_title is not None:
        cleaned_title = ' '.join(str(initial_title).strip().split())[:32]
        if not cleaned_title:
            raise ChatSessionError('对话标题不能为空')

    conn = get_db()
    if conn.in_transaction:
        # Do not merge a public API turn into an unrelated caller transaction.
        raise RuntimeError('聊天消息写入前数据库事务尚未结束')

    now = _now_text()
    transaction_started = False
    try:
        conn.execute('BEGIN IMMEDIATE')
        transaction_started = True
        creating_session = session_id is None
        if creating_session:
            title = cleaned_title or '新的对话'
            cur = conn.execute(
                """
                INSERT INTO chat_sessions (user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, title, now, now),
            )
            session_id = cur.lastrowid
            session = {
                'id': session_id,
                'title': title,
                'created_at': now,
                'updated_at': now,
            }
        else:
            row = conn.execute(
                """
                SELECT id, title, created_at
                FROM chat_sessions
                WHERE user_id=? AND id=?
                """,
                (user_id, session_id),
            ).fetchone()
            if row is None:
                raise ChatSessionError('对话不存在')
            # A title is only "initial" while the session still carries its default.
            title = (
                cleaned_title
                if cleaned_title is not None and row['title'] == '新的对话'
                else row['title']
            )
            session = {
                'id': row['id'],
                'title': title,
                'created_at': row['created_at'],
                'updated_at': now,
            }

        user_message = _insert_chat_message(
            conn, session_id, user_role, user_content, user_html, now,
        )
        assistant_message = _insert_chat_message(
            conn, session_id, assistant_role, assistant_content, assistant_html, now,
        )
        if not creating_session:
            if conn.execute(
                """
                UPDATE chat_sessions
                SET title=?, updated_at=?
                WHERE user_id=? AND id=?
                """,
                (session['title'], now, user_id, session_id),
            ).rowcount != 1:
                raise ChatSessionError('对话不存在')
        conn.commit()
        transaction_started = False
    except Exception:
        if transaction_started and conn.in_transaction:
            conn.rollback()
        raise
    return session, user_message, assistant_message


def recent_model_messages(session_id: int, pending_user_content: str = '') -> list[dict[str, str]]:
    """Build bounded model history and append an unpersisted pending user turn."""
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
    pending_content = str(pending_user_content or '').strip()
    if pending_content:
        messages.append({'role': 'user', 'content': pending_content})
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
    """Keep the legacy helper available for callers that only need an extension."""
    try:
        _, extension = normalize_upload_filename(filename)
    except UploadValidationError:
        return ''
    return extension


class _Utf8TextUploadValidator:
    """Reject binary or malformed text while it is streamed to a temporary file."""

    def __init__(self):
        self._decoder = codecs.getincrementaldecoder('utf-8')('strict')

    def consume(self, chunk: bytes) -> None:
        if b'\x00' in chunk:
            raise UploadValidationError('文本文件不能包含空字符')
        try:
            self._decoder.decode(chunk)
        except UnicodeDecodeError as exc:
            raise UploadValidationError('文本文件必须使用 UTF-8 编码') from exc

    def finish(self) -> None:
        try:
            self._decoder.decode(b'', final=True)
        except UnicodeDecodeError as exc:
            raise UploadValidationError('文本文件必须使用 UTF-8 编码') from exc


def _read_text_upload(raw: bytes, ext: str) -> str:
    """Return a bounded preview already validated as UTF-8 during streaming."""
    if ext not in TEXT_UPLOAD_EXTENSIONS:
        return ''
    return raw.decode('utf-8', errors='ignore')[:MAX_FILE_TEXT_CHARS]


def _chat_max_file_bytes(settings: dict) -> int:
    """Derive the effective service limit even if a legacy setting was oversized."""
    configured_mb = min(int(settings['chat_file_max_mb']), MAX_CHAT_FILE_UPLOAD_MB)
    return configured_mb * 1024 * 1024


def chat_upload_request_limit_bytes(settings: dict | None = None) -> int:
    """Bound request parsing as well as the later streaming copy of a chat upload."""
    settings = settings or get_access_settings()
    return _chat_max_file_bytes(settings) + CHAT_UPLOAD_MULTIPART_OVERHEAD_BYTES


def _validate_docx_file(path: Path) -> bool:
    """Check the minimal Office Open XML structure without extracting untrusted ZIP data."""
    try:
        with zipfile.ZipFile(path) as archive:
            member_names = {entry.filename for entry in archive.infolist()}
    except (OSError, zipfile.BadZipFile):
        return False
    return '[Content_Types].xml' in member_names and any(
        name.startswith('word/') for name in member_names
    )


def _validate_chat_upload_content(
    extension: str,
    reported_mime: object,
    staged_upload,
) -> str:
    """Return canonical MIME only when name, report and file contents agree."""
    allowed_mimes = set(CHAT_UPLOAD_MIME_TYPES[extension])
    if extension in {'jpg', 'jpeg'}:
        allowed_mimes.add('image/jpg')
    validate_reported_mime(
        reported_mime,
        allowed_mimes,
        '文件 MIME 类型与扩展名不匹配',
    )

    if extension in TEXT_UPLOAD_EXTENSIONS:
        return 'text/plain' if extension == 'txt' else 'text/markdown'
    if extension == 'pdf':
        if b'%PDF-' not in staged_upload.header[:1024]:
            raise UploadValidationError('PDF 文件内容无效')
        return 'application/pdf'
    if extension == 'docx':
        if not _validate_docx_file(staged_upload.path):
            raise UploadValidationError('DOCX 文件内容无效')
        return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

    expected_mime = CHAT_UPLOAD_MIME_TYPES[extension]
    detected_mime = sniff_image_mime_type(staged_upload.header)
    if detected_mime not in expected_mime:
        raise UploadValidationError('图片内容与文件扩展名不匹配')
    return detected_mime


def _remove_empty_upload_directory(upload_directory: Path) -> None:
    """Remove only empty folders created for an upload that later rolled back."""
    try:
        upload_directory.rmdir()
    except OSError:
        return
    try:
        upload_directory.parent.rmdir()
    except OSError:
        pass


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

    staged_upload = None
    stored_path = None
    size_bytes = 0
    metadata_committed = False
    upload_directory = _upload_root() / str(user_id) / str(session_id)
    try:
        original_name, extension = normalize_upload_filename(file_storage.filename)
        if extension not in ALLOWED_UPLOAD_EXTENSIONS:
            raise UploadValidationError('不支持的文件类型')

        text_validator = _Utf8TextUploadValidator() if extension in TEXT_UPLOAD_EXTENSIONS else None
        staged_upload = stage_upload(
            file_storage.stream,
            upload_directory,
            _chat_max_file_bytes(settings),
            capture_bytes=MAX_FILE_TEXT_CAPTURE_BYTES if text_validator else 0,
            validator=text_validator,
        )
        mime_type = _validate_chat_upload_content(
            extension,
            file_storage.mimetype,
            staged_upload,
        )
        extracted_text = _read_text_upload(staged_upload.captured_bytes, extension)
        size_bytes = staged_upload.size_bytes

        stored_name = f"{uuid.uuid4().hex}.{extension}"
        destination_path = upload_directory / stored_name
        try:
            staged_upload.path.replace(destination_path)
        except OSError as exc:
            raise UploadStorageError('文件保存失败') from exc
        staged_upload = None
        stored_path = destination_path

        # Lock only the metadata mutation so concurrent uploads cannot bypass quotas.
        conn = get_db()
        try:
            conn.execute('BEGIN IMMEDIATE')
            session_row = conn.execute(
                "SELECT id FROM chat_sessions WHERE user_id=? AND id=?",
                (user_id, session_id),
            ).fetchone()
            if not session_row:
                raise ChatSessionError('对话不存在')
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM chat_files WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if int(row['total'] or 0) >= settings['chat_session_file_limit']:
                raise ChatFileUploadError(f'单个对话最多上传 {settings["chat_session_file_limit"]} 个文件')
            if _user_storage_bytes(user_id) + size_bytes > settings['chat_user_storage_mb'] * 1024 * 1024:
                raise ChatFileUploadError(f'当前用户文件空间不能超过 {settings["chat_user_storage_mb"]}MB')

            rel_path = str(stored_path.relative_to(_upload_root()))
            now = _now_text()
            cur = conn.execute(
                """
                INSERT INTO chat_files (session_id, original_name, stored_path, mime_type, size_bytes, extracted_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    original_name,
                    rel_path,
                    mime_type,
                    size_bytes,
                    extracted_text,
                    now,
                ),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at=? WHERE id=?",
                (now, session_id),
            )
            conn.commit()
            metadata_committed = True
        except (ChatFileUploadError, ChatSessionError):
            conn.rollback()
            raise
        except sqlite3.Error as exc:
            conn.rollback()
            raise UploadStorageError('文件元数据保存失败') from exc

        return {
            'id': cur.lastrowid,
            'name': original_name,
            'mime_type': mime_type,
            'size_bytes': size_bytes,
            'has_text': bool(extracted_text),
            'created_at': now,
        }
    except UploadValidationError as exc:
        raise ChatFileUploadError(str(exc)) from exc
    except UploadStorageError as exc:
        raise ChatFileUploadError(str(exc)) from exc
    finally:
        if staged_upload is not None:
            cleanup_upload_file(staged_upload.path)
        if stored_path is not None and not metadata_committed:
            # A successful metadata transaction owns the final file; failures must not orphan it.
            cleanup_upload_file(stored_path)
        if not metadata_committed:
            _remove_empty_upload_directory(upload_directory)
