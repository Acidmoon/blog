"""编辑器自动备份：与草稿分离的防丢失机制。

每篇被编辑的文章（已发布或草稿）有且仅有一个 JSON 备份文件，存放在
``data/article_backups/``。编辑器每隔一段时间把当前表单的全部内容覆盖写入
对应的备份文件，防止断连、崩溃导致未保存内容丢失。文章保存、发布或删除后
对应的备份文件即被清理。尚未保存过的新文章使用前端生成的 UUID 作为备份标识，
首次保存成功后由服务端按表单携带的 ``backup_key`` 清理。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

import config

_MAX_KEY_LENGTH = 200
_KEY_FORBIDDEN = re.compile(r'[\\/]')
_BACKUP_FIELDS = ('title', 'tags', 'content', 'cover_image', 'cover_alt')


def _backup_dir() -> Path:
    path = Path(config.DATA_DIR) / 'article_backups'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _validate_key(key: str) -> str:
    """备份标识即文件名，必须杜绝路径穿越。slug 允许中文等 Unicode 字符。"""
    key = str(key or '').strip()
    if (
        not key
        or len(key) > _MAX_KEY_LENGTH
        or '..' in key
        or _KEY_FORBIDDEN.search(key)
    ):
        raise ValueError('非法的备份标识')
    return key


def _backup_path(key: str) -> Path:
    return _backup_dir() / f'{_validate_key(key)}.json'


def save_backup(key: str, payload: dict) -> dict:
    """覆盖写入某篇文章唯一的备份文件，先写临时文件再原子替换。"""
    path = _backup_path(key)
    data = {field: str(payload.get(field) or '') for field in _BACKUP_FIELDS}
    data['saved_at'] = datetime.now().isoformat(timespec='seconds')
    tmp_path = path.with_suffix('.json.tmp')
    tmp_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp_path, path)
    return data


def load_backup(key: str) -> dict | None:
    """读取备份内容；标识非法、文件缺失或内容损坏时返回 None。"""
    try:
        path = _backup_path(key)
    except ValueError:
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None


def delete_backup(key: str) -> None:
    """删除备份文件；标识非法或文件不存在时静默忽略。"""
    try:
        path = _backup_path(key)
        path.unlink()
    except (ValueError, FileNotFoundError):
        pass
