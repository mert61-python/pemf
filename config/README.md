# config/ — Uygulama Yapılandırması

> ## ⚠️ ESP ALT SİSTEMİ ŞU AN DEVRE DIŞI (2026-09-11)
>
> Sahip ESP kartlarını sistemden **söktü**. Bobin 6-7 zaten 2026-09-10'da STM32'ye taşınmıştı;
> geriye ESP olarak yalnız **slot 8** kalmıştı ve o da artık takılı değil.
>
> **Tek kaldıraç:** `PEMF_ESP_ENABLED` (varsayılan `0`) → `apps/backend/servers/live_state.esp_etkin()`
> * `0` — MQTT dinleyicisi hiç başlamaz, `_mqtt_publish` yayın yapmadan `False` döner,
>   arayüzde "ESP / MQTT" rozeti çizilmez (durum `devre_disi`, arıza değil).
> * `1` — aşağıda anlatılan her şey **aynen** geri gelir.
>
> ⚠️ **KOD SİLİNMEDİ, SİLİNMEYECEK** (sahip: "ileride tekrar hibrit ESP+STM ya da sadece ESP
> sistemine dönebilirim"). Bu belgedeki MQTT/Mosquitto anlatımı **geçerlidir** — yalnız bugün
> kullanılmıyor. Kapı: `tests/test_internetsiz_ve_esp_kapali.py`.


Backend'in okuduğu statik yapılandırma dosyaları. (Çalışma-zamanı özellik bayrakları **burada değil** —
kök `.env.example`'daki `PEMF_*` değişkenlerindedir.)

## Dosyalar
| Yol | İçerik |
|---|---|
| `config.json` | Ana app config: MQTT `mode:local` (Mosquitto 127.0.0.1:1883, HiveMQ bulut kaldırıldı), zamanlayıcılar, performans (sensör penceresi, sqlite batch, bulut-sync temposu) |
| `config.json.template` | Yukarıdakinin temizlenmiş şablonu |
| `pemf_config.json` | ⚠️ **KULLANIM DIŞI** (denetim 2026-08-03: hiçbir kod okumuyor; dosyanın kendi `_DEPRECATED` notu var). Eski sunucu-ağ config'i (`http_port 5080`, `websocket_port 5555`, UDP keşif 5766, `max_esp_devices 8`, SSL kapalı) — değerleri CANLI YAPILANDIRMA DEĞİL. Gerçek ayarlar: CORS/host/auth → `deploy/*.env` (`PEMF_CORS_ORIGINS`/`PEMF_API_HOST`/`PEMF_REQUIRE_AUTH`); app ayarları → `config.json` + `apps/backend/utils/production_config_manager.py`. Yeni ayar EKLEME |
| `credentials/` | **Sırlar** — `credentials.json`, `mosquitto_acl.conf`, `mosquitto_passwords.txt`, `secrets_coil_6.h` (ESP bobin-6 sır başlığı) |
| `mosquitto/mosquitto.conf` | Yerel broker: `listener 1883 0.0.0.0`, `allow_anonymous true` (bilinçli — ESP anon bağlanır, hotspot-subnet firewall + WPA2 ile savunulur), persistence kapalı |

## Notlar
- **Bobin GPIO haritası yalnız firmware'dedir** (`../firmware/stm32_pemf/Core/Src/main.c`), config'te değil.
- `credentials/` dosyaları [`../services/credential_manager.py`](../services/README.md) tarafından üretilir/tüketilir.
- ⚠️ `credentials/` sır içerir → repoya girmemeli / ACL-kilitli olmalı (bkz. [`../utils/file_acl.py`](../utils/README.md)).

---
İlgili: [apps/backend/services/ (credential_manager)](../services/README.md) · [apps/backend/utils/secrets_manager](../utils/README.md) · [deploy/ (env profilleri)](../deploy/README.md)
