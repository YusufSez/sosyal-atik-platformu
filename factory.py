from dotenv import load_dotenv
from flask import Flask

load_dotenv()

import models  # noqa: F401 — Alembic tüm modelleri keşfetsin

from app_bootstrap.blueprints import register_blueprints
from app_bootstrap.cli import register_cli
from app_bootstrap.config import configure_app
from app_bootstrap.extensions import init_extensions
from app_bootstrap.hooks import (
    register_https_exemptions,
    register_proxy_and_security,
    register_request_hooks,
)
from app_bootstrap.logging import register_rate_limit_and_csrf_handlers, setup_logging
from app_bootstrap.scheduler import start_background_scheduler
from app_bootstrap.startup import run_startup_tasks
from app_bootstrap.template_filters import register_template_filters


def create_app(config_overrides=None):
    app = Flask(__name__)
    behind_proxy = configure_app(app, config_overrides)
    setup_logging(app)
    init_extensions(app)
    register_rate_limit_and_csrf_handlers(app)
    register_proxy_and_security(app, behind_proxy)
    register_request_hooks(app)
    register_blueprints(app)
    register_https_exemptions(app)
    run_startup_tasks(app)
    start_background_scheduler(app)
    register_template_filters(app)
    register_cli(app)
    return app
