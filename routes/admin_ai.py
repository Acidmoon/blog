"""AI polish & preview API endpoints — separate blueprint to keep admin.py lean."""

from flask import Blueprint, jsonify, request

from services.ai_polish import polish_content
from services.article_backups import checkpoint_backup_content
from services.article_preview import render_editor_preview
from services.auth import admin_required

ai_bp = Blueprint('admin_ai', __name__, url_prefix='/admin')


@ai_bp.route('/api/ai/polish', methods=['POST'])
@admin_required
def ai_polish():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    tags = (data.get('tags') or '').strip()
    content = (data.get('content') or '').strip()
    provider_id = (data.get('provider') or '').strip()
    model = (data.get('model') or '').strip()
    mode = (data.get('mode') or '').strip()
    organize_first = bool(data.get('organize_first'))
    backup_key = (data.get('backup_key') or '').strip()
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
    if backup_key:
        # 润色是整篇替换，不是键入：把备份基线推进到润色结果，
        # 避免下一次自动备份的 diff 把全文计成当天新键入字数。
        checkpoint_backup_content(backup_key, polished)
    return jsonify({'content': polished})


@ai_bp.route('/api/preview', methods=['POST'])
@admin_required
def preview_markdown():
    data = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'html': ''})
    preview = render_editor_preview(
        title=data.get('title') or '',
        tags=data.get('tags') or '',
        content=content,
        cover_image=data.get('cover_image') or '',
        cover_alt=data.get('cover_alt') or '',
    )
    return jsonify(preview)
