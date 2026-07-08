#!/bin/sh
# DNS yayılımını kontrol eder.
DOMAIN="${1:-atikport.com}"
EXPECTED_IP="${2:?VPS IP gerekli}"

echo "DNS kontrol: $DOMAIN -> beklenen $EXPECTED_IP"
RESOLVED=$(dig +short "$DOMAIN" A | tail -1)
if [ "$RESOLVED" = "$EXPECTED_IP" ]; then
  echo "OK: $DOMAIN -> $RESOLVED"
  exit 0
fi
echo "BEKLENIYOR: $DOMAIN -> $RESOLVED (beklenen: $EXPECTED_IP)"
exit 1
