import os
import threading
import time

from .config import skip_startup_hooks

_MAINTENANCE_INTERVAL_SEC = int(os.getenv("MAINTENANCE_INTERVAL_SEC", "300"))
_scheduler_lock = threading.Lock()
_scheduler_started = False


def run_scheduled_backup(app):
    """Zamanlanmış veritabanı yedeklemesini çalıştırır."""
    try:
        from services.backup import maybe_run_scheduled_backup

        backup_path = maybe_run_scheduled_backup(app)
        if backup_path:
            app.logger.info("Otomatik veritabanı yedeği oluşturuldu: %s", backup_path)
    except Exception as exc:
        app.logger.warning("Otomatik yedekleme başarısız: %s", exc)


def run_maintenance_tasks(app):
    """Periyodik bakım görevlerini uygulama bağlamında çalıştırır."""
    if app.config.get("TESTING"):
        return
    try:
        from services.maintenance import run_scheduled_maintenance

        run_scheduled_maintenance(app)
    except Exception as exc:
        app.logger.warning("Periyodik bakım başarısız: %s", exc)


def start_background_scheduler(app):
    """Arka plan bakım döngüsünü başlatır (TESTING ve db CLI'da devre dışı)."""
    global _scheduler_started

    if app.config.get("TESTING"):
        return
    if skip_startup_hooks():
        return

    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    interval = _MAINTENANCE_INTERVAL_SEC

    def _maintenance_loop():
        app.logger.info(
            "Arka plan bakım scheduler başlatıldı (aralık=%s saniye)",
            interval,
        )
        with app.app_context():
            run_maintenance_tasks(app)
        while True:
            time.sleep(interval)
            with app.app_context():
                run_maintenance_tasks(app)

    thread = threading.Thread(
        target=_maintenance_loop,
        name="atikport-maintenance",
        daemon=True,
    )
    thread.start()
