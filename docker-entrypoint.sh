#!/bin/sh
set -e

wait_for_postgres() {
  case "${USE_POSTGRES}" in
    true|True|1|yes|YES|on|ON) python scripts/wait_for_postgres.py ;;
  esac
  case "${DATABASE_URL}" in
    postgresql:*|postgres:*) python scripts/wait_for_postgres.py ;;
  esac
}

run_migrate() {
  if flask db upgrade 2>/tmp/migrate.log; then
    return 0
  fi
  if grep -qi "already exists" /tmp/migrate.log; then
    echo "Mevcut şema algılandı — flask db stamp head uygulanıyor..."
    flask db stamp head
    flask db upgrade
    return 0
  fi
  cat /tmp/migrate.log >&2
  return 1
}

wait_for_postgres
run_migrate
exec gunicorn --bind 0.0.0.0:5000 --workers "${GUNICORN_WORKERS:-2}" --timeout "${GUNICORN_TIMEOUT:-120}" app:app
