from services.logging_setup import init_logging, register_error_handlers


def setup_logging(app):
    """Uygulama günlüğü ve temel hata işleyicilerini kaydeder."""
    init_logging(app)
    register_error_handlers(app)


def register_rate_limit_and_csrf_handlers(app):
    from flask_limiter.errors import RateLimitExceeded
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit(error):
        from flask import jsonify, render_template, request

        message = "Çok fazla istek gönderdiniz. Lütfen bir süre bekleyip tekrar deneyin."
        arka_plan = (
            request.path.startswith("/api/")
            or request.path.startswith("/mesajlar_getir/")
            or request.path == "/bildirimleri_getir"
            or request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in (request.headers.get("Accept") or "")
        )
        if arka_plan:
            return jsonify({"error": message}), 429
        return render_template("errors/429.html"), 429

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        from flask import flash, jsonify, redirect, request

        from utils import safe_redirect_url

        message = "Güvenlik doğrulaması başarısız. Sayfayı yenileyip tekrar deneyin."
        if request.path.startswith("/api/") or request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": message}), 400
        flash(message, "danger")
        return redirect(safe_redirect_url(request.referrer))
