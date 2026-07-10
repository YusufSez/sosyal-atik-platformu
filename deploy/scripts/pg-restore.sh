#!/bin/sh
# VPS üzerinde PostgreSQL dump geri yükler.
# Kullanım: ./scripts/pg-restore.sh /opt/atikport/atikport.dump
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

POSTGRES_USER="${POSTGRES_USER:?POSTGRES_USER .env içinde tanımlı olmalı}"
POSTGRES_DB="${POSTGRES_DB:?POSTGRES_DB .env içinde tanımlı olmalı}"
COMPOSE_FILE="${COMPOSE_FILE:-$DEPLOY_DIR/docker-compose.prod.yml}"
VPS_INIT_FILE="${VPS_INIT_FILE:-$DEPLOY_DIR/docker-compose.vps-init.yml}"
DUMP_FILE="${1:?Dump dosya yolu gerekli}"
COMPOSE="docker compose -f $COMPOSE_FILE -f $VPS_INIT_FILE"

if [ ! -f "$DUMP_FILE" ]; then
  echo "Hata: Dosya bulunamadı: $DUMP_FILE"
  exit 1
fi

cd "$DEPLOY_DIR"
echo "==> Postgres hazır bekleniyor..."
$COMPOSE up -d postgres
$COMPOSE exec postgres sh -c "until pg_isready -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\"; do sleep 2; done"

echo "==> Şema oluşturuluyor (flask db upgrade)..."
$COMPOSE up -d web
sleep 15
$COMPOSE stop web

echo "==> Dump geri yükleniyor..."
docker cp "$DUMP_FILE" "$($COMPOSE ps -q postgres):/tmp/restore.dump"
set +e
$COMPOSE exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists /tmp/restore.dump
RESTORE_EXIT=$?
set -e
if [ "$RESTORE_EXIT" -ne 0 ]; then
  echo "Uyarı: pg_restore çıkış kodu $RESTORE_EXIT (bazı nesneler zaten mevcut olabilir)"
fi

echo "==> Geri yükleme doğrulaması..."
USER_COUNT=$($COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A -c 'SELECT COUNT(*) FROM "user";')
KAYNAK_COUNT=$($COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A -c 'SELECT COUNT(*) FROM kaynak;')
ATIK_COUNT=$($COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A -c 'SELECT COUNT(*) FROM atik;')

if [ -z "$USER_COUNT" ] || [ "$USER_COUNT" -lt 1 ]; then
  echo "Hata: Geri yükleme doğrulaması başarısız — user tablosu boş veya okunamadı."
  exit 1
fi

echo "==> Stack yeniden başlatılıyor..."
$COMPOSE up -d

echo "==> Kayıt sayıları:"
$COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c \
  "SELECT 'user', COUNT(*) FROM \"user\" UNION ALL SELECT 'kaynak', COUNT(*) FROM kaynak UNION ALL SELECT 'atik', COUNT(*) FROM atik;"
echo "Doğrulama: user=$USER_COUNT kaynak=$KAYNAK_COUNT atik=$ATIK_COUNT"
