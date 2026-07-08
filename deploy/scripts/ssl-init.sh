#!/bin/sh
# Let's Encrypt ilk sertifika + HTTPS nginx geçişi (VPS).
set -e
cd "$(dirname "$0")/.."
COMPOSE_BASE="docker compose -f docker-compose.prod.yml"
COMPOSE_INIT="$COMPOSE_BASE -f docker-compose.vps-init.yml"
COMPOSE_VPS="$COMPOSE_BASE -f docker-compose.vps.yml"

echo "==> HTTP stack çalışıyor olmalı (port 80)..."
$COMPOSE_INIT up -d

echo "==> Certbot ile sertifika alınıyor..."
$COMPOSE_BASE --profile ssl-init run --rm certbot-init

echo "==> HTTPS nginx'e geçiliyor..."
$COMPOSE_INIT stop nginx 2>/dev/null || true
$COMPOSE_VPS --profile ssl up -d

echo "==> SSL kurulumu tamamlandı."
echo "Doğrulama: curl -I https://atikport.com/health"
