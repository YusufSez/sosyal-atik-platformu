"""Periyodik bakım görevleri (idempotent, çoklu worker güvenli)."""

import os
import tempfile
from pathlib import Path

from utils import utc_now

_MAINTENANCE_LOCK_NAME = "atikport.maintenance.lock"


def _maintenance_lock_path(app) -> Path:
    """Çoklu worker kilidi — yazılabilir temp dizininde (read-only /app uyumlu)."""
    safe_name = (getattr(app, "import_name", None) or "atikport").replace("/", "_")
    lock_name = _MAINTENANCE_LOCK_NAME
    if safe_name != "atikport":
        lock_name = f"{safe_name}.maintenance.lock"
    return Path(tempfile.gettempdir()) / lock_name


def _acquire_lock(lock_path: Path) -> bool:
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return False


def _release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass


def run_scheduled_maintenance(app) -> dict:
    """
    Periyodik bakım görevlerini çalıştırır.
    Aynı anda yalnızca bir worker işi yürütür; görevler idempotent'tir.
    """
    lock_path = _maintenance_lock_path(app)
    if not _acquire_lock(lock_path):
        app.logger.info("Bakım atlandı: başka worker veya işlem kilidi tutuyor")
        return {}

    results = {}
    try:
        from services.user_moderation import expire_temporary_bans

        count = expire_temporary_bans()
        results["expire_temporary_bans"] = count
        app.logger.info(
            "Bakım tamamlandı: expire_temporary_bans süresi_dolan=%s zaman=%s",
            count,
            utc_now().isoformat(),
        )
    except Exception:
        app.logger.exception("Bakım görevi başarısız")
        raise
    finally:
        _release_lock(lock_path)

    return results
