"""Small key/value settings store backed by SQLite."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from models import get_db


def get_setting(key: str, default: str = '') -> str:
    row = get_db().execute(
        "SELECT value FROM site_settings WHERE key=?",
        (key,),
    ).fetchone()
    if not row:
        return default
    return row['value']


def get_settings(defaults: Mapping[str, str]) -> dict[str, str]:
    settings = dict(defaults)
    keys = list(defaults.keys())
    if not keys:
        return settings
    placeholders = ','.join('?' for _ in keys)
    rows = get_db().execute(
        f"SELECT key, value FROM site_settings WHERE key IN ({placeholders})",
        keys,
    ).fetchall()
    for row in rows:
        settings[row['key']] = row['value']
    return settings


def set_setting(key: str, value: str) -> None:
    set_settings({key: value})


def set_settings(values: Mapping[str, str]) -> None:
    if not values:
        return
    now = datetime.now().isoformat(timespec='seconds')
    conn = get_db()
    conn.executemany(
        """
        INSERT INTO site_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at
        """,
        [(key, str(value), now) for key, value in values.items()],
    )
    conn.commit()


def delete_settings(keys: list[str]) -> None:
    if not keys:
        return
    placeholders = ','.join('?' for _ in keys)
    conn = get_db()
    conn.execute(f"DELETE FROM site_settings WHERE key IN ({placeholders})", keys)
    conn.commit()
