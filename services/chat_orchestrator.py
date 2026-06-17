"""High-level public chat workflows."""

from __future__ import annotations

from services.ai_chat import (
    ChatAPIError,
    ChatDisabledError,
    ChatNotConfiguredError,
    ChatRateLimitError,
    ChatTimeoutError,
    ChatValidationError,
    chat_completion,
    generate_chat_session_title,
    get_public_chat_settings,
    render_chat_markdown,
)
from services.chat_sessions import (
    ChatSessionError,
    append_chat_message,
    build_session_title,
    ensure_session_for_message,
    list_chat_messages,
    recent_model_messages,
    session_file_context,
    update_chat_session_title,
)


def send_public_chat_message(
    *,
    visitor_id: int,
    content: str,
    session_id: int | None,
    client_ip: str,
) -> dict:
    """Append a user message, call the model, persist the assistant reply."""
    settings = get_public_chat_settings()
    if not settings['enabled']:
        raise ChatDisabledError('公开聊天未启用')

    content = str(content or '').strip()
    if not content:
        raise ChatValidationError('消息内容不能为空')
    if len(content) > 4000:
        raise ChatValidationError('单条用户消息不能超过 4000 字符')

    session = ensure_session_for_message(visitor_id, session_id, content)
    needs_title = session['title'] == '新的对话'
    user_message = append_chat_message(session['id'], 'user', content)
    model_messages = recent_model_messages(session['id'])
    assistant_content = chat_completion(
        model_messages,
        client_ip,
        extra_system_context=session_file_context(session['id']),
    )
    assistant_message = append_chat_message(session['id'], 'assistant', assistant_content)
    if needs_title:
        try:
            title = generate_chat_session_title(list_chat_messages(visitor_id, session['id']))
        except (
            ChatDisabledError,
            ChatNotConfiguredError,
            ChatRateLimitError,
            ChatAPIError,
            ChatTimeoutError,
            ChatValidationError,
            ValueError,
        ):
            title = build_session_title(content)
        session = update_chat_session_title(visitor_id, session['id'], title or build_session_title(content))
    return {
        'session': session,
        'user_message': user_message,
        'assistant_message': assistant_message,
        'content': assistant_content,
        'html': render_chat_markdown(assistant_content),
    }
