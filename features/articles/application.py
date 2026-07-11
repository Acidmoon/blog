"""Application workflows that compose article metadata, bodies, and navigation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.articles import get_article_meta, read_article_file, render_md

from .content_store import count_words
from .repository import find_published_neighbors


@dataclass(frozen=True)
class PublicArticlePage:
    """Read model needed to render one public article page."""

    article: dict[str, Any]
    content_html: str
    previous_article: dict[str, Any] | None
    next_article: dict[str, Any] | None


def load_public_article_page(slug: str) -> PublicArticlePage | None:
    """Load a published article and all article-domain context for its page."""
    article = get_article_meta(slug)
    if not article:
        return None
    content = read_article_file(slug, article.get("content_key", ""))
    if content is None:
        return None
    article = dict(article)
    article["current_word_count"] = count_words(content)
    previous_article, next_article = find_published_neighbors(article["id"], article["created_at"])
    return PublicArticlePage(
        article=article,
        content_html=render_md(content),
        previous_article=previous_article,
        next_article=next_article,
    )
