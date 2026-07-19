#!/bin/sh
# PEMF Vet — kaldırma sonrası: eklenen mosquitto drop-in config'i temizle + broker'ı yeniden başlat
# (varsayılan davranışa dönsün). Idempotent.
set -e

rm -f /etc/mosquitto/conf.d/pemf.conf
if command -v systemctl >/dev/null 2>&1; then
  systemctl restart mosquitto >/dev/null 2>&1 || true
fi

exit 0
