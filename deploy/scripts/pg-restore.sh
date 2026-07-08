#!/bin/sh
# VPS üzerinde PostgreSQL dump geri yükler.
# Kullanım: ./scripts/pg-restore.sh /opt/atikport/atikport.dump
set -e
cd "$(dirname "$0")/.."
DUMP_FILE="${1:?Dump dosya yolu gerekli}"
COMPOSE="docker compose -f docker-compose.prod.yml -f docker-compose.vps-init.yml"

if [ ! -f "$DUMP_FILE" ]; then
  echo "Hata: Dosya bulunamadı: $DUMP_FILE"
  exit 1
fi

echo "==> Postgres hazır bekleniyor..."
$COMPOSE up -d postgres
$COMPOSE exec postgres sh -c 'until pg_isready -U postgres -d atikport; do sleep 2; done'

echo "==> Şema oluşturuluyor (flask db upgrade)..."
$COMPOSE up -d web
sleep 15
$COMPOSE stop web

echo "==> Dump geri yükleniyor..."
docker cp "$DUMP_FILE" "$($COMPOSE ps -q postgres):/tmp/atikport.dump"
$COMPOSE exec -T postgres pg_restore -U postgres -d atikport --clean --if-exists /tmp/atikport.dump || true

echo "==> Stack yeniden başlatılıyor..."
$COMPOSE up -d

echo "==> Kayıt sayıları:"
$COMPOSE exec -T postgres psql -U postgres -d atikport -t -c \
  "SELECT 'user', COUNT(*) FROM \"user\" UNION ALL SELECT 'kaynak', COUNT(*) FROM kaynak UNION ALL SELECT 'atik', COUNT(*) FROM atik;"
