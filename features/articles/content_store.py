"""Article-body operations independent from SQLite metadata persistence."""

from __future__ import annotations

import re


def count_words(text: str) -> int:
    """Count CJK characters and Latin-number word groups in a Markdown body."""
    source = str(text or "")
    cjk = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", source))
    latin_words = len(re.findall(r"[a-zA-Z0-9]+", source))
    return cjk + latin_words
