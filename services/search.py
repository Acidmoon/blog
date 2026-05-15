import re

from models import get_db
from services.articles import read_article_file


def highlight_text(text, query):
    """Case-insensitive highlight: wrap occurrences of query in <mark> tags."""
    if not query or not text:
        return text
    q = re.escape(query)
    return re.sub(f'({q})', r'<mark>\1</mark>', text, flags=re.IGNORECASE)


def search_articles(query):
    """Search articles by title, tags, and content. Returns (article_dict, snippet_html, title_html)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE published=1 ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    q = query.lower().strip()
    results = []
    for row in rows:
        article = dict(row)
        title_match = q in article['title'].lower()
        tag_match = q in (article['tags'] or '').lower()
        content = read_article_file(article['slug'])
        content_match = content and q in content.lower()
        if title_match or tag_match or content_match:
            snippet = ''
            if content_match and content:
                idx = content.lower().find(q)
                start = max(0, idx - 60)
                end = min(len(content), idx + len(q) + 120)
                snippet = content[start:end].strip()
                if start > 0:
                    snippet = '…' + snippet
                if end < len(content):
                    snippet = snippet + '…'
                snippet = highlight_text(snippet, query)
            elif tag_match:
                snippet = f'标签包含「{query}」'
            else:
                snippet = '标题匹配'
            title_html = highlight_text(article['title'], query)
            results.append((article, snippet, title_html, title_match))
    results.sort(key=lambda x: (not x[3], x[0]['created_at']), reverse=False)
    return results
