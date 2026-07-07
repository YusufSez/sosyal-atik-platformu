#!/usr/bin/env python3
"""PostgreSQL bağlantısı hazır olana kadar bekler (Docker entrypoint)."""

from __future__ import annotations

import os
import sys
import time


def _env_bool(value, default=False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _should_wait() -> bool:
    if _env_bool(os.getenv("USE_POSTGRES"), default=False):
        return True
    url = os.getenv("DATABASE_URL", "").strip()
    return url.startswith("postgresql")


def main() -> int:
    if not _should_wait():
        return 0

    import psycopg2

    host = os.getenv("POSTGRES_HOST", "localhost").strip()
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    database = os.getenv("POSTGRES_DB", "atikport").strip()
    user = os.getenv("POSTGRES_USER", "postgres").strip()
    password = os.getenv("POSTGRES_PASSWORD", "")
    max_wait = int(os.getenv("POSTGRES_WAIT_SECONDS", "90"))
    interval = float(os.getenv("POSTGRES_WAIT_INTERVAL", "2"))

    if not password:
        print("Hata: POSTGRES_PASSWORD tanımlı değil.", file=sys.stderr)
        return 1

    deadline = time.monotonic() + max_wait
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                dbname=database,
                user=user,
                password=password,
                connect_timeout=3,
            )
            conn.close()
            print(f"PostgreSQL hazır ({host}:{port}/{database})", flush=True)
            return 0
        except psycopg2.OperationalError as exc:
            print(f"PostgreSQL bekleniyor ({attempt}): {exc}", flush=True)
            time.sleep(interval)

    print(f"Hata: PostgreSQL {max_wait}s içinde hazır olmadı.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
