from werkzeug.middleware.proxy_fix import ProxyFix

from security import apply_force_https_exemptions, init_security

from .config import skip_startup_hooks


def register_proxy_and_security(app, behind_proxy: bool):
    if behind_proxy:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    init_security(app)


def register_request_hooks(app):
    @app.before_request
    def _enforce_active_account():
        if skip_startup_hooks():
            return
        from services.user_moderation import enforce_active_account

        return enforce_active_account()


def register_https_exemptions(app):
    apply_force_https_exemptions(app)
