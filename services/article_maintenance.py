"""Offline maintenance for immutable article-body versions.

This module is intentionally not called from request handlers. Version files can
briefly exist before their database pointer commits, so online cleanup would race
with writers. Operators first run the default dry-run command, then run an apply
operation only while writes are stopped. Applied files are moved into a timestamped
recovery batch with a manifest instead of being deleted permanently.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import config


CONTENT_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}$")
DEFAULT_RETENTION_DAYS = 30


def _article_directory() -> Path:
    """Return the canonical article directory without following arbitrary paths."""
    return Path(config.ARTICLES_DIR).resolve()


def _referenced_content_keys() -> set[str]:
    """Read all committed immutable body pointers from SQLite."""
    connection = sqlite3.connect(config.DATABASE)
    try:
        rows = connection.execute(
            "SELECT content_key FROM articles WHERE content_key <> ''"
        ).fetchall()
    finally:
        connection.close()
    return {
        str(row[0]).lower()
        for row in rows
        if CONTENT_KEY_PATTERN.fullmatch(str(row[0] or "").lower())
    }


def _write_recovery_manifest(path: Path, report: dict[str, Any]) -> None:
    """Atomically persist a recovery-batch audit record before and after moves."""
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix='.tmp',
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def plan_article_version_cleanup(
    retention_days: int = DEFAULT_RETENTION_DAYS,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """List old unreferenced immutable versions without changing any files."""
    if not isinstance(retention_days, int) or retention_days < 0:
        raise ValueError("保留天数必须是非负整数")

    article_directory = _article_directory()
    current_time = now or datetime.now()
    cutoff = current_time - timedelta(days=retention_days)
    referenced = _referenced_content_keys()
    candidates: list[dict[str, str]] = []
    retained = {"referenced": 0, "recent": 0, "non_version": 0}

    if not article_directory.is_dir():
        return {
            "retention_days": retention_days,
            "cutoff": cutoff.isoformat(),
            "candidates": candidates,
            "retained": retained,
        }

    for path in sorted(article_directory.glob("*.md")):
        content_key = path.stem.lower()
        if not CONTENT_KEY_PATTERN.fullmatch(content_key):
            retained["non_version"] += 1
            continue
        if content_key in referenced:
            retained["referenced"] += 1
            continue
        try:
            modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            # A disappeared or unreadable file should be left for the next dry run.
            retained["recent"] += 1
            continue
        if modified_at > cutoff:
            retained["recent"] += 1
            continue
        candidates.append(
            {
                "content_key": content_key,
                "path": str(path),
                "modified_at": modified_at.isoformat(),
            }
        )

    return {
        "retention_days": retention_days,
        "cutoff": cutoff.isoformat(),
        "candidates": candidates,
        "retained": retained,
    }


def quarantine_article_versions(
    retention_days: int = DEFAULT_RETENTION_DAYS,
    *,
    dry_run: bool = True,
    offline: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Move planned versions into a recoverable batch after offline confirmation."""
    if not dry_run and not offline:
        raise ValueError("实际回收必须显式确认离线维护模式")

    plan = plan_article_version_cleanup(retention_days, now=now)
    plan["dry_run"] = dry_run
    plan["quarantined"] = []
    if dry_run or not plan["candidates"]:
        return plan

    # Re-read pointers immediately before moves so a stale plan never removes a
    # version that was committed after the dry run began.
    referenced = _referenced_content_keys()
    article_directory = _article_directory()
    batch_name = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    recovery_directory = article_directory / ".recovery" / batch_name
    recovery_directory.mkdir(parents=True, exist_ok=False)
    plan["recovery_directory"] = str(recovery_directory)
    manifest_path = recovery_directory / "manifest.json"
    plan["manifest"] = str(manifest_path)
    plan["state"] = "in_progress"
    # If the process crashes during moves, this initial manifest still records
    # the intent and lets an operator reconcile the recoverable batch.
    _write_recovery_manifest(manifest_path, plan)

    for candidate in plan["candidates"]:
        content_key = candidate["content_key"]
        source_path = article_directory / f"{content_key}.md"
        if content_key in referenced or not source_path.is_file():
            continue
        destination_path = recovery_directory / source_path.name
        try:
            os.replace(source_path, destination_path)
        except OSError as exc:
            candidate["error"] = str(exc)
            continue
        plan["quarantined"].append(
            {
                **candidate,
                "recovery_path": str(destination_path),
            }
        )

    plan["state"] = "complete"
    _write_recovery_manifest(manifest_path, plan)
    return plan


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查或隔离未引用文章正文版本")
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    parser.add_argument("--apply", action="store_true", help="移动候选文件到恢复目录")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="确认应用写入已停止；仅 --apply 时必填",
    )
    return parser


def main() -> int:
    """Run the maintenance command and print a machine-readable audit record."""
    args = _build_parser().parse_args()
    if args.apply and not args.offline:
        raise SystemExit("--apply 只能与 --offline 一起使用")
    report = quarantine_article_versions(
        args.retention_days,
        dry_run=not args.apply,
        offline=args.offline,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
