#!/bin/sh
# Production smoke test (VPS veya yerel).
set -e
BASE_URL="${1:-https://atikport.com}"
cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.prod.yml"

echo "==> Health: $BASE_URL/health"
curl -fsS "$BASE_URL/health" | head -c 200
echo

echo "==> Ana sayfa HTTP durumu"
curl -fsS -o /dev/null -w "HTTP %{http_code}\n" "$BASE_URL/"

echo "==> Giriş sayfası"
curl -fsS -o /dev/null -w "HTTP %{http_code}\n" "$BASE_URL/giris"

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q postgres; then
  echo "==> PostgreSQL kayıt sayıları"
  $COMPOSE exec -T postgres psql -U postgres -d atikport -t -c \
    "SELECT 'user', COUNT(*) FROM \"user\" UNION ALL SELECT 'kaynak', COUNT(*) FROM kaynak UNION ALL SELECT 'atik', COUNT(*) FROM atik;" 2>/dev/null || true
fi

echo "==> Smoke test tamamlandı."
