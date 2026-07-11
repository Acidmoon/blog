"""Public HTML page routes."""

from flask import abort, redirect, render_template, request, send_from_directory, url_for

import config
from features.articles.application import load_public_article_page
from features.home.application import build_public_home_context
from routes.public_utils import client_ip
from services.articles import (
    list_all_tags,
)
from services.comments import count_likes, has_liked, list_comments
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
        return render_template(
            'index.html',
            **build_public_home_context(
                page=page,
                current_tag=tag,
                request_context=request.args.to_dict(flat=True),
            ),
        )

    @bp.route('/article/<slug>')
    def article(slug):
        page = load_public_article_page(slug)
        if page is None:
            abort(404)
        meta = page.article
        visitor = current_visitor()
        comments = list_comments(meta['id'], page=1)
        likes = {
            'count': count_likes(meta['id']),
            'liked': has_liked(meta['id'], visitor['id'] if visitor else None, client_ip()),
        }
        return render_template(
            'article.html',
            article=meta,
            content=page.content_html,
            comments=comments,
            likes=likes,
            visitor=visitor,
            prev_article=page.previous_article,
            next_article=page.next_article,
        )

    @bp.route('/static/<path:filename>')
    def static_files(filename):
        return send_from_directory('static', filename)
