"""Shared full-text index document construction for article write transactions."""

from __future__ import annotations

import re


_MARKDOWN_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
_SEARCH_TOKEN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]|[A-Za-z0-9_]+")


def article_search_text(markdown_text: str) -> str:
    """Produce a CJK character/word token stream for Unicode61 FTS matching."""
    text = str(markdown_text or "")
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = _HTML_TAG.sub(" ", text)
    text = text.replace("`", " ").replace("#", " ")
    text = _WHITESPACE.sub(" ", text).strip()
    return " ".join(_SEARCH_TOKEN.findall(text))


def article_search_terms(query: str) -> list[str]:
    """Return literal FTS terms for untrusted query text without query operators."""
    return _SEARCH_TOKEN.findall(str(query or ""))


def sync_article_search(
    conn,
    article_id: int,
    title: str,
    tags: str,
    markdown_text: str,
) -> None:
    """Replace one article's FTS row within its existing metadata transaction."""
    conn.execute("DELETE FROM article_search WHERE article_id=?", (article_id,))
    conn.execute(
        """
        INSERT INTO article_search (article_id, title, tags, content)
        VALUES (?, ?, ?, ?)
        """,
        (
            article_id,
            article_search_text(title),
            article_search_text(tags),
            article_search_text(markdown_text),
        ),
    )


def delete_article_search(conn, article_id: int) -> None:
    """Remove a deleted article's FTS row within the caller's transaction."""
    conn.execute("DELETE FROM article_search WHERE article_id=?", (article_id,))
