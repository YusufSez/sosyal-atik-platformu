from .config import skip_startup_hooks
from .scheduler import run_scheduled_backup


def run_startup_tasks(app):
    """Veritabanı bootstrap, admin seed ve backfill işlemleri."""
    with app.app_context():
        from services.db_bootstrap import bootstrap_database

        bootstrap_database(app)
        if skip_startup_hooks():
            return

        from services.admin_bootstrap import bootstrap_admin_from_env
        from services.ilan_images import backfill_ilan_resimleri

        bootstrap_admin_from_env()
        backfill_ilan_resimleri()
        run_scheduled_backup(app)
