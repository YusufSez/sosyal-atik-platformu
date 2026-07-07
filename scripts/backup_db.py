"""Veritabanı yedeği alır. Zamanlayıcı/cron ile günlük çalıştırılabilir.

Kullanım:
    python scripts/backup_db.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from factory import create_app
from services.backup import backup_database


def main():
    app = create_app()
    with app.app_context():
        if not app.config.get("BACKUP_ENABLED", True):
            print("BACKUP_ENABLED=False — yedekleme atlandı.")
            return

        dest = backup_database(
            app.config["SQLALCHEMY_DATABASE_URI"],
            app.config["BACKUP_DIR"],
            retention_days=app.config.get("BACKUP_RETENTION_DAYS", 7),
        )
        if dest:
            print(f"Yedek oluşturuldu: {dest}")
        else:
            print("Yedek oluşturulamadı (kilit veya veritabanı yok).")
            sys.exit(1)


if __name__ == "__main__":
    main()
