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
| `image_domain.py` | **Görüntü ALAN (modalite) kapısı** — `check()` girdinin modalitesini (grayscale/stained/color) görüntünün fiziğinden ölçer; modülün beklediğiyle KESİN uyuşmazlıkta reddeder (softmax'ın yanlış görüntüye %100 "güven" vermesini önler). Muhafazakâr: kararsızsa GEÇİRİR. Yaprak modül (stdlib + numpy) |
| `ses_kalitesi.py` | **Ses kaydı kalite kapısı** — kedi-sesi sınıflandırmasından ÖNCE RMS-dBFS + normalize-entropi ile sessizlik/gürültü reddi. Model "kedi yok" DİYEMEZ (10 sınıf da duygu) → karar model DIŞINDA verilir. Yaprak modül (stdlib) |
| `klinik_asgari.py` | **Asgari klinik girdi kapıları** (`vital_kapisi` / `ckd_kapisi`) — `ai_router`'daki iki kapının BİT-AYNI taşınması, `:8100` (auth-muaf) transportu da kapılasın diye. Yaprak modül (yalnız stdlib) — `docker/Dockerfile.ai` imajına tek satırla girer |
| `source_crypto.py` | **Kaynak-şifreleme kripto ilkeleri** (`.pyenc` üret/çöz) — çözücü sahada çalıştığı için `utils`'te; `build_tools/source_crypto.py` buradan yeniden dışa aktarır (aynı algoritma). ⚠️ Kopyalamayı zorlaştırır, tersine-mühendisliği ENGELLEMEZ (anahtar üründe) — asıl koruma `.py→.pyd` |
| `encrypted_import.py` | **Şifreli kaynak yükleyici** — `.pyenc` modüllerini BELLEKTE çözen import bulucusu (`sys.meta_path` SONUNA eklenir); diske yazmaz, düz `.py` varsa onu kullanır (geliştirme etkilenmez), parola yoksa sessiz no-op, çözme hatası yutulmaz |
| `data_export.py` | **Klinik veri taşıma** — kullanıcı parolalı, RASTGELE-tuzlu şifreli dışa/içe aktarma (`encrypt_bundle` / `decrypt_bundle`; `PEMFDATA1` imzası + Fernet, açık metin = gzip(JSON)). Cihaz değişiminde geçmişi taşımak için (bulut senkronu yok). ⚠️ `source_crypto`'nun SABİT tuzuyla KARIŞTIRMA (amaç farklı) |
| `backup_recovery.py` | **Makineden BAĞIMSIZ felaket-kurtarma zarfı** — SİSTEM üretimi 150-bit kurtarma kodu; SQLCipher anahtarlarını scrypt-türetilmiş anahtarla yedeklerin yanına `kurtarma-zarfi.enc`'e sarar (DPAPI makine-bağı, off-site yedeği anakart/disk arızasında açamıyordu) |
| `support_bundle.py` | **PII-maskeli tek-dosya teşhis paketi** (`olustur`) — sağlık/sürüm özeti, log kuyrukları, çökme, denetim ÖZETİ toplar; sır / DB / anahtar / kurtarma-zarfı ASLA girmez; o cihazdaki gerçek hasta/operatör adlarını maskeler + ne kadar maskelendiğinin özetini taşır |
| `gizli_surec.py` | **Konsol penceresi AÇMADAN alt-süreç başlatma** TEK KAYNAK (`calistir` / `baslat`) — konsolsuz backend'ten spawn'da siyah pencere sızmasını önler; `creationflags` EZER (ek bayrak `bayraklar()`a EKLENİR, ayrıca verilmez) |
| `turkce_metin.py` | **Türkçe metin yardımcıları** — `arama_katla()` aksan-KORUYAN arama katlaması (yalnız `İ→i` / `I→ı` + NFC; `Şirin`≠`Sirin`, yanlış-hasta riskini önler — mobil ile bit-aynı) + `sayiya_cevir()` Türkçe ondalık-virgül toleranslı sayı ayrıştırma (`"3,5"`→`3.5`; float() ValueError→sessiz varsayılan-kilo→yanlış-doz kategorisini önler). Yaprak modül (stdlib + unicodedata) |
| `multipart_limit.py` | **Multipart form-alanı limiti** — `buyuk_form_alani_limitini_uygula()` Starlette'in DOSYA-DIŞI form alanı için 1MB `max_part_size` varsayılanını 32MB'a çıkarır (base64 görüntü `image_base64` bir form ALANI olduğu için 1MB'a takılıyordu — "Part exceeded maximum size of 1024KB"). Idempotent (`_pemf_multipart_patched`); `api_server.py` FastAPI() örneğinden ÖNCE çağırır |
| `runtime_guards.py` | **Çalışma-anı davranış kilitleri** — `pip_kurulumunu_yasakla()` sevk edilen EXE'nin kendine `pip install` denemesini engeller (ultralytics her AI modelinde `onnxruntime`'ı EKSİK sanıp `PEMF_Backend.exe -m pip install …` çalıştırıyordu). Üç zararı keser: yanıltıcı kırmızı log, model başına ~2,9 sn israf (3,975 s→1,069 s), istenmeyen internet erişimi. `kurulum_yasagi_etkin_mi()` durum sorgusu (DENETİM 2026-08-28 #10) |

## ⚠️ Dikkat
- `stm32_protocol_limits.py` = **güvenlik-limitlerinin kaynağı**. Değerleri zayıflatma; testleri `tests/test_stm32_protocol_limits.py`.
- `model_downloader.py` **offline-only** — internetten model çekmez (gömülü/kopyalı olmalı).
- `secrets_manager.py` tek sır-noktasıdır; yeni sırları buradan ekle (dağınık keyring/env değil).

---
İlgili: [proje geneli](../README.md) · [controllers/](../controllers/README.md) · [database/](../database/README.md) · [firmware/](../firmware/README.md)
