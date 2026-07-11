"""Regression coverage for offline immutable-body maintenance."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from services import article_maintenance, articles


def _make_old_unreferenced_version() -> tuple[dict, str, Path]:
    """Create an old body that is no longer referenced after a normal edit."""
    article = articles.create_article_draft(
        f"回收测试 {uuid.uuid4().hex[:8]}",
        "维护",
        "旧正文",
    )
    old_key = article["content_key"]
    updated = articles.update_article(article["slug"], article["title"], "维护", "新正文")
    old_path = articles._content_path(old_key)
    old_timestamp = (datetime.now() - timedelta(days=60)).timestamp()
    os.utime(old_path, (old_timestamp, old_timestamp))
    return updated, old_key, old_path


def test_cleanup_plan_keeps_current_versions_and_lists_old_unreferenced_ones(app):
    """Dry runs identify only stale unreferenced immutable files."""
    with app.app_context():
        article, old_key, old_path = _make_old_unreferenced_version()
        try:
            plan = article_maintenance.quarantine_article_versions(retention_days=30)

            assert plan["dry_run"] is True
            assert any(item["content_key"] == old_key for item in plan["candidates"])
            assert old_path.is_file()
            assert all(item["content_key"] != article["content_key"] for item in plan["candidates"])
        finally:
            articles.delete_article(article["slug"])
            for content_key in (old_key, article["content_key"]):
                path = articles._content_path(content_key)
                if path.exists():
                    articles.delete_article_file(article["slug"], content_key=content_key)


def test_cleanup_apply_requires_offline_confirmation_and_creates_recovery_manifest(app):
    """Apply mode is explicit and moves files into an auditable recovery batch."""
    with app.app_context():
        article, old_key, old_path = _make_old_unreferenced_version()
        recovery_directory = None
        try:
            with pytest.raises(ValueError, match="离线维护"):
                article_maintenance.quarantine_article_versions(retention_days=30, dry_run=False)

            report = article_maintenance.quarantine_article_versions(
                retention_days=30,
                dry_run=False,
                offline=True,
            )
            recovery_directory = Path(report["recovery_directory"])
            moved = next(item for item in report["quarantined"] if item["content_key"] == old_key)

            assert not old_path.exists()
            assert Path(moved["recovery_path"]).is_file()
            manifest = json.loads(Path(report["manifest"]).read_text(encoding="utf-8"))
            assert manifest["dry_run"] is False
            assert manifest["state"] == "complete"
        finally:
            articles.delete_article(article["slug"])
            current_path = articles._content_path(article["content_key"])
            if current_path.exists():
                articles.delete_article_file(article["slug"], content_key=article["content_key"])
            if recovery_directory and recovery_directory.exists():
                for path in recovery_directory.iterdir():
                    path.unlink()
                recovery_directory.rmdir()
                recovery_parent = recovery_directory.parent
                if not any(recovery_parent.iterdir()):
                    recovery_parent.rmdir()
