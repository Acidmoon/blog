"""Focused tests for safe homepage-layout and daily-quote persistence."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest

from services import home_layout


def _use_layout_path(monkeypatch, tmp_path: Path) -> Path:
    """Point the service at a pytest-owned layout file."""
    path = tmp_path / "home_layout.json"
    monkeypatch.setattr(home_layout.config, "HOME_LAYOUT_PATH", path)
    monkeypatch.setattr(home_layout.config, "DEFAULT_HOME_LAYOUT_PATH", tmp_path / "missing-default.json")
    return path


def _use_cache_path(monkeypatch, tmp_path: Path) -> Path:
    """Point the service at a pytest-owned quote cache file."""
    path = tmp_path / "quote_cache.json"
    monkeypatch.setattr(home_layout.config, "QUOTE_CACHE_PATH", path)
    return path


def test_load_home_layout_recovers_malformed_json(monkeypatch, tmp_path):
    path = _use_layout_path(monkeypatch, tmp_path)
    path.write_text('{"quotes": [', encoding="utf-8")

    loaded = home_layout.load_home_layout()

    assert loaded == {
        "quotes": home_layout.FALLBACK_QUOTES,
        "section_order": [],
    }
    assert loaded["quotes"] is not home_layout.FALLBACK_QUOTES


def test_load_home_layout_uses_read_only_seed_when_runtime_copy_is_bad(monkeypatch, tmp_path):
    runtime_path = _use_layout_path(monkeypatch, tmp_path)
    seed_path = tmp_path / "tracked-seed.json"
    runtime_path.write_text("not-json", encoding="utf-8")
    seed_payload = {
        "hero": {"label": "种子标签", "title": "种子标题", "subtitle": "种子副标题"},
        "quotes": ["种子一言"],
        "section_order": ["article_list"],
    }
    seed_text = json.dumps(seed_payload, ensure_ascii=False)
    seed_path.write_text(seed_text, encoding="utf-8")
    monkeypatch.setattr(home_layout.config, "DEFAULT_HOME_LAYOUT_PATH", seed_path)

    loaded = home_layout.load_home_layout()

    assert loaded == seed_payload
    assert runtime_path.read_text(encoding="utf-8") == "not-json"
    assert seed_path.read_text(encoding="utf-8") == seed_text


def test_load_home_layout_normalizes_known_fields_and_keeps_extensions(monkeypatch, tmp_path):
    path = _use_layout_path(monkeypatch, tmp_path)
    path.write_text(
        json.dumps(
            {
                "quotes": ["  有效一言  ", 7, ""],
                "section_order": ["article_list", "article_list", 8, ""],
                "section_visibility": {"article_list": True, "bad": "yes"},
                "hero": {
                    "_default": None,
                    "tags": {
                        "图文": {"title": "让我看看", "subtitle": 3},
                        "坏标签": "not-an-object",
                    },
                },
                "extension_data": {"version": 2},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    loaded = home_layout.load_home_layout()

    assert loaded["quotes"] == ["有效一言"]
    assert loaded["section_order"] == ["article_list"]
    assert loaded["section_visibility"] == {"article_list": True}
    assert loaded["hero"] == {
        "_default": {},
        "tags": {"图文": {"title": "让我看看"}},
    }
    assert loaded["extension_data"] == {"version": 2}


def test_save_home_layout_fsyncs_and_atomically_replaces(monkeypatch, tmp_path):
    path = _use_layout_path(monkeypatch, tmp_path)
    path.write_text('{"old": true}\n', encoding="utf-8")
    fsync_calls = []
    replace_calls = []
    real_fsync = os.fsync
    real_replace = os.replace

    def recording_fsync(file_descriptor):
        fsync_calls.append(file_descriptor)
        return real_fsync(file_descriptor)

    def recording_replace(source, destination):
        replace_calls.append((Path(source), Path(destination)))
        return real_replace(source, destination)

    monkeypatch.setattr(home_layout.os, "fsync", recording_fsync)
    monkeypatch.setattr(home_layout.os, "replace", recording_replace)

    home_layout.save_home_layout(
        {
            "quotes": ["测试一言"],
            "section_order": ["article_list", "article_list"],
            "section_visibility": {"article_list": True},
        }
    )

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "quotes": ["测试一言"],
        "section_order": ["article_list"],
        "section_visibility": {"article_list": True},
    }
    assert fsync_calls
    assert len(replace_calls) == 1
    assert replace_calls[0][0].parent == path.parent
    assert replace_calls[0][1] == path
    assert not list(tmp_path.glob(".home_layout.json.*.tmp"))


def test_save_home_layout_preserves_original_when_replace_fails(monkeypatch, tmp_path):
    path = _use_layout_path(monkeypatch, tmp_path)
    original = '{"quotes": ["旧内容"], "section_order": []}\n'
    path.write_text(original, encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(home_layout.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        home_layout.save_home_layout({"quotes": ["新内容"], "section_order": []})

    assert path.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob(".home_layout.json.*.tmp"))


def test_save_home_layout_rejects_invalid_schema_without_touching_file(monkeypatch, tmp_path):
    path = _use_layout_path(monkeypatch, tmp_path)
    original = '{"quotes": ["旧内容"], "section_order": []}\n'
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="quotes 必须是字符串数组"):
        home_layout.save_home_layout({"quotes": "不是数组", "section_order": []})

    assert path.read_text(encoding="utf-8") == original


def test_daily_quote_ignores_invalid_cache_without_starting_background_work(monkeypatch, tmp_path):
    cache_path = _use_cache_path(monkeypatch, tmp_path)
    cache_path.write_text('{"date": "not-a-date", "text": 123}', encoding="utf-8")

    quote = home_layout.get_daily_quote(["本地一言"])

    assert quote == "本地一言"
    assert json.loads(cache_path.read_text(encoding="utf-8")) == {"date": "not-a-date", "text": 123}


def test_daily_quote_maintenance_refresh_writes_valid_record(monkeypatch, tmp_path):
    cache_path = _use_cache_path(monkeypatch, tmp_path)
    monkeypatch.setattr(home_layout, "fetch_hitokoto", lambda: "新的 API 一言")

    assert home_layout.refresh_daily_quote(["本地一言"])

    assert json.loads(cache_path.read_text(encoding="utf-8")) == {
        "date": date.today().isoformat(),
        "text": "新的 API 一言",
        "source": "hitokoto",
    }
    assert not (tmp_path / ".quote_cache.json.refresh.lock").exists()


def test_daily_quote_cache_write_failure_falls_back_without_page_failure(monkeypatch, tmp_path):
    _use_cache_path(monkeypatch, tmp_path)

    quote = home_layout.get_daily_quote(["本地一言"])

    assert quote == "本地一言"


def test_daily_quote_uses_stale_cache_without_waiting_for_upstream(monkeypatch, tmp_path):
    cache_path = _use_cache_path(monkeypatch, tmp_path)
    cache_path.write_text(
        json.dumps({"date": "2020-01-01", "text": "旧缓存一言", "source": "hitokoto"}),
        encoding="utf-8",
    )
    assert home_layout.get_daily_quote(["本地一言"]) == "旧缓存一言"


def test_resolve_hero_tolerates_invalid_nested_values():
    hero = home_layout.resolve_hero(
        {
            "_default": None,
            "tags": {"图文": "invalid", "笔记": {"title": "笔记页", "subtitle": 7}},
        },
        "笔记",
    )

    assert hero == {
        "label": "水浇岭",
        "title": "笔记页",
        "subtitle": "写点有意思的东西",
    }
