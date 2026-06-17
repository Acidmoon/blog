"""Shared helpers for public route modules."""

from flask import request


def client_ip() -> str:
    return request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
