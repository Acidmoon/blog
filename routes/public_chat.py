"""Public AI chat page and JSON API routes."""

from flask import jsonify, redirect, render_template, request, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from routes.public_utils import client_ip
from services.auth import safe_next_url
from services.access_settings import get_access_settings
from services.ai_chat import (
    ChatAPIError,
    ChatDisabledError,
    ChatNotConfiguredError,
    ChatRateLimitError,
    ChatTimeoutError,
    ChatValidationError,
    get_public_chat_settings,
)
from services.chat_orchestrator import send_public_chat_message
from services.chat_sessions import (
    ChatFileUploadError,
    ChatSessionError,
    chat_upload_request_limit_bytes,
    create_chat_session,
    delete_chat_session,
    list_chat_files,
    list_chat_message_page,
    list_chat_sessions,
    save_chat_upload,
)
from services.visitor_auth import current_visitor


def _require_visitor_json():
    visitor = current_visitor()
    if not visitor:
        return None, (jsonify({'error': '请先登录'}), 401)
    return visitor, None


def _parse_message_page_value(value, *, name: str, default: int | None = None) -> int | None:
    """Parse bounded positive page controls before they reach SQLite LIMIT/OFFSET."""
    if value in (None, ''):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name}必须是正整数') from exc
    if parsed < 1:
        raise ValueError(f'{name}必须是正整数')
    return parsed


def register_routes(bp):
    @bp.route('/chat')
    def chat():
        settings = get_public_chat_settings()
        visitor = current_visitor()
        if not visitor:
            next_url = safe_next_url(request.full_path.rstrip('?'), url_for('public.index'))
            return redirect(url_for('public.login', next=next_url))
        return render_template(
            'chat.html',
            chat_enabled=settings['enabled'],
            chat_model=settings['model'],
            chat_visitor=visitor,
            chat_upload_enabled=get_access_settings()['chat_file_upload_enabled'],
        )

    @bp.route('/api/chat/sessions', methods=['GET'])
    def api_chat_sessions():
        visitor, error = _require_visitor_json()
        if error:
            return error
        return jsonify({'sessions': list_chat_sessions(visitor['id'])})

    @bp.route('/api/chat/sessions', methods=['POST'])
    def api_chat_create_session():
        visitor, error = _require_visitor_json()
        if error:
            return error
        data = request.get_json(silent=True) or {}
        title = str(data.get('title') or '新的对话').strip()[:32] or '新的对话'
        return jsonify({'session': create_chat_session(visitor['id'], title)})

    @bp.route('/api/chat/sessions/<int:session_id>', methods=['DELETE'])
    def api_chat_delete_session(session_id):
        visitor, error = _require_visitor_json()
        if error:
            return error
        try:
            delete_chat_session(visitor['id'], session_id)
        except ChatSessionError as exc:
            return jsonify({'error': str(exc)}), 404
        return jsonify({'ok': True})

    @bp.route('/api/chat/sessions/<int:session_id>/messages', methods=['GET'])
    def api_chat_session_messages(session_id):
        visitor, error = _require_visitor_json()
        if error:
            return error
        try:
            before_id = _parse_message_page_value(request.args.get('before_id'), name='消息游标')
            limit = _parse_message_page_value(request.args.get('limit'), name='消息数量', default=100)
            page = list_chat_message_page(
                visitor['id'],
                session_id,
                before_id=before_id,
                limit=limit,
            )
            files = list_chat_files(visitor['id'], session_id)
        except ChatSessionError as exc:
            return jsonify({'error': str(exc)}), 404
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        return jsonify({**page, 'files': files})

    @bp.route('/api/chat/sessions/<int:session_id>/files', methods=['POST'])
    def api_chat_upload_file(session_id):
        visitor, error = _require_visitor_json()
        if error:
            return error
        upload_settings = get_access_settings()
        request_limit = chat_upload_request_limit_bytes(upload_settings)
        if (
            request.content_length is not None
            and request.content_length > request_limit
        ):
            return jsonify({
                'error': f'单个文件不能超过 {upload_settings["chat_file_max_mb"]}MB',
            }), 400
        request.max_content_length = request_limit
        try:
            file_info = save_chat_upload(visitor['id'], session_id, request.files.get('file'))
        except RequestEntityTooLarge:
            return jsonify({
                'error': f'单个文件不能超过 {upload_settings["chat_file_max_mb"]}MB',
            }), 400
        except ChatSessionError as exc:
            return jsonify({'error': str(exc)}), 404
        except ChatFileUploadError as exc:
            return jsonify({'error': str(exc)}), 400
        return jsonify({'file': file_info})

    @bp.route('/api/chat', methods=['POST'])
    def api_chat():
        visitor, error = _require_visitor_json()
        if error:
            return error
        data = request.get_json(silent=True) or {}
        try:
            incoming_session_id = int(data.get('session_id')) if data.get('session_id') else None
            payload = send_public_chat_message(
                visitor_id=visitor['id'],
                content=data.get('content', ''),
                session_id=incoming_session_id,
                client_ip=client_ip(),
            )
        except ChatDisabledError as exc:
            return jsonify({'error': str(exc)}), 403
        except ChatNotConfiguredError as exc:
            return jsonify({'error': str(exc)}), 503
        except ChatSessionError as exc:
            return jsonify({'error': str(exc)}), 404
        except (ChatValidationError, ValueError) as exc:
            return jsonify({'error': str(exc)}), 400
        except ChatRateLimitError as exc:
            return jsonify({'error': str(exc)}), 429
        except ChatTimeoutError as exc:
            return jsonify({'error': str(exc)}), 504
        except ChatAPIError as exc:
            return jsonify({'error': str(exc)}), 502
        return jsonify(payload)
