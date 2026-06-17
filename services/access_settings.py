"""Site access settings."""

from __future__ import annotations

from typing import Mapping

from services.site_settings import get_setting, get_settings, set_settings


PUBLIC_SITE_LOGIN_REQUIRED_KEY = 'public_site_login_required'
LEGACY_VISITOR_LOGIN_ENABLED_KEY = 'visitor_login_enabled'
PUBLIC_SITE_LOGIN_REQUIRED_DEFAULT = '0'

ACCESS_SETTING_DEFAULTS = {
    'visitor_login_days': '7',
}


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _as_positive_int(value: str, default: int) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(1, number)


def _public_site_login_required_value() -> str:
    value = get_setting(PUBLIC_SITE_LOGIN_REQUIRED_KEY, None)
    if value is not None:
        return value
    legacy_value = get_setting(LEGACY_VISITOR_LOGIN_ENABLED_KEY, None)
    if legacy_value is not None:
        return legacy_value
    return PUBLIC_SITE_LOGIN_REQUIRED_DEFAULT


def get_access_settings() -> dict:
    raw = get_settings(ACCESS_SETTING_DEFAULTS)
    public_site_login_required = _as_bool(_public_site_login_required_value())
    return {
        'public_site_login_required': public_site_login_required,
        'visitor_login_enabled': public_site_login_required,
        'visitor_login_days': _as_positive_int(raw['visitor_login_days'], 7),
    }


def is_public_site_login_required() -> bool:
    return bool(get_access_settings()['public_site_login_required'])


def is_visitor_login_enabled() -> bool:
    return is_public_site_login_required()


def save_access_settings(form: Mapping[str, str]) -> None:
    public_site_login_required = (
        str(form.get(PUBLIC_SITE_LOGIN_REQUIRED_KEY) or form.get(LEGACY_VISITOR_LOGIN_ENABLED_KEY) or '').lower()
        in {'1', 'true', 'yes', 'on'}
    )
    fields = {
        'visitor_login_days': '访客登录有效天数',
    }
    parsed: dict[str, int] = {}
    for key, label in fields.items():
        try:
            value = int(str(form.get(key) or ACCESS_SETTING_DEFAULTS[key]).strip())
        except ValueError as exc:
            raise ValueError(f'{label}必须是正整数') from exc
        if value < 1:
            raise ValueError(f'{label}必须大于 0')
        parsed[key] = value

    set_settings({
        PUBLIC_SITE_LOGIN_REQUIRED_KEY: '1' if public_site_login_required else '0',
        LEGACY_VISITOR_LOGIN_ENABLED_KEY: '1' if public_site_login_required else '0',
        'visitor_login_days': str(parsed['visitor_login_days']),
    })
