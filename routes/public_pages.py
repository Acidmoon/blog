"""Public HTML page routes."""

from flask import abort, redirect, render_template, request, send_from_directory, url_for

import config
from models import get_db
from routes.public_utils import client_ip
from services.activity_heatmap import build_month_activity_heatmap
from services.articles import (
    _count_words,
    get_article_meta,
    list_all_tags,
    list_published_articles,
    read_article_file,
    render_md,
)
from services.comments import count_likes, has_liked, list_comments
from services.home_layout import load_home_layout, resolve_hero
from services.home_modules import build_home_sections
from services.search import search_articles
from services.visitor_auth import current_visitor


SIDEBAR_SECTION_IDS = {'activity_heatmap'}


def _split_home_sections(all_home_sections: list[dict]) -> tuple[list[dict], list[dict]]:
    sidebar_sections = [
        section for section in all_home_sections
        if section.get('id') in SIDEBAR_SECTION_IDS
    ]
    home_sections = [
        section for section in all_home_sections
        if section.get('id') not in SIDEBAR_SECTION_IDS
    ]
    return home_sections, sidebar_sections


def _inject_sidebar_context(sidebar_sections: list[dict]) -> None:
    heatmap_year = request.args.get('heatmap_year', type=int)
    heatmap_month = request.args.get('heatmap_month', type=int)
    for section in sidebar_sections:
        if section.get('id') == 'activity_heatmap':
            section['context']['activity_heatmap'] = build_month_activity_heatmap(
                year=heatmap_year,
                month=heatmap_month,
            )
            break


def register_routes(bp):
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

        return render_template(
            'search.html',
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
        all_home_sections = build_home_sections(
            layout,
            articles=articles,
            page=page,
            total=total,
            current_tag=tag,
            all_tags=list_all_tags(),
        )
        home_sections, sidebar_sections = _split_home_sections(all_home_sections)
        _inject_sidebar_context(sidebar_sections)
        hero = resolve_hero(layout.get('hero'), tag)

        return render_template(
            'index.html',
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
        visitor = current_visitor()
        comments = list_comments(meta['id'], page=1)
        likes = {
            'count': count_likes(meta['id']),
            'liked': has_liked(meta['id'], visitor['id'] if visitor else None, client_ip()),
        }
        # Previous / Next article by creation date
        conn = get_db()
        prev_row = conn.execute(
            "SELECT slug, title FROM articles WHERE published=1 AND created_at < ? ORDER BY created_at DESC LIMIT 1",
            (meta['created_at'],)
        ).fetchone()
        next_row = conn.execute(
            "SELECT slug, title FROM articles WHERE published=1 AND created_at > ? ORDER BY created_at ASC LIMIT 1",
            (meta['created_at'],)
        ).fetchone()
        prev_article = dict(prev_row) if prev_row else None
        next_article = dict(next_row) if next_row else None
        return render_template(
            'article.html',
            article=meta,
            content=render_md(content),
            comments=comments,
            likes=likes,
            visitor=visitor,
            prev_article=prev_article,
            next_article=next_article,
        )

    @bp.route('/static/<path:filename>')
    def static_files(filename):
        return send_from_directory('static', filename)
