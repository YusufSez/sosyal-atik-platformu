"""Flask-Talisman ile HTTP güvenlik başlıkları ve HTTPS yönlendirmesi."""

from flask_talisman import Talisman

# Bootstrap CDN, Leaflet, reCAPTCHA, harita ve İBB API ile uyumlu CSP
CONTENT_SECURITY_POLICY = {
    "default-src": "'self'",
    "script-src": [
        "'self'",
        "'unsafe-inline'",
        "https://cdn.jsdelivr.net",
        "https://unpkg.com",
        "https://cdnjs.cloudflare.com",
        "https://www.google.com",
        "https://www.gstatic.com",
    ],
    "style-src": [
        "'self'",
        "'unsafe-inline'",
        "https://cdn.jsdelivr.net",
        "https://fonts.googleapis.com",
        "https://unpkg.com",
    ],
    "font-src": [
        "'self'",
        "https://fonts.gstatic.com",
        "https://cdn.jsdelivr.net",
    ],
    "img-src": ["'self'", "data:", "blob:", "https:"],
    "connect-src": [
        "'self'",
        "https://www.google.com",
        "https://data.ibb.gov.tr",
    ],
    "frame-src": [
        "https://www.google.com",
        "https://www.gstatic.com",
    ],
}

PERMISSIONS_POLICY = {
    "geolocation": ["self"],
    "microphone": [],
    "camera": [],
}


def init_security(app):
    force_https = app.config.get("FORCE_HTTPS", False)

    Talisman(
        app,
        force_https=force_https,
        force_https_permanent=True,
        strict_transport_security=force_https,
        strict_transport_security_max_age=31536000,
        strict_transport_security_include_subdomains=True,
        content_security_policy=CONTENT_SECURITY_POLICY,
        referrer_policy="strict-origin-when-cross-origin",
        frame_options="SAMEORIGIN",
        permissions_policy=PERMISSIONS_POLICY,
        session_cookie_secure=force_https,
    )
