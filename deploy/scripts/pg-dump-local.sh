#!/bin/sh
# Yerel Docker PostgreSQL dump alır.
set -e
cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.prod.yml"
DUMP_FILE="${1:-../atikport.dump}"

echo "==> PostgreSQL dump alınıyor..."
$COMPOSE exec -T postgres pg_dump -U postgres -d atikport -Fc > "$DUMP_FILE"
echo "Dump kaydedildi: $DUMP_FILE ($(wc -c < "$DUMP_FILE" | tr -d ' ') byte)"
