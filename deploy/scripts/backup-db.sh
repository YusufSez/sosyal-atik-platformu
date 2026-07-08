#!/bin/sh
# PostgreSQL yedekleme (cron veya manuel).
set -e
BACKUP_DIR="${BACKUP_DIR:-/opt/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
STAMP=$(date +%Y%m%d_%H%M%S)
DEST="$BACKUP_DIR/atikport_$STAMP.sql.gz"

cd /opt/atikport/deploy
mkdir -p "$BACKUP_DIR"

docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U postgres atikport | gzip > "$DEST"

find "$BACKUP_DIR" -name 'atikport_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete
echo "Yedek: $DEST"
