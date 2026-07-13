"""Rol bazlı giriş sonrası portal yönlendirmesi."""

from __future__ import annotations

from constants import (
    ROLE_ADMIN,
    ROLE_COMPANY,
    ROLE_INSTITUTION,
    ROLE_MINISTRY,
    ROLE_MUNICIPALITY,
    ROLE_SUPERADMIN,
    ROLE_USER,
)

# Flask endpoint adları (URL path'ler değişmez)
_ROLE_HOME_ENDPOINT = {
    ROLE_USER: "main.anasayfa",
    ROLE_COMPANY: "marketplace.panel",
    ROLE_INSTITUTION: "kurum.analiz_paneli",
    ROLE_MUNICIPALITY: "belediye.dashboard",
    ROLE_MINISTRY: "admin_ministry.dashboard",
    ROLE_ADMIN: "admin.admin_panel",
    ROLE_SUPERADMIN: "admin.admin_panel",
}


def post_login_endpoint(user) -> str:
    """Kullanıcı rolüne göre giriş sonrası Flask endpoint adı."""
    if not user:
        return _ROLE_HOME_ENDPOINT[ROLE_USER]

    role = (getattr(user, "role", None) or ROLE_USER).strip().lower()

    # Admin bayrağı (eski hesaplar) — role alanı user olsa bile admin paneline
    if role in (ROLE_ADMIN, ROLE_SUPERADMIN) or getattr(user, "is_admin", False):
        return _ROLE_HOME_ENDPOINT[ROLE_ADMIN]

    return _ROLE_HOME_ENDPOINT.get(role, _ROLE_HOME_ENDPOINT[ROLE_USER])


def post_login_url(user) -> str:
    """Giriş sonrası göreli URL — request context dışında da güvenli."""
    from flask import current_app, has_request_context, url_for

    endpoint = post_login_endpoint(user)

    if has_request_context():
        return url_for(endpoint)

    server_name = current_app.config.get("SERVER_NAME")
    if server_name:
        scheme = current_app.config.get("PREFERRED_URL_SCHEME") or "http"
        with current_app.test_request_context(base_url=f"{scheme}://{server_name}/"):
            return url_for(endpoint)

    with current_app.test_request_context(base_url="http://localhost"):
        return url_for(endpoint)
