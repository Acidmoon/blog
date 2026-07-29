"""Regression coverage for the public Markdown download endpoint and editor CSRF field."""

from __future__ import annotations

import uuid

from services import articles


def _remove_article(article: dict) -> None:
    """Delete test metadata and its immutable body without touching shared data."""
    articles.delete_article(article["slug"])
    articles.delete_article_file(article["slug"], content_key=article["content_key"])


def test_article_download_serves_markdown_attachment(app, client):
    """A published article downloads as a .md attachment with a title heading."""
    with app.app_context():
        marker = uuid.uuid4().hex[:8]
        article = articles.create_article_draft(f"下载测试 {marker}", "测试", "下载正文内容")
        articles.publish_article(article["slug"])
        article = articles.get_article_meta(article["slug"], published_only=False)
    try:
        response = client.get(f"/article/{article['slug']}/download.md")
        assert response.status_code == 200
        assert response.mimetype == "text/markdown"
        disposition = response.headers.get("Content-Disposition", "")
        assert "attachment" in disposition
        body = response.get_data(as_text=True)
        assert body.startswith(f"# 下载测试 {marker}\n")
        assert "下载正文内容" in body
    finally:
        with app.app_context():
            _remove_article(article)


def test_article_download_rejects_drafts_and_unknown_slugs(app, client):
    """Drafts stay private and unknown slugs return 404."""
    with app.app_context():
        marker = uuid.uuid4().hex[:8]
        draft = articles.create_article_draft(f"草稿下载 {marker}", "测试", "未发布内容")
        draft = articles.get_article_meta(draft["slug"], published_only=False)
    try:
        assert client.get(f"/article/{draft['slug']}/download.md").status_code == 404
        assert client.get("/article/不存在的文章/download.md").status_code == 404
    finally:
        with app.app_context():
            _remove_article(draft)


def test_editor_form_includes_csrf_token(login):
    """The editor form must carry the synchronizer token for draft saves."""
    response = login.get("/admin/new")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="csrf_token"' in html
