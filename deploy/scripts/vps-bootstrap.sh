#!/bin/sh
# VPS ilk kurulum — Ubuntu 22.04/24.04 üzerinde çalıştırın (root veya sudo).
set -e

echo "==> Sistem güncelleniyor..."
apt-get update && apt-get upgrade -y

echo "==> Paketler kuruluyor..."
apt-get install -y git curl ufw fail2ban

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Docker kuruluyor..."
  curl -fsSL https://get.docker.com | sh
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "==> Docker Compose plugin kuruluyor..."
  apt-get install -y docker-compose-plugin
fi

echo "==> Firewall (UFW)..."
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> Saat dilimi (Europe/Istanbul)..."
timedatectl set-timezone Europe/Istanbul 2>/dev/null || true

mkdir -p /opt/backups

echo "==> VPS bootstrap tamamlandı."
echo "Sonraki adım: depoyu /opt/atikport altına klonlayın ve deploy/DEPLOY.md dosyasını izleyin."
