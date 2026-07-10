#!/bin/sh
set -e

# Root olarak başlatıldıysa yazılabilir dizin izinlerini düzelt, ardından atikport'a geç
if [ "$(id -u)" = "0" ]; then
  for dir in /app/static/item_pics /app/static/profile_pics /app/data/support_attachments /app/logs; do
    mkdir -p "$dir"
    chown -R atikport:atikport "$dir" 2>/dev/null || true
    chmod -R u+rwX,g+rwX "$dir" 2>/dev/null || true
  done
  exec gosu atikport "$0" "$@"
fi

wait_for_postgres() {
  case "${USE_POSTGRES}" in
    true|True|1|yes|YES|on|ON) python scripts/wait_for_postgres.py ;;
  esac
  case "${DATABASE_URL}" in
    postgresql:*|postgres:*) python scripts/wait_for_postgres.py ;;
  esac
}

run_migrate() {
  echo "[entrypoint] Veritabanı migration başlatılıyor (flask db upgrade)..."
  if flask db upgrade 2>/tmp/migrate.log; then
    echo "[entrypoint] Migration tamamlandı."
    return 0
  fi
  echo "[entrypoint] HATA: flask db upgrade başarısız." >&2
  echo "[entrypoint] Olası nedenler:" >&2
  echo "  - Alembic sürümü ile mevcut şema uyumsuz" >&2
  echo "  - PostgreSQL bağlantısı veya yetki sorunu" >&2
  echo "  - Eksik veya çakışan migration dosyası" >&2
  echo "[entrypoint] flask db upgrade çıktısı:" >&2
  cat /tmp/migrate.log >&2
  return 1
}

wait_for_postgres
run_migrate
GUNICORN_WORKER_CLASS="${GUNICORN_WORKER_CLASS:-eventlet}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-1}"
exec gunicorn \
  --worker-class "$GUNICORN_WORKER_CLASS" \
  --bind 0.0.0.0:5000 \
  --workers "$GUNICORN_WORKERS" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  app:app
