"""DeepSeek API balance fetcher with file-based caching.

Stores API key in /app/data/deepseek_balance_config.json (persisted via volume).
Caches balance for 5 minutes to avoid hitting the API on every page load.
"""

import json
import os
import time
import urllib.error
import urllib.request

import config

CONFIG_PATH = os.path.join(config.DATA_DIR, "deepseek_balance_config.json")
CACHE_PATH = os.path.join(config.DATA_DIR, "deepseek_balance_cache.json")
CACHE_TTL = 300  # 5 minutes

DEEPSEEK_BALANCE_URL = "https://api.deepseek.com/user/balance"


def _load_config() -> dict:
    """Load API key config. Returns {'api_key': '...'} or {}."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_api_key() -> str:
    """Return the configured DeepSeek API key, or empty string."""
    return _load_config().get("api_key", "").strip()


def save_api_key(api_key: str) -> None:
    """Save the DeepSeek API key to config file."""
    cfg = _load_config()
    cfg["api_key"] = (api_key or "").strip()
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _read_cache() -> dict | None:
    """Read cached balance if still fresh. Returns None if stale/missing."""
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if time.time() - cache.get("ts", 0) > CACHE_TTL:
        return None
    return cache


def _write_cache(data: dict) -> None:
    cache = {"ts": time.time(), "data": data}
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def fetch_balance(api_key: str | None = None) -> dict:
    """Fetch DeepSeek balance. Returns a dict for template rendering.

    Result keys:
        configured: bool    — whether an API key is set
        error: str | None   — error message, or None on success
        total_balance: str  — e.g. "14.32 CNY"
        granted_balance: str
        topped_up_balance: str
        currency: str
    """
    key = (api_key or get_api_key()).strip()

    if not key:
        return {
            "configured": False,
            "error": None,
            "total_balance": "—",
            "granted_balance": "—",
            "topped_up_balance": "—",
            "currency": "CNY",
        }

    # Try cache first
    cached = _read_cache()
    if cached:
        return cached["data"]

    # Fetch from API
    try:
        req = urllib.request.Request(
            DEEPSEEK_BALANCE_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "User-Agent": "Waterhill-Blog/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")[:300]
        result = {
            "configured": True,
            "error": f"HTTP {exc.code}: {body}",
            "total_balance": "—",
            "granted_balance": "—",
            "topped_up_balance": "—",
            "currency": "CNY",
        }
        _write_cache(result)
        return result
    except urllib.error.URLError as exc:
        result = {
            "configured": True,
            "error": f"连接失败: {exc.reason}",
            "total_balance": "—",
            "granted_balance": "—",
            "topped_up_balance": "—",
            "currency": "CNY",
        }
        _write_cache(result)
        return result

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "configured": True,
            "error": "API 返回格式异常",
            "total_balance": "—",
            "granted_balance": "—",
            "topped_up_balance": "—",
            "currency": "CNY",
        }
        _write_cache(result)
        return result

    if not data.get("is_available", False):
        result = {
            "configured": True,
            "error": "账户不可用或余额查询受限",
            "total_balance": "—",
            "granted_balance": "—",
            "topped_up_balance": "—",
            "currency": "CNY",
        }
        _write_cache(result)
        return result

    balances = data.get("balance_infos", [])
    if not balances:
        result = {
            "configured": True,
            "error": "未返回余额信息",
            "total_balance": "—",
            "granted_balance": "—",
            "topped_up_balance": "—",
            "currency": "CNY",
        }
        _write_cache(result)
        return result

    info = balances[0]
    currency = info.get("currency", "CNY")
    total = info.get("total_balance", "0")
    granted = info.get("granted_balance", "0")
    topped_up = info.get("topped_up_balance", "0")

    result = {
        "configured": True,
        "error": None,
        "total_balance": _fmt_balance(total, currency),
        "granted_balance": _fmt_balance(granted, currency),
        "topped_up_balance": _fmt_balance(topped_up, currency),
        "currency": currency,
    }
    _write_cache(result)
    return result


def _fmt_balance(amount: str, currency: str) -> str:
    """Format a balance string like '14.32 CNY'."""
    try:
        val = float(amount)
        return f"{val:,.2f} {currency}"
    except (ValueError, TypeError):
        return f"{amount} {currency}"
