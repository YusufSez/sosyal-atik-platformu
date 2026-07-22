"""Upload isteği meta verisi (IP, cihaz parmak izi)."""

from __future__ import annotations

import hashlib

from flask import request


def request_ip() -> str | None:
    from services.client_ip import client_ip

    return client_ip()


def request_user_agent() -> str | None:
    if not request:
        return None
    return (request.headers.get("User-Agent") or "")[:500] or None


def device_fingerprint(user_agent: str | None = None) -> str | None:
    ua = user_agent or request_user_agent()
    if not ua:
        return None
    return hashlib.sha256(ua.encode("utf-8")).hexdigest()[:32]
