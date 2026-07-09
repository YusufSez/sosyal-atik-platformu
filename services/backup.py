"""SQLite veritabanı yedekleme ve saklama politikası."""

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from services.database_config import is_sqlite_uri
from utils import utc_now


def _db_path_from_uri(uri: str) -> Path:
    if uri.startswith("sqlite:///"):
        raw = uri.replace("sqlite:///", "", 1)
        if raw == ":memory:":
            raise ValueError("Bellek içi veritabanı yedeklenemez.")
        return Path(raw)
    raise ValueError(f"Desteklenmeyen veritabanı URI: {uri}")


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


def _cleanup_old_backups(backup_dir: Path, retention_days: int) -> int:
    if retention_days <= 0:
        return 0
    cutoff = utc_now() - timedelta(days=retention_days)
    removed = 0
    for path in backup_dir.glob("site_*.db"):
        try:
            if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def backup_database(
    db_uri: str,
    backup_dir: str | Path,
    retention_days: int = 7,
) -> Path | None:
    """Veritabanının tutarlı bir kopyasını oluşturur (yalnızca SQLite)."""
    if not is_sqlite_uri(db_uri):
        return None
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    lock_path = backup_dir / ".backup.lock"
    if not _acquire_lock(lock_path):
        return None

    try:
        db_path = _db_path_from_uri(db_uri)
        if not db_path.is_file():
            return None

        timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
        dest = backup_dir / f"site_{timestamp}.db"

        src_conn = sqlite3.connect(str(db_path))
        dest_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
            src_conn.close()

        marker = backup_dir / ".last_backup"
        marker.write_text(utc_now().isoformat(), encoding="utf-8")
        _cleanup_old_backups(backup_dir, retention_days)
        return dest
    finally:
        _release_lock(lock_path)


def should_run_daily_backup(backup_dir: str | Path, interval_hours: int = 24) -> bool:
    backup_dir = Path(backup_dir)
    marker = backup_dir / ".last_backup"
    if not marker.is_file():
        return True
    try:
        last = datetime.fromisoformat(marker.read_text(encoding="utf-8").strip())
    except ValueError:
        return True
    return utc_now() - last >= timedelta(hours=interval_hours)


def maybe_run_scheduled_backup(app) -> Path | None:
    if app.config.get("TESTING"):
        return None
    if not app.config.get("BACKUP_ENABLED"):
        return None

    backup_dir = app.config.get("BACKUP_DIR")
    if not should_run_daily_backup(backup_dir, app.config.get("BACKUP_INTERVAL_HOURS", 24)):
        return None

    return backup_database(
        app.config["SQLALCHEMY_DATABASE_URI"],
        backup_dir,
        retention_days=app.config.get("BACKUP_RETENTION_DAYS", 7),
    )
