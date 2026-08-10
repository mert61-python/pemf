# config/ — Uygulama Yapılandırması

Backend'in okuduğu statik yapılandırma dosyaları. (Çalışma-zamanı özellik bayrakları **burada değil** —
kök `.env.example`'daki `PEMF_*` değişkenlerindedir.)

## Dosyalar
| Yol | İçerik |
|---|---|
| `config.json` | Ana app config: MQTT `mode:local` (Mosquitto 127.0.0.1:1883, HiveMQ bulut kaldırıldı), zamanlayıcılar, performans (sensör penceresi, sqlite batch, bulut-sync temposu) |
| `config.json.template` | Yukarıdakinin temizlenmiş şablonu |
| `pemf_config.json` | Daha eski/sunucu ağ config'i: `http_port 5080`, `websocket_port 5555`, UDP keşif 5766, `max_esp_devices 8`, heartbeat, SSL kapalı |
| `credentials/` | **Sırlar** — `credentials.json`, `mosquitto_acl.conf`, `mosquitto_passwords.txt`, `secrets_coil_6.h` (ESP bobin-6 sır başlığı) |
| `mosquitto/mosquitto.conf` | Yerel broker: `listener 1883 0.0.0.0`, `allow_anonymous true` (bilinçli — ESP anon bağlanır, hotspot-subnet firewall + WPA2 ile savunulur), persistence kapalı |

## Notlar
- **Bobin GPIO haritası yalnız firmware'dedir** (`../firmware/main.c`), config'te değil.
- `credentials/` dosyaları [`../services/credential_manager.py`](../services/README.md) tarafından üretilir/tüketilir.
- ⚠️ `credentials/` sır içerir → repoya girmemeli / ACL-kilitli olmalı (bkz. [`../utils/file_acl.py`](../utils/README.md)).

---
İlgili: [services/ (credential_manager)](../services/README.md) · [utils/secrets_manager](../utils/README.md) · [deploy/ (env profilleri)](../deploy/README.md)
