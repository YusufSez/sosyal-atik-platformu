"""İstemci IP çözümleme — ProxyFix sonrası request.remote_addr güvenilir kaynaktır."""

from __future__ import annotations

from flask import has_request_context, request


def client_ip(max_len: int = 45) -> str | None:
    """
    Spoof edilemeyen istemci IP.

    BEHIND_PROXY + ProxyFix(x_for=1) ile nginx'in eklediği sağ hop
    `request.remote_addr` olur. X-Forwarded-For'un sol (istemci) değerine
    asla güvenilmez.
    """
    if not has_request_context() or not request:
        return None
    ip = (request.remote_addr or "").strip()
    return ip[:max_len] or None
