# PEMF Backend — Production-Readiness & Endüstri Standardı Denetimi

**Tarih:** 2026-07-08 · **Kapsam:** `guii/` (FastAPI backend) + `C:\Users\merta\pf` (Expo/React Native web+mobil, `guii/frontend` junction) · **Sürüm:** backend `1.5.0`, mobil `2.0.0` (vc5)
**Yöntem:** Önce yapı/stack/deps haritalandı; sonra 3 paralel derin-kesif (DB · backend-runtime · frontend) + güvenlik/CI/deps/docs manuel denetimi. **Her bulgu gerçek koda dayanır (dosya:satır).** Bilinçli mimari kararlar "kabul edilmiş risk" olarak ayrı işaretlendi — vulnerability sanılmadı.

---

## 1. Yönetici Özeti (Executive Summary)

**Karar: KOŞULLU üretime-hazır (Conditional).** Amaçlanan dağıtım (tek-cihaz klinik: LAN + Cloudflare tünel, tek operatör) için — `deploy/server.env|device.env` profilleri uygulandığında (CORS daraltma, `PEMF_REQUIRE_AUTH=1`, TLS reverse-proxy) — **kısa bir "çıkmadan önce" listesi dışında hazır.** Genel çok-kiracılı (multi-tenant) SaaS için değil — ama bu ürün **tıbbi cihaz backend'i**, o mimariyi hedeflemiyor.

Bu, **olgun ve çok-denetimli** bir kod tabanı: kaynakta `audit B-1.x`…`B-11.x` izleri, **SQL-injection'a kapalı** (~171 sorgu parametreli), **fail-closed auth + şifreleme + rate-limit**, ham traceback/`str(e)` sızdırmayan global exception handler, `/metrics` (Prometheus) + Sentry + rotating-log, otomatik **şifreli DB yedeği + retention + KVKK anonimleştirme**, API versiyonlama (`/api/v1`), 4 CI workflow (lint/pip-audit/test/dependabot) ve zengin doküman (ARCHITECTURE/RUNBOOK/VERIFICATION). Önceki audit'ler gerçek P0'ları (bundle-credential sızıntısı, fail-open auth, ham-str(e), web-crypto CVE'leri) **zaten kapatmış**.

Kalan boşlukların **hiçbiri Critical değil.** En yüksek etkili 5: (1) `history_router` 11 uçta `str(e)` sızıntısı — B3 sertleştirmesi bu router'ı atlamış; (2) tüketici APK'sinde **erişilebilirlik (a11y) zayıf**; (3) iki en-karmaşık frontend modülü (WS istemci + telemetri reducer) **testsiz**; (4) birkaç `async` uçta senkron DB/MQTT event-loop'u bloke ediyor; (5) klasik güvenlik header'ları (nosniff/frame/CSP/HSTS) eksik. Genel olgunluk **~3.7/5** — sektör ortalamasının üstünde.

---

## 2. Olgunluk Skoru Tablosu

| # | Boyut | Skor (0-5) | Tek satır gerekçe |
|---|---|:---:|---|
| 1 | Güvenlik | **4.0** | Fail-closed auth+rate-limit, injection-yok, sır-yönetimi (SecretsManager), web/crypto CVE yamalı; eksik: klasik header'lar, CORS=* varsayılan, auth-muaf AI (kabul-risk) |
| 2 | Mimari & Kod Kalitesi | **3.5** | Modüler router ayrımı + refactor temiz; ama `api_server`1833/`ai_router`1384/`treatment_history_db`2338 büyük, stil-lint 2200+ ihlal ertelenmiş, mypy lenient |
| 3 | Test | **3.0** | 94 test, güvenlik-yolları characterization-testli + CI-koşulu; ama **kapsam ~%36**, `wsClient`+telemetri-reducer testsiz |
| 4 | Hata Yönetimi & Dayanıklılık | **4.0** | Global handler sızıntısız, fail-closed, bounded queue, subprocess timeout; eksik: `history_router` str(e), başarı-şekilli-200 |
| 5 | Gözlemlenebilirlik | **4.0** | `/metrics` Prometheus + Sentry (PII-scrub) + `/health` + crash.log + rotating; eksik: normal-yolda request-correlation-id |
| 6 | Performans & Ölçeklenebilirlik | **3.0** | Keyset pagination, bounded HW queue, hot-path `to_thread`; eksik: bazı async-blok, WS timeout'suz, tek-instance (tasarım) |
| 7 | Veri & Veritabanı | **4.5** | Injection-yok, WAL+index+FK, fail-closed SQLCipher, **otomatik şifreli yedek+retention+KVKK**; eksik: ad-hoc migration, sync upsert kolon-düşürme |
| 8 | API Tasarımı | **4.0** | Versiyonlama `/v1`, OpenAPI gated, pagination, çoğunlukla tutarlı hata; eksik: başarısızlıkta HTTP-200 |
| 9 | DevOps / CI-CD | **3.0** | CI (lint+pip-audit+test+dependabot) + `.env` profilleri; eksik: Docker-yok, build/deploy-CI-yok, security-CI bloklamıyor, ubuntu'da Windows-hedef test |
| 10 | Frontend (Expo/Web) | **3.0** | Ağ/WS katmanı güçlü, code-splitting, tri-state, `strict`; eksik: a11y zayıf, `React.memo`-yok, karmaşık-modül-testsiz, bloklayan alert |
| 11 | Dokümantasyon | **4.5** | README+ARCHITECTURE+RUNBOOK+VERIFICATION+.env.example+deploy/README; eksik: README'nin işaret ettiği `DEPLOYMENT.md` yok |

**Ağırlıklı ortalama ≈ 3.7 / 5.**

---

## 3. Kategori Bazında Detaylı Bulgular

> **Önem ölçeği:** Critical (çıkmadan MUTLAKA) · High · Medium · Low.
> **Efor:** S (<½ gün) · M (½–2 gün) · L (>2 gün).

### 1. Güvenlik

**✅ Güçlü (doğrulandı — aksiyon yok):** Fail-closed auth katmanı (`servers/api_server.py:177-217`; auth-layer patlarsa muaf-yollar geçer/gerisi 503, token patlarsa 401) + WebSocket auth (`:569-596`). LAN-muafiyet + tünel-zorunlu token (`servers/auth.py:133-147`, proxy-header ile FAIL-CLOSED). `check_token` **timing-safe** `compare_digest` + boş-token'da fail-closed (`auth.py:105-114`). API token dosyası **NTFS ACL kilitli** (`auth.py:73-78`). **Hardcoded literal sır YOK** — hepsi `SecretsManager`/env (`utils/secrets_manager.py`); tek gömülü `sb_publishable_...` = Supabase **publishable/client-side** anahtar (tasarım, `secrets_manager.py:181`). **`config/credentials/` (gerçek MQTT/ESP şifreleri) EXE'ye GÖMÜLMÜYOR** (`build_tools/PEMF_Backend_onedir.spec:108-115`, P0-2026-06-28 kapatılmış) + gitignore'lu (`.gitignore:120-122`). CVE'ler yamalı: `cryptography==43.0.1`, `starlette==1.3.1`, `python-multipart==0.0.31` (requirements.txt:23,25,63 — 2026-07-06 fix'leri).

| # | Önem | Bulgu | Dosya:satır | Endüstri beklentisi | Öneri | Efor |
|---|---|---|---|---|---|---|
| S-1 | **Medium** | Klasik güvenlik header'ları eksik: `add_security_headers` yalnız COOP/COEP/CORP/X-API-Version set ediyor; `X-Content-Type-Options:nosniff`, `X-Frame-Options`/CSP, `Strict-Transport-Security` (HSTS), `Referrer-Policy` YOK | `api_server.py:157-174` | Tarayıcıya servis edilen tüm yanıtlarda nosniff+frame+HSTS+referrer | Aynı middleware'e 4 header ekle (HSTS yalnız tünel/proxy TLS'te) | S |
| S-2 | **Medium** | `PEMF_CORS_ORIGINS=*` **varsayılan** + `allow_headers=["*"]` | `.env.example:26`, `api_server.py:130` | Prod'da yalnız bilinen origin | `deploy/server.env:23` bunu zaten daraltıyor (`https://app...`) → **prod profil zorunlu kılınmalı**; dev-varsayılan `*` kabul | S |
| S-3 | **Low (kabul-risk)** | Auth **varsayılan KAPALI** (`PEMF_REQUIRE_AUTH=0`); tünel açılınca oto-1'e zorlanır | `.env.example:24`, `auth.py:85-96` | Auth varsayılan açık | Tasarım: LAN-güvenli + vet-dostu; **prod device.env `=1`** ayarlamalı (belge var). Kabul edilebilir | — |
| S-4 | **Low (kabul-risk — SAHİP KARARI)** | AI **tedavi** uçları auth-MUAF: `/api/ai/pro`, `/api/ai/ai_pro` (uzaktan kimliksiz bobin başlat/durdur) | `auth.py:24-31` (gerekçe+geri-alma belgeli) | Tedavi-tetikleyen uç kimlik ister | **Cihaz sahibinin 2026-07-01 açık talebi; riski bilerek kabul.** Vulnerability DEĞİL. Geri almak = 2 prefix'i listeden çıkar | — |
| S-5 | **Low** | Supabase RLS/anon-dump durumu **koddan doğrulanamadı** (publishable key gömülü olduğundan güvenlik RLS'e bağlı) | `secrets_manager.py:181` | Publishable key + sıkı RLS + anon-dump kapalı | Supabase konsol tarafı — manuel doğrula (bkz §5) | — |

**Backend safety-limit yokluğu (freq/duty/48°C):** Kaynakta backend eşik dayatmaz — **cihaz sahibinin bilinçli kararı** (donanım/operatör karar verir). Bu bir "eksik güvenlik kontrolü" **değil**, tasarım kararıdır; **rapor bunu düzeltme önermez.**

### 2. Mimari & Kod Kalitesi

**✅ Güçlü:** Modüler router ayrımı (`servers/{ai,history,patient,settings,system,session,update,auth}_router.py`) + shared-state modülleri (`live_state.py`, `session_state.py`). Ruff (F+E9) + `ruff format` + pre-commit (`.pre-commit-config.yaml`) + mypy config (`pyproject.toml`). TODO/FIXME/HACK borcu **~0**. Circular-import lazy-import deseniyle önlenmiş.

| # | Önem | Bulgu | Dosya:satır | Endüstri beklentisi | Öneri | Efor |
|---|---|---|---|---|---|---|
| A-1 | **Medium** | Büyük dosyalar: `treatment_history_db.py` **2338**, `api_server.py` **1833**, `ai_router.py` **1384** satır | `database/`, `servers/` | Modül <~800 satır | `treatment_history_db` = repository katmanına bölünebilir; `ai_router` cohesive (paylaşılan model-cache → bilinçli bırakılmış, bkz REFACTOR_LOG). Kademeli | L |
| A-2 | **Low** | Stil-lint **enforce edilmiyor**: 2200+ pycodestyle/UP/SIM/B ihlali `select`'e alınmamış | `pyproject.toml:29-35` | Tam lint CI-enforced | **Bilinçli** (28k satır olgun kod, tek-seferde reformat riskli); pre-commit kademeli açıyor. Kademe-1 (`B`+`I`) önerilir | M |
| A-3 | **Low** | mypy **lenient + CI-zorunlu değil** (`disallow_untyped_defs=false`) | `pyproject.toml:59-68` | Kademeli tam-tipleme | Kademeli tipleme kabul; kritik modüllerden (`auth`, `session_state`) başlanabilir | M |

### 3. Test

**✅ Güçlü:** 22 dosya / **94 test**, CI'da koşuyor (`tests.yml`). Güvenlik-yolları **characterization-testli**: `test_session_watchdog` (süre-aşımı auto-stop), `test_api_safety`/`emergency_stop`, `test_coil_transport` (STM/ESP yönlendirme), `test_auth` (zorlama+muafiyet), `test_patient_encryption`+`test_pii_protection`+`test_kvkk_anonymization`, `test_rate_limit`, `test_treatment_persistence/retention`, `test_route_contract`+`test_status_shapes` (sözleşme).

| # | Önem | Bulgu | Dosya:satır | Endüstri beklentisi | Öneri | Efor |
|---|---|---|---|---|---|---|
| T-1 | **Medium** | Satır kapsamı **~%36** (eşik %33, ratchet) | `pyproject.toml:54-56` | Tıbbi backend için >%70 çekirdek | Kritik yollar zaten kapalı; kapsamı kademeli yükselt (ratchet mekanizması hazır) | L |
| T-2 | **High (frontend)** | En-karmaşık iki modül testsiz: `wsClient.ts` (heartbeat/backoff/half-open/1008) + `LiveDataContext` 12-case telemetri reducer (`:169-318`) | `pf/src/services/wsClient.ts`, `pf/src/context/LiveDataContext.tsx:169-318` | En yüksek-churn stateful mantık en çok testli | Reducer'ı saf-fonksiyona çıkar + her mesaj tipini test et (özellikle `emergency_stop`/`stm_coil_update`); wsClient'ı fake-timer+mock-WS ile | M |
| T-3 | **Low** | CI testleri **ubuntu**'da; ürün **Windows** (NSSM) hedefli → Windows-özgü yollar (ACL, ProgramData, serial) CI'da test edilmiyor | `.github/workflows/tests.yml:15` | Hedef-OS'te CI | Windows runner matrix eklenebilir (maliyet/fayda değerlendir) | M |

### 4. Hata Yönetimi & Dayanıklılık

**✅ Güçlü:** Global exception handler **ham traceback/str(e) sızdırmaz** + korelasyon-id + PII-scrub validation (`api_server.py:138-154`). **0 bare `except:`**, **0 stray `print()`** çalışan servis kodunda (20 print yalnız `credential_manager.py` `__main__` CLI'sinde). ~40 `except:pass` — hepsi meşru cleanup (incelendi). Bounded hardware queue (`Queue(maxsize=4)` + `put_nowait`, `headless_core.py:55`) + serial auto-reconnect. Subprocess'lerde `timeout=5-15`.

| # | Önem | Bulgu | Dosya:satır | Endüstri beklentisi | Öneri | Efor |
|---|---|---|---|---|---|---|
| E-1 | **Medium** | `history_router` **11 uçta** `raise HTTPException(500, detail=str(e))` — DB-katmanı mesajları (SQLCipher/dosya-yolu/şema) istemciye sızar; **B3 sertleştirmesi bu router'ı atlamış** | `history_router.py:74,84,108,154,175,186,202,279,333,346,356` + `update_manager.py:102,239,299` | Generic mesaj + server-side `logger.exception`+id | Ev-desenini uygula (`_ai_fail` gibi): logla + `detail="İşlem başarısız"` | S |
| E-2 | **Low** | Başarısızlıkta **HTTP 200 + `{"status":"error"}`**: unknown-command, `mqtt_unavailable` | `api_server.py:909,1009,1060` | Non-2xx + tek hata-zarfı | `502/503`/`400` + `{"detail}` standardı; mobil sözleşme kırılırsa `/api/v1` alias'ı arkasına | M |

### 5. Gözlemlenebilirlik

**✅ Güçlü:** `/api/health` (`system_router.py:105`) + **Prometheus `/metrics`** (dış-bağımlılıksız, `api_server.py:623`) + **Sentry opt-in + PII-scrub** (`utils/telemetry.py`, `backend_service.py:447`) + rotating-file-log + ayrı `crash.log` + thread-excepthook (`backend_service.py:65,134`) + opsiyonel **JSON structured log** (`PEMF_LOG_JSON`).

| # | Önem | Bulgu | Dosya:satır | Endüstri beklentisi | Öneri | Efor |
|---|---|---|---|---|---|---|
| O-1 | **Low** | Normal yolda **request-correlation-id yok** (`error_id` yalnız 500'lerde); `access_log=False` | `api_server.py:140`, `backend_service.py:368` | Her istekte `X-Request-ID` (kabul/üret + log + echo) | Küçük contextvar middleware; 7/24 saha-cihazında debug değeri yüksek | S |

### 6. Performans & Ölçeklenebilirlik

**✅ Güçlü:** Hot hardware yolları `to_thread` (28 kullanım); `emergency_stop` doğru threadli (`api_server.py:1803`). Keyset pagination + SQL-agregasyon (RAM-patlaması yok). Bounded HW queue.

| # | Önem | Bulgu | Dosya:satır | Endüstri beklentisi | Öneri | Efor |
|---|---|---|---|---|---|---|
| P-1 | **Medium** | `async def` uçlarda senkron DB/MQTT → **event-loop bloke**: `stop_session`→`_stop_session_coils` senkron `_mqtt_publish` (~2s/ESP-bobin) `:1654`; `start_session` inline SQLCipher `:1150-1178`; `get_kpi_summary` tam-tablo agregasyon `:193-255`; `patient_router`/`session_router` senkron `db.*` | `api_server.py:1632-1654,1066`, `system_router.py:169`, `patient_router.py:31-74` | Event-loop'ta blocking-I/O yok | `to_thread`'e sar VEYA `async`→`def` (Starlette threadpool'lar) — en düşük-risk fix | M |
| P-2 | **Medium** | WS broadcast **tek-kilit + timeout'suz** seri gönderim → bir yavaş istemci tüm telemetriyi bloklar | `live_state.py:46-74` (`_send_all`) | Per-client bounded queue veya `wait_for(send, timeout)`+drop | Her `send_text`'i `asyncio.wait_for(...,5s)` + timeout'ta istemciyi düşür | M |
| P-3 | **Low (kabul-risk — TASARIM)** | Modül-global mutable state (`_live_state`, `_active_session`, `_ai_models`, `_rl_hits`) → **yatay ölçeklenemez** | `live_state.py`, `session_state.py`, `ai_router.py` | Stateless / paylaşımlı-store | Servis **tek fiziksel donanıma bağlı** (STM serial, `VideoCapture(0)`, localhost MQTT) → yatay-ölçek uygulanamaz; doğru hikaye tek-instance HA (crash-handler+startup-reconcile var). Kabul | — |

### 7. Veri & Veritabanı

**✅ Güçlü (endüstri-üstü):** **~171 SQL sitesi parametreli — injection YOK** (dinamik parçalar yalnız whitelist/literal identifier: `_ENCRYPTED_FIELDS` filtresi `patient_database.py:484`). Thread-local connection pooling + WAL + `busy_timeout=5000` + `foreign_keys=ON` (`treatment_history_db.py:285-297`). **Şifreleme fail-closed** (`PEMF_ENCRYPT_AT_REST=1`+eksik-key ⇒ RuntimeError, DB açılmaz, `:269-274`) + plaintext-dev'de PII-maskeleme. Kapsamlı index'ler (query-pattern eşleşen). **Otomatik şifreli yedek/24h + 14-rotasyon + retention + KVKK anonimleştirme** (`services/headless_db_maintenance.py`). N+1-yok (11-JOIN pivot + keyset).

| # | Önem | Bulgu | Dosya:satır | Endüstri beklentisi | Öneri | Efor |
|---|---|---|---|---|---|---|
| D-1 | **Medium** | `INSERT OR REPLACE` **subset-kolon** → cloud-pull'da `owner_email`/`last_treatment_at`/`anonymized` sıfırlanır + FK-cascade `patient_search_index`'i siler (hasta aranamaz olur). **`PEMF_CLOUD_PATIENT_SYNC=1` gated (varsayılan KAPALI) → latent** | `sync_worker.py:172-183,240-251` | `ON CONFLICT(id) DO UPDATE SET` yalnız-değişen-kolon | Upsert'i kolon-tam yap + `_refresh_search_index_for_patient()` çağır. **Cloud-sync açılmadan önce düzelt** | M |
| D-2 | **Low-Medium** | Şema migration **ad-hoc**: `TARGET_SCHEMA_VERSION=3` kozmetik; v1→v2→v3 dönüşüm-scripti yok; her açılışta `CREATE IF NOT EXISTS`+idempotent-ALTER. (İyi: `_run_startup_migrations_with_rollback` tam-yedek+rollback var) | `treatment_history_db.py:38,768-803,725-766` | Alembic (sıralı, geri-alınabilir revision) | Ya gerçek stepwise-migration ya da "idempotent additive + backup/rollback" olarak belgele | L / (belgele=S) |
| D-3 | **Low** | Çift SQLCipher-key çözüm-yolu: `treatment_history_db._get_sqlcipher_key` SecretsManager'ı **bypass** eder (keyring→env→file) | `treatment_history_db.py:92-138` vs `sqlcipher_util.py:45-53` | Tek key-çözüm kaynağı | `treatment_history_db`, `sqlcipher_util.get_sqlcipher_key()` çağırsın (worst-case fail-closed, sessiz-plaintext değil) | S |
| D-4 | **Low** | `session_coil_runs.session_id` + `sensor_run_summary.coil_run_id`'de **FK deklarasyonu yok** (diğer child-tablolar var) | `treatment_history_db.py:622-651` | Tüm child'da FK | Yeni-DB'lerde FK ekle (SQLite ALTER-FK yok → mevcut DB manuel-cleanup'la; `delete_session` zaten temizliyor) | S |

### 8. API Tasarımı

**✅ Güçlü:** **API versiyonlama** (`/api/v1/*`→`/api/*` rewrite, `api_server.py:164-168`, `test_api_design`'da testli). OpenAPI/Swagger **auth/tünel açıkken kapatılıyor** (`:70-75`, `PEMF_ENABLE_DOCS`). Pagination: history **keyset/cursor** (`history_router.py:62`), patients limit/offset, CSV export 10000-bounded, AI-log limit-bounded. Tutarlı `{"detail"}` hata (FastAPI).

| # | Önem | Bulgu | Dosya:satır | Endüstri beklentisi | Öneri | Efor |
|---|---|---|---|---|---|---|
| API-1 | **Low** | İki farklı hata-şeması: çoğu uç `{"detail}` ama bazıları `200 {"status":"error"}` (bkz E-2) → istemci HTTP-status'e güvenemez | `api_server.py:909,1009,1060` | Tek hata-zarfı + doğru status | E-2 ile birlikte standardize | M |

### 9. DevOps / CI-CD / Altyapı

**✅ Güçlü:** 4 CI workflow — `lint.yml` (Ruff F+E9), `security.yml` (pip-audit haftalık), `tests.yml` (94 test + coverage), `dependabot.yml` (haftalık pip+actions, security-grouped, AI-core major-ignore). `.env.example` (44 satır) + 3 dağıtım profili (`deploy/{device,server,staging}.env`) + `setup_services.ps1` (NSSM, mod-seçimli).

| # | Önem | Bulgu | Dosya:satır | Endüstri beklentisi | Öneri | Efor |
|---|---|---|---|---|---|---|
| DO-1 | **Medium** | **Docker YOK** — dağıtım PyInstaller onedir + NSSM (Windows-native) | (yok) | Containerize / IaC | Ürün Windows-donanım-bağlı cihaz → Docker uygulanamaz (device); **server/demo profili** için opsiyonel Docker değerlendirilebilir | M |
| DO-2 | **Medium** | Build/deploy **CI-YOK** — EXE/APK/installer **elle/yerel** üretiliyor; `build_installer.ps1` stale (eski spec-adı) | `build_tools/` | Tag→otomatik-build+release | GitHub Actions Windows-runner ile onedir+installer build; en azından tag→APK. (Not: bu oturumda doğrudan-ISCC yolu belgelendi) | L |
| DO-3 | **Low** | `security.yml` **bloklamıyor** (`continue-on-error`) — bilinen pinli AI-CVE'ler (onnx/torch) kasıtlı-ertelenmiş | `.github/workflows/security.yml:38` | Güvenlik-CI bloklar | **Bilinçli** (AI-uyumluluk pin'i); web/crypto CVE'leri zaten yamalı. Kabul; yorumu güncelle (stale: 41.0.3 yazıyor, gerçek 43.0.1) | S |

### 10. Frontend (Expo / React Web + Mobil)

**✅ Güçlü:** Ağ katmanı — `apiClient.ts` 8s AbortController-timeout, idempotent-GET tek-retry (POST asla), X-API-Key, error-normalize, `silent`-poll (testli). `wsClient.ts` 15s heartbeat+25s half-open+1.5×backoff+1008-auth. **Tri-state** error/empty/loading (`apiGet(path,null)` sentinel) + live/stale/offline banner (donmuş-telemetriyi "canlı" göstermez — terapi cihazı için kritik). Code-splitting `lazy()` 8 ekran + per-route ErrorBoundary. `tsconfig strict:true` + SecureStore token.

| # | Önem | Bulgu | Dosya:satır | Endüstri beklentisi | Öneri | Efor |
|---|---|---|---|---|---|---|
| F-1 | **High** | **a11y zayıf** (tüketici APK): ~182 etkileşimli öğe ama yalnız 31 `accessibilityLabel`/16 `accessibilityRole`/**0 `accessibilityState`**. `WelcomeScreen`+`DashboardScreen` sıfır-a11y; `NavButton` aktif-sekmeyi ekran-okuyucuya bildirmiyor | `pf/src/components/ui/AppShell.tsx:263-278`, `WelcomeScreen.tsx:21,33` | Her kontrol role+label; stateful'da `accessibilityState` (WCAG 4.1.2) | `accessibilityState={{selected}}` NavButton'a; label WelcomeScreen/AiHubScreen inputlarına | M |
| F-2 | **High** | Karmaşık modüller testsiz (bkz T-2) | `pf/src/services/wsClient.ts`, `LiveDataContext.tsx:169-318` | — | Reducer saf-fn + test | M |
| F-3 | **Medium** | **`React.memo` = 0** → her WS-tick'te statik alt-ağaç re-reconcile: `SensorMonitorScreen` 8 kart + chart, `KpiDashboardScreen` chart-kit (mount'ta çekilen KPI'ı her tick render) | `pf/src/screens/SensorMonitorScreen.tsx:120-140`, `KpiDashboardScreen.tsx:25` | Saf-leaf memoize + `useMemo` chart-data | `React.memo(CoilStatCard)` + KPI chart wrapper; davranış-nötr | S |
| F-4 | **Medium** | Renk-tek-başına durum (WCAG 1.4.1): "canlı" yeşil-nokta metin-siz; coil/axis chip'ler yalnız renk | `AppShell.tsx:158-168`, `SensorMonitorScreen.tsx:64-99` | İkon/metin + `accessibilityState` | Aktif chip'e "✓"/"Canlı" + state | S |
| F-5 | **Low** | Web `lang="en"` ama UI %100 Türkçe; favicon/description yok | `pf/dist/index.html` (Expo default) | `lang` içerikle eşleşmeli | `app/+html.tsx` → `lang="tr"` + favicon | S |
| F-6 | **Low** | Hata için bloklayan `window.alert` (Toast sistemi varken) | `pf/src/services/apiClient.ts:5-11,62,98` | Non-blocking toast | `showError`→`useToast`; native-Alert yalnız yıkıcı-onayda | M |
| F-7 | **Low** | ErrorBoundary crash'i yutuyor (yalnız `console.error`, raporlama yok) | `pf/src/components/ui/ErrorBoundary.tsx:19-21` | Log-sink'e raporla | `componentStack`'i backend `/api/log`'a fire-and-forget POST | S |

### 11. Dokümantasyon

**✅ Güçlü (çoğu projeden iyi):** `README.md` (210 satır, kurulum/build/deploy) + `docs/ARCHITECTURE.md` + `docs/RUNBOOK.md` (ops runbook!) + `docs/VERIFICATION.md` + `.env.example` (tüm PEMF_* belgeli) + `deploy/README.md` (95 satır, reverse-proxy/TLS/cloudflared adımları).

| # | Önem | Bulgu | Dosya:satır | Endüstri beklentisi | Öneri | Efor |
|---|---|---|---|---|---|---|
| DOC-1 | **Low** | README `kökteki DEPLOYMENT.md`'ye işaret ediyor ama **dosya YOK** | `README.md:128` | Kırık-referans olmamalı | `DEPLOYMENT.md` oluştur ya da referansı `deploy/README.md`'ye çevir | S |

---

## 4. Öncelikli Yol Haritası

### 🔴 Production'a çıkmadan önce MUTLAKA (Critical/High)
1. **E-1 — `history_router` `str(e)` sızıntısını kes** (11 uç + update_manager 3) — bilgi-ifşası, ev-deseni hazır. **[S]**
2. **S-1 — Klasik güvenlik header'ları ekle** (nosniff/frame/HSTS/referrer) — tarayıcı yüzeyi. **[S]**
3. **S-2 — Prod'da CORS daralt + auth zorla** — `deploy/server.env`/`device.env` profillerinin uygulandığını doğrula (`PEMF_REQUIRE_AUTH=1`, `PEMF_CORS_ORIGINS=<origin>`, `PEMF_ENCRYPT_AT_REST=1`). **[S]**
4. **S-4 — Auth-muaf AI-tedavi kararını yazılı onayla** — sahip riski kabul etti; prod-checklist'e "kabul edilmiş risk" olarak imzalat (tıbbi-cihaz denetim izi). **[S]**
5. **F-1/F-2 (tüketici APK ise) — a11y temel + karmaşık-modül testleri** — kamuya açık "hayvan sahibi" app için. Yalnız-klinik-LAN ise Orta'ya iner. **[M]**

### ⚡ Hızlı Kazanımlar (Quick Wins — düşük efor, net değer)
- **F-3 — `React.memo(CoilStatCard)` + KPI chart `useMemo`** (telemetri re-render, davranış-nötr) **[S]**
- **O-1 — request-correlation-id middleware** (7/24 saha debug) **[S]**
- **D-3 — SQLCipher key-yolunu tekleştir** **[S]**
- **F-5 — web `lang="tr"` + favicon** **[S]**
- **DOC-1 — `DEPLOYMENT.md` oluştur / referansı düzelt** + **DO-3 — `security.yml` stale-yorumu güncelle** **[S]**
- **F-7 — ErrorBoundary'yi backend log'a raporla** **[S]**

### 🟡 Orta Vadeli İyileştirmeler
- **P-1 — `async` uçlardaki senkron DB/MQTT'yi `to_thread`/`def`'e taşı** (event-loop bloke) **[M]**
- **P-2 — WS broadcast'e per-send timeout + yavaş-istemci-düşür** **[M]**
- **T-1/T-2 — kapsamı kademeli yükselt** (özellikle wsClient + telemetri reducer) **[M-L]**
- **E-2/API-1 — başarısızlıkta doğru HTTP-status + tek hata-zarfı** (mobil-sözleşme dikkat) **[M]**
- **D-1 — cloud-sync upsert'i kolon-tam yap** (`PEMF_CLOUD_PATIENT_SYNC` açılmadan önce) **[M]**
- **A-1 — `treatment_history_db.py` (2338) repository-katmanına böl** · **A-2 — Ruff kademe-1 (`B`+`I`)** **[L/M]**
- **DO-2 — build/deploy CI** (tag→APK/installer, Windows-runner) **[L]**

---

## 5. Doğrulayamadıklarım (manuel kontrol gerek)
- **Supabase RLS + anon-dump politikası** — publishable key gömülü; güvenlik server-side RLS'e bağlı, bu **Supabase konsol** tarafında (kodda görünmez). RLS'in `devices` tablosuna kilitli + anon-select-kapalı olduğunu doğrula. **(S-5)**
- **Runtime davranışı** — bu rapor **statik** okuma; `PEMF_SIMULATE=1` altında testler yeşil (94) ama gerçek-donanım (STM serial, ESP MQTT, kamera) yol-uçları çalıştırılarak doğrulanmadı.
- **Yük/stres** — WS broadcast (P-2) ve async-blok (P-1) etkileri **yük altında ölçülmedi**; tek-operatör senaryosunda sorun görünmüyor, çok-istemci polling'de test edilmeli.
- **Prod `.env` değerleri** — `deploy/*.env` **profilleri** doğru; ama gerçek dağıtımda uygulanan değerler (auth=1, CORS, encrypt=1, sqlcipher3-wheel kurulu) cihaz-üstünde teyit edilmeli.
- **SQLCipher fiili şifreleme** — kod fail-closed; ama üretim cihazında `sqlcipher3` wheel'in kurulu + `PEMF_ENCRYPT_AT_REST=1` olduğu (yani `atRestEncrypted:true`) çalışan servis `/api/health`'ten doğrulanmalı. *(Bu oturumda frozen-EXE smoke-test'te `atRestEncrypted:true` görüldü — iyi işaret.)*
- **CI'nın gerçekten yeşil olduğu** — workflow'lar tanımlı; son koşuların yeşil olduğu GitHub Actions'tan teyit edilmeli.

---

### Kapanış
Bu kod tabanı, tek-cihaz tıbbi kullanım için **çıkmaya yakın** — güvenlik/veri/gözlemlenebilirlik temelleri sağlam ve önceki denetimlerle sertleştirilmiş. Kalan iş, **Critical değil**; yukarıdaki 🔴 listesi (çoğu **S**-efor) tamamlanıp prod-profilleri uygulandığında amaçlanan dağıtım için üretime-hazır sayılabilir. Genişleme (çok-cihaz/multi-tenant) hedeflenirse P-3 (tek-instance) ve build/deploy-CI (DO-2) mimari yatırım gerektirir.
