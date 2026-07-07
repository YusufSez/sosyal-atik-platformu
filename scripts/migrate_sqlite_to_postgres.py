#!/usr/bin/env python3
"""
SQLite site.db verisini PostgreSQL'e aktarır.

Yerel kullanım (.env içinde POSTGRES_* veya DATABASE_URL):
  python scripts/migrate_sqlite_to_postgres.py
  python scripts/migrate_sqlite_to_postgres.py --sqlite-path site.db --reset

Docker (PostgreSQL compose servisi çalışırken):
  cd deploy
  docker compose -f docker-compose.prod.yml --profile migrate run --rm migrate-sqlite
  docker compose -f docker-compose.prod.yml --profile migrate run --rm migrate-sqlite \\
    python scripts/migrate_sqlite_to_postgres.py --sqlite-path /import/site.db --reset
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from factory import create_app
from models import (
    AdminAuditLog,
    Atik,
    AtikMerkezi,
    Bildirim,
    CevreselEtki,
    Comment,
    EmailToken,
    Favori,
    Goruntulenme,
    IlanResim,
    Kaynak,
    KullaniciRozet,
    Mesaj,
    Sikayet,
    User,
)
from services.database_config import is_postgres_uri, is_sqlite_uri, resolve_database_uri

# Yabancı anahtar sırasına göre
COPY_MODELS = (
    User,
    AtikMerkezi,
    Kaynak,
    Atik,
    IlanResim,
    Mesaj,
    Favori,
    Goruntulenme,
    Bildirim,
    Sikayet,
    CevreselEtki,
    KullaniciRozet,
    EmailToken,
    AdminAuditLog,
)

RESERVED_TABLES = frozenset({"user"})


def _quote_table(name: str) -> str:
    if name in RESERVED_TABLES:
        return f'"{name}"'
    return name


def _reset_sequences(engine) -> None:
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in insp.get_table_names():
            if "id" not in {c["name"] for c in insp.get_columns(table)}:
                continue
            quoted = _quote_table(table)
            seq = conn.execute(
                text(f"SELECT pg_get_serial_sequence('{quoted}', 'id')")
            ).scalar()
            if not seq:
                continue
            conn.execute(
                text(
                    f"SELECT setval(:seq, COALESCE((SELECT MAX(id) FROM {quoted}), 1), true)"
                ),
                {"seq": seq},
            )


def _copy_model(model, src_session, dest_session) -> int:
    rows = src_session.query(model).order_by(model.id).all()
    for row in rows:
        src_session.expunge(row)
        dest_session.merge(row)
    dest_session.commit()
    return len(rows)


def _copy_comments(src_session, dest_session) -> int:
    total = 0
    for batch in (
        src_session.query(Comment).filter(Comment.parent_id.is_(None)).order_by(Comment.id),
        src_session.query(Comment).filter(Comment.parent_id.isnot(None)).order_by(Comment.id),
    ):
        for row in batch.all():
            src_session.expunge(row)
            dest_session.merge(row)
            total += 1
    dest_session.commit()
    return total


def _postgres_has_data(engine) -> bool:
    insp = inspect(engine)
    with engine.connect() as conn:
        for table in insp.get_table_names():
            quoted = _quote_table(table)
            count = conn.execute(text(f"SELECT COUNT(*) FROM {quoted}")).scalar()
            if count and count > 0:
                return True
    return False


def _clear_postgres(engine) -> None:
    insp = inspect(engine)
    tables = insp.get_table_names()
    if not tables:
        return
    quoted = ", ".join(_quote_table(t) for t in tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))


def migrate(sqlite_path: Path, reset: bool) -> None:
    if not sqlite_path.is_file():
        print(f"Hata: SQLite dosyası bulunamadı: {sqlite_path}")
        sys.exit(1)

    postgres_uri = resolve_database_uri(str(ROOT))
    if not is_postgres_uri(postgres_uri):
        print(
            "Hata: PostgreSQL bağlantısı yok. .env dosyanıza USE_POSTGRES=True ve "
            "POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD ekleyin."
        )
        sys.exit(1)

    sqlite_uri = f"sqlite:///{sqlite_path.resolve()}"
    if not is_sqlite_uri(sqlite_uri):
        print("Hata: Geçersiz SQLite yolu.")
        sys.exit(1)

    print(f"Kaynak : {sqlite_path}")
    print(f"Hedef  : {postgres_uri.split('@')[-1]}")

    src_engine = create_engine(sqlite_uri)
    dest_engine = create_engine(postgres_uri)

    src_session = sessionmaker(bind=src_engine)()
    dest_session = sessionmaker(bind=dest_engine)()

    app = create_app()
    with app.app_context():
        from flask_migrate import upgrade

        upgrade()

    if _postgres_has_data(dest_engine):
        if not reset:
            print(
                "Hata: PostgreSQL veritabanında veri var. "
                "Üzerine yazmak için --reset kullanın."
            )
            sys.exit(1)
        print("Mevcut PostgreSQL tabloları temizleniyor (--reset)...")
        _clear_postgres(dest_engine)
        with app.app_context():
            from flask_migrate import upgrade

            upgrade()

    totals: dict[str, int] = {}
    for model in COPY_MODELS:
        name = model.__tablename__
        count = _copy_model(model, src_session, dest_session)
        totals[name] = count
        print(f"  {name}: {count} kayıt")

    comment_count = _copy_comments(src_session, dest_session)
    totals["comment"] = comment_count
    print(f"  comment: {comment_count} kayıt")

    _reset_sequences(dest_engine)

    src_session.close()
    dest_session.close()

    print("\nAktarım tamamlandı.")
    for name, count in totals.items():
        print(f"  - {name}: {count}")
    print("\nUygulamayı PostgreSQL ile başlatmak için .env içinde USE_POSTGRES=True olduğundan emin olun.")


def main():
    parser = argparse.ArgumentParser(description="SQLite → PostgreSQL veri aktarımı")
    parser.add_argument(
        "--sqlite-path",
        default=os.getenv("SQLITE_IMPORT_PATH", str(ROOT / "site.db")),
        help="Kaynak SQLite dosyası (varsayılan: site.db veya SQLITE_IMPORT_PATH)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Hedefte mevcut veriyi silip yeniden aktar",
    )
    args = parser.parse_args()
    migrate(Path(args.sqlite_path), reset=args.reset)


if __name__ == "__main__":
    main()
