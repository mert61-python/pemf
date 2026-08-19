# utils/ — Kesişen Yardımcılar (cross-cutting)

Backend'in her yerinden kullanılan bağımsız yardımcılar: STM32 seri/protokol, sırlar, yollar, config, PDF, telemetri.

## Dosyalar
| Dosya | Görev |
|---|---|
| `stm32_transport.py` | **`Stm32SerialTransport`** — STM32 port seçimi (`PEMF_STM_PORT` env / sabit `COM10` / ST-Link VCP oto-algılama USB VID/PID ile), 115200 baud açılış + handshake, güvenli sıfır-duty probe paketi |
| `stm32_protocol_limits.py` | **Güvenlik-limit sabitleri + normalizer'lar** — 5 STM / 8 ESP bobin, freq 1 Hz–25 kHz (`DDS_ISR_HZ/2`), faz 0–360°, süre 0–9999 dk (0=sınırsız), AI-Pro duty tavanı 0.50. Python-tarafı STM duty-max **yok** (firmware doyurur) |
| `simple_signal.py` | **`SimpleSignal`** — minimal Qt-siz signal/slot (STM-bağlandı bildirimleri için) |
| `path_utils.py` | App-data dizini, benzersiz cihaz-id, pairing-code, PyInstaller resource-path çözümü, `initialize_database()`, `get_app_version()` |
| `secrets_manager.py` | Şifreli sır deposu — Windows DPAPI + makine-bağlı Fernet + keyring; token/pairing/admin-code/device-id üreteçleri. **TÜM sırlar tek dosyada** (`pemf_secrets.json`). 2026-08-19: `mqtt_cloud_host/port/user/pass` eklendi (operator bölümü; E-stop **bulut aynası** — tanımsızsa ayna sessiz devre dışı; env fallback `PEMF_MQTT_CLOUD_*`) |
| `file_acl.py` | `lock_down_file()` — bir dosyanın ACL'ini yalnız mevcut kullanıcıya kısıtla (sır dosyalarını sertleştirir) |
| `production_config_manager.py` | **`ProductionConfigManager`** singleton — bundled+kullanıcı JSON config birleştir (şifreli değerler, noktalı-anahtar get/set) |
| `pdf_report_generator.py` | **`PDFReportGenerator`** — ReportLab ile seans/hasta tedavi PDF raporu (istatistik+coil-run tabloları, DejaVu font) |
| `request_context.py` | `get_request_id()` — contextvar tabanlı istek-başı korelasyon-id (yapılandırılmış log) |
| `telemetry.py` | `init_telemetry()` — opsiyonel Sentry (yalnız `PEMF_SENTRY_DSN` varsa); PII-temizleyen `before_send` |
| `zeroconf_singleton.py` | Süreç-geneli tek Zeroconf örneği + LAN-arayüz tazeleme + re-register callback'i (çok-homed mDNS fix) |
| `platform_support.py` | Çapraz-platform çalıştırılabilir/binary yol yardımcıları (`exe_suffix`, `find_executable`, `find_bundled_file`) |
| `model_downloader.py` | AI model ağırlığı **çözümü** — YALNIZ yerel kökleri sırayla arar (ProgramData → AppData cache → `release_assets/ai_models` → EXE bundle). **Hugging Face indirme YOK** — bulunamazsa hata |

## ⚠️ Dikkat
- `stm32_protocol_limits.py` = **güvenlik-limitlerinin kaynağı**. Değerleri zayıflatma; testleri `tests/test_stm32_protocol_limits.py`.
- `model_downloader.py` **offline-only** — internetten model çekmez (gömülü/kopyalı olmalı).
- `secrets_manager.py` tek sır-noktasıdır; yeni sırları buradan ekle (dağınık keyring/env değil).

---
İlgili: [proje geneli](../README.md) · [controllers/](../controllers/README.md) · [database/](../database/README.md) · [firmware/](../firmware/README.md)
