"""Command line interface for deployment-time database migrations."""

from __future__ import annotations

import argparse

from .runner import current_version, migrate_database


def main() -> int:
    """Run a migration command and print a concise, automation-friendly result."""
    parser = argparse.ArgumentParser(description="管理 Waterhill Blog SQLite 数据库迁移")
    parser.add_argument("command", choices=("upgrade", "status"), nargs="?", default="upgrade")
    args = parser.parse_args()
    if args.command == "status":
        print(f"current_version={current_version()}")
        return 0
    applied = migrate_database()
    if applied:
        print("applied=" + ",".join(f"{migration.version}:{migration.name}" for migration in applied))
    else:
        print(f"current_version={current_version()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
