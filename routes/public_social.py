"""Article comments and likes JSON API routes."""

from flask import jsonify, request

from routes.public_utils import client_ip
from services.auth import current_identity
from services.articles import get_article_meta
from services.comments import (
    CommentError,
    LikeUnavailableError,
    add_comment,
    count_comments,
    delete_comment,
    get_comment,
    list_comments,
    toggle_like,
)
from services.query_params import QueryParameterError, parse_positive_page
from services.visitor_auth import current_visitor


def _comment_view(comment: dict, visitor: dict | None) -> dict:
    is_admin = current_identity().is_admin
    can_delete = is_admin or (visitor is not None and visitor['id'] == comment['user_id'])
    return {
        'id': comment['id'],
        'username': comment['username'],
        'content': comment['content'],
        'created_at': comment['created_at'],
        'can_delete': can_delete,
    }


def register_routes(bp):
    @bp.route('/api/article/<slug>/comments', methods=['GET'])
    def api_list_comments(slug):
        meta = get_article_meta(slug)
        if not meta:
            return jsonify({'error': '文章不存在'}), 404
        try:
            page = parse_positive_page(request.args.get('page'))
        except QueryParameterError as exc:
            return jsonify({'error': str(exc)}), 400
        visitor = current_visitor()
        result = list_comments(meta['id'], page=page)
        return jsonify({
            'comments': [_comment_view(c, visitor) for c in result['comments']],
            'page': result['page'],
            'per_page': result['per_page'],
            'total': result['total'],
            'total_pages': result['total_pages'],
        })

    @bp.route('/api/article/<slug>/comments', methods=['POST'])
    def api_add_comment(slug):
        meta = get_article_meta(slug)
        if not meta:
            return jsonify({'error': '文章不存在'}), 404
        visitor = current_visitor()
        if not visitor:
            return jsonify({'error': '请先登录'}), 401
        data = request.get_json(silent=True) or {}
        try:
            comment = add_comment(meta['id'], visitor['id'], data.get('content', ''))
        except CommentError as exc:
            return jsonify({'error': str(exc)}), 400
        return jsonify({
            'comment': _comment_view(comment, visitor),
            'total': count_comments(meta['id']),
        })

    @bp.route('/api/comments/<int:comment_id>', methods=['DELETE'])
    def api_delete_comment(comment_id):
        comment = get_comment(comment_id)
        if not comment:
            return jsonify({'error': '评论不存在'}), 404
        visitor = current_visitor()
        is_admin = current_identity().is_admin
        is_author = visitor is not None and visitor['id'] == comment['user_id']
        if not (is_admin or is_author):
            return jsonify({'error': '无权删除该评论'}), 403
        delete_comment(comment_id)
        return jsonify({'ok': True, 'total': count_comments(comment['article_id'])})

    @bp.route('/api/article/<slug>/like', methods=['POST'])
    def api_toggle_like(slug):
        meta = get_article_meta(slug)
        if not meta:
            return jsonify({'error': '文章不存在'}), 404
        visitor = current_visitor()
        try:
            result = toggle_like(
                meta['id'],
                visitor['id'] if visitor else None,
                client_ip(),
            )
        except LikeUnavailableError as exc:
            return jsonify({'error': str(exc)}), 503
        return jsonify(result)
