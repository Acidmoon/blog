from datetime import datetime

from flask import Blueprint, abort, flash, jsonify, make_response, redirect, render_template, request, send_from_directory, url_for

import config
from services.activity_heatmap import build_month_activity_heatmap
from services.access_settings import get_access_settings
from services.ai_chat import (
    ChatAPIError,
    ChatDisabledError,
    ChatNotConfiguredError,
    ChatRateLimitError,
    ChatTimeoutError,
    ChatValidationError,
    chat_completion,
    get_public_chat_settings,
    render_chat_markdown,
)
from services.articles import _count_words, get_article_meta, list_all_tags, list_published_articles, read_article_file, render_md
from services.chat_sessions import (
    ChatFileUploadError,
    ChatSessionError,
    append_chat_message,
    create_chat_session,
    delete_chat_session,
    ensure_session_for_message,
    list_chat_files,
    list_chat_messages,
    list_chat_sessions,
    recent_model_messages,
    save_chat_upload,
    session_file_context,
)
from services.home_layout import load_home_layout, resolve_hero
from services.home_modules import build_home_sections
from services.search import search_articles
from services.visitor_auth import (
    VisitorAuthError,
    clear_visitor_cookie,
    current_visitor,
    login_visitor,
    revoke_current_visitor_token,
    set_visitor_cookie,
)

bp = Blueprint('public', __name__)


def _client_ip() -> str:
    return request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()


@bp.context_processor
def inject_now():
    return {'now': datetime.now}


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_visitor():
        return redirect(request.args.get('next') or url_for('public.index'))
    error = ''
    if request.method == 'POST':
        next_url = request.form.get('next') or url_for('public.index')
        try:
            visitor, token, expires_at = login_visitor(
                request.form.get('username', ''),
                request.form.get('password', ''),
            )
        except VisitorAuthError as exc:
            error = str(exc)
        else:
            response = make_response(redirect(next_url))
            set_visitor_cookie(response, token, expires_at)
            flash(f'欢迎，{visitor["username"]}', 'success')
            return response
    return render_template('login.html', error=error, next_url=request.args.get('next') or url_for('public.index'))


@bp.route('/logout')
def logout():
    revoke_current_visitor_token()
    response = make_response(redirect(url_for('public.login')))
    clear_visitor_cookie(response)
    return response


@bp.route('/search')
def search():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    if not q:
        return redirect(url_for('public.index'))
    results = search_articles(q)
    total = len(results)
    start = (page - 1) * config.ARTICLES_PER_PAGE
    end = start + config.ARTICLES_PER_PAGE
    page_results = results[start:end]

    return render_template('search.html',
        query=q,
        articles=[(a, s, t) for a, s, t, _ in page_results],
        page=page,
        total=total,
        per_page=config.ARTICLES_PER_PAGE,
        total_pages=max(1, (total + config.ARTICLES_PER_PAGE - 1) // config.ARTICLES_PER_PAGE),
        all_tags=list_all_tags(),
    )


@bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    tag = request.args.get('tag', '').strip()
    articles, total = list_published_articles(page=page, tag=tag)
    layout = load_home_layout()
    all_tags = list_all_tags()
    all_home_sections = build_home_sections(
        layout,
        articles=articles,
        page=page,
        total=total,
        current_tag=tag,
        all_tags=all_tags,
    )
    sidebar_ids: set[str] = {"activity_heatmap"}
    sidebar_sections = [section for section in all_home_sections if section.get("id") in sidebar_ids]
    home_sections = [section for section in all_home_sections if section.get("id") not in sidebar_ids]

    # Inject heatmap year/month from query params into sidebar section
    heatmap_year = request.args.get("heatmap_year", type=int)
    heatmap_month = request.args.get("heatmap_month", type=int)
    for section in sidebar_sections:
        if section.get("id") == "activity_heatmap":
            section["context"]["activity_heatmap"] = build_month_activity_heatmap(
                year=heatmap_year, month=heatmap_month
            )
            break

    hero = resolve_hero(layout.get("hero"), tag)

    return render_template('index.html',
        hero=hero,
        home_sections=home_sections,
        sidebar_sections=sidebar_sections,
    )


@bp.route('/article/<slug>')
def article(slug):
    meta = get_article_meta(slug)
    if not meta:
        abort(404)
    content = read_article_file(slug)
    if content is None:
        abort(404)
    meta['current_word_count'] = _count_words(content)
    html = render_md(content)
    return render_template('article.html', article=meta, content=html)


@bp.route('/chat')
def chat():
    settings = get_public_chat_settings()
    visitor = current_visitor()
    if not visitor:
        return redirect(url_for('public.login', next=request.full_path.rstrip('?')))
    return render_template(
        'chat.html',
        chat_enabled=settings['enabled'],
        chat_model=settings['model'],
        chat_visitor=visitor,
        chat_upload_enabled=get_access_settings()['chat_file_upload_enabled'],
    )


@bp.route('/api/chat/sessions', methods=['GET'])
def api_chat_sessions():
    visitor = current_visitor()
    if not visitor:
        return jsonify({'error': '请先登录'}), 401
    return jsonify({'sessions': list_chat_sessions(visitor['id'])})


@bp.route('/api/chat/sessions', methods=['POST'])
def api_chat_create_session():
    visitor = current_visitor()
    if not visitor:
        return jsonify({'error': '请先登录'}), 401
    data = request.get_json(silent=True) or {}
    title = str(data.get('title') or '新的对话').strip()[:32] or '新的对话'
    return jsonify({'session': create_chat_session(visitor['id'], title)})


@bp.route('/api/chat/sessions/<int:session_id>', methods=['DELETE'])
def api_chat_delete_session(session_id):
    visitor = current_visitor()
    if not visitor:
        return jsonify({'error': '请先登录'}), 401
    try:
        delete_chat_session(visitor['id'], session_id)
    except ChatSessionError as exc:
        return jsonify({'error': str(exc)}), 404
    return jsonify({'ok': True})


@bp.route('/api/chat/sessions/<int:session_id>/messages', methods=['GET'])
def api_chat_session_messages(session_id):
    visitor = current_visitor()
    if not visitor:
        return jsonify({'error': '请先登录'}), 401
    try:
        messages = list_chat_messages(visitor['id'], session_id)
        files = list_chat_files(visitor['id'], session_id)
    except ChatSessionError as exc:
        return jsonify({'error': str(exc)}), 404
    return jsonify({'messages': messages, 'files': files})


@bp.route('/api/chat/sessions/<int:session_id>/files', methods=['POST'])
def api_chat_upload_file(session_id):
    visitor = current_visitor()
    if not visitor:
        return jsonify({'error': '请先登录'}), 401
    try:
        file_info = save_chat_upload(visitor['id'], session_id, request.files.get('file'))
    except ChatSessionError as exc:
        return jsonify({'error': str(exc)}), 404
    except ChatFileUploadError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'file': file_info})


@bp.route('/api/chat', methods=['POST'])
def api_chat():
    visitor = current_visitor()
    if not visitor:
        return jsonify({'error': '请先登录'}), 401
    settings = get_public_chat_settings()
    if not settings['enabled']:
        return jsonify({'error': '公开聊天未启用'}), 403
    data = request.get_json(silent=True) or {}
    client_ip = _client_ip()
    try:
        content = str(data.get('content') or '').strip()
        session_id = data.get('session_id')
        if not content:
            raise ChatValidationError('消息内容不能为空')
        if len(content) > 4000:
            raise ChatValidationError('单条用户消息不能超过 4000 字符')
        session = ensure_session_for_message(visitor['id'], int(session_id) if session_id else None, content)
        user_message = append_chat_message(session['id'], 'user', content)
        model_messages = recent_model_messages(session['id'])
        assistant_content = chat_completion(model_messages, client_ip, extra_system_context=session_file_context(session['id']))
        assistant_message = append_chat_message(session['id'], 'assistant', assistant_content)
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
    return jsonify({
        'session': session,
        'user_message': user_message,
        'assistant_message': assistant_message,
        'content': assistant_content,
        'html': render_chat_markdown(assistant_content),
    })


@bp.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


@bp.route('/api/heatmap')
def api_heatmap():
    """Return the activity heatmap HTML fragment for AJAX month switching."""
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    data = build_month_activity_heatmap(year=year, month=month)
    return render_template('home_sections/activity_heatmap.html', activity_heatmap=data)
