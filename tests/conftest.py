"""Pytest fixtures that keep every mutable blog path outside the repository."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_DATA_DIR = (REPOSITORY_ROOT / "data").resolve()
TRACKED_HOME_LAYOUT_PATH = (REPOSITORY_ROOT / "home_layout.json").resolve()


def pytest_configure() -> None:
    """Mark the process as a test run before test modules import application code."""
    os.environ["BLOG_TESTING"] = "1"


def _is_within(path: Path, parent: Path) -> bool:
    """Return whether a resolved path is contained by another resolved path."""
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def assert_test_runtime_paths_are_safe(config_module, runtime_root: Path) -> None:
    """Reject a test configuration that could write repository runtime content."""
    runtime_root = runtime_root.resolve()
    configured_paths = {
        "DATABASE": Path(config_module.DATABASE),
        "ARTICLES_DIR": Path(config_module.ARTICLES_DIR),
        "UPLOAD_DIR": Path(config_module.UPLOAD_DIR),
        "CHAT_UPLOAD_DIR": Path(config_module.CHAT_UPLOAD_DIR),
        "HOME_LAYOUT_PATH": Path(config_module.HOME_LAYOUT_PATH),
        "QUOTE_CACHE_PATH": Path(config_module.QUOTE_CACHE_PATH),
    }
    for name, path in configured_paths.items():
        resolved_path = path.resolve()
        if resolved_path == TRACKED_HOME_LAYOUT_PATH or _is_within(resolved_path, REPOSITORY_DATA_DIR):
            raise RuntimeError(f"测试路径 {name} 指向仓库运行数据，已拒绝执行")
        if not _is_within(resolved_path, runtime_root):
            raise RuntimeError(f"测试路径 {name} 未位于 pytest 临时运行目录，已拒绝执行")


@pytest.fixture(scope="session")
def test_runtime_paths(tmp_path_factory):
    """Configure all mutable application paths under a pytest-owned directory."""
    patcher = pytest.MonkeyPatch()
    patcher.setenv("BLOG_TESTING", "1")

    import config

    runtime_root = tmp_path_factory.mktemp("waterhill-blog-runtime")
    data_dir = runtime_root / "data"
    articles_dir = data_dir / "articles"
    uploads_dir = runtime_root / "uploads"
    chat_uploads_dir = data_dir / "chat_uploads"
    home_layout_path = data_dir / "home_layout.json"
    quote_cache_path = data_dir / "quote_cache.json"

    for directory in (data_dir, articles_dir, uploads_dir, chat_uploads_dir):
        directory.mkdir(parents=True, exist_ok=True)
    home_layout_path.write_text(TRACKED_HOME_LAYOUT_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    patcher.setattr(config, "DATA_DIR", data_dir)
    patcher.setattr(config, "DATABASE", str(data_dir / "blog.db"))
    patcher.setattr(config, "ARTICLES_DIR", str(articles_dir))
    patcher.setattr(config, "UPLOAD_DIR", str(uploads_dir))
    patcher.setattr(config, "CHAT_UPLOAD_DIR", str(chat_uploads_dir))
    patcher.setattr(config, "HOME_LAYOUT_PATH", home_layout_path)
    patcher.setattr(config, "QUOTE_CACHE_PATH", quote_cache_path)
    assert_test_runtime_paths_are_safe(config, runtime_root)

    yield {
        "root": runtime_root,
        "data_dir": data_dir,
        "home_layout_template": TRACKED_HOME_LAYOUT_PATH,
        "assert_paths_are_safe": lambda: assert_test_runtime_paths_are_safe(config, runtime_root),
    }

    patcher.undo()


@pytest.fixture(scope="session")
def app(test_runtime_paths):
    """Create one app backed only by the pytest-owned runtime paths."""
    from app import create_app
    from migrations import migrate_database
    from services.articles import create_article_draft, get_article_meta, publish_article

    # Production applies the same migration command before web workers start.
    migrate_database()
    test_app = create_app({"TESTING": True})
    with test_app.app_context():
        if not get_article_meta("这是我的博客的第一篇文章", published_only=False):
            article = create_article_draft("这是我的博客的第一篇文章", "博客", "测试文章内容")
            publish_article(article["slug"])
    return test_app


@pytest.fixture
def client(app):
    """A test client for the isolated Flask app."""
    return app.test_client()


@pytest.fixture
def login(client):
    """Log in and return the client with an active session."""
    client.post(
        "/login",
        data={"username": "Acidmoon", "password": "admin123", "action": "login", "next": "/admin"},
    )
    return client
