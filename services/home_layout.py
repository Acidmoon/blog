"""Homepage layout loading and durable daily-quote caching."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

import config


logger = logging.getLogger(__name__)
HERO_FIELDS = ("label", "title", "subtitle")
HITOKOTO_TIMEOUT_SECONDS = 2
HITOKOTO_MAX_RESPONSE_BYTES = 32 * 1024
MAX_DAILY_QUOTE_LENGTH = 600
QUOTE_REFRESH_LOCK_TTL_SECONDS = 60

# 精选备用库（API 挂了的时候用）
FALLBACK_QUOTES = [
    "我们听过无数的道理，却仍旧过不好这一生。 — 韩寒",
    "世界上只有一种真正的英雄主义，那就是认清生活的真相后依然热爱生活。 — 罗曼·罗兰",
    "一个人可以被毁灭，但不能被打败。 — 海明威",
    "生活在阴沟里，依然有仰望星空的权利。 — 王尔德",
    "我只是个路过的假面骑士。 — 门矢士",
    "愿你在冷铁卷刃前，得以窥见天光。 — priest",
    "人类的赞歌就是勇气的赞歌。 — 乔纳森·乔斯达",
    "所谓无底深渊，下去，也是前程万里。 — 木心",
    "正因为生来什么都没有，所以能拥有一切。 — 空条承太郎",
    "不要停止奔跑，不要回顾来路。 — 村上春树",
    "你知道人类最大的武器是什么吗？是豁出去的决心。 — 伊坂幸太郎",
    "念念不忘，必有回响。 — 王家卫",
    "满地都是六便士，他却抬头看见了月亮。 — 毛姆",
    "生命中最伟大的光辉不在于永不坠落，而是坠落后总能再度升起。 — 曼德拉",
    "我们一路奋战，不是为了改变世界，而是为了不让世界改变我们。 — 《熔炉》",
    "当你凝视深渊的时候，深渊也在凝视着你。 — 尼采",
    "每个人心中都有一团火，路过的人只看到烟。 — 梵高",
    "万物皆有裂痕，那是光照进来的地方。 — 莱昂纳德·科恩",
    "没有最终的成功，也没有致命的失败，最可贵的是继续前进的勇气。 — 丘吉尔",
    "人的一切痛苦，本质上都是对自己无能的愤怒。 — 王小波",
    "天空是蓝色的，所以恋爱是蓝色的。 — 动漫名言",
    "我渴望一种真正活着的感受。 — 切·格瓦拉",
    "重要的不是治愈，而是带着病痛活下去。 — 加缪",
    "做你自己，因为别人都有人做了。 — 奥斯卡·王尔德",
    "人生而自由，却无往不在枷锁之中。 — 卢梭",
    "我来，我见，我征服。 — 凯撒",
    "心之所向，素履以往。生如逆旅，一苇以航。 — 七堇年",
    "即使世界明天就要毁灭，我今天仍然要种下我的苹果树。 — 马丁·路德",
    "君子不器。 — 孔子",
    "一切都是瞬息，一切都将会过去。 — 普希金",
    "如果不去遍历幽谷，你永远不知道自己能做到多少。 — 高迪",
    "无论风暴将我带到什么岸边，我都将以主人的身份上岸。 — 贺拉斯",
    "人间有味是清欢。 — 苏轼",
    "船在海上，马在山中。 — 洛尔迦",
    "日光之下并无新事。 — 《圣经》",
    "身在无间，心在桃源。 — 《天官赐福》",
    "有人把磨难看做灾难，有人把它看做重生。 — 维克多·弗兰克尔",
    "如果你的梦想不让你害怕，那说明你的梦想还不够大。 — 昂山素季",
    "比鬼神更可怕的，是人心。 — 南派三叔",
    "人类的伟大之处在于，我们有能力改变自己的命运。 — 阿兰·图灵",
]


def _default_home_layout() -> dict[str, Any]:
    """Return a fresh fallback value so callers cannot mutate shared defaults."""
    return {"quotes": list(FALLBACK_QUOTES), "section_order": []}


def _normalize_quotes(raw_quotes: Any, *, strict: bool) -> list[str]:
    """Validate the quote list while preserving the supported empty-list form."""
    if not isinstance(raw_quotes, list):
        if strict:
            raise ValueError("首页布局 quotes 必须是字符串数组")
        return list(FALLBACK_QUOTES)

    quotes: list[str] = []
    for item in raw_quotes:
        if not isinstance(item, str):
            if strict:
                raise ValueError("首页布局 quotes 只能包含字符串")
            continue
        text = item.strip()
        if text:
            quotes.append(text)
    return quotes


def _normalize_section_order(raw_order: Any, *, strict: bool) -> list[str]:
    """Return a deduplicated list of section ids without discarding unknown ids."""
    if not isinstance(raw_order, list):
        if strict:
            raise ValueError("首页布局 section_order 必须是字符串数组")
        return []

    order: list[str] = []
    for item in raw_order:
        if not isinstance(item, str):
            if strict:
                raise ValueError("首页布局 section_order 只能包含字符串")
            continue
        section_id = item.strip()
        if section_id and section_id not in order:
            order.append(section_id)
    return order


def _normalize_section_visibility(raw_visibility: Any, *, strict: bool) -> dict[str, bool]:
    """Validate persisted visibility without interpreting truthy strings as booleans."""
    if not isinstance(raw_visibility, dict):
        if strict:
            raise ValueError("首页布局 section_visibility 必须是对象")
        return {}

    visibility: dict[str, bool] = {}
    for raw_section_id, enabled in raw_visibility.items():
        section_id = str(raw_section_id).strip()
        if not section_id:
            if strict:
                raise ValueError("首页布局 section_visibility 包含空模块 id")
            continue
        if not isinstance(enabled, bool):
            if strict:
                raise ValueError(f"首页模块 {section_id} 的可见性必须是布尔值")
            continue
        visibility[section_id] = enabled
    return visibility


def _normalize_hero_fields(raw_fields: Any, *, strict: bool, field_name: str) -> dict[str, str]:
    """Keep only the three supported hero text fields with safe string values."""
    if not isinstance(raw_fields, dict):
        if strict:
            raise ValueError(f"首页布局 {field_name} 必须是对象")
        return {}

    fields: dict[str, str] = {}
    for key in HERO_FIELDS:
        if key not in raw_fields:
            continue
        value = raw_fields[key]
        if not isinstance(value, str):
            if strict:
                raise ValueError(f"首页布局 {field_name}.{key} 必须是字符串")
            continue
        fields[key] = value
    return fields


def _normalize_hero(raw_hero: Any, *, strict: bool) -> dict[str, Any]:
    """Validate both the legacy flat hero and the current per-tag hero schema."""
    if not isinstance(raw_hero, dict):
        if strict:
            raise ValueError("首页布局 hero 必须是对象")
        return {}

    if "_default" not in raw_hero and "tags" not in raw_hero:
        return _normalize_hero_fields(raw_hero, strict=strict, field_name="hero")

    default_fields = _normalize_hero_fields(
        raw_hero.get("_default", {}),
        strict=strict,
        field_name="hero._default",
    )
    raw_tags = raw_hero.get("tags", {})
    if not isinstance(raw_tags, dict):
        if strict:
            raise ValueError("首页布局 hero.tags 必须是对象")
        raw_tags = {}

    tags: dict[str, dict[str, str]] = {}
    for raw_tag, raw_fields in raw_tags.items():
        tag = str(raw_tag).strip()
        if not tag:
            if strict:
                raise ValueError("首页布局 hero.tags 包含空标签")
            continue
        if not isinstance(raw_fields, dict):
            if strict:
                raise ValueError(f"首页布局 hero.tags.{tag} 必须是对象")
            continue
        tags[tag] = _normalize_hero_fields(
            raw_fields,
            strict=strict,
            field_name=f"hero.tags.{tag}",
        )
    return {"_default": default_fields, "tags": tags}


def _normalize_home_layout(raw_layout: Any, *, strict: bool) -> dict[str, Any]:
    """Normalize known layout fields and retain unknown top-level extension data."""
    if not isinstance(raw_layout, dict):
        if strict:
            raise ValueError("首页布局根节点必须是对象")
        return _default_home_layout()

    layout = dict(raw_layout)
    layout["quotes"] = _normalize_quotes(
        raw_layout.get("quotes", list(FALLBACK_QUOTES)),
        strict=strict,
    )
    layout["section_order"] = _normalize_section_order(
        raw_layout.get("section_order", []),
        strict=strict,
    )
    if "section_visibility" in raw_layout:
        layout["section_visibility"] = _normalize_section_visibility(
            raw_layout["section_visibility"],
            strict=strict,
        )
    if "hero" in raw_layout:
        layout["hero"] = _normalize_hero(raw_layout["hero"], strict=strict)
    return layout


def _read_json(path: Path, label: str) -> Any | None:
    """Read JSON without allowing a damaged optional file to break a request."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        logger.warning("无法读取%s %s：%s", label, path, exc)
        return None


def _fsync_parent_directory(directory: Path) -> None:
    """Persist a completed rename on POSIX; Windows does not support directory fsync."""
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        directory_fd = os.open(directory, flags)
    except OSError as exc:
        logger.warning("无法打开目录以同步 JSON 重命名 %s：%s", directory, exc)
        return
    try:
        os.fsync(directory_fd)
    except OSError as exc:
        logger.warning("无法同步 JSON 所在目录 %s：%s", directory, exc)
    finally:
        os.close(directory_fd)


def _atomic_write_json(path: Path, data: Any, *, indent: int | None) -> None:
    """Serialize first, then fsync and atomically replace a JSON file in-place."""
    try:
        payload = json.dumps(data, ensure_ascii=False, indent=indent)
    except (TypeError, ValueError) as exc:
        raise ValueError("JSON 数据无法安全序列化") from exc
    payload += "\n"

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as temporary_file:
            file_descriptor = -1
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
        _fsync_parent_directory(path.parent)
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        temporary_path.unlink(missing_ok=True)


def _fallback_home_layout(primary_path: Path) -> dict[str, Any]:
    """Prefer the tracked seed as a read-only fallback when the runtime copy is bad."""
    default_path_value = getattr(config, "DEFAULT_HOME_LAYOUT_PATH", None)
    if default_path_value:
        default_path = Path(default_path_value)
        try:
            is_distinct_path = default_path.resolve() != primary_path.resolve()
        except OSError:
            is_distinct_path = default_path != primary_path
        if is_distinct_path:
            default_layout = _read_json(default_path, "默认首页布局")
            if isinstance(default_layout, dict):
                return _normalize_home_layout(default_layout, strict=False)
    return _default_home_layout()


def load_home_layout():
    """Load a safe layout while preserving valid extension fields and legacy hero data."""
    path = Path(config.HOME_LAYOUT_PATH)
    raw_layout = _read_json(path, "首页布局")
    if not isinstance(raw_layout, dict):
        if raw_layout is not None:
            logger.warning("首页布局 %s 的根节点不是对象，已使用安全回退", path)
        return _fallback_home_layout(path)
    return _normalize_home_layout(raw_layout, strict=False)


def save_home_layout(data):
    """Validate and atomically persist the authoritative homepage layout."""
    layout = _normalize_home_layout(data, strict=True)
    _atomic_write_json(Path(config.HOME_LAYOUT_PATH), layout, indent=2)


def fetch_hitokoto() -> str | None:
    """Fetch one bounded, validated quote without trusting upstream response size."""
    try:
        req = urllib.request.Request(
            "https://v1.hitokoto.cn/?c=d&c=k&c=b&c=h&encode=json",
            headers={"User-Agent": "Waterhill-Blog/1.0"},
        )
        with urllib.request.urlopen(req, timeout=HITOKOTO_TIMEOUT_SECONDS) as resp:
            headers = getattr(resp, "headers", None)
            content_type = getattr(headers, "get_content_type", lambda: "")()
            if content_type and content_type not in {"application/json", "text/json"}:
                logger.warning("每日一言响应类型不受支持: %s", content_type)
                return None
            payload = resp.read(HITOKOTO_MAX_RESPONSE_BYTES + 1)
            if len(payload) > HITOKOTO_MAX_RESPONSE_BYTES:
                logger.warning("每日一言响应超过大小限制")
                return None
            data = json.loads(payload.decode("utf-8"))
            if not isinstance(data, dict):
                return None
            text = str(data.get("hitokoto") or "").strip()
            source = str(data.get("from") or "").strip()
            who = str(data.get("from_who") or "").strip()
            if text:
                if who:
                    text = f"{text} — {who}"
                if source:
                    text = f"{text} — {source}"
                if len(text) <= MAX_DAILY_QUOTE_LENGTH:
                    return text
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        logger.info("每日一言刷新失败: %s", exc)
        return None


def _quote_refresh_lock_path() -> Path:
    """Store a short-lived refresh lease beside the durable quote cache."""
    cache_path = Path(config.QUOTE_CACHE_PATH)
    return cache_path.with_name(f".{cache_path.name}.refresh.lock")


def _try_acquire_quote_refresh_lock() -> Path | None:
    """Acquire a cross-process lease, recovering only clearly stale lock files."""
    lock_path = _quote_refresh_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                return None
            if attempt == 0 and age > QUOTE_REFRESH_LOCK_TTL_SECONDS:
                try:
                    lock_path.unlink()
                except OSError:
                    return None
                continue
            return None
        except OSError as exc:
            logger.info("无法获取每日一言刷新锁: %s", exc)
            return None
        else:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
            return lock_path
    return None


def _refresh_daily_quote(today_key: str, lock_path: Path) -> None:
    """Refresh cache outside request handling and always release the lease."""
    try:
        quote = fetch_hitokoto()
        if quote:
            _save_quote_cache({"date": today_key, "text": quote, "source": "hitokoto"})
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.info("无法释放每日一言刷新锁: %s", exc)


def _schedule_quote_refresh(today_key: str) -> None:
    """Start at most one short-lived cross-process refresh for the current day."""
    lock_path = _try_acquire_quote_refresh_lock()
    if lock_path is None:
        return
    worker = threading.Thread(
        target=_refresh_daily_quote,
        args=(today_key, lock_path),
        name="daily-quote-refresh",
        daemon=True,
    )
    worker.start()


def _local_daily_quote(quotes: list[str], today: date) -> str:
    """Select a deterministic local fallback without relying on remote state."""
    source = _normalize_quotes(quotes, strict=False) or list(FALLBACK_QUOTES)
    return source[today.toordinal() % len(source)]


def get_daily_quote(quotes: list[str]) -> str:
    """Return cached/local content immediately and refresh remote content asynchronously."""
    today = date.today()
    today_key = today.isoformat()
    cached = _load_quote_cache()

    if cached.get("date") == today_key and cached.get("text"):
        return cached["text"]

    # A stale cache is better than holding a homepage request open on an external API.
    visible_quote = cached.get("text")
    if not visible_quote:
        visible_quote = _local_daily_quote(quotes, today)
        _save_quote_cache({"date": today_key, "text": visible_quote, "source": "local"})
    _schedule_quote_refresh(today_key)
    return visible_quote


def resolve_hero(layout_hero, tag: str) -> dict:
    """Resolve hero config for a given tag (empty string = default)."""
    defaults = {"label": "水浇岭", "title": "水浇岭的博客", "subtitle": "写点有意思的东西"}
    normalized_hero = _normalize_hero(layout_hero, strict=False)

    if not normalized_hero:
        hero = dict(defaults)
    elif "_default" in normalized_hero:
        # new format: {_default: {...}, tags: {tag: {...}}}
        base = {**defaults, **normalized_hero.get("_default", {})}
        if tag:
            base.update(normalized_hero.get("tags", {}).get(tag, {}))
        hero = base
    else:
        # legacy flat format: {label, title, subtitle}
        hero = {**defaults, **normalized_hero}

    # ensure all three keys exist
    for k in ("label", "title", "subtitle"):
        hero.setdefault(k, defaults[k])
    return hero


def _load_quote_cache() -> dict[str, str]:
    """Return only a complete, date-valid quote cache record."""
    path = Path(config.QUOTE_CACHE_PATH)
    raw_cache = _read_json(path, "每日一言缓存")
    if not isinstance(raw_cache, dict):
        return {}

    raw_date = raw_cache.get("date")
    raw_text = raw_cache.get("text")
    if not isinstance(raw_date, str) or not isinstance(raw_text, str) or not raw_text.strip():
        return {}
    try:
        normalized_date = date.fromisoformat(raw_date).isoformat()
    except ValueError:
        return {}

    cache = {"date": normalized_date, "text": raw_text.strip()}
    raw_source = raw_cache.get("source")
    if isinstance(raw_source, str) and raw_source.strip():
        cache["source"] = raw_source.strip()
    return cache


def _save_quote_cache(cache: dict[str, str]) -> None:
    """Persist optional cache data without turning a cache failure into a page failure."""
    try:
        _atomic_write_json(Path(config.QUOTE_CACHE_PATH), cache, indent=None)
    except OSError as exc:
        logger.warning("无法持久化每日一言缓存 %s：%s", config.QUOTE_CACHE_PATH, exc)
