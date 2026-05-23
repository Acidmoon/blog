from datetime import datetime

from flask import Blueprint, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for

import config
from services.activity_heatmap import build_month_activity_heatmap
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
    verify_access_code,
)
from services.articles import _count_words, get_article_meta, list_all_tags, list_published_articles, read_article_file, render_md
from services.home_layout import load_home_layout, resolve_hero
from services.home_modules import build_home_sections
from services.search import search_articles

bp = Blueprint('public', __name__)


@bp.context_processor
def inject_now():
    return {'now': datetime.now}


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
    authorized = bool(session.get('public_chat_authorized'))
    return render_template(
        'chat.html',
        chat_enabled=settings['enabled'],
        chat_authorized=authorized,
        chat_model=settings['model'],
    )


@bp.route('/api/chat/auth', methods=['POST'])
def api_chat_auth():
    data = request.get_json(silent=True) or {}
    code = data.get('code') or ''
    if not verify_access_code(code):
        return jsonify({'error': '朋友口令不正确'}), 401
    session['public_chat_authorized'] = True
    return jsonify({'ok': True})


@bp.route('/api/chat', methods=['POST'])
def api_chat():
    settings = get_public_chat_settings()
    if not settings['enabled']:
        return jsonify({'error': '公开聊天未启用'}), 403
    if not session.get('public_chat_authorized'):
        return jsonify({'error': '请先输入朋友口令'}), 401
    data = request.get_json(silent=True) or {}
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    try:
        content = chat_completion(data.get('messages'), client_ip)
    except ChatDisabledError as exc:
        return jsonify({'error': str(exc)}), 403
    except ChatNotConfiguredError as exc:
        return jsonify({'error': str(exc)}), 503
    except ChatValidationError as exc:
        return jsonify({'error': str(exc)}), 400
    except ChatRateLimitError as exc:
        return jsonify({'error': str(exc)}), 429
    except ChatTimeoutError as exc:
        return jsonify({'error': str(exc)}), 504
    except ChatAPIError as exc:
        return jsonify({'error': str(exc)}), 502
    return jsonify({'content': content, 'html': render_chat_markdown(content)})


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
