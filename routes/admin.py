import os
import sqlite3
import uuid
from datetime import datetime
from functools import wraps

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for

import config
from models import get_db
from services.admin_modules import build_admin_module_context, build_admin_nav, get_admin_module
from services.ai_polish import get_public_polish_profiles, polish_content
from services.articles import (
    delete_article_file,
    get_article_meta,
    list_admin_articles,
    read_article_file,
    slugify,
    write_article_file,
)
from services.home_layout import load_home_layout, save_home_layout
from services.home_modules import (
    normalize_section_order,
    normalize_section_visibility,
    section_order_from_text,
    section_order_to_text,
    section_registry,
)

bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.context_processor
def inject_admin_nav():
    return {'admin_nav': build_admin_nav()}


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return wrapper


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == config.ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin.dashboard'))
        flash('密码错误', 'error')
    return render_template('admin/login.html')


@bp.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('public.index'))


@bp.route('')
@login_required
def dashboard():
    return render_template('admin/dashboard.html', articles=list_admin_articles())


@bp.route('/modules')
@login_required
def module_index():
    return render_template('admin/modules.html')


@bp.route('/modules/<module_id>')
@login_required
def module_page(module_id):
    admin_module = get_admin_module(module_id)
    if not admin_module:
        abort(404)
    if admin_module.url != request.path:
        return redirect(admin_module.url)
    if module_id == 'daily_quote':
        return layout()
    if not admin_module.template:
        return render_template('admin/module_placeholder.html', module=admin_module)
    return render_template(admin_module.template, **build_admin_module_context(admin_module))


def _edit_template(article=None):
    return render_template(
        'admin/edit.html',
        article=article,
        ai_polish_profiles=get_public_polish_profiles(),
    )


@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_article():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        tags = request.form.get('tags', '').strip()
        content = request.form.get('content', '').strip()
        if not title or not content:
            flash('标题和内容不能为空', 'error')
            return _edit_template(article=None)
        slug = slugify(title)
        now = datetime.now().isoformat()
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO articles (slug, title, tags, created_at, updated_at) VALUES (?,?,?,?,?)",
                (slug, title, tags, now, now)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"
            conn.execute(
                "INSERT INTO articles (slug, title, tags, created_at, updated_at) VALUES (?,?,?,?,?)",
                (slug, title, tags, now, now)
            )
            conn.commit()
        conn.close()
        write_article_file(slug, content)
        flash('文章已发布', 'success')
        return redirect(url_for('public.article', slug=slug))
    return _edit_template(article=None)


@bp.route('/edit/<slug>', methods=['GET', 'POST'])
@login_required
def edit_article(slug):
    article = get_article_meta(slug, published_only=False)
    if not article:
        abort(404)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        tags = request.form.get('tags', '').strip()
        content = request.form.get('content', '').strip()
        now = datetime.now().isoformat()
        conn = get_db()
        conn.execute(
            "UPDATE articles SET title=?, tags=?, updated_at=? WHERE slug=?",
            (title, tags, now, slug)
        )
        conn.commit()
        conn.close()
        write_article_file(slug, content)
        flash('文章已更新', 'success')
        return redirect(url_for('public.article', slug=slug))
    article['content'] = read_article_file(slug) or ''
    return _edit_template(article=article)


@bp.route('/delete/<slug>', methods=['POST'])
@login_required
def delete_article(slug):
    conn = get_db()
    conn.execute("DELETE FROM articles WHERE slug=?", (slug,))
    conn.commit()
    conn.close()
    delete_article_file(slug)
    flash('文章已删除', 'success')
    return redirect(url_for('admin.dashboard'))


@bp.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'file' not in request.files:
        return jsonify({'error': '没有文件'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'):
        return jsonify({'error': '不支持的图片格式'}), 400
    filename = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(config.UPLOAD_DIR, filename))
    return jsonify({'url': url_for('static', filename=f'images/{filename}')})


@bp.route('/api/ai/polish', methods=['POST'])
@login_required
def ai_polish():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    tags = (data.get('tags') or '').strip()
    content = (data.get('content') or '').strip()
    provider_id = (data.get('provider') or '').strip()
    model = (data.get('model') or '').strip()
    if not content:
        return jsonify({'error': '正文不能为空'}), 400
    try:
        polished = polish_content(title, tags, content, provider_id=provider_id, model=model)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': str(exc)}), 502
    return jsonify({'content': polished})


@bp.route('/layout', methods=['GET', 'POST'])
@login_required
def layout():
    layout_config = load_home_layout()
    if request.method == 'POST':
        quotes_raw = request.form.get("quotes", "").strip()
        quotes = [q.strip() for q in quotes_raw.splitlines() if q.strip()]
        section_order_raw = request.form.get("section_order", "")
        registry = section_registry()

        layout_config["quotes"] = quotes or ["书山有路勤为径，学海无涯苦作舟。"]
        layout_config["section_order"] = section_order_from_text(section_order_raw)
        layout_config["section_visibility"] = {
            section_id: request.form.get(f"section_enabled_{section_id}") == "on"
            for section_id in registry
        }
        save_home_layout(layout_config)
        flash('首页布局已更新', 'success')
        return redirect(url_for('admin.layout'))

    quotes_text = "\n".join(layout_config.get("quotes", []))
    section_order = normalize_section_order(layout_config.get("section_order"))
    section_order_text = section_order_to_text(section_order)
    registry = section_registry()
    section_visibility = normalize_section_visibility(layout_config.get("section_visibility"))
    section_help = [
        {
            "id": section_id,
            "name": definition.name,
            "template": definition.template,
            "enabled": section_visibility.get(section_id, True),
            "in_order": section_id in section_order,
        }
        for section_id, definition in sorted(
            registry.items(),
            key=lambda item: (item[1].default_order, item[0]),
        )
    ]
    return render_template(
        'admin/layout.html',
        quotes_text=quotes_text,
        section_order_text=section_order_text,
        section_help=section_help,
    )
