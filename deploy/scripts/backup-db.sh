#!/bin/sh
# PostgreSQL yedekleme (cron veya manuel).
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

BACKUP_DIR="${BACKUP_DIR:-/opt/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
POSTGRES_USER="${POSTGRES_USER:?POSTGRES_USER .env içinde tanımlı olmalı}"
POSTGRES_DB="${POSTGRES_DB:?POSTGRES_DB .env içinde tanımlı olmalı}"
COMPOSE_FILE="${COMPOSE_FILE:-$DEPLOY_DIR/docker-compose.prod.yml}"
STAMP=$(date +%Y%m%d_%H%M%S)
DB_DEST="$BACKUP_DIR/${POSTGRES_DB}_$STAMP.sql.gz"
ATTACH_DEST="$BACKUP_DIR/support_attachments_$STAMP.tar.gz"
SUPPORT_DIR="${SUPPORT_ATTACHMENTS_DIR:-$ROOT_DIR/data/support_attachments}"

cd "$DEPLOY_DIR"
mkdir -p "$BACKUP_DIR"

docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$DB_DEST"

if [ -d "$SUPPORT_DIR" ]; then
  tar -czf "$ATTACH_DEST" -C "$(dirname "$SUPPORT_DIR")" "$(basename "$SUPPORT_DIR")"
  echo "Destek ekleri yedeği: $ATTACH_DEST"
fi

find "$BACKUP_DIR" -name "${POSTGRES_DB}_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name 'support_attachments_*.tar.gz' -mtime +"$RETENTION_DAYS" -delete
echo "Veritabanı yedeği: $DB_DEST"
