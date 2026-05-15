from datetime import datetime

from flask import Blueprint, abort, redirect, render_template, request, send_from_directory, url_for

import config
from services.articles import get_article_meta, list_all_tags, list_published_articles, read_article_file, render_md
from services.home_layout import get_daily_quote, load_home_layout
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
    quote = get_daily_quote(layout.get("quotes", []))

    return render_template('index.html',
        articles=articles,
        page=page,
        total=total,
        per_page=config.ARTICLES_PER_PAGE,
        total_pages=max(1, (total + config.ARTICLES_PER_PAGE - 1) // config.ARTICLES_PER_PAGE),
        current_tag=tag,
        all_tags=list_all_tags(),
        daily_quote=quote,
    )


@bp.route('/article/<slug>')
def article(slug):
    meta = get_article_meta(slug)
    if not meta:
        abort(404)
    content = read_article_file(slug)
    if content is None:
        abort(404)
    html = render_md(content)
    return render_template('article.html', article=meta, content=html)


@bp.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)
