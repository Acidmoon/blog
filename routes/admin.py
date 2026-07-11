from flask import Blueprint, abort, flash, jsonify, make_response, redirect, render_template, request, url_for

from services.admin_modules import build_admin_module_context, build_admin_nav, build_admin_nav_groups, get_admin_module
from services.access_settings import get_access_settings, save_access_settings
from services.ai_chat import get_public_chat_admin_settings, save_public_chat_settings
from services.ai_polish import get_public_polish_modes, get_public_polish_profiles
from services.articles import (
    create_article_draft,
    delete_article as svc_delete_article,
    get_article_meta,
    list_admin_articles,
    list_all_tags_admin,
    list_drafts,
    publish_article as svc_publish_article,
    read_article_file,
    update_article as svc_update_article,
)
from services.auth import (
    admin_required,
    clear_admin_session,
    current_identity,
    mark_admin_authenticated,
    safe_next_url,
)
from services.request_security import rotate_csrf_token
from services.media_uploads import MediaUploadError, save_admin_image
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
    return {
        'admin_nav': build_admin_nav(),
        'admin_nav_groups': build_admin_nav_groups(),
    }


@bp.route('/login', methods=['GET', 'POST'])
def login():
    next_url = safe_next_url(request.values.get('next'), url_for('admin.dashboard'))
    if current_identity().is_admin:
        return redirect(next_url)
    if request.method == 'POST':
        try:
            visitor, token, expires_at = authenticate_admin(request.form.get('password', ''))
        except VisitorAuthError:
            return render_template('admin/login.html', error='密码错误', next_url=next_url), 400
        mark_admin_authenticated()
        rotate_csrf_token()
        response = make_response(redirect(next_url))
        set_visitor_cookie(response, token, expires_at)
        return response
    return render_template(
        'login.html',
        error='',
        next_url=next_url,
        auth_mode='login',
        admin_context=True,
    )


@bp.route('/logout')
def logout():
    clear_admin_session()
    revoke_current_visitor_token()
    response = make_response(redirect(url_for('public.index')))
    clear_visitor_cookie(response)
    return response


@bp.route('')
@admin_required
def dashboard():
    drafts = list_drafts()
    published = list_admin_articles()
    return render_template('admin/dashboard.html', drafts=drafts, articles=published)


@bp.route('/modules')
@admin_required
def module_index():
    return render_template('admin/modules.html')


@bp.route('/chat-settings', methods=['GET', 'POST'])
@admin_required
def chat_settings():
    """Keep the restored public-chat controls inside the current admin shell."""
    if request.method == 'POST':
        try:
            save_public_chat_settings(request.form)
        except ValueError as exc:
            flash(str(exc), 'error')
        else:
            flash('聊天设置已保存', 'success')
            return redirect(url_for('admin.chat_settings'))
    return render_template('admin/chat_settings.html', settings=get_public_chat_admin_settings())


@bp.route('/access-settings', methods=['GET', 'POST'])
@admin_required
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
@admin_required
def module_page(module_id):
    admin_module = get_admin_module(module_id)
    if not admin_module:
        abort(404)
    if admin_module.url != request.path:
        return redirect(admin_module.url)
    if admin_module.handler:
        return admin_module.handler()
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
@admin_required
def new_article():
    if request.method == 'POST':
        try:
            article = create_article_draft(
                request.form.get('title', ''),
                request.form.get('tags', ''),
                request.form.get('content', ''),
                request.form.get('cover_image', ''),
                request.form.get('cover_alt', ''),
            )
        except ValueError as exc:
            flash(str(exc), 'error')
            return _edit_template(article=None)
        flash('草稿已保存', 'success')
        return redirect(url_for('admin.edit_article', slug=article['slug']))
    return _edit_template(article=None)


@bp.route('/edit/<slug>', methods=['GET', 'POST'])
@admin_required
def edit_article(slug):
    article = get_article_meta(slug, published_only=False)
    if not article:
        abort(404)
    if request.method == 'POST':
        try:
            svc_update_article(
                slug,
                request.form.get('title', ''),
                request.form.get('tags', ''),
                request.form.get('content', ''),
                request.form.get('cover_image', ''),
                request.form.get('cover_alt', ''),
            )
        except ValueError as exc:
            flash(str(exc), 'error')
            article['content'] = request.form.get('content', '')
            return _edit_template(article=article)
        flash('文章已更新', 'success')
        if article.get('published'):
            return redirect(url_for('public.article', slug=slug))
        return redirect(url_for('admin.edit_article', slug=slug))
    article['content'] = read_article_file(slug) or ''
    return _edit_template(article=article)


@bp.route('/wechat-export/<slug>')
@admin_required
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
@admin_required
def delete_article(slug):
    svc_delete_article(slug)
    flash('文章已删除', 'success')
    return redirect(url_for('admin.dashboard'))


@bp.route('/publish/<slug>', methods=['POST'])
@admin_required
def publish(slug):
    article = get_article_meta(slug, published_only=False)
    if not article:
        abort(404)
    if request.form.get('content') is not None:
        try:
            article = svc_update_article(
                slug,
                request.form.get('title', ''),
                request.form.get('tags', ''),
                request.form.get('content', ''),
                request.form.get('cover_image', ''),
                request.form.get('cover_alt', ''),
            )
        except ValueError as exc:
            flash(str(exc), 'error')
            article['title'] = request.form.get('title', '')
            article['tags'] = request.form.get('tags', '')
            article['cover_image'] = request.form.get('cover_image', '')
            article['cover_alt'] = request.form.get('cover_alt', '')
            article['content'] = request.form.get('content', '')
            return _edit_template(article=article)
        except LookupError:
            abort(404)

    try:
        svc_publish_article(slug)
    except ValueError as exc:
        flash(str(exc), 'error')
        article['content'] = read_article_file(slug) or ''
        return _edit_template(article=article)
    flash('文章已发布', 'success')
    return redirect(url_for('public.article', slug=slug))


@bp.route('/upload', methods=['POST'])
@admin_required
def upload():
    try:
        static_filename = save_admin_image(request.files.get('file'))
    except MediaUploadError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'url': url_for('static', filename=static_filename)})


@bp.route('/layout', methods=['GET', 'POST'])
@admin_required
def layout():
    return handle_layout()
