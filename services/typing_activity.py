"""按天统计新键入的有效字符数（类似 git 的版本 diff 模型）。

基线链：已提交正文（HEAD）→ 编辑器自动备份（工作区）→ 下一次提交。
每次备份写入时与上一个备份（或 HEAD）diff，每次文章提交时与最新备份
（或旧 HEAD）diff，只把新增片段计入当天，避免重复计数与漏计。
有效字符与全站「字数」口径一致：CJK 汉字逐个计，英文/数字按单词计。
指标只用于首页热力图，任何失败都不能影响备份与文章主流程。
"""

from __future__ import annotations

import difflib
import re
from datetime import date

from models import get_db

_CJK_RE = re.compile(r'[一-鿿㐀-䶿]')
_EN_WORD_RE = re.compile(r'[a-zA-Z0-9]+')
_NEW_ARTICLE_KEY_PREFIX = 'new-'


def _effective_count(text: str) -> int:
    """与文章字数同口径：汉字逐字 + 英文单词。"""
    return len(_CJK_RE.findall(text)) + len(_EN_WORD_RE.findall(text))


def _added_effective_chars(old: str, new: str) -> int:
    """diff 两个版本，统计新增片段里的有效字符（删除不计）。"""
    if not new or old == new:
        return 0
    matcher = difflib.SequenceMatcher(None, old or '', new, autojunk=False)
    added = 0
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ('insert', 'replace'):
            added += _effective_count(new[j1:j2])
    return added


def _add_to_today(chars: int) -> None:
    if chars <= 0:
        return
    today = date.today().isoformat()
    conn = get_db()
    conn.execute(
        """
        INSERT INTO typing_daily (day, chars) VALUES (?, ?)
        ON CONFLICT(day) DO UPDATE SET chars = chars + excluded.chars
        """,
        (today, int(chars)),
    )
    conn.commit()


def _committed_content(key: str) -> str:
    """读取文章的已提交版本（git 里的 HEAD）；新文章或读取失败返回空串。"""
    key = str(key or '')
    if not key or key.startswith(_NEW_ARTICLE_KEY_PREFIX):
        return ''
    from services.articles import read_article_file

    try:
        return read_article_file(key) or ''
    except Exception:
        return ''


def record_backup_typing(key: str, previous_content: str | None, new_content: str) -> None:
    """备份写入时调用：与上一备份 diff，无上一备份时与 HEAD diff。"""
    try:
        old = previous_content if previous_content is not None else _committed_content(key)
        _add_to_today(_added_effective_chars(old, str(new_content or '')))
    except Exception:
        pass


def record_commit_typing(
    slug: str,
    previous_committed: str,
    new_content: str,
    backup_key: str = '',
) -> None:
    """文章提交（创建/更新）时调用：基线取最新备份，其次旧 HEAD。

    编辑期间新文章用前端生成的临时备份标识，与保存后的 slug 不同，
    因此调用方需要把表单里的 ``backup_key`` 透传过来才能接上 diff 链。
    """
    try:
        from services.article_backups import load_backup

        backup = load_backup(backup_key or slug)
        if backup is not None and backup.get('content') is not None:
            old = backup.get('content') or ''
        else:
            old = previous_committed or ''
        _add_to_today(_added_effective_chars(old, str(new_content or '')))
    except Exception:
        pass
