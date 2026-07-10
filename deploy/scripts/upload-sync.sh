#!/bin/sh
# Yerel upload ve destek ekleri klasörlerini VPS'e kopyalar.
# Kullanım: VPS_HOST=deploy@VPS_IP ./scripts/upload-sync.sh
set -e

VPS_HOST="${VPS_HOST:?VPS_HOST gerekli (ör. deploy@1.2.3.4)}"
REMOTE_DIR="${REMOTE_DIR:-/opt/atikport}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "==> Upload klasörleri kopyalanıyor -> $VPS_HOST:$REMOTE_DIR"
scp -r "$ROOT/static/item_pics" "$ROOT/static/profile_pics" "$VPS_HOST:$REMOTE_DIR/static/"

if [ -d "$ROOT/data/support_attachments" ]; then
  ssh "$VPS_HOST" "mkdir -p $REMOTE_DIR/data/support_attachments"
  scp -r "$ROOT/data/support_attachments/." "$VPS_HOST:$REMOTE_DIR/data/support_attachments/"
fi

echo "==> Tamamlandı."
