"""每日新键入字数（typing_daily）与真实文章预览的回归测试。"""

from __future__ import annotations

import uuid
from datetime import date

from models import get_db
from services import articles
from services.activity_heatmap import build_month_activity_heatmap
from services.article_backups import (
    checkpoint_backup_content,
    delete_backup,
    save_backup,
)


def _today_chars() -> int:
    row = get_db().execute(
        "SELECT chars FROM typing_daily WHERE day=?", (date.today().isoformat(),)
    ).fetchone()
    return int(row["chars"]) if row else 0


def _remove_article(article: dict) -> None:
    articles.delete_article(article["slug"])
    articles.delete_article_file(article["slug"], content_key=article["content_key"])


def test_backup_diff_counts_only_newly_typed_chars(app):
    """连续备份按 diff 计新增，重复内容不重复计数。"""
    key = f'test-{uuid.uuid4().hex[:8]}'
    with app.app_context():
        before = _today_chars()
        try:
            save_backup(key, {'content': '你好世界'})
            assert _today_chars() - before == 4
            # 内容不变时不产生新的计数
            save_backup(key, {'content': '你好世界'})
            assert _today_chars() - before == 4
            # 追加两个汉字只计新增部分
            save_backup(key, {'content': '你好世界追加'})
            assert _today_chars() - before == 6
            # 删字不计负数
            save_backup(key, {'content': '你好'})
            assert _today_chars() - before == 6
        finally:
            delete_backup(key)


def test_backup_without_previous_uses_committed_head_as_baseline(app):
    """新一轮编辑没有旧备份时，与已提交正文（HEAD）diff。"""
    with app.app_context():
        marker = uuid.uuid4().hex[:8]
        article = articles.create_article_draft(f'基线测试 {marker}', '测试', '你好世界')
        article = articles.get_article_meta(article['slug'], published_only=False)
        before = _today_chars()
        try:
            save_backup(article['slug'], {'content': '你好世界追加'})
            assert _today_chars() - before == 2
        finally:
            delete_backup(article['slug'])
            _remove_article(article)


def test_commit_with_editor_backup_does_not_double_count(app):
    """编辑期间的备份已计入键入量，保存草稿时不重复计。"""
    key = f'new-{uuid.uuid4().hex[:8]}'
    with app.app_context():
        before = _today_chars()
        marker = uuid.uuid4().hex[:8]
        try:
            save_backup(key, {'content': '你好世界'})
            assert _today_chars() - before == 4
            article = articles.create_article_draft(
                f'防重测试 {marker}', '测试', '你好世界', backup_key=key
            )
            assert _today_chars() - before == 4
            _remove_article(articles.get_article_meta(article['slug'], published_only=False))
        finally:
            delete_backup(key)


def test_checkpoint_backup_content_skips_typing_count(app):
    """AI 润色推进备份基线不计入键入字数。"""
    key = f'test-{uuid.uuid4().hex[:8]}'
    with app.app_context():
        before = _today_chars()
        try:
            save_backup(key, {'content': '原始口语稿内容'})
            assert _today_chars() - before == 7
            checkpoint_backup_content(key, '润色之后完全不同的成稿内容')
            assert _today_chars() - before == 7
            # 基线已推进：继续备份润色稿不产生计数
            save_backup(key, {'content': '润色之后完全不同的成稿内容'})
            assert _today_chars() - before == 7
        finally:
            delete_backup(key)


def test_heatmap_uses_daily_typed_chars(app):
    """热力图指标直接来自 typing_daily 的当天新键入字数。"""
    key = f'test-{uuid.uuid4().hex[:8]}'
    with app.app_context():
        try:
            save_backup(key, {'content': '热力图验证文字'})
            expected = _today_chars()
            heatmap = build_month_activity_heatmap()
            assert heatmap['today_words'] == expected
            today_cell = next(
                cell for week in heatmap['weeks'] for cell in week if cell['is_today']
            )
            assert today_cell['count'] == expected
            assert f'新键入 {expected} 字' in today_cell['label']
        finally:
            delete_backup(key)


def test_preview_renders_full_article_structure(login):
    """实时预览返回标题、封面、目录、正文的完整发布页结构。"""
    response = login.post(
        '/admin/api/preview',
        json={
            'title': '预览标题',
            'tags': '测试, 随笔',
            'content': '## 第一章\n\n正文内容\n\n## 第二章\n\n更多内容',
            'cover_image': 'images/cover.jpg',
            'cover_alt': '封面',
        },
    )
    assert response.status_code == 200
    html = response.get_json()['html']
    assert 'article-cover-hero' in html
    assert '/static/images/cover.jpg' in html
    assert '预览标题' in html
    assert 'article-body' in html
    assert 'preview-toc' in html
    assert html.count('toc-item') >= 2
    assert '第一章' in html and '第二章' in html
    assert 'tag-sm' in html


def test_preview_without_cover_uses_plain_header(login):
    """无封面时预览走普通标题头，不渲染 hero。"""
    response = login.post(
        '/admin/api/preview',
        json={'title': '无封面', 'tags': '', 'content': '正文'},
    )
    assert response.status_code == 200
    html = response.get_json()['html']
    assert 'article-header' in html
    assert 'article-cover-hero' not in html
    assert '无封面' in html
