#!/bin/sh
# PEMF Vet — kurulum sonrası maintainer script (.deb + .rpm ortak).
# Sistem mosquitto'sunu LAN'daki ESP/STM cihazları için yapılandırır: mosquitto 2.x VARSAYILANI
# yalnız-loopback + allow_anonymous=false'tur → bu, anonim bağlanan bobin 6-8 (ESP) ve STM'yi
# KOPARIR ve backend'i sağlıklı-ama-donanımsız gösterir. Idempotent (her kurulum/güncellemede güvenli).
set -e

if [ -d /etc/mosquitto ]; then
  mkdir -p /etc/mosquitto/conf.d
  cat > /etc/mosquitto/conf.d/pemf.conf <<'EOF'
# ── PEMF Vet tarafından yazıldı — YEREL MQTT broker (ESP/STM anonim bağlanır) ──
# GÜVENLİK NOTU: anonim + tüm arayüzler (Windows bundled mosquitto ile aynı politika). Klinik
# ağını güvenli tutun veya broker'ı yalnız hotspot arayüzüne/subnet'ine firewall'layın.
listener 1883 0.0.0.0
allow_anonymous true
persistence false
max_queued_messages 10000
max_connections 30
max_keepalive 120
EOF
  if command -v systemctl >/dev/null 2>&1; then
    systemctl enable mosquitto >/dev/null 2>&1 || true
    systemctl restart mosquitto >/dev/null 2>&1 || true
  fi
fi

exit 0
