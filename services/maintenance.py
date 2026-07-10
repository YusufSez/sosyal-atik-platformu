"""Periyodik bakım görevleri (idempotent, çoklu worker güvenli)."""

import os
from pathlib import Path

from utils import utc_now


def _maintenance_lock_path(app) -> Path:
    data_dir = Path(app.root_path) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / ".maintenance.lock"


def _acquire_lock(lock_path: Path) -> bool:
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
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
