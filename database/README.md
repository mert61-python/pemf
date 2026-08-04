# database/ — Kalıcılık Katmanı (SQLite / SQLCipher)

Hasta, tedavi-seansı, sensör ve kimlik verilerinin **yerel şifreli** deposu. Tek kaynak yereldir;
bulut (Supabase) yalnız cihaz-registry + opsiyonel şifreli PII içindir (bkz. [`../servers/sync_worker.py`](../servers/README.md)).

## Dosyalar
| Dosya | Görev |
|---|---|
| `treatment_history_db.py` | **`TreatmentHistoryDB`** (ana tedavi DB'si) — seanslar, coil-run'lar, sensör örnekleri (batch insert), seans olayları, AI analizleri, dayanıklı **MQTT outbox** (enqueue/inflight/retry-backoff), şema migrasyonları (rollback'li), bütünlük kontrolü, veri-saklama/PII-redaksiyon temizliği. SQLCipher-veya-düz-metin farkında |
| `patient_database.py` | **`PatientDatabase`** — hasta CRUD; **alan-başı Fernet şifreleme**, HMAC tokenize arama indeksi, pasif hastaların anonimleştirilmesi, yedek |
| `session_manager.py` | **`SessionManager`** — canlı seans kaydedici: seans başlat/bitir, batch parametre + sensör yazımı, notlar, bayatlamış-seansı zorla-bitir |
| `auth_db.py` | **`AuthDB`** — yerel kullanıcı kimlik deposu (kayıt/doğrula/sıfırla), tuzlanmış parola hash'i |
| `sqlcipher_util.py` | Paylaşımlı SQLCipher yardımcıları — binding import, at-rest anahtarı keyring'den türet (`PEMF_GUI`/`sqlcipher_key`), şifreli bağlantı aç, `PEMF_ENCRYPT_AT_REST=1` iken düz-metin→şifreli migrasyon |

## Supabase şeması — ⚠️ ÇALIŞTIRMA SIRASI ÖNEMLİ

Bu üç `.sql` dosyası Supabase Dashboard → SQL Editor'de **bu sırayla** çalıştırılır. Üçü de bu
dizinde ama README'de hiç listelenmiyordu (denetim 2026-08-04, P2 — sıra hiçbir yerde yazılı değildi).

| # | Dosya | Ne yapar |
|---|---|---|
| 1 | `supabase_devices.sql` | `devices` tablosu + RLS + **v1** RPC'ler (`upsert_device`/`resolve_device`) |
| 2 | `supabase_patients.sql` | `patients` + `treatment_sessions` + RLS + **v1** RPC'ler |
| 3 | `supabase_secure_v2.sql` | v1 imzalarını **düşürür**, yerine `p_secret` (bcrypt capability-token) isteyen **v2** sürümleri kurar |

> **v2'den SONRA 1. ya da 2. dosyayı tekrar çalıştırmayın.** `create or replace` +
> `grant execute … to anon` içerdikleri için **sırsız aşırı-yükler geri gelir ve anon rolüne
> yeniden grant edilir** — v2 fonksiyonları da yerinde kaldığından **hiçbir hata görünmez**,
> güvenlik sessizce v1'e düşer. Bu yüzden 1. ve 2. dosyanın başına, v2 zaten uygulanmışsa
> çalışmayı `raise exception` ile **durduran** bir kapı eklendi (`_pemf_verify_device` varlığına bakar).
> Kapıyı kaldırmayın.

## Şifreleme modeli (iki katman)
1. **Tüm-DB SQLCipher** — `PEMF_ENCRYPT_AT_REST=1` ile; anahtar OS keyring'de (`sqlcipher_util.py`).
2. **Alan-başı Fernet** — hasta PII'si (`patient_database.py`), DB şifreli olsa da ekstra.

## ⚠️ Dikkat
- **PII maskeleme VARSAYILAN KAPALI** (bilinçli sahip kararı) — tedavi geçmişi gerçek isim gösterir; `PEMF_MASK_HISTORY_PII=1` ile açılır. Geri maskeleme ekleme.
- `outbox` **DRAIN-only bir tablo değildir**; enqueue tarafı canlıdır — silme/temizleme yapma.
- Gerçek DB dosyaları burada değil, app-data'dadır (`~/.pemf_gui` / `PEMF_DATA_DIR`, tipik `C:\ProgramData\PEMF_System\PEMF_GUI`).

---
İlgili: [proje geneli](../README.md) · [servers/](../servers/README.md) · [utils/secrets_manager](../utils/README.md) · [mimari](../docs/ARCHITECTURE.md)
