# data/ — Tohum/Geliştirme Verisi · **ÇOĞU BAYAT**

Küçük seed/geliştirme verisi. **Çalışma-zamanı DB'si veya migrasyon burada DEĞİL** — gerçek veritabanı
app-data'dadır (`~/.pemf_gui` / `PEMF_DATA_DIR`, tipik `C:\ProgramData\PEMF_System\PEMF_GUI`).

## İçerik
| Dosya | İçerik | Durum |
|---|---|---|
| `config.json` | ESP `device.env`-tarzı tohum (`coil_id`, `wifi_ssid/pass`, `mqtt_*`, `pwm_freq` — placeholder) | seed |
| `cloud_mqtt_provision.json` | E-stop bulut aynası provizyonu (`mqtt_cloud_host/user/pass/port`); build-time üretilir, git'e girmez. İlk çalışmada `pemf_secrets.json`'a taşınır (parola DPAPI). | provizyon |
| `file_inventory.json` (~50 KB) | Eski bir dev ağacının tek-seferlik dizin dökümü (`.conda\envs\gui\...`) | **BAYAT** |
| `kpi_data.json`, `kpi_values.json` | Küçük KPI tohum blob'ları | seed |

## ⚠️ Not
- Runtime'ı etkilemez; gerçek veri app-data'da. `file_inventory.json` güvenle yok sayılır.

---
İlgili: [database/ (gerçek DB)](../database/README.md) · [proje geneli](../README.md)
