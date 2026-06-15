"""AI polish & preview API endpoints — separate blueprint to keep admin.py lean."""

from flask import Blueprint, jsonify, request

from services.ai_polish import polish_content
from services.articles import render_md
from services.auth import login_required

ai_bp = Blueprint('admin_ai', __name__, url_prefix='/admin')


@ai_bp.route('/api/ai/polish', methods=['POST'])
@login_required
def ai_polish():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    tags = (data.get('tags') or '').strip()
    content = (data.get('content') or '').strip()
    provider_id = (data.get('provider') or '').strip()
    model = (data.get('model') or '').strip()
    mode = (data.get('mode') or '').strip()
    organize_first = bool(data.get('organize_first'))
    if not content:
        return jsonify({'error': '正文不能为空'}), 400
    try:
        polished = polish_content(
            title,
            tags,
            content,
            provider_id=provider_id,
            model=model,
            mode_id=mode,
            organize_first=organize_first,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': str(exc)}), 502
    except SystemExit:
        return jsonify({'error': 'AI 接口请求超时或连接中断'}), 504
    return jsonify({'content': polished})


@ai_bp.route('/api/preview', methods=['POST'])
@login_required
def preview_markdown():
    data = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    html = render_md(content) if content else ''
    return jsonify({'html': html})
