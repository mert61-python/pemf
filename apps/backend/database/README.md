# database/ — Kalıcılık Katmanı (SQLite / SQLCipher)

Hasta, tedavi-seansı, sensör ve kimlik verilerinin **yerel şifreli** deposu. Tek kaynak yereldir;
bulut (Supabase) yalnız cihaz-registry + opsiyonel şifreli PII içindir (bkz. [`../servers/sync_worker.py`](../servers/README.md)).

## Dosyalar
| Dosya | Görev |
|---|---|
| `treatment_history_db.py` | **`TreatmentHistoryDB`** — `thdb_*` karışımlarını birleştiren ana sınıf (**karışım/mixin**, işbirlikçi nesne DEĞİL: `get_treatment_db(...)` ürünün her yerinden alınıp metotlar DOĞRUDAN çağrıldığı için genel API birebir korunur). Bağlantı havuzu / kilit yönetimi (`_get_connection`, `close_connections`), SQLCipher-veya-düz-metin farkındalığı ve karışımların paylaştığı sınıf sabitleri burada kalır; açılış kurtarması dahil seans yaşam döngüsü `thdb_seans`tadır (her karışımın ana sınıftan kullandığı üyeler kendi başlığında, AST kapısıyla: `tests/test_database_README_ve_karisim_basliklari_GERCEK_D6_60.py`) |
| `thdb_seans.py` | **`SeansKarisimi`** — seans yaşam döngüsü: `treatment_sessions` · `session_parameters` · `session_events` + `upsert_patient` tedavi aynası. ⚠️ Tıbbi kaydın mühürlendiği yer (`end_session` → PDF/KPI/geçmişte GERÇEK DOZ) |
| `thdb_telemetri.py` | **`TelemetriKarisimi`** — bobin koşusu + sensör telemetrisi: `session_coil_runs` · `sensor_samples` · `sensor_run_summary`. ⚠️ Sensör örnekleri **dakika-ortalamasıdır** (`sample_count`), ham akış değil |
| `thdb_outbox.py` | **`OutboxKarisimi`** — dayanıklı MQTT outbox (`outbox_messages`): enqueue / inflight / retry-backoff |
| `thdb_denetim.py` | **`DenetimKarisimi`** — denetim izi (`audit_events` — salt-ekle; UPDATE/DELETE trigger'la engelli; `denetim_yaz`). ⚠️ KVKK talepleri dahil "kim ne zaman dokundu"nun TEK kanıtı; hasta ADI yazılmaz |
| `thdb_sema.py` | **`SemaKarisimi`** — tablo/indeks kurulumu, açılış göçleri, şema sürümü, düz-metin→SQLCipher göçünün tetiklenmesi (gövde `sqlcipher_util`e delege). ⚠️ Rollback YALNIZ şema sürümü (metadata) adımını korur: kolon göçleri (`_safe_add_column`, eklemeli + idempotent) `pre_migration_*` yedeğinden ÖNCE koşar ve geri alınmaz; yedek göç SONRASI şemayı taşır (D6.61, ölçüldü). ⚠️ EN HASSAS küme — yarım göç hasta geçmişini kaybettirir |
| `thdb_pii.py` | **`PiiKarisimi`** — PII redaksiyonu / KVKK: `anonymize_patients_by_uuid` (GERİ DÖNÜŞSÜZ), saklama süresi. ⚠️ Maskeleme varsayılan KAPALI |
| `thdb_bakim.py` | **`BakimKarisimi`** — tabloya değil VERİTABANINA dokunan işler: yedek, bütünlük denetimi, disk durumu, dışa/içe aktarma, `apply_data_retention_policy` (GERİ DÖNÜŞSÜZ silme), `system_settings` |
| `thdb_ai_gecmisi.py` | **`AiGecmisiKarisimi`** — AI analiz geçmişi (`ai_analyses`) + `set_ai_review` (`review_status`/`review_note`/`reviewed_by`/`reviewed_at`). ⚠️ AI çıktısı ÖNERİDİR, karar hekimindir — bu alanları kaldırmayın |
| `db_hatalari.py` | Paylaşılan `_DB_ERROR` istisna demetleri (SQLCipher + sqlite3) — **TEK KAYNAK**. `sqlite3` except'leri `sqlcipher3` istisnalarını YAKALAMAZ; kendi kopyanızı yazmayın, buradan import edin |
| `patient_database.py` | **`PatientDatabase`** — hasta CRUD; **alan-başı Fernet şifreleme**, HMAC tokenize arama indeksi, pasif hastaların anonimleştirilmesi, yedek |
| `session_manager.py` | **`SessionManager`** — canlı seans kaydedici: seans başlat/bitir, batch parametre + sensör yazımı, notlar, bayatlamış-seansı zorla-bitir |
| `auth_db.py` | **`AuthDB`** — yerel kullanıcı kimlik deposu (kayıt/doğrula/sıfırla), tuzlanmış parola hash'i |
| `sqlcipher_util.py` | Paylaşımlı SQLCipher yardımcıları — binding import, at-rest anahtarını SecretsManager'dan al (`<veri kökü>\pemf_secrets.json` → `auto.sqlcipher_key`, DPAPI ile makineye bağlı; keyring / `.sqlcipher_key` yalnız eski kaynak olarak bir kez taşınır), şifreli bağlantı aç, `PEMF_ENCRYPT_AT_REST=1` iken düz-metin→şifreli migrasyon |

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
> `apps/web` indirme sayfasındaki kullanım bölümü **sessizce hiç görünmez**
> (`src/lib/usageStats.ts` bilerek `null` döner: "uydurma sayı göstermektense hiç gösterme").
> Yani belirti "hata" değil, **eksik bölüm**tür — bu yüzden fark edilmeden kalabilir.

> **v2'den SONRA 1. ya da 2. dosyayı tekrar çalıştırmayın.** `create or replace` +
> `grant execute … to anon` içerdikleri için **sırsız aşırı-yükler geri gelir ve anon rolüne
> yeniden grant edilir** — v2 fonksiyonları da yerinde kaldığından **hiçbir hata görünmez**,
> güvenlik sessizce v1'e düşer. Bu yüzden 1. ve 2. dosyanın başına, v2 zaten uygulanmışsa
> çalışmayı `raise exception` ile **durduran** bir kapı eklendi (`_pemf_verify_device` varlığına bakar).
> Kapıyı kaldırmayın.

### Kurulumdan SONRA elle uygulanan yamalar (depo kökü `supabase/`)

Yukarıdaki üç dosya v2'den sonra tekrar çalıştırılamadığı için, yayına çıkmış bir projede tek bir
RPC'yi güncellemek gerektiğinde **ayrı, dar kapsamlı** bir dosya yazılır. Bunlar bu dizinde
DEĞİL, **depo kökündeki** `supabase/` dizinindedir (buradan `../../../supabase/`) ve
**sahibi tarafından elle** (SQL Editor → yapıştır → Run) uygulanır:

| Dosya | Ne yapar | Zorunlu mu |
|---|---|---|
| `../../../supabase/resolve_device_bayat_gorunur.sql` | `resolve_device` tazelik penceresini 5 dk → **30 gün** yapar. Pencere istemcinin `STALE_MS`i ile eşit olduğu için bayat satır istemciye hiç ulaşmıyor, "cihaz kapalı" teşhisi ölü kod kalıyordu; kullanıcı doğru kodda bile **"Kodu kontrol edin"** görüyordu (denetim 2026-08-17) | **Evet** — uygulanmazsa saha teşhisi yanlış yöne bakmaya devam eder. APK/web yayını gerekmez. |
| `../../../supabase/upsert_device_envanter.sql` | `upsert_device`e envanter alanları ekler (bcrypt modeli korunur) | Envanter alanları kullanılacaksa |
| `../../../supabase/seans_kimligi_bilesik_anahtar.sql` | `treatment_sessions` birincil anahtarını `(id)` → **`(device_id, id)`** bileşiğine çevirir. `id` kliniğin YEREL SQLite `AUTOINCREMENT`'inden geldiği için her klinik 1, 2, 3… diye başlıyordu → çoklu klinikte sessiz veri kaybı (denetim 2026-08-30) | Çoklu klinik kullanılacaksa **Evet** |

### Abonelik tablosu — ÜÇÜNCÜ konum (`apps/ui/supabase/`)

| Dosya | Ne yapar | Zorunlu mu |
|---|---|---|
| `../../ui/supabase/subscriptions.sql` | `subscriptions` (abonelik / entitlement) tablosu + RLS + `anon`/`authenticated` yazma yetkilerini geri alma; kullanıcı yalnız kendi satırını okur, yazma yalnız `service_role` (Stripe webhook). Mobil arayüzle birlikte taşındığı için bu dizinde değil (D4.25: SQL değişmez kapısı bu dosyayı da tarar — taranan küme `git ls-files '*.sql'`) | Abonelik/hak gösterimi kullanılacaksa |

### Jeton ücretlendirme + canlı-şema sertleştirme

Bu `.sql` dosyaları da bu dizindedir ama yukarıdaki v1→v2 sırasından **bağımsızdır**; canlıya
depo kökünden `python scripts/supabase_sql.py --dosya apps/backend/database/<dosya>.sql --yaz` (ya da SQL Editor) ile
uygulanır (betik kökte, SQL bu dizinde — F4 taşımasından beri; D6.60).

| Dosya | Ne yapar | Zorunlu mu |
|---|---|---|
| `supabase_jetonlar.sql` | JETON ücretlendirme altyapısı — `token_balances` (iki-cepli: **aylik_hak** devretmez + **satin_alinan** süresiz/devreder) + `token_ledger` (UNIQUE `istek_id` → çift-düşme yok) + atomik `jeton_tuket` RPC. Yazma yalnız `service_role`; kullanıcı yalnız kendi bakiyesini okur. ⚠️ TİCARİ kapı, güvenlik DEĞİL — tedavi yolunu engellemez (bkz. [`../servers/jeton.py`](../servers/README.md)) | Jeton satışı açılacaksa |
| `supabase_sertlestirme.sql` | Canlı-şema sertleştirme — `public` tablolarındaki `anon`/`authenticated` **doğrudan tablo yetkilerini** (Supabase varsayılanı) geri alır. Bugün RLS sızıntıyı önlüyor; bu, "gizli mayını" (ileride izin-verici politika ya da göç sırasında RLS kapanması) kapatır | Evet (savunma-derinliği) |
| `supabase_okuma_rpc.sql` | Kullanıcı okumalarını **SECURITY DEFINER** RPC'lere taşır — tablolarda HİÇBİR role yetki kalmaz; her fonksiyon `auth.uid()` kullanır (kimliği parametre olarak ALMAZ), `anon`a grant verilmez, dönen alan kümesi imzada sabitlenir | Evet (sertleştirme ile birlikte) |

### Profil buluta — CH2 (S-SG.8 / sahip kararı Y151)

Seans ve hasta / denek kaydının **arayüz profili** (veterinarian / researcher / pet_owner) bulut kopyasına da yazılır. Yalnız
**eklemelidir** (kolon ekler, RPC imzaları AYNI kalır) ve cihaz kodu bu dosya uygulanmadan da çalışır — canlıya **yayın
hazırlığında, sahiple** uygulanır. ⚠️ Ön koşul (dosyanın başındaki kapı denetler, eksikse hiçbir şey yapmadan durur):
`supabase_secure_v2.sql` ve `../../../supabase/seans_kimligi_bilesik_anahtar.sql` uygulanmış olmalı.

| Dosya | Ne yapar | Zorunlu mu |
|---|---|---|
| `supabase_profil.sql` | `treatment_sessions.profil` + `patients.profil` (`text not null default ''`); `upsert_session` / `upsert_patient` aynı imzayla yükteki `profil`i yazar (normalize, boş gelen dolu değeri ezmez); yetkiler rol rol (yalnız `anon`). Uygulama: `python scripts/supabase_sql.py --dosya apps/backend/database/supabase_profil.sql --yaz` | Hasta / seans bulut senkronu (`PEMF_CLOUD_PATIENT_SYNC=1`) açılacaksa |
| `supabase_profil_geri_al.sql` | Geri alma: iki fonksiyonu önceki gövdelerine döndürür; kolonları SİLMEZ (veri kaybı yok) | Yalnız geri dönüş gerekirse |

## Şifreleme modeli (iki katman)
1. **Tüm-DB SQLCipher** — `PEMF_ENCRYPT_AT_REST=1` ile; anahtar `<veri kökü>\pemf_secrets.json` → `auto.sqlcipher_key` (DPAPI `CRYPTPROTECT_LOCAL_MACHINE` — bu makineye bağlı; `sqlcipher_util.get_sqlcipher_key` → `utils/secrets_manager`). Yedekler aynı anahtarla şifrelidir (A-13); makine dışında açmak için kurtarma kodu + `kurtarma-zarfi.enc` gerekir (`utils/backup_recovery.py`, [RUNBOOK](../../../docs/RUNBOOK.md) "Kurtarma kodu").
2. **Alan-başı Fernet** — hasta PII'si (`patient_database.py`), DB şifreli olsa da ekstra.

## ⚠️ Dikkat
- **PII maskeleme VARSAYILAN KAPALI** (bilinçli sahip kararı) — tedavi geçmişi gerçek isim gösterir; `PEMF_MASK_HISTORY_PII=1` ile açılır. Geri maskeleme ekleme.
- `outbox` mekanizması (tablo + `enqueue_outbox_message` / boşaltma yöntemleri) **SİLİNMEZ** (sahip kararı, drain-only). ⚠️ Bugün üretimde enqueue çağıranı YOK: tek çağıranı `SessionManager.start_session` / `end_session`, `SessionManager` örneği (`headless_core.session_manager`) ise hiçbir yerde kullanılmıyor; boşaltıcı (`get_pending_outbox_messages`) da çağrılmıyor — üretim kodunda yalnız sayım (`get_outbox_status_counts`) ve ölü-ileti budaması (`purge_old_dead_outbox`) çağrılır. Yeni bir enqueue çağıranı eklenirse boşaltıcı da gerekir; silme/temizleme yapma (kapı: AST ölçümü, D6.60).
- Gerçek DB dosyaları burada değil, app-data'dadır (`~/.pemf_gui` / `PEMF_DATA_DIR`, tipik `C:\ProgramData\PEMF_System\PEMF_GUI`).

---
İlgili: [proje geneli](../../../README.md) · [servers/](../servers/README.md) · [utils/secrets_manager](../utils/README.md) · [mimari](../../../docs/ARCHITECTURE.md)

## ⚠️ Uygulama sırası GÜVENLİĞİ — `ON_ERROR_STOP` ŞART

`supabase_devices.sql` ve `supabase_patients.sql` başında bir **sıra-güvenliği kapısı** var:
`secure_v2` şeması zaten kuruluysa (`_pemf_verify_device` işaretçisi) `raise exception` ile
durur. Bu, ESKİ dosyaların YENİ şemayı geri sarmasını engeller.

**Ama bu garanti, dosyanın hata anında GERÇEKTEN durmasına bağlıdır.** `psql -f dosya.sql` ile
uygulanırsa `ON_ERROR_STOP` **varsayılan olarak KAPALIDIR**: `raise exception` yalnız o ifadeyi
düşürür, `psql` kalan ifadeleri çalıştırmaya DEVAM EDER ve kapı hiçbir şeyi durdurmamış olur.

Doğru kullanım:

```bash
psql -v ON_ERROR_STOP=1 -f apps/backend/database/supabase_devices.sql "$DATABASE_URL"   # depo kökünden
```

Supabase **SQL Editor**'da yapıştırıp çalıştırmak güvenlidir (tek transaction, ilk hata tüm
çalıştırmayı iptal eder) — önerilen yol budur.
