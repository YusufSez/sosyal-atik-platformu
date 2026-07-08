#!/bin/sh
# Yerel upload klasörlerini VPS'e kopyalar.
# Kullanım: VPS_HOST=deploy@VPS_IP ./scripts/upload-sync.sh
set -e
VPS_HOST="${VPS_HOST:?VPS_HOST gerekli (ör. deploy@1.2.3.4)}"
REMOTE_DIR="${REMOTE_DIR:-/opt/atikport}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "==> Upload klasörleri kopyalanıyor -> $VPS_HOST:$REMOTE_DIR"
scp -r "$ROOT/static/item_pics" "$ROOT/static/profile_pics" "$VPS_HOST:$REMOTE_DIR/static/"

echo "==> Tamamlandı."
