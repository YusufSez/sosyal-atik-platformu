#!/bin/sh
# PostgreSQL + statik dosya yedekleme (cron veya manuel).
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
ITEM_PICS_DEST="$BACKUP_DIR/item_pics_$STAMP.tar.gz"
PROFILE_PICS_DEST="$BACKUP_DIR/profile_pics_$STAMP.tar.gz"
MANIFEST="$BACKUP_DIR/manifest_$STAMP.json"

SUPPORT_DIR="${SUPPORT_ATTACHMENTS_DIR:-$ROOT_DIR/data/support_attachments}"
ITEM_PICS_DIR="${ITEM_PICS_DIR:-$ROOT_DIR/static/item_pics}"
PROFILE_PICS_DIR="${PROFILE_PICS_DIR:-$ROOT_DIR/static/profile_pics}"

cd "$DEPLOY_DIR"
mkdir -p "$BACKUP_DIR"

docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$DB_DEST"

if [ -d "$SUPPORT_DIR" ]; then
  tar -czf "$ATTACH_DEST" -C "$(dirname "$SUPPORT_DIR")" "$(basename "$SUPPORT_DIR")"
fi

if [ -d "$ITEM_PICS_DIR" ]; then
  tar -czf "$ITEM_PICS_DEST" -C "$(dirname "$ITEM_PICS_DIR")" "$(basename "$ITEM_PICS_DIR")"
fi

if [ -d "$PROFILE_PICS_DIR" ]; then
  tar -czf "$PROFILE_PICS_DEST" -C "$(dirname "$PROFILE_PICS_DIR")" "$(basename "$PROFILE_PICS_DIR")"
fi

DB_BYTES=0
ATTACH_BYTES=0
ITEM_BYTES=0
PROFILE_BYTES=0
[ -f "$DB_DEST" ] && DB_BYTES=$(wc -c < "$DB_DEST")
[ -f "$ATTACH_DEST" ] && ATTACH_BYTES=$(wc -c < "$ATTACH_DEST")
[ -f "$ITEM_PICS_DEST" ] && ITEM_BYTES=$(wc -c < "$ITEM_PICS_DEST")
[ -f "$PROFILE_PICS_DEST" ] && PROFILE_BYTES=$(wc -c < "$PROFILE_PICS_DEST")

cat > "$MANIFEST" <<EOF
{
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "stamp": "$STAMP",
  "database": "$(basename "$DB_DEST")",
  "database_bytes": $DB_BYTES,
  "support_attachments": "$(basename "$ATTACH_DEST")",
  "support_attachments_bytes": $ATTACH_BYTES,
  "item_pics": "$(basename "$ITEM_PICS_DEST")",
  "item_pics_bytes": $ITEM_BYTES,
  "profile_pics": "$(basename "$PROFILE_PICS_DEST")",
  "profile_pics_bytes": $PROFILE_BYTES
}
EOF

find "$BACKUP_DIR" -name "${POSTGRES_DB}_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name 'support_attachments_*.tar.gz' -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name 'item_pics_*.tar.gz' -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name 'profile_pics_*.tar.gz' -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name 'manifest_*.json' -mtime +"$RETENTION_DAYS" -delete

echo "Manifest: $MANIFEST"
echo "Veritabanı yedeği: $DB_DEST"
