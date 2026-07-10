#!/bin/sh
# Yerel Docker PostgreSQL dump alır.
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
DUMP_FILE="${1:-../${POSTGRES_DB}.dump}"

cd "$DEPLOY_DIR"
echo "==> PostgreSQL dump alınıyor ($POSTGRES_DB)..."
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$DUMP_FILE"
echo "Dump kaydedildi: $DUMP_FILE ($(wc -c < "$DUMP_FILE" | tr -d ' ') byte)"
