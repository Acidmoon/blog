"""Article feature-boundary coverage for public detail page reads."""

from __future__ import annotations

import uuid

from features.articles.application import load_public_article_page
from models import get_db
from services import articles


def _remove_article(article: dict) -> None:
    """Delete test metadata and its immutable body without touching shared data."""
    articles.delete_article(article["slug"])
    articles.delete_article_file(article["slug"], content_key=article["content_key"])


def test_article_feature_builds_detail_and_stable_neighbors_for_equal_timestamps(app):
    """The feature owns words, rendering, and navigation without route SQL."""
    with app.app_context():
        marker = uuid.uuid4().hex[:8]
        created = [
            articles.create_article_draft(f"导航测试 {marker} {index}", "测试", f"正文 {index}")
            for index in range(3)
        ]
        published = []
        try:
            for article in created:
                articles.publish_article(article["slug"])
                published.append(articles.get_article_meta(article["slug"], published_only=False))
            get_db().executemany(
                "UPDATE articles SET created_at=? WHERE id=?",
                [("2026-01-01T00:00:00", article["id"]) for article in published],
            )
            get_db().commit()

            page = load_public_article_page(published[1]["slug"])

            assert page is not None
            assert page.article["current_word_count"] > 0
            assert page.previous_article == {"slug": published[0]["slug"], "title": published[0]["title"]}
            assert page.next_article == {"slug": published[2]["slug"], "title": published[2]["title"]}
            assert "<p>" in page.content_html
        finally:
            for article in published or created:
                _remove_article(article)
