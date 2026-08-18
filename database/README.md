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

Bu `.sql` dosyaları Supabase Dashboard → SQL Editor'de **bu sırayla** çalıştırılır. Hepsi bu
dizinde ama README'de hiç listelenmiyordu (denetim 2026-08-04, P2 — sıra hiçbir yerde yazılı değildi).

| # | Dosya | Ne yapar | Zorunlu mu |
|---|---|---|---|
| 1 | `supabase_devices.sql` | `devices` tablosu + RLS + **v1** RPC'ler (`upsert_device`/`resolve_device`) | Evet |
| 2 | `supabase_patients.sql` | `patients` + `treatment_sessions` + RLS + **v1** RPC'ler | Evet |
| 3 | `supabase_secure_v2.sql` | v1 imzalarını **düşürür**, yerine `p_secret` (bcrypt capability-token) isteyen **v2** sürümleri kurar | Evet |
| 4 | `supabase_kullanim_sayaci.sql` | `usage_counts()` RPC — sitedeki sayaç "indirme" değil BENZERSİZ KULLANIM göstersin (yalnız üç tamsayı döner, satır/kimlik dökmez) | Hayır |

> **4. dosya listede YOKTU (denetim 2026-08-18).** Sıra-güvenliği açısından zararsız (kendi
> başına idempotent, v2'ye dokunmaz) ama uygulanmazsa `usage_counts` RPC'si bulunmaz →
> `pemf-vet-web` indirme sayfasındaki kullanım bölümü **sessizce hiç görünmez**
> (`src/lib/usageStats.ts` bilerek `null` döner: "uydurma sayı göstermektense hiç gösterme").
> Yani belirti "hata" değil, **eksik bölüm**tür — bu yüzden fark edilmeden kalabilir.

> **v2'den SONRA 1. ya da 2. dosyayı tekrar çalıştırmayın.** `create or replace` +
> `grant execute … to anon` içerdikleri için **sırsız aşırı-yükler geri gelir ve anon rolüne
> yeniden grant edilir** — v2 fonksiyonları da yerinde kaldığından **hiçbir hata görünmez**,
> güvenlik sessizce v1'e düşer. Bu yüzden 1. ve 2. dosyanın başına, v2 zaten uygulanmışsa
> çalışmayı `raise exception` ile **durduran** bir kapı eklendi (`_pemf_verify_device` varlığına bakar).
> Kapıyı kaldırmayın.

### Kurulumdan SONRA elle uygulanan yamalar (`../supabase/`)

Yukarıdaki üç dosya v2'den sonra tekrar çalıştırılamadığı için, yayına çıkmış bir projede tek bir
RPC'yi güncellemek gerektiğinde **ayrı, dar kapsamlı** bir dosya yazılır. Bunlar `supabase/`
dizinindedir ve **sahibi tarafından elle** (SQL Editor → yapıştır → Run) uygulanır:

| Dosya | Ne yapar | Zorunlu mu |
|---|---|---|
| `resolve_device_bayat_gorunur.sql` | `resolve_device` tazelik penceresini 5 dk → **30 gün** yapar. Pencere istemcinin `STALE_MS`i ile eşit olduğu için bayat satır istemciye hiç ulaşmıyor, "cihaz kapalı" teşhisi ölü kod kalıyordu; kullanıcı doğru kodda bile **"Kodu kontrol edin"** görüyordu (denetim 2026-08-17) | **Evet** — uygulanmazsa saha teşhisi yanlış yöne bakmaya devam eder. APK/web yayını gerekmez. |
| `upsert_device_envanter.sql` | `upsert_device`e envanter alanları ekler (bcrypt modeli korunur) | Envanter alanları kullanılacaksa |

## Şifreleme modeli (iki katman)
1. **Tüm-DB SQLCipher** — `PEMF_ENCRYPT_AT_REST=1` ile; anahtar OS keyring'de (`sqlcipher_util.py`).
2. **Alan-başı Fernet** — hasta PII'si (`patient_database.py`), DB şifreli olsa da ekstra.

## ⚠️ Dikkat
- **PII maskeleme VARSAYILAN KAPALI** (bilinçli sahip kararı) — tedavi geçmişi gerçek isim gösterir; `PEMF_MASK_HISTORY_PII=1` ile açılır. Geri maskeleme ekleme.
- `outbox` **DRAIN-only bir tablo değildir**; enqueue tarafı canlıdır — silme/temizleme yapma.
- Gerçek DB dosyaları burada değil, app-data'dadır (`~/.pemf_gui` / `PEMF_DATA_DIR`, tipik `C:\ProgramData\PEMF_System\PEMF_GUI`).

---
İlgili: [proje geneli](../README.md) · [servers/](../servers/README.md) · [utils/secrets_manager](../utils/README.md) · [mimari](../docs/ARCHITECTURE.md)

## ⚠️ Uygulama sırası GÜVENLİĞİ — `ON_ERROR_STOP` ŞART

`supabase_devices.sql` ve `supabase_patients.sql` başında bir **sıra-güvenliği kapısı** var:
`secure_v2` şeması zaten kuruluysa (`_pemf_verify_device` işaretçisi) `raise exception` ile
durur. Bu, ESKİ dosyaların YENİ şemayı geri sarmasını engeller.

**Ama bu garanti, dosyanın hata anında GERÇEKTEN durmasına bağlıdır.** `psql -f dosya.sql` ile
uygulanırsa `ON_ERROR_STOP` **varsayılan olarak KAPALIDIR**: `raise exception` yalnız o ifadeyi
düşürür, `psql` kalan ifadeleri çalıştırmaya DEVAM EDER ve kapı hiçbir şeyi durdurmamış olur.

Doğru kullanım:

```bash
psql -v ON_ERROR_STOP=1 -f database/supabase_devices.sql "$DATABASE_URL"
```

Supabase **SQL Editor**'da yapıştırıp çalıştırmak güvenlidir (tek transaction, ilk hata tüm
çalıştırmayı iptal eder) — önerilen yol budur.
