"""Explicit offline and scheduled maintenance commands for the blog runtime."""

from __future__ import annotations

import argparse

import config
from services.home_layout import load_home_layout, refresh_daily_quote


def _refresh_daily_quote() -> int:
    """Refresh the durable quote cache without starting a Flask web worker."""
    config.ensure_directories()
    layout = load_home_layout()
    refreshed = refresh_daily_quote(layout.get("quotes", []))
    print(f"daily_quote_refreshed={str(refreshed).lower()}")
    return 0 if refreshed else 1


def main() -> int:
    """Dispatch one explicit maintenance operation from automation or a shell."""
    parser = argparse.ArgumentParser(description="管理 Waterhill Blog 的离线维护任务")
    parser.add_argument("command", choices=("refresh-daily-quote",))
    args = parser.parse_args()
    if args.command == "refresh-daily-quote":
        return _refresh_daily_quote()
    raise AssertionError(f"unsupported maintenance command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
