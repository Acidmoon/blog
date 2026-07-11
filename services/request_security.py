"""Request-bound security helpers shared by routes and authentication services.

The helpers deliberately keep proxy and CSRF policy in one place so rate limits,
visitor activity, and state-changing endpoints cannot disagree about a client.
"""

from __future__ import annotations

import ipaddress
import secrets
from collections.abc import Iterable

from flask import current_app, g, jsonify, request, session

import config


CSRF_SESSION_KEY = "_csrf_token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
CSRF_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def csrf_protection_enabled() -> bool:
    """Return the configured CSRF policy, defaulting to strict public runtime.

    Existing isolated tests intentionally do not need to attach a browser token.
    A test can still exercise production behavior by explicitly setting
    ``CSRF_PROTECTION_ENABLED`` to ``True``.
    """
    configured = current_app.config.get("CSRF_PROTECTION_ENABLED")
    if configured is not None:
        return bool(configured)
    return not (current_app.testing or config.is_testing_environment())


def csrf_token() -> str:
    """Return the synchronizer token stored in the signed Flask session."""
    token = session.get(CSRF_SESSION_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def rotate_csrf_token() -> str:
    """Replace the token after an authentication boundary changes."""
    token = secrets.token_urlsafe(32)
    session[CSRF_SESSION_KEY] = token
    return token


def clear_csrf_token() -> None:
    """Remove a token when its authenticated session is explicitly ended."""
    session.pop(CSRF_SESSION_KEY, None)


def csrf_request_is_valid() -> bool:
    """Validate a header or form token for an unsafe same-origin request."""
    expected = session.get(CSRF_SESSION_KEY)
    if not isinstance(expected, str) or not expected:
        return False
    provided = request.headers.get(CSRF_HEADER)
    if provided is None:
        # Reading ``request.form`` forces multipart parsing before upload routes
        # can install their endpoint-specific size limit. Browser upload clients
        # already send the header token, so fail closed without parsing instead.
        if request.mimetype == 'multipart/form-data':
            return False
        provided = request.form.get(CSRF_FORM_FIELD)
    if not isinstance(provided, str) or not provided:
        return False
    return secrets.compare_digest(expected, provided)


def csrf_failure_response():
    """Use one JSON error shape for browser fetches and form submissions."""
    return jsonify({"error": "CSRF 校验失败，请刷新页面后重试"}), 400


def parse_trusted_proxy_networks(raw_networks: object) -> tuple[ipaddress._BaseNetwork, ...]:
    """Parse configured proxy CIDRs and ignore malformed values fail-closed."""
    if isinstance(raw_networks, str):
        values: Iterable[object] = raw_networks.split(",")
    elif isinstance(raw_networks, Iterable):
        values = raw_networks
    elif raw_networks is None:
        values = ()
    else:
        values = (raw_networks,)

    networks: list[ipaddress._BaseNetwork] = []
    for raw_value in values:
        value = str(raw_value or "").strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            # Invalid entries must never broaden trust to an arbitrary sender.
            continue
    return tuple(networks)


def _parse_address(raw_value: object) -> ipaddress._BaseAddress | None:
    """Return a normalized IP address, accepting only literal header values."""
    value = str(raw_value or "").strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _is_trusted(address: ipaddress._BaseAddress, networks: tuple[ipaddress._BaseNetwork, ...]) -> bool:
    return any(address.version == network.version and address in network for network in networks)


def _forwarded_addresses(raw_header: str | None) -> list[ipaddress._BaseAddress]:
    """Extract valid X-Forwarded-For literal addresses in wire order."""
    addresses: list[ipaddress._BaseAddress] = []
    for raw_value in str(raw_header or "").split(","):
        address = _parse_address(raw_value)
        if address is not None:
            addresses.append(address)
    return addresses


def client_ip() -> str:
    """Return the effective peer IP, honoring XFF only from trusted proxies.

    When a request arrives through a configured trusted proxy, the complete XFF
    chain is walked right-to-left and every trusted proxy is skipped. This keeps
    the first untrusted address as the client while preserving a safe fallback
    when a proxy sends malformed forwarding data.
    """
    cached = getattr(g, "_client_ip", None)
    if isinstance(cached, str):
        return cached

    remote = _parse_address(request.remote_addr)
    if remote is None:
        resolved = str(request.remote_addr or "unknown").strip() or "unknown"
        g._client_ip = resolved
        return resolved

    networks = parse_trusted_proxy_networks(current_app.config.get("TRUSTED_PROXY_CIDRS"))
    if not networks or not _is_trusted(remote, networks):
        resolved = str(remote)
        g._client_ip = resolved
        return resolved

    chain = _forwarded_addresses(request.headers.get("X-Forwarded-For")) + [remote]
    for address in reversed(chain):
        if not _is_trusted(address, networks):
            resolved = str(address)
            g._client_ip = resolved
            return resolved

    # A chain containing only trusted addresses cannot identify an end client.
    resolved = str(remote)
    g._client_ip = resolved
    return resolved
