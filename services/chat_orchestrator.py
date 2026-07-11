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
    build_session_title,
    ensure_session_for_message,
    list_chat_messages,
    persist_chat_exchange,
    recent_model_messages,
    session_file_context,
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

    session = ensure_session_for_message(visitor_id, session_id, content) if session_id else None
    needs_title = session is None or session['title'] == '新的对话'
    model_messages = (
        recent_model_messages(session['id'], content)
        if session is not None
        else [{'role': 'user', 'content': content}]
    )
    assistant_content = chat_completion(
        model_messages,
        client_ip,
        extra_system_context=session_file_context(session['id']) if session is not None else '',
    )
    initial_title = None
    if needs_title:
        title_messages = (
            list_chat_messages(visitor_id, session['id'])
            if session is not None
            else []
        )
        title_messages.extend([
            {'role': 'user', 'content': content},
            {'role': 'assistant', 'content': assistant_content},
        ])
        try:
            initial_title = generate_chat_session_title(title_messages)
        except (
            ChatDisabledError,
            ChatNotConfiguredError,
            ChatRateLimitError,
            ChatAPIError,
            ChatTimeoutError,
            ChatValidationError,
            ValueError,
        ):
            initial_title = build_session_title(content)
        initial_title = initial_title or build_session_title(content)
    session, user_message, assistant_message = persist_chat_exchange(
        visitor_id,
        session['id'] if session is not None else None,
        content,
        assistant_content,
        initial_title,
    )
    return {
        'session': session,
        'user_message': user_message,
        'assistant_message': assistant_message,
        'content': assistant_content,
        'html': render_chat_markdown(assistant_content),
    }
