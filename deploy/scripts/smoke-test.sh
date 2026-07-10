#!/bin/sh
# Production smoke test (VPS veya yerel).
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

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-atikport}"
BASE_URL="${1:-${SITE_URL:-https://atikport.com}}"
COMPOSE_FILE="${COMPOSE_FILE:-$DEPLOY_DIR/docker-compose.prod.yml}"

cd "$DEPLOY_DIR"
COMPOSE="docker compose -f $COMPOSE_FILE"

echo "==> Health: $BASE_URL/health"
curl -fsS "$BASE_URL/health" | head -c 200
echo

echo "==> Ana sayfa HTTP durumu"
curl -fsS -o /dev/null -w "HTTP %{http_code}\n" "$BASE_URL/"

echo "==> Giriş sayfası"
curl -fsS -o /dev/null -w "HTTP %{http_code}\n" "$BASE_URL/giris"

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q postgres; then
  echo "==> PostgreSQL kayıt sayıları"
  $COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c \
    "SELECT 'user', COUNT(*) FROM \"user\" UNION ALL SELECT 'kaynak', COUNT(*) FROM kaynak UNION ALL SELECT 'atik', COUNT(*) FROM atik;" 2>/dev/null || true
fi

echo "==> Smoke test tamamlandı."
