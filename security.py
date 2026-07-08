"""Flask-Talisman ile HTTP güvenlik başlıkları ve HTTPS yönlendirmesi."""

import os

from flask import request
from flask_talisman import Talisman

from utils import env_to_bool

# Yerel statik dosyalar, Cloudflare Turnstile ve OpenStreetMap karoları ile uyumlu sıkı CSP
CONTENT_SECURITY_POLICY = {
    "default-src": "'self'",
    "base-uri": "'self'",
    "form-action": "'self'",
    "object-src": "'none'",
    "frame-ancestors": "'self'",
    "script-src": [
        "'self'",
        "https://challenges.cloudflare.com",
    ],
    "style-src": [
        "'self'",
        "https://challenges.cloudflare.com",
        "'unsafe-inline'",
    ],
    "font-src": [
        "'self'",
        "https://challenges.cloudflare.com",
    ],
    "img-src": [
        "'self'",
        "data:",
        "blob:",
        "https://challenges.cloudflare.com",
        "https://a.tile.openstreetmap.org",
        "https://b.tile.openstreetmap.org",
        "https://c.tile.openstreetmap.org",
    ],
    "connect-src": [
        "'self'",
        "https://challenges.cloudflare.com",
        "https://data.ibb.gov.tr",
    ],
    "frame-src": [
        "'self'",
        "https://challenges.cloudflare.com",
    ],
    "worker-src": "'self'",
    "manifest-src": "'self'",
}

PERMISSIONS_POLICY = {
    "geolocation": ["self"],
    "microphone": [],
    "camera": [],
}

_STATIC_CACHE_PATH_PREFIXES = (
    "/static/",
    "/favicon.ico",
)

# Docker healthcheck ve dahili probe'lar — container içinde HTTPS yok
INTERNAL_HTTP_EXEMPT_PATHS = frozenset({"/health"})


def apply_force_https_exemptions(app):
    """Belirtilen path'lerde Talisman force_https yönlendirmesini kapatır."""
    for rule in app.url_map.iter_rules():
        if rule.rule not in INTERNAL_HTTP_EXEMPT_PATHS:
            continue
        view = app.view_functions.get(rule.endpoint)
        if view is None:
            continue
        options = dict(getattr(view, "talisman_view_options", {}))
        options["force_https"] = False
        view.talisman_view_options = options


def init_security(app):
    force_https = app.config.get("FORCE_HTTPS", False)
    enable_hsts = force_https or env_to_bool(os.getenv("ENABLE_HSTS"), default=False)

    Talisman(
        app,
        force_https=force_https,
        force_https_permanent=True,
        strict_transport_security=enable_hsts,
        strict_transport_security_max_age=31536000,
        strict_transport_security_include_subdomains=True,
        strict_transport_security_preload=False,
        content_security_policy=CONTENT_SECURITY_POLICY,
        content_security_policy_nonce_in=["script-src"],
        referrer_policy="strict-origin-when-cross-origin",
        frame_options="SAMEORIGIN",
        permissions_policy=PERMISSIONS_POLICY,
        session_cookie_secure=force_https,
    )

    @app.after_request
    def harden_response(response):
        response.headers.pop("Server", None)

        if request.path.startswith(_STATIC_CACHE_PATH_PREFIXES):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif response.content_type and "text/html" in response.content_type:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"

        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")

        return response
