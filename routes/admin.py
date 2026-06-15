import os
import sqlite3
import uuid
from datetime import datetime

from flask import Blueprint, abort, flash, jsonify, make_response, redirect, render_template, request, session, url_for

import config
from models import get_db
from services.admin_modules import build_admin_module_context, build_admin_nav, get_admin_module
from services.access_settings import get_access_settings, save_access_settings
from services.ai_chat import get_public_chat_admin_settings, save_public_chat_settings
from services.ai_polish import get_public_polish_modes, get_public_polish_profiles
from services.articles import (
    delete_article_file,
    get_article_meta,
    list_admin_articles,
    list_all_tags,
    list_all_tags_admin,
    list_drafts,
    publish_article as svc_publish_article,
    read_article_file,
    slugify,
    write_article_file,
)
from services.activity_heatmap import _count_words
from services.auth import login_required
from services.visitor_auth import (
    VisitorAuthError,
    authenticate_admin,
    clear_visitor_cookie,
    revoke_current_visitor_token,
    set_visitor_cookie,
)
from services.home_layout_admin import handle_layout
from services.wechat_export import build_digest, render_wechat_html

bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.context_processor
def inject_admin_nav():
    return {'admin_nav': build_admin_nav()}


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            visitor, token, expires_at = authenticate_admin(request.form.get('password', ''))
        except VisitorAuthError:
            flash('密码错误', 'error')
        else:
            session['logged_in'] = True
            response = make_response(redirect(url_for('admin.dashboard')))
            set_visitor_cookie(response, token, expires_at)
            return response
    return render_template('admin/login.html')


@bp.route('/logout')
def logout():
    session.pop('logged_in', None)
    revoke_current_visitor_token()
    response = make_response(redirect(url_for('public.index')))
    clear_visitor_cookie(response)
    return response


@bp.route('')
@login_required
def dashboard():
    drafts = list_drafts()
    published = list_admin_articles()
    return render_template('admin/dashboard.html', drafts=drafts, articles=published)


@bp.route('/modules')
@login_required
def module_index():
    return render_template('admin/modules.html')


@bp.route('/chat-settings', methods=['GET', 'POST'])
@login_required
def chat_settings():
    if request.method == 'POST':
        try:
            save_public_chat_settings(request.form)
        except ValueError as exc:
            flash(str(exc), 'error')
        else:
            flash('AI 对话设置已保存', 'success')
            return redirect(url_for('admin.chat_settings'))
    return render_template('admin/chat_settings.html', settings=get_public_chat_admin_settings())


@bp.route('/access-settings', methods=['GET', 'POST'])
@login_required
def access_settings():
    if request.method == 'POST':
        try:
            save_access_settings(request.form)
        except ValueError as exc:
            flash(str(exc), 'error')
        else:
            flash('访问设置已保存', 'success')
            return redirect(url_for('admin.access_settings'))
    return render_template('admin/access_settings.html', settings=get_access_settings())


@bp.route('/modules/<module_id>', methods=['GET', 'POST'])
@login_required
def module_page(module_id):
    admin_module = get_admin_module(module_id)
    if not admin_module:
        abort(404)
    if admin_module.url != request.path:
        return redirect(admin_module.url)
    if module_id == 'daily_quote':
        return handle_layout()
    if not admin_module.template:
        return render_template('admin/module_placeholder.html', module=admin_module)
    return render_template(admin_module.template, **build_admin_module_context(admin_module))


def _edit_template(article=None):
    return render_template(
        'admin/edit.html',
        article=article,
        all_tags=list_all_tags_admin(),
        ai_polish_profiles=get_public_polish_profiles(),
        ai_polish_modes=get_public_polish_modes(),
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
            wc = _count_words(content)
            conn.execute(
                "INSERT INTO articles (slug, title, tags, created_at, updated_at, published, word_count) VALUES (?,?,?,?,?,0,?)",
                (slug, title, tags, now, now, wc)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"
            conn.execute(
                "INSERT INTO articles (slug, title, tags, created_at, updated_at, published, word_count) VALUES (?,?,?,?,?,0,?)",
                (slug, title, tags, now, now, wc)
            )
            conn.commit()
        write_article_file(slug, content)
        flash('草稿已保存', 'success')
        return redirect(url_for('admin.edit_article', slug=slug))
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
        write_article_file(slug, content)
        flash('文章已更新', 'success')
        if article.get('published'):
            return redirect(url_for('public.article', slug=slug))
        return redirect(url_for('admin.edit_article', slug=slug))
    article['content'] = read_article_file(slug) or ''
    return _edit_template(article=article)


@bp.route('/wechat-export/<slug>')
@login_required
def wechat_export(slug):
    article = get_article_meta(slug, published_only=False)
    if not article:
        abort(404)
    content = read_article_file(slug) or ''
    base_url = request.url_root.rstrip('/')
    source_url = url_for('public.article', slug=slug, _external=True)
    export = render_wechat_html(
        title=article.get('title') or '',
        markdown_text=content,
        base_url=base_url,
        source_url=source_url,
        author='水浇岭',
        tags=article.get('tags') or '',
    )
    export['digest'] = build_digest(content)
    export['source_url'] = source_url
    export['article'] = article
    return render_template('admin/wechat_export.html', **export)


@bp.route('/delete/<slug>', methods=['POST'])
@login_required
def delete_article(slug):
    conn = get_db()
    conn.execute("DELETE FROM articles WHERE slug=?", (slug,))
    conn.commit()
    delete_article_file(slug)
    flash('文章已删除', 'success')
    return redirect(url_for('admin.dashboard'))


@bp.route('/publish/<slug>', methods=['POST'])
@login_required
def publish(slug):
    article = get_article_meta(slug, published_only=False)
    if not article:
        abort(404)
    svc_publish_article(slug)
    flash('文章已发布', 'success')
    return redirect(url_for('public.article', slug=slug))


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


@bp.route('/layout', methods=['GET', 'POST'])
@login_required
def layout():
    return handle_layout()
