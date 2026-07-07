"""HTTP güvenlik başlıkları ve HTTPS yönlendirmesi."""


def init_security(app):
    force_https = app.config.get("FORCE_HTTPS", False)

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self), microphone=(), camera=()"
        if force_https:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        csp = "; ".join([
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://www.google.com https://www.gstatic.com",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net",
            "img-src 'self' data: blob: https:",
            "connect-src 'self' https://www.google.com",
            "frame-src https://www.google.com https://www.gstatic.com",
        ])
        response.headers["Content-Security-Policy"] = csp
        return response

    if not force_https:
        return

    from flask import redirect, request

    @app.before_request
    def require_https():
        if request.endpoint == "static":
            return None
        proto = request.headers.get("X-Forwarded-Proto", request.scheme)
        if proto != "https":
            url = request.url.replace("http://", "https://", 1)
            return redirect(url, code=301)
