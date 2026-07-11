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
    list_featured_articles,
    list_published_articles,
    read_article_file,
    render_md,
)
from services.comments import count_likes, has_liked, list_comments
from services.home_layout import load_home_layout, resolve_hero
from services.home_modules import build_home_sections, render_home_section, split_home_sections
from services.query_params import QueryParameterError, parse_positive_page
from services.search import search_articles_page
from services.tagging import normalize_tag_filter
from services.visitor_auth import current_visitor


def register_routes(bp):
    @bp.route('/search')
    def search():
        q = request.args.get('q', '').strip()
        try:
            page = parse_positive_page(request.args.get('page'))
            results, total = search_articles_page(q, page=page, per_page=config.ARTICLES_PER_PAGE)
        except (QueryParameterError, ValueError) as exc:
            return str(exc), 400
        if not q:
            return redirect(url_for('public.index'))

        return render_template(
            'search.html',
            query=q,
            articles=[(a, s, t) for a, s, t, _ in results],
            page=page,
            total=total,
            per_page=config.ARTICLES_PER_PAGE,
            total_pages=max(1, (total + config.ARTICLES_PER_PAGE - 1) // config.ARTICLES_PER_PAGE),
            all_tags=list_all_tags(),
        )

    @bp.route('/')
    def index():
        try:
            page = parse_positive_page(request.args.get('page'))
            raw_tag = request.args.get('tag', '').strip()
            tag = normalize_tag_filter(raw_tag) if raw_tag else ''
            if raw_tag and not tag:
                raise QueryParameterError('标签格式无效')
        except (QueryParameterError, ValueError) as exc:
            return str(exc), 400
        articles, total = list_published_articles(page=page, tag=tag)
        layout = load_home_layout()
        featured_articles = list_featured_articles(layout.get('featured_articles'), limit=5)
        all_home_sections = build_home_sections(
            layout,
            articles=articles,
            page=page,
            total=total,
            current_tag=tag,
            all_tags=list_all_tags(),
            request_context=request.args.to_dict(flat=True),
        )
        home_sections, sidebar_sections = split_home_sections(all_home_sections)
        for section in home_sections:
            section['html'] = render_home_section(section)
        for section in sidebar_sections:
            if section['id'] != 'activity_heatmap':
                section['html'] = render_home_section(section)
        hero = resolve_hero(layout.get('hero'), tag)

        return render_template(
            'index.html',
            hero=hero,
            body_class='home-page',
            featured_articles=featured_articles,
            home_sections=home_sections,
            sidebar_sections=sidebar_sections,
        )

    @bp.route('/article/<slug>')
    def article(slug):
        meta = get_article_meta(slug)
        if not meta:
            abort(404)
        content = read_article_file(slug, meta.get('content_key', ''))
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
