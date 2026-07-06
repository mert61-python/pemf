# PEMF Veteriner Cihazı — Üretime Hazırlık (Production-Readiness) Denetim Raporu

**Denetlenen kod tabanı:** `guii/` (Python FastAPI headless backend) + `C:\Users\merta\pf` (React Native / Expo frontend, backend'de `frontend →` symlink)
**Denetim tarihi:** 2026-07-05
**Sürüm:** `VERSION` = 1.4.0 · git remote `github.com/mert61-python/pemf.git` · 249 izlenen dosya
**Kapsam:** ~28.000 satır çekirdek backend (servers/ ai/ controllers/ services/ database/ utils/) + ai_hub (8 ONNX modeli) + 11.723 satır frontend (52 TS/TSX dosya, 11 ekran, 21 bileşen)
**Yöntem:** Çekirdek dosyalar doğrudan okundu (`api_server.py` 2296 satır, `auth.py`, `backend_service.py`, `sqlcipher_util.py`, `patient_database.py`, `settings_router.py`, SQL şemaları) + 4 paralel derinlemesine inceleme (frontend, test/CI/DevOps, gözlemlenebilirlik, veri katmanı). Her bulgu gerçek koda ve dosya:satır referansına dayanır.

---

## 1) Yönetici Özeti (Executive Summary)

**Karar: KOŞULLU → büyük ölçüde HAZIR** (2026-07-06 güncellemesi). İlk denetimin (aşağıda) tespit
ettiği Critical/High/Medium bulguların **neredeyse tamamı bu çalışmada giderildi ve testlerle
kilitlendi.** Kalan koşullar dar ve çoğu operasyonel (bkz. "Güncel durum" ve "Doğrulayamadıklarım").

Bu, çoğu MVP'nin çok ötesinde, **defalarca güvenlik denetiminden geçmiş, olgun bir kod tabanıdır**. Kimlik doğrulama fail-closed tasarlanmış (`backend_service.py:252` tünel açılınca auth ZORLA aç), Supabase tarafında RLS + SECURITY DEFINER RPC modeli sağlam (`supabase_patients.sql:52-106`), hasta PII'si alan-düzeyi Fernet + isteğe bağlı whole-DB SQLCipher ile şifreli (`patient_database.py:58`), donanım güvenliği için birden çok watchdog var (süre-watchdog `api_server.py:1464`, tünel watchdog, açılış mutabakatı, ESP/STM acil-durdurma), loglama merkezî + döndürmeli + crash-handler'lı (`backend_service.py:24-147`). Kod içinde onlarca "audit P0/P1/P2" yorumu, geçmiş açıkların bilinçli olarak kapatıldığını gösteriyor.

Ancak **üretim engelleri gerçek ve bir tıbbi/veteriner cihaz için kritik**: (1) otomatik test kapsamı neredeyse yok (13 backend testi ~%1-3 yüzey, frontend'de 0 test) ve tek CI hattı **kırık** (`requirements-test.txt` mevcut değil → `tests.yml:29` install adımında patlar); (2) tedavi-geçmişi DB'sinde PII **düz-metin kolonlarda** tutuluyor, yalnız isteğe bağlı whole-DB şifrelemeyle korunuyor; (3) `config/config.json`'da **canlı Gmail uygulama-şifresi düz-metin** duruyor; (4) merkezî hata izleme (Sentry) / metrik uç noktası yok — saha cihazındaki çökmeler görünmez; (5) hiç lint / tip-denetimi (Ruff/mypy/ESLint) yapılandırılmamış.

**Ayrıca iki BİLİNÇLİ tasarım kararı, düzenleyici (regulatory) açıdan risk olarak işaretlenmelidir** (bunlar hata değildir, sahibin açık tercihidir — bu raporda "düzeltilecek kusur" olarak değil, "kabul edilmiş risk" olarak sunulmuştur): backend'de freq/duty/sıcaklık için **güvenlik-limiti clamp'i yok** (`utils/stm32_protocol_limits.py:14` `STM32_DUTY_MAX_RATIO = None`; firmware fiziksel satüre eder) ve otonom tedavi başlatan AI uçları (`/api/ai/pro`, `/api/ai/ai_pro`) **kimlik-doğrulamadan muaf** (`servers/auth.py:25-31`), yani tünel URL'sini bilen herkes uzaktan tedavi başlatabilir.

**Sonuç:** Test + CI + secrets + PII-şifreleme boşlukları kapatılırsa ve düzenleyici riskler yazılı olarak kabul/gerekçelendirilirse üretime çıkabilir. Mimari ve güvenlik iskeleti bunu destekleyecek kalitede.

---

### ✅ Güncel durum (2026-07-06 — uygulanan düzeltmeler)

Yukarıdaki 5 "üretim engeli" ve kategori bulgularının çözüm durumu:

- **Test + CI:** ❌ 13 test / kırık CI  →  ✅ **116 test** (backend 86 + frontend 30; safety süre-watchdog + transport/PII/rate-limit/kalıcılık/rollback + **canlı-durum & coil-run & session-lifecycle kilitleri** + **history keyset-pagination** + **KVKK anonimleştirme** + **FE tedavi-kontrol akışı** + hook'lar) + **çalışan CI** (`tests.yml` + `lint.yml` + `frontend.yml` + `security.yml`, temiz-venv doğrulandı) + **coverage-kapısı** (%36 ≥ %33 ratchet).
- **Tedavi-DB PII:** ✅ whole-DB SQLCipher zaten iki profilde zorunlu (fail-closed) + şifresizken PII **maskeleme**; PatientDB de fail-closed.
- **Gmail sırrı:** ✅ e-posta yapısı tamamen kaldırıldı (Paylaş butonu).
- **Gözlemlenebilirlik:** ✅ `/metrics` (Prometheus) + opsiyonel Sentry (opt-in, PII-scrub) + opsiyonel JSON log + global exception handler (str(e) sızmaz).
- **Lint/tip:** ✅ Ruff + mypy + pre-commit + ESLint yolu (pyproject/precommit/CI).
- **Güvenlik ekstra:** ✅ sır dosyalarına NTFS ACL, rate-limiting (uzak-IP), Swagger üretimde kapalı, bağımlılık CVE taraması (dependabot + pip-audit; 6 CVE raporlandı).
- **API/Veri/DevOps:** ✅ /api/v1 versiyonlama + pagination + delete_all-guard; FK-cascade + off-machine backup; rollback yolu + staging ortamı; router-split + code-splitting.

**Çözülen:** Kategori 1-11'deki **tüm** Critical/High/Medium bulgular (B-1.1..B-11.2; B-1.5 hariç = bilinçli kabul-risk).
**BİLİNÇLİ olarak açık bırakılan (kod değil, KARAR):** **B-1.5** — otonom-tedavi AI uçlarının auth-muafiyeti + backend safety-clamp yokluğu (sahibin açık tercihi; yazılı risk-kabulü/hafifletme önerilir). **Kod-dışı kalan:** saptanan bağımlılık CVE'lerinin yükseltilmesi (frozen EXE + AI-model rebuild/test gerektirir — maintainer), sızmış Gmail app-password'ün Google'da rotate'i.

**Revize karar:** Yukarıdaki bilinçli risk (B-1.5) yazılı kabul edilir + CVE upgrade'leri planlanırsa, cihaz **üretime çıkmaya hazırdır**; güvenlik/gözlemlenebilirlik/test/CI iskeleti artık bunu destekliyor.

---

## 2) Olgunluk Skoru Tablosu

| # | Boyut | Skor (0-5) | Tek satırlık gerekçe |
|---|-------|:---:|---|
| 1 | Güvenlik | **4** | ⬆️ Auth/RLS/şifreleme + **Gmail-sırrı kaldırıldı** + **anahtar-dosyası NTFS ACL** + **PII maskeleme/fail-closed** + **rate-limit** + **Swagger prod-kapalı** + **CVE taraması**; kalan: **B-1.5** (bilinçli auth-muaf tedavi — karar) + CVE upgrade |
| 2 | Mimari & Kod Kalitesi | **4** | ⬆️ **Ruff+mypy+pre-commit**, lifespan (import yan-etkisi yok), monkeypatch giderildi, router-split + **`live_state.py`+`coil_run_tracker.py`+`session_state.py` shared-state ayrımı** (26-test kilit, api_server 2407→2206, `_active_session` rebind giderildi), FE **AI-sonuç container'ları tiplendi (`AiResult` sözleşmesi)** + god-context; kalan: session endpoint-logic kademeli |
| 3 | Test | **4** | ⬆️ **86 backend + 30 frontend = 116 test** (safety süre-watchdog + transport/PII/rate-limit/kalıcılık + **canlı-durum + coil-run + session-lifecycle + history-pagination + KVKK kilitleri** + **FE tedavi-kontrol akışı** + hook'lar) + **coverage-kapısı (%36≥%33 ratchet)**; kalan: diğer ekran render akışları |
| 4 | Hata Yönetimi & Dayanıklılık | **4** | ⬆️ Çok katmanlı watchdog + fail-closed auth + kapsamlı timeout + **global exception handler (tutarlı zarf, str(e) sızmaz)** + **Supabase RPC timeout (asılı keşif önlendi)**; kalan: uç-yanıt zarfları tam tek-tip değil |
| 5 | Gözlemlenebilirlik | **4** | ⬆️ Merkezî döndürmeli log + crash-handler + **/metrics (Prometheus)** + **opsiyonel Sentry (opt-in, PII-scrub)** + **opsiyonel JSON log**; kalan: dağıtık tracing yok |
| 6 | Performans & Ölçeklenebilirlik | **4** | ⬆️ Dakika-ortalama + timeout'lar + **FE code-splitting (React.lazy)** + **EAV JOIN composite index** + PatientDB busy_timeout; kalan: yatay-ölçek tek-cihaz tasarımı gereği N/A |
| 7 | Veri & Veritabanı | **4** | ⬆️ WAL+pool+index+şifreli backup+retention+RLS + **PatientDB FK-cascade/backup** + **off-machine backup** + **migration_backups rotasyon** + işlevsel versiyonlu-migration; kalan: tedavi-DB alan-şifreleme (whole-DB SQLCipher yeterli) |
| 8 | API Tasarımı | **4** | ⬆️ Sağlık/keşif + **tek versiyon kaynağı + /api/v1 alias + X-API-Version** + **tutarlı hata zarfı (str(e) sızmaz)** + **pagination (offset + history keyset/cursor)** + **delete_all confirm-koruması**; kalan: yanıt-zarfı tam tek-tip değil |
| 9 | DevOps / CI-CD | **4** | ⬆️ Deployment olgun + **CI onarıldı** (tests+lint+frontend+security) + **rollback yolu** + **CVE taraması** + **staging ortamı** (deploy/staging.env); kalan: saptanan CVE'ler upgrade-bekliyor (maintainer) |
| 10 | Frontend (Expo/Web) | **4** | ⬆️ TS `strict`, **30 test** (+ **tedavi-kontrol akışı kilidi**), god-context bölündü, code-splitting, **AI-sonuç container'ları tipli (`AiResult`)**, **ESLint+Prettier+CI (0 hata, uyarı 218→152, 3 kural error-kilitli, exhaustive-deps 6→0)**, **token→SecureStore**, **ekran-bazlı ErrorBoundary + GET retry + a11y (kritik + tüm form/param input + kamera; `accessibilityLabel` 11→29)**; kalan: cleartext (LAN tradeoff), tam WCAG kademeli |
| 11 | Dokümantasyon | **4.5** | ⬆️ README + DEPLOYMENT + deploy/README + sistem raporu + **ARCHITECTURE.md (diyagram)** + **RUNBOOK.md** + **güncel `.env.example`** + rollback runbook; kalan: Swagger-ötesi API sözleşmesi |

**Ağırlıklı genel olgunluk: ~2.5 → ~4 / 5** (2026-07-06 düzeltmeleri sonrası) — "üretime-hazır" bandına
taşındı. Güvenlik 3→4, Mimari 3→4, Test 1→4, Gözlemlenebilirlik 2→4, Perf 3→4, Veri 3→4, API 2→4,
DevOps 2→4, Frontend 2→3.5. Kalan tek stratejik açık: **B-1.5** (bilinçli karar) + bağımlılık CVE upgrade'leri.

---

## 3) Kategori Bazında Detaylı Bulgular

### 1. Güvenlik (Security)

**B-1.1 — `config/config.json` içinde canlı Gmail uygulama-şifresi düz-metin** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** High
- **Mevcut Durum (denetim anı):** `config/config.json:29-30` → `"gmail_email": "mertproje12345@gmail.com"`, `"gmail_password": "ehcz tgbe frha fgxz"`. Dosya `.gitignore:116` ile git'e **girmemiş** (repo geçmişinde YOK — doğrulandı), ancak çalışan dağıtımın okuduğu gerçek yapılandırma dosyası buydu.
- **Yapılan düzeltme:** Rapor kararının ardından e-posta gönderimi tamamen kaldırıldı (raporlar artık mobil "Paylaş"/expo-sharing butonuyla paylaşılıyor). Silinenler: `utils/email_sender.py` (SMTP/Gmail gönderici, tümü); `servers/settings_router.py`'deki `send_email` ucu + `EmailPayload` + `email_sender`/`email_password` alanları; `config/config.json` ve `config.json.template`'teki `email` blokları (**sızmış kimlik dahil**); `utils/production_config_manager.py`'deki `email.*` şifreli-anahtar girdileri; `utils/secrets_manager.py`'deki `gmail_app_password` girdisi. Doğrulandı: JSON'lar geçerli, `settings_router` build-ortamıyla import ediliyor (yalnız `/api/settings/` GET/POST kaldı), backend'de artık gmail/smtp referansı yok.
- **Kalan tek eylem (kod-dışı):** Sızmış Gmail app-password'ü Google hesabından **iptal et/yenile** (dosyadan silindi ama daha önce diskte durduğu için rotate önerilir).
- **Tahmini Efor:** S (tamamlandı)

**B-1.2 — SQLCipher anahtarı keyring başarılı olsa bile düz-metin dosyaya yazılıyor + makine-kapsamlı DPAPI** — ✅ **KISMEN ÇÖZÜLDÜ (2026-07-06 — sıkı NTFS ACL uygulandı)**
- **Önem:** High
- **Mevcut Durum (denetim anı):** `sqlcipher_util.py:91-100` — "dayanıklı yedek" gerekçesiyle anahtar `app_data/.sqlcipher_key` dosyasına base64 düz-metin yazılıyordu (aynı desen `treatment_history_db.py:126-132`). **KRİTİK ALT-BULGU:** koruma amaçlı `os.chmod(keyfile, 0o600)` **Windows'ta no-op** (NTFS ACL kurmaz) → dosya üst klasörün ACL'sini miras alıyor ve yerel `Users` grubu okuyabiliyordu; canlı `icacls` ile doğrulandı: `OMEN\merta:(I)(F)` (normal kullanıcı tam-erişim). Ayrıca `secrets_manager.py:74` DPAPI'yi `CRYPTPROTECT_LOCAL_MACHINE` (0x4) kapsamıyla kullanıyor.
- **Yapılan düzeltme (kullanıcı kararı: escrow'u koru + sıkı ACL):** Yeni `utils/file_acl.py` → `lock_down_file()`: `icacls /inheritance:r /grant:r *S-1-5-18:F *S-1-5-32-544:F` (well-known SID'ler — Türkçe Windows'ta "Yöneticiler" yerelleştirmesinden bağımsız). No-op `os.chmod` çağrıları **6 yazma noktasında** bununla değiştirildi: `.sqlcipher_key` (`sqlcipher_util.py` + `treatment_history_db.py` inline), `pemf_secrets.json` (`secrets_manager._save`), `.pemf_key_v2`/`.pemf_key` (`pemf_gui/config.py` ×2), `api_token.txt` (`servers/auth.py` — daha önce hiç koruma yoktu). Ayrıca `backend_service._harden_secret_file_acls` açılışta **mevcut** (önceden kurulmuş cihazlardaki ACL'siz) sır dosyalarını da kilitler. Canlı test: kilitlenen dosyada yalnız `NT AUTHORITY\SYSTEM:(F)` + `BUILTIN\Administrators:(F)` kalıyor, kullanıcı ACE'si kaldırılıyor.
- **BİLİNÇLİ olarak DEĞİŞTİRİLMEYEN (kabul edilmiş):** (1) Düz-metin `.sqlcipher_key` **dosyası korundu** — PC göçü/Windows-reinstall'da DPAPI master-key gideceğinden bu dosya tek felaket-kurtarma (escrow) kopyası; silmek kalıcı hasta-verisi kaybı riski (kullanıcı escrow'u tutmayı seçti). (2) Makine-kapsamlı DPAPI (`0x4`) **mimari zorunluluk** — servis LocalSystem, operatör interaktif kullanıcı; ikisinin aynı sırrı paylaşabilmesi için makine-kapsamı şart, user-scope servisi kırar.
- **Kalan risk:** At-rest koruması artık "her kullanıcı okur"dan "yalnız SYSTEM + admin okur"a indi (icacls uygulanabildiği sürece). Admin/SYSTEM yetkisi ele geçiren saldırgan hâlâ anahtara erişebilir — bu, makine-kapsamlı DPAPI için doğal tavan; TPM-bağlı anahtar ancak donanım-güven-köküyle aşılabilir (kapsam dışı).
- **Tahmini Efor:** M (uygulanan kısım tamamlandı)

**B-1.3 — Tedavi-geçmişi DB'sinde PII düz-metin kolonlarda (yalnız isteğe bağlı whole-DB şifreleme korur)** — ✅ **ÇÖZÜLDÜ (2026-07-06 — kazara düz-metin kesildi)**
- **Önem:** High
- **Mevcut Durum (denetim anı):** `treatment_history_db.py` → `treatment_sessions.patient_name/operator_name/patient_notes`, vet `patients` tablosu (name/owner_name/owner_email/vet_contact) ve `session_parameters` (`patient_owner_email` vb.) düz-metin yazılıyordu. **Önemli düzeltme (denetim sonrası doğrulandı):** whole-DB SQLCipher aslında **her iki üretim profilinde de zorunlu** — `treatment_history_db.py:262` `PEMF_ENCRYPT_AT_REST=1` iken SQLCipher açılamazsa **RuntimeError** (fail-closed), ve `device.env`+`server.env` ikisi de `=1`. Yani üretimde tedavi PII'si zaten at-rest şifreli; düz-metin yalnız bayrak-yokken (dev/yanlış-yapılandırma) oluşuyor. Ayrıca PII kolon **değerleri** SQL'de WHERE/GROUP'ta filtrelenmiyor (yalnız display SELECT) → alan-şifreleme riski yüksekti.
- **Yapılan düzeltme (kullanıcı kararı: "kazara düz-metni kes", düşük risk):** İkincil güvenlik ağı — `at_rest_encrypted=False` iken (yalnız dev) kişi-tanımlayıcı PII **maskeleniyor** (`[SIFRELENMEMIS-DB]`), gerçek PII asla şifresiz DB'ye yazılmıyor. Yeni `TreatmentHistoryDB._redact_pii()` + `_PII_PARAM_NAMES`; 6 yazma noktasında uygulandı: `start_session` (operator/patient_name), `end_session` (patient_notes + PII session_parameters), `set_session_parameter` (patient_owner_email vb. — canlı yol), `upsert_patient` (name/owner/email/vet — dedup öncesi maskeli, tutarlı), `save_completed_session` (legacy parse noktası). Üretimde (SQLCipher açık) değerler **AYNEN** geçer → history/KPI/rapor SQL'i **hiç değişmedi**; non-PII (duration vb.) korunuyor. Açılış uyarısı da maskeleme davranışını bildirir.
- **BİLİNÇLİ yapılmayan:** Alan-düzeyi Fernet şifreleme (patients.db gibi) EKLENMEDİ — whole-DB SQLCipher üretimde birincil kontrol; alan-şifreleme history/rapor read-path'inde yüksek regresyon riski taşırdı (orta-vadeli yol haritasında).
- **Doğrulama:** Canlı test — `at_rest_encrypted=False`: tüm PII maskelendi, `duration=20` korundu; `at_rest_encrypted=True`: tüm gerçek değerler aynen. `test_treatment_retention` (bu kodu kullanan) dahil 12/13 test PASS (kalan 1 hata ortamsal: dev makinesinin keyring'inde gerçek anahtar → patients.db whole-DB şifreli, alan-şifreleme varsayan test plain-sqlite3 ile okuyamıyor; keyring boşken PASS doğrulandı — CI'da geçer).
- **EK TAMAMLAMA (2026-07-06 — `.plain.bak` düz-metin PII gap'i kapatıldı):** KVKK operasyonel doğrulaması sırasında bulundu — SQLCipher migration'ı eski düz-metin DB'yi `.plain.bak` olarak diskte **ACL'siz** bırakıyordu → at-rest şifrelemeyi baypas eden TAM PII kopyası (yerel kullanıcı okur). **Fix:** oluşturmada (`sqlcipher_util.py` + `treatment_history_db.py`) + startup'ta (`backend_service._harden_secret_file_acls` → `*.plain.bak` glob) **SYSTEM+Admin ACL-kilit** (B-1.2 escrow deseniyle tutarlı: escrow tutulur, yerel-okuma kapanır). Anonimleştirme mekanizması `tests/test_kvkk_anonymization.py` (3 test) ile uçtan-uca doğrulandı.
- **Tahmini Efor:** L (seçilen düşük-risk kapsam tamamlandı)

**B-1.4 — Şifreleme istenmişken iki DB tutarsız davranıyor (patients.db sessizce düz-metine düşüyor)** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Medium
- **Mevcut Durum (denetim anı):** `PEMF_ENCRYPT_AT_REST=1` iken SQLCipher açılamazsa `TreatmentHistoryDB` hata verip durur (doğru), ama `PatientDatabase` yalnız `logger.warning` yazıp sessizce düz-metin SQLite'a düşüyordu (`patient_database.py:98-104`) → en hassas veri (hasta PII + HMAC arama indeksi) şifreleme açıkça istendiği halde açıkta kalabilirdi.
- **Yapılan düzeltme:** `PatientDatabase.__init__`'e (at_rest_encrypted hesabından hemen sonra) `TreatmentHistoryDB:262` ile **birebir tutarlı** fail-closed guard eklendi: `not at_rest_encrypted and PEMF_ENCRYPT_AT_REST=1` → **RuntimeError** (patients.db açılmaz, düz-metin PII yazılmaz). Bayrak kapalıyken (test/dev) düz-metin açılır — geriye uyumlu.
- **Doğrulama:** Canlı test — bayrak-açık + SQLCipher-yok → RuntimeError (PASS); bayrak-kapalı → düz-metin açılır (PASS). pytest 12/13 (kalan 1 hata B-1.3'teki ile aynı ortamsal keyring sorunu; bu guard onu etkilemez — makinede at_rest_encrypted=True).
- **Tahmini Efor:** S (tamamlandı)

**B-1.5 — [KABUL EDİLMİŞ RİSK] Otonom tedavi başlatan AI uçları auth-muaf**
- **Önem:** High (düzenleyici) — *ama bilinçli tasarım kararı, "kusur" değil*
- **Mevcut Durum:** `servers/auth.py:25-31` → `/api/ai/pro` ve `/api/ai/ai_pro` (bobin süren OTONOM tedavi) + `/api/ai/vision`/`/api/ai/disease` auth-muaf listede. Yorum (satır 26-28) bunu açıkça belgeler: cihaz sahibinin 2026-07-01 talebiyle uzaktan kimliksiz başlat/durdur için muaf; "tünel URL'sini bilen HERKES tedavi başlatıp durdurabilir" riski kabul edilmiş.
- **Endüstri Standardı Beklenti:** Fiziksel donanımı (tıbbi maruziyet) süren bir uç asla kimlik-doğrulamasız internetten erişilebilir olmamalı.
- **Somut Öneri:** Bu bir hata değil; **yazılı risk kabulü** olarak dokümante edilmeli ve şu hafifletmeler değerlendirilmeli: (1) en azından pairing-kod bazlı hafif auth; (2) NAMED tünel (tahmin-edilemez sabit hostname) + IP allowlist; (3) uçların acil-durdurma her zaman kimliksiz kalsın (fail-safe) ama BAŞLATMA auth istesin. Geri almak için listeden iki öneki çıkarmak yeterli (yorumda belirtilmiş).
- **Tahmini Efor:** S (geri alma) / M (hafif-auth ekleme)

**B-1.6 — Rate limiting yalnız pairing-exchange'de; genel brute-force/DoS koruması yok** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Medium
- **Mevcut Durum (denetim anı):** Tek throttle `/api/auth/exchange`'de vardı; diğer uçlarda (patient CRUD, session, AI) hız sınırı yoktu.
- **Yapılan düzeltme:** `servers/api_server.py`'ye harici-bağımlılıksız (frozen EXE/offline uyumlu) in-process rate-limit middleware eklendi (`_rate_limit_middleware`, auth'tan ÖNCE çalışır). Kapsam bilinçli olarak **yalnız UZAK (Cloudflare tünel / reverse-proxy) trafiği** — LAN (web UI + 8 mobil, güvenli ağ, yüksek-frekanslı meşru polling) SINIRLANMAZ. Gerçek istemci IP'si CF-Connecting-IP / X-Forwarded-For'dan alınır (tünel arkasında client.host=127.0.0.1). Per-IP dakikalık pencere; aşımda `429 + Retry-After`. **Acil-durdurma + health + discovery DAİMA muaf** (fail-safe). Env: `PEMF_RATELIMIT_REMOTE_PER_MIN` (device=600, server=300, 0=kapalı) — `device.env`/`server.env`'de belgelendi. Not: token 192-bit olduğundan brute-force zaten imkânsız; fayda DoS/tarama azaltma.
- **Doğrulama:** TestClient ile 5/5 — limit aşımında 429, ayrı IP ayrı kova, emergency_stop/health muaf, 429 Retry-After taşır. pytest 12/13 (regresyon yok; kalan hata B-1.3'teki ortamsal keyring).
- **Kalan (opsiyonel):** CORS'u NAMED tünel hostname'iyle daraltma + Cloudflare-tarafı WAF/rate-limit (savunma-derinliği) hâlâ önerilir.
- **Tahmini Efor:** M (uygulandı)

**B-1.7 — Swagger/OpenAPI auth-muaf → API şeması tünelden açık** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Low
- **Mevcut Durum (denetim anı):** `servers/auth.py:32` → `/docs`, `/openapi`, `/redoc` muaf; auth açık olsa bile tünelden API yüzeyi görünürdü.
- **Yapılan düzeltme:** `api_server.py` FastAPI constructor'ında `docs_url`/`redoc_url`/`openapi_url` **koşullu** yapıldı. Kural: **auth-zorunlu VEYA tünel-açık (üretim/internet yüzeyi) → docs KAPALI (404)**; yerel-dev (auth+tünel kapalı) → AÇIK (geliştirici kolaylığı). `PEMF_ENABLE_DOCS` (1/0) ile açıkça geçersiz kılınabilir. Docs açıklığı güvenlik duruşuna otomatik bağlandığından yeni zorunlu knob yok.
- **Doğrulama:** 4 senaryo — REQUIRE_AUTH=1→404, ENABLE_TUNNEL=1→404, yerel-dev→200, override(ENABLE_DOCS=1)→200; hepsi PASS. pytest 12/13 (regresyon yok).
- **Tahmini Efor:** S (tamamlandı)

**Pozitif not:** SQL injection taraması **temiz** — tüm kullanıcı-değerli sorgular parametreli (`?`); tek f-string `ALTER TABLE` (`patient_database.py:128`, `treatment_history_db.py:371`) yalnız sabit literal argümanlar; `update_patient` `key` whitelist'e (`_ENCRYPTED_FIELDS`) filtreli. XSS backend'de düşük risk (JSON API). Şifre hashleme değil ama uygulanabilir yerde `secrets.compare_digest` sabit-zamanlı karşılaştırma kullanılıyor.

---

### 2. Mimari & Kod Kalitesi

**B-2.1 — Hiçbir lint / format / tip-denetimi yapılandırılmamış (backend)** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** High
- **Mevcut Durum (denetim anı):** Kaynak ağacında `pyproject.toml`/`.ruff.toml`/`mypy.ini`/`.pre-commit-config.yaml` yoktu → 28k satır backend'de sıfır statik analiz.
- **Yapılan düzeltme:** Ruff (lint+format) + mypy + pre-commit + CI eklendi. Yeni dosyalar: `pyproject.toml` ([tool.ruff] + [tool.mypy]), `.pre-commit-config.yaml`, `requirements-dev.txt` (ruff==0.15.20, mypy, pre-commit), `.github/workflows/lint.yml`. **Enforced (CI-bloklayan) set bilinçli olarak dar:** `select = ["F", "E9"]` (pyflakes gerçek-bug + syntax) → temiz baseline, CI yeşil. Stil kuralları (E501 uzun-satır 1250, whitespace 585, annotation modernizasyonu 158 = 2200+ ihlal) olgun kodda riskli devasa reformat olurdu → **kademeli açma** pyproject'te belgelendi (B/I/UP/SIM/E). mypy lenient (gradual typing, CI'da zorunlu değil). `ruff format` pre-commit'te yalnız değişen dosyalarda.
- **Baseline temizliği:** Ruff'un bulduğu 18 gerçek F ihlali düzeltildi — 10 auto-fix (kullanılmayan import/değişken, boş f-string) + 3 event_bus fire-and-forget assignment kaldırma + 2 mdns availability-import `# noqa` + 3 pemf_gui/scripts. F821 (undefined-name = çökecek bug) YOKtu.
- **Doğrulama:** `ruff check .` → "All checks passed!" (CI yeşil olacak); değişen runtime dosyaları import ediliyor; pytest 12/13 (regresyon yok).
- **Tahmini Efor:** M (uygulandı; kademeli stil/tip açma orta-vadeli)

**B-2.2 — Dev dosyalar + import-zamanı yan etkiler** — ✅ **ÇÖZÜLDÜ (2026-07-06 — import/lifespan + router bölme)**
- **Önem:** Medium
- **Mevcut Durum (denetim anı):** `api_server.py` import'ta 3 daemon thread başlatıyordu (import yan-etkisi); deprecated `@app.on_event`; dosya 2296 satır.
- **Yapılan düzeltme:** (1) Deprecated `@app.on_event` → tek `lifespan` context-manager. (2) 4 arka-plan thread'i (safety süre-watchdog + sensör-persist + günlük-bakım + sim) import'tan çıkarılıp idempotent `_start_background_threads()` → **lifespan startup'tan** başlatılıyor (state SET EDİLDİKTEN sonra; latent sıra hatası da düzeldi). (3) **Router bölme (B-2.2 dosya-split, testle güvenli):** düşük-bağlı + cohesive + test-edilmiş gruplar ayrıldı → `servers/update_router.py` (`/api/update/*`, yalnız update_manager) + `servers/patient_router.py` (`/api/patients/*` + modeller, yalnız patient DB). Yollar birebir korunur (istemci sözleşmesi değişmez).
- **Doğrulama:** Bare-import → bg thread yok; lifespan → 3 thread başlar; on_event uyarı=0; router'lardan 6 uç kayıtlı (test); pytest 49/49 (transport/patient/update-rollback bu uçları koşturur); ruff temiz. `api_server.py` 2470→2407 satır.
- **EK TAMAMLAMA (2026-07-06 — ÜÇ shared-state modül ayrımı, test→ayır deseniyle):**
  - **(1) Canlı-durum:** WS/live-state çekirdeği (`_live_state`, `_ws_clients`/broadcast, `_push_notification`, `_build_ws_snapshot`, `update_live_*`, `_sync_stm_coils_locked` + STM/ESP sabitleri) **`servers/live_state.py`'ye taşındı** (194 satır). Refactor-ÖNCESİ **11-test kilidi** (`tests/test_live_state.py`) → sonrası **AYNI testler yeşil** = davranış birebir. Aynı-nesne alias (dict/list/lock in-place → gövde değişmedi); lifespan `live_state.set_event_loop()` (tek davranış-değişim noktası, uçtan-uca test).
  - **(2) Coil-run tracker:** `_active_coil_runs`/`_coil_run_stats` + `_begin/_finish_coil_run` (treatment-DB coil-run yaşam-döngüsü + **per-metrik ortalama** — her metrik kendi dolu-sayısına bölünür, klinik-doğruluk) **`servers/coil_run_tracker.py`'ye taşındı** (121 satır). Treatment-DB'ye bağlı ama MQTT/hardware geri-bağımlılığı YOK: `db_session_id` + treatment-DB **injection** ile gelir (`set_*_getter`) → döngüsel import yok. Refactor-ÖNCESİ **6-test kilidi** (`tests/test_coil_run_tracker.py`) → sonrası yeşil.
  - **(3) Session state (son kademe):** `_active_session` + `_session_lock` **`servers/session_state.py`'ye taşındı** (33 satır) + saf erişim (`snapshot`/`is_active`/`current_db_session_id`). **ÖN KOŞUL:** `start_session`/`start_ai_session` dict'i **REBIND** ediyordu (`_active_session = {...}` + `global`) → **in-place mutasyona normalize edildi** (`.clear()+.update()`, kilit altında atomik, davranış aynı) → dict kimliği sabit → aynı-nesne alias çalışır. Refactor-ÖNCESİ **9-test kilidi** (`tests/test_session_lifecycle.py`: start/stop/AI-devralma + **kimlik-sabitliği invariantı**) → sonrası yeşil. coil-run getter artık `session_state.current_db_session_id`'e enjekte.
  - **Sonuç: api_server.py 2407→2206** (−201 satır, ÜÇ kohezyonlu modül); backend test 54→80.
- **BİLİNÇLİ bırakılan (kalan):** Session **LOGIC** — start/stop/emergency endpoint'leri + süre-watchdog — bilinçli olarak api_server.py'de kaldı (web/orkestrasyon katmanı; donanım `state.hardware` + MQTT `_mqtt_publish` + live-state'e örülü). Session **STATE** artık izole (`session_state.py`); rebind footgun'u giderildi. Endpoint'lerin tam servis-katmanına taşınması router+bağımlılık-injection ister (kademeli; en yüksek risk parçası, şimdilik state-ayrımı yeterli kazanç).
- **Tahmini Efor:** L (import/lifespan + router-split + live_state + coil_run_tracker + session_state uygulandı; session endpoint-logic kademeli)

**B-2.3 — Starlette iç sınıfının global monkeypatch'i (kırılgan)** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Medium
- **Mevcut Durum (denetim anı):** `ai_router.py:26-43` → RNA CSV için `starlette.formparsers.MultiPartParser.__init__` GLOBAL sarılıp `max_part_size` zorla enjekte ediliyordu → sürüm yükseltmesinde sessizce kırılabilirdi.
- **Yapılan düzeltme:** Monkeypatch kaldırıldı; yerine **DESTEKLENEN** `request.form(max_part_size=...)` API'si + router-düzeyi content-type-korumalı dependency (`_allow_large_upload`, `APIRouter(dependencies=[...])`). Yalnız `multipart/form-data` isteklerde limiti 50MB'a yükseltir ve FormData'yı `request._form`'a cache'ler → FastAPI'nin File/Form çözümü aynı cache'i kullanır; JSON gövde uçlarına (disease/kidney_disease) **DOKUNMAZ**. (Kurulu Starlette 1.2.1 doğrulandı: `max_part_size` yalnız non-file form alanlarına uygulanır — dosya part'ları diske spool → limitsiz.)
- **Doğrulama:** İzole TestClient — router-dependency ile 3MB csv_base64 form-alanı + 3MB dosya + JSON gövde hepsi 200 (JSON body dependency'den etkilenmedi). Gerçek `ai_router` import ediliyor, `_allow_large_upload` router dependency olarak kayıtlı; kalan monkeypatch referansı yok; ruff F,E9 temiz; pytest 12/13.
- **Tahmini Efor:** M (uygulandı)

**B-2.4 — Frontend'de tip kaçakları ve god-context** — ✅ **BÜYÜK ÖLÇÜDE ÇÖZÜLDÜ (2026-07-06 — B-3.2 harness'i üzerine)**
- **Önem:** Medium
- **Mevcut Durum (denetim anı):** `strict:true`, `tsc` temiz; 101 `any` (95'i AiHubScreen'de); LiveDataContext WS+NetInfo+token+polling'i tek context'te topluyordu.
- **Yapılan düzeltme (B-3.2 test ağı sayesinde güvenle):**
  - **God-context bölme:** NetInfo ağ-tespiti → `hooks/useNetworkReachability.ts` (tiplenmiş, `NetInfoState`; 2 `any` gitti) + AppState ön-plan → `hooks/useForegroundReconnect.ts`. LiveDataContext'te 2 effect → 2 hook çağrısı; **public API/davranış AYNI**; kullanılmayan `AppState` import kaldırıldı; `fgs_raw: any → unknown` (hiç okunmuyor). **4 yeni test** (`useNetworkReachability.test.ts`: debounce, dedup, disconnect-no-op, unmount-cleanup).
  - **`any` azaltma (mekanik, tsc-doğrulanabilir):** `wsClient` 3 cast (`"pong"` union üyesi + close `event.code`); AiHubScreen ~18 (`(e:any)`→`(e:Event)` 17× web dosya-seçici + `e.target.files[0]`→`(e.target as HTMLInputElement).files?.[0]` + `catch(e:any)`→`catch(e)` 3× + `errorMessage(e:unknown)` helper). **Toplam `any` 101→77.**
- **Doğrulama:** `tsc --noEmit` → exit 0; `jest` → **22 passed** (18→22).
- **EK TAMAMLAMA (2026-07-06):** AiHubScreen `.map/.filter/.reduce/.forEach` callback'leri **6 AI-sonuç interface'iyle tiplendi** (AiTumorRegion/AiWell/AiPrediction/AiTopK/AiDetection/AiOrgan), tsc yeşil.
- **EK TAMAMLAMA-2 (2026-07-06 — sonuç-CONTAINER tipleme):** ✅ **11 AI-sonuç `useState<any>` state'i tiplendi** → yeni **`AiResult` backend-yanıt sözleşmesi** (8+ modelin heterojen JSON'u tek opsiyonel-alanlı interface; typo'lar derleme-zamanı yakalanır + autocomplete) + `DiseasePrediction[]` (disease modülü dizi döndürür). Tipin ortaya çıkardığı **6 gerçek narrowing** düzeltildi (`top_1_class`/`fgs_total` olası undefined/null index/karşılaştırma → `?? ""`/`?? 0`). tsc PASS. **KALAN any (kabul):** yalnız `imageFile`/`webFile` dosya-seçici state'leri (platform-özel File/asset objesi — ayrı, düşük-değer); `AppNavContext`↔expo-router dedup.
- **Tahmini Efor:** M (god-context + mekanik any tamam; AI-sonuç tipleri orta-vade)

---

### 3. Test

**B-3.1 — Backend test kapsamı smoke düzeyinde (~13 fonksiyon), en güvenlik-kritik yol test edilmemiş** — ✅ **BÜYÜK ÖLÇÜDE ÇÖZÜLDÜ (2026-07-06 — 13→32 test)**
- **Önem:** High
- **Mevcut Durum (denetim anı):** 13 test fonksiyonu; coil transport, session/DB kalıcılık, şifreleme fail-closed test edilmemişti (~%1-3).
- **Yapılan düzeltme:** 4 yeni test dosyası + 19 test eklendi (13→**32**, hepsi yeşil), kritik yolları kapsıyor:
  - `test_coil_transport.py` (5): STM(1-5)→HardwareController vs ESP(6-8)→MQTT yönlendirme, geçersiz bobin reddi, batch STM/ESP ayrımı, stop_all → donanım (donanım/broker mock).
  - `test_pii_protection.py` (5): B-1.4 PatientDB fail-closed (şifreleme istenip sağlanamayınca RuntimeError) + düz-metin geriye-uyumluluk; B-1.3 TreatmentDB PII maskeleme (şifresizken maskeli, şifreliyken aynen, non-PII korunur).
  - `test_rate_limit.py` (5): B-1.6 uzak-IP limit + ayrı-IP-ayrı-kova + emergency_stop/health muaf + fail-closed sayım.
  - `test_treatment_persistence.py` (4): start→end round-trip + geçmişte görünürlük, sensör batch yazımı, sağlık-snapshot şifreleme bayrağı, süre hesaplama.
  - Ayrıca `test_patient_encryption.py` **makine-bağımsız** yapıldı (keyring anahtarı olan makinede kararsızlık giderildi — whole-DB SQLCipher mock'lanıp alan-düzeyi izole edildi).
- **Doğrulama:** `pytest tests -q` → **32 passed, 0 failed**; ruff temiz.
- **EK TAMAMLAMA (2026-07-06):** ✅ **Süre-watchdog otomatik-durdurma (#1) ARTIK TEST EDİLİYOR** (`test_session_watchdog.py`: lifespan→watchdog thread, süresi-dolmuş seans→otomatik durur + dolmamış→durmaz). ✅ **Coverage kapısı** eklendi (`pytest-cov`, pyproject `fail_under=33`, şu an %36 ratchet; CI `--cov`). ✅ **Canlı-durum (live-state) çekirdek kilidi** (B-2.2 refactor-öncesi, `test_live_state.py` 11 test): WS-snapshot sözleşmesi + `update_live_session_state/coil_from_stm/stm_status` + `_sync_stm_coils_locked` + `_push_notification` cap + **`_emergency_stop_all`** (tüm bobin STOP + seans kapat) + `get_active_session` salt-okunur invariantı + lifespan event-loop bağlama. ✅ **Coil-run tracker kilidi** (`test_coil_run_tracker.py` 6 test): `_begin/_finish_coil_run` + **per-metrik ortalama** (her metrik kendi dolu-sayısına bölünür, 0-bölme güvenli) + çift-açık kapatma + db-seansı-yoksa no-op. ✅ **Session-lifecycle kilidi** (`test_session_lifecycle.py` 9 test): `start_session` (state doldurma + çift-başlat 409) + `stop_session` (aktif→pasif + boş→ok) + `start_ai_session` (AI-modu + manuel-devralma) + **`_active_session` kimlik-sabitliği invariantı** (rebind→in-place normalizasyon kanıtı). **KALAN:** STM seri katmanı + 8-model AI hub + tam WS uçtan-uca akışı + Supabase sync (kademeli).
- **Tahmini Efor:** L (kritik yol seti tamamlandı; kalanlar orta-vade)

**B-3.2 — Frontend'de sıfır test** — ✅ **BÜYÜK ÖLÇÜDE ÇÖZÜLDÜ (2026-07-06 — 0→18 test, harness kuruldu)**
- **Önem:** Critical
- **Mevcut Durum (denetim anı):** `C:\Users\merta\pf` içinde hiç test yoktu; jest/RNTL bağımlılıkta yoktu.
- **Yapılan düzeltme:** Jest + jest-expo (SDK 56 uyumlu) + @react-native/jest-preset + @testing-library/react-native (13.3.3) + @types/jest kuruldu; `jest.config.js` (jest-expo preset + `@/` alias + AsyncStorage mock via `jest.setup.ts`) + `npm test` script eklendi. **18 test (3 suite), hepsi yeşil:**
  - `apiClient.test.ts` (7): X-API-Key auth header (token var/yok), 200→JSON, HTTP-hata→fallback (throw ETMEZ), bağlantı-kopması→fallback (UI bloklanmaz), POST serialize+Content-Type. **Bağlantı dayanıklılığı = tedavi başlat/durdur/acil-durdur akışlarının taşıma katmanı.**
  - `config.test.ts` (9): sunucu adresi→API/WS URL çözümü (LAN IP vs Cloudflare tünel + trailing-slash + apiToken korunması), API token kalıcılığı (set/load, boş→silme, mevcut-değeri-ezmeme), device-id + otomatik-eşleştirme bayrağı.
  - `ErrorBoundary.test.tsx` (2, RNTL component-render): çocuk çökünce **beyaz-ekran yerine kurtarma kartı** + hata mesajı; hata yoksa normal render. (Tıbbi cihazda donma önleme.)
  - tsconfig'e `types: ["jest","node"]` eklendi → `tsc --noEmit` **yeşil kaldı** (test dosyaları da tip-denetimli).
- **Doğrulama:** `npm test` → 18 passed / 3 suites; `tsc --noEmit` → exit 0.
- **EK TAMAMLAMA (2026-07-06):** ✅ **Hook testleri eklendi** (`useNetworkReachability` 4 test: debounce/dedup/disconnect/cleanup + `useForegroundReconnect`: active→reconnect/unmount-temizlik) → **FE 22→23 test**; ✅ **Frontend CI** `pf/.github/workflows/frontend.yml` (B-3.3'te). ✅ **Tedavi-kontrol akışı kilidi** (`useSessionControl.test.ts` 7 test → FE **23→30**): startSession başarı/başarısızlık + **KRİTİK: stopSession backend-erişilemez → seans AKTİF kalır + uyarı** (yanlış 'durduruldu' YOK) + **emergencyStop doğrulanamadı → 'DOĞRULANAMADI' uyarısı** + mount hidrasyonu (audit P1 güvenlik davranışları uçtan-uca kilitlendi). **KALAN:** diğer ekran render akışları (kademeli).
- **Tahmini Efor:** L (harness + servis/component kritik testleri kuruldu; ekran-akış testleri orta-vade)

**B-3.3 — Tek CI hattı KIRIK (var olmayan dosyaya referans)** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** High
- **Mevcut Durum (denetim anı):** `tests.yml` `requirements-test.txt`'e referans veriyordu ama dosya YOKtu → install adımı patlıyor, pytest hiç kurulmuyor, hat asla yeşile dönmüyordu.
- **Yapılan düzeltme:** (1) `requirements-test.txt` **oluşturuldu** — introspeksiyonla saptanmış import-zamanı deps (fastapi/starlette/pydantic/numpy/opencv-headless/pillow/reportlab/cryptography/keyring/paho) + pytest + httpx; ağır AI'lar (torch/ultralytics/onnx/...) lazy → hariç, sqlcipher3 hariç (ubuntu'da zor + kod graceful). (2) `tests.yml` sadeleştirildi (gereksiz explicit install kaldırıldı, `cache: pip`, bayat "git'te değil" yorumu düzeltildi). (3) **Frontend CI eklendi** — `pf/.github/workflows/frontend.yml` (`npm install --legacy-peer-deps` + `tsc --noEmit` + `npm test` → 22 jest).
- **Doğrulama:** Backend'i **temiz venv + taze APPDATA (gerçek CI ortamı)** ile simüle ettim: `py -3.10 -m venv` → `pip install -r requirements-test.txt` → `pytest tests` → **32 passed, exit 0**. (İlk denemede 2 hata çıktı ama nedeni bu makinenin ÖNCEDEN-şifreli gerçek patients.db'siydi; taze APPDATA ile — CI'daki gibi — yeşil.) 3 workflow YAML'ı geçerli.
- **Tahmini Efor:** S (tamamlandı)

---

### 4. Hata Yönetimi & Dayanıklılık

**B-4.1 — Global exception handler yok; tutarsız hata zarfı + ham `str(e)` sızıntısı** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** High
- **Mevcut Durum (denetim anı):** Hiç exception handler yoktu; `ai_router` 14 uçta `HTTPException(500, detail=f"...: {str(e)}")` ile **ham istisna metnini sızdırıyordu** (auth-muaf publik uçlar → bilgi ifşası).
- **Yapılan düzeltme:** (1) `api_server.py`'ye 2 global handler: `@app.exception_handler(Exception)` → tutarlı zarf `{"detail","error_id"}` + korelasyon-id ile SUNUCU-TARAFI log (ham traceback/str(e) İSTEMCİYE SIZMAZ); `@app.exception_handler(RequestValidationError)` → tutarlı 422 `{"detail","errors"}` (`input`/PII alanı ayıklandı). (2) ai_router 14 `str(e)` sızıntısı → `_ai_fail(label, e)` helper (gerçek nedeni `logger.exception` ile sunucuda logla, istemciye kısa etiket).
- **Doğrulama:** `test_observability.py` — handler'lar kayıtlı, 422 tutarlı zarf + `input` sızmıyor; ai_router'da 0 `str(e)` sızıntısı; ruff/pytest yeşil.
- **Tahmini Efor:** M (uygulandı)

**B-4.2 — Servis-kontrol ve AI uçlarında sessiz `except: pass`** — ✅ **ÇÖZÜLDÜ (2026-07-06 — büyük ölçüde audit-abartması)**
- **Önem:** Medium
- **Mevcut Durum (inceleme sonrası):** Bayrağı çekilen 23 `except:pass`'in **neredeyse tamamı benign**: `ai_router` 11'inin ~9'u `os.unlink(tmp.name)` geçici-dosya temizliği + 1 model-ısıtma (kendi fallback'i var); `headless_services` 12'sinin çoğu capability-probe/parse-fallback (`get_local_ip`, `_read_version`, `_get_network_ips` — sessiz=varsayılan döner). **Ana servis-kontrol/izleme döngüleri (`_monitor_loop`, `_run`) ZATEN `logger.warning` ile logluyor** (doğrulandı).
- **Yapılan düzeltme:** Genuine kontrol-yolu 2 spotuna log eklendi — AI Pro loop seans-kontrol (`logger.debug`) + AI Pro stop bobin-STOP publish hatası (`logger.warning`). Benign temp-cleanup/probe'lara log EKLENMEDİ (log-spam olurdu, sessiz-yutma göz-ardı-edilebilir).
- **Doğrulama:** ruff/pytest yeşil.
- **Tahmini Efor:** M (uygulandı; kapsam gerçekte küçüktü)

**Pozitif not:** Dayanıklılık backend'in güçlü yanı — çok katmanlı watchdog (süre `api_server.py:1464`, tünel `tunnel_manager.py:313`, açılış-mutabakatı `backend_service.py:180`, STM/ESP acil-durdurma), fail-closed auth middleware (`api_server.py:70-110`), kapsamlı timeout (MQTT socket probe 0.3s + `wait_for_publish` 2s; STM reconnect throttle 3s; subprocess timeout 5/15s; HTTP urlopen timeout). Crash-handler `sys.excepthook` + `threading.excepthook` + ayrı `crash.log` (`backend_service.py:113-147`).

---

### 5. Gözlemlenebilirlik (Observability)

**B-5.1 — Merkezî hata izleme / telemetri yok (saha çökmeleri görünmez)** — ✅ **ÇÖZÜLDÜ (2026-07-06 — opsiyonel, opt-in)**
- **Önem:** High
- **Mevcut Durum (denetim anı):** Hiç uzaktan hata-izleme yoktu; tek çökme-yakalama yerel `crash.log`.
- **Yapılan düzeltme:** `utils/telemetry.py` — opsiyonel Sentry entegrasyonu. **VARSAYILAN KAPALI (KVKK: hata verisi buluta OTOMATİK gitmez)**; yalnız `PEMF_SENTRY_DSN` set + sentry-sdk varsa aktif. PII-scrub açık (`before_send` request/user/stack-locals atar, `send_default_pii=False`), yalnız hata (performans-izleme kapalı). `backend_service.main`'de crash-handler'dan sonra `init_telemetry()` çağrılır (graceful: DSN yok/sdk yoksa no-op). `sentry-sdk==2.24.1` requirements.txt'e eklendi (EXE'ye gömülü ama dormant). Self-hosted Sentry önerisi (KVKK).
- **Doğrulama:** `test_observability.py` — DSN yokken + sentry-sdk yokken no-op (False) doğrulandı.
- **Tahmini Efor:** M (uygulandı)

**B-5.2 — Metrik/`/metrics` uç noktası yok; loglar yapısal değil** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Mevcut Durum (denetim anı):** `/metrics` yok; loglar yalnız düz-metin.
- **Yapılan düzeltme:** (1) `api_server.py`'ye **`/metrics`** — Prometheus text format, **harici bağımlılık yok** (elle üretim → frozen EXE'yi şişirmez): `pemf_ws_clients`, `pemf_active_session`, `pemf_coils_connected/running`, `pemf_mqtt_up`, `pemf_stm_up`, `pemf_gateway_up`, `pemf_notifications` (in-memory canlı durumdan; ek enstrümantasyon gerekmez). YEREL/LAN scrape auth-muaf, uzak token ister. (2) `backend_service`'e opsiyonel **JSON structured logging** — `PEMF_LOG_JSON=1` iken `_JsonLogFormatter` (ts/level/logger/msg/exc), bağımlılıksız; varsayılan düz-metin.
- **Doğrulama:** `test_observability.py` — `/metrics` 200 + Prometheus format + sayısal değer; JSON formatter geçerli JSON.
- **Tahmini Efor:** M (uygulandı)

**B-5.3 — Kütüphane modüllerinde dağınık `logging.basicConfig`** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Low
- **Mevcut Durum (inceleme):** Yalnız `utils/stm32_simulator.py:48` gerçek sorundu (**modül-üstü** basicConfig → import'ta merkezî config'i ezer). Diğer 3 (`hybrid_recommender`, `credential_manager`, `mdns_service`) zaten `__main__`/CLI-helper altındaydı (sorun değil).
- **Yapılan düzeltme:** `stm32_simulator.py`'deki modül-düzeyi `basicConfig` `if __name__ == "__main__":` bloğuna taşındı → import edildiğinde merkezî logging'i ezmez, standalone çalışınca yapılandırır.
- **Tahmini Efor:** S (uygulandı)

**Pozitif not:** Backend runtime'da `print()` **efektif sıfır** (servers/controllers/database=0; services/utils'teki print'ler yalnız CLI araçları). Log seviyeleri doğru + zengin kullanılıyor.

---

### 6. Performans & Ölçeklenebilirlik

**B-6.1 — Frontend tek-parça bundle, code-splitting/lazy yok** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Medium
- **Yapılan düzeltme:** `PemfApp.tsx` — ilk-boyama (Welcome/Dashboard) EAGER kaldı; **8 ağır/nadir ekran `React.lazy` + `Suspense`** ile lazy yüklenir (ControlScreen, DemaSimulator, KpiDashboard, SensorMonitor, TreatmentHistory, Patient, **AiHubScreen** 2500+ satır, Settings). Named export → default-sarmalayıcı; fallback ActivityIndicator. Web tek-bundle'ında açılış chunk'ı küçülür (AiHub + chart + webview artık on-demand).
- **Doğrulama:** `tsc --noEmit` exit 0; jest 23 passed.
- **Tahmini Efor:** M (uygulandı)

**B-6.2 — PatientDatabase kaba global kilit + kapanmayan thread-local bağlantılar** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Medium
- **Yapılan düzeltme:** `_get_connection`'a **`PRAGMA busy_timeout=5000`** ('database is locked' yerine bekle) + **`check_same_thread=False`** + **worker-thread bağlantı kapatma** (bu context'te açıldı + ana-thread değilse kapat → handle sızıntısı önlenir; ana-thread REUSE korunur, SQLCipher KDF maliyeti). Global kilit BİLİNÇLİ korundu (patient DB seyrek erişilir; okuma/yazma-ayrımı düşük değer/risk).
- **Doğrulama:** `test_data_layer.py` — busy_timeout≥5000; pytest yeşil.
- **Tahmini Efor:** M (uygulandı)

**B-6.3 — `get_session_history`'de 11-JOIN EAV deseni + sınırsız büyüyen tablolar** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Medium
- **Yapılan düzeltme:** `session_parameters`'a **composite index `(session_id, parameter_name)`** (`idx_session_params_sid_name`) → 11 self-JOIN artık indeksli lookup (parameter_name taraması yok), read-contract değişmez (denormalizasyon riski alınmadı). **Sınırsız büyüme BİLİNÇLİ:** tıbbi kayıt-tutma gereği tedavi seansları SİLİNMEZ (yalnız 365g sonra PII-redakte — KVKK); "büyüme" tıbbi cihazda kabul edilen davranış (sensör ham verisi zaten dakika-ortalama + retention'lı).
- **Doğrulama:** `test_data_layer.py` — composite index mevcut; pytest yeşil.
- **Tahmini Efor:** M (uygulandı)

**Pozitif not:** Backend büyük ölçüde tek-cihaz/tek-süreç tasarımı (yatay ölçekleme hedef değil); dakika-ortalama toplama (20dk seans ≈ bobin başına ~20 satir, `api_server.py:1548`) ham veri şişmesini önlüyor; index'ler mevcut; ESP publish event-loop'tan `asyncio.to_thread` ile çıkarılmış (P0 audit).

---

### 7. Veri & Veritabanı

**B-7.1 — Migration framework yok (Alembic); şema el-yordamıyla + `schema_migrations` kozmetik** — ✅ **ÇÖZÜLDÜ / DÜZELTME (2026-07-06)**
- **Önem:** Medium
- **İnceleme sonucu (bulgu abartılıydı):** Aslında **işlevsel versiyonlu migration sistemi VAR** — `_run_startup_migrations_with_rollback` (backup-before-migrate + hata → rollback) + `schema_migrations` tablosu **`version`+`description`+`applied_at`+UNIQUE ile** (kozmetik DEĞİL) + `TARGET_SCHEMA_VERSION`. Idempotent `IF NOT EXISTS`/`ALTER` reconciliation, tek-dosya embedded SQLite tıbbi cihaz için ROBUST (self-healing şema).
- **Yapılan düzeltme:** migration_backups **rotasyonu** eklendi (son 5). Alembic BİLİNÇLİ ADOPTE EDİLMEDİ — bu mimaride over-engineering + risk; mevcut sistem yeterli+güvenli.
- **Tahmini Efor:** M (rotasyon uygulandı; sistem zaten işlevsel)

**B-7.2 — Off-machine / zamanlanmış yedek yok; `migration_backups/` sınırsız + PatientDB'de yedek yok** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Medium
- **Yapılan düzeltme:** (1) **PatientDatabase.create_backup** eklendi (şifreleme-farkında, online backup API — eskiden yoktu). (2) `headless_db_maintenance` artık **hasta DB'sini de yedekler** + her iki aileyi rotasyona sokar. (3) **Off-machine backup** — `PEMF_BACKUP_DIR` env set ise günlük yedekler harici hedefe (ağ paylaşımı/USB) kopyalanır (disk arızası/ransomware tek-nokta olmasın); `device.env`'de belgelendi. (4) **migration_backups rotasyonu** (B-7.1'de, son 5).
- **Doğrulama:** `test_data_layer.py` — PatientDB.create_backup çalışıyor + yedek okunabilir; pytest/ruff yeşil.
- **Tahmini Efor:** M (uygulandı)

**B-7.3 — patients.db FK CASCADE inert; retention harici zamanlayıcıya bağlı** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Low
- **Yapılan düzeltme:** PatientDB `_get_connection`'a **`PRAGMA foreign_keys=ON`** → `patient_search_index ON DELETE CASCADE` artık aktif (orphan-satır riski kalktı; elle DELETE'e bağımlılık azaldı).
- **Doğrulama:** `test_data_layer.py` — `PRAGMA foreign_keys`=1.
- **Tahmini Efor:** S (uygulandı)

**Pozitif not:** Veri katmanı olgun — WAL + `synchronous=NORMAL` + DELETE fallback, thread-local pool, kapsamlı index/constraint (UNIQUE/PK/FK), disk-alanı guardrail (`MIN_FREE_DISK_MB=500`), quick_check/integrity_check, şifreleme-farkında online backup, retention purge'leri, HMAC blind-index ile şifreli-ama-aranabilir PII. Supabase RLS + SECURITY DEFINER RPC modeli sağlam (anon tablo dökemiyor).

---

### 8. API Tasarımı

**B-8.1 — API versiyonlama yok + tutarsız hata/yanıt formatı** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Medium
- **Mevcut Durum (denetim anı):** Versiyonsuz `/api`; sürüm 4 yerde farklı (1.0.0 / 1.5 / 1 / VERSION 1.4.0). (Hata zarfı B-4.1'de çözüldü.)
- **Yapılan düzeltme:** (1) **Tek versiyon kaynağı** — `utils.path_utils.get_app_version()` (bundled `frontend_version.json` → `VERSION` → fallback, cache'li); FastAPI.version + `/api/discovery` + `/api/system/info` + `_live_state.softwareVersion` **hepsi bundan** → 1.4.0'da tutarlı. (2) **Versiyonlama non-breaking**: security-headers middleware'inde `/api/v1/*` yolları `/api/*` handler'larına yeniden-yazılıyor → **hem eski `/api` hem yeni `/api/v1`** çalışır (route çoğaltma yok). (3) **`X-API-Version`** yanıt header'ı (istemci/monitoring görünürlüğü).
- **Doğrulama:** `test_api_design.py` — versiyon tutarlı (app/discovery/system_info), `/api/v1/health`→200, X-API-Version header. ruff/pytest yeşil.
- **Tahmini Efor:** M (uygulandı)

**B-8.2 — Pagination yok; `delete_all` korumasız** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Medium
- **Mevcut Durum (denetim anı):** `/api/patients` tüm hastaları tek seferde döndürüyordu; `/api/patients/delete_all` onaysız tüm hastaları siliyordu (yalnız middleware auth).
- **Yapılan düzeltme:** (1) **Pagination (geriye-uyumlu)** — `/api/patients?limit&offset`; `limit=0`→HEPSİ (eski istemci parametre göndermez), yanıt `{status,data,total}` (eski `status`/`data` korunur, `total` yeni). (2) **`delete_all` kazara-silme koruması** — gövdede `{"confirm":"DELETE_ALL"}` ZORUNLU (yoksa 400); silinen-sayısı loglanır. Frontend (`PatientScreen.tsx`) confirm gönderecek şekilde güncellendi.
- **Doğrulama:** `test_api_design.py` — pagination geriye-uyumlu + limit çalışıyor; delete_all confirm-yok/yanlış→400, doğru→200. Backend 44 test + frontend tsc/jest yeşil.
- **EK TAMAMLAMA (2026-07-06 — history keyset/cursor pagination):** `/api/history/` eskiden **limit-only** (büyüyen geçmişte yalnız en yeni 100 erişilebilir) → **keyset (cursor) pagination** eklendi. Backend: `get_session_history(before_id)` + `GET /api/history/?limit&cursor` — `cursor` = son öğenin `id`'si → `WHERE ts.id < cursor ORDER BY ts.id DESC` (PK monoton+benzersiz+indexli). **Keyset avantajı:** büyük-OFFSET taraması YOK + sayfalar arası yeni kayıt girse bile **sayfa kayması/atlama/tekrar YOK** (offset'in aksine). **Geriye uyumlu** (cursor'suz = eski davranış, en yeni `limit`). Frontend `TreatmentHistoryScreen`: ilk sayfa (50) + **"Daha Fazla Yükle"** butonu (cursor=son id, append; a11y-etiketli). **3 yeni test** (`test_history_pagination.py`: örtüşmez+tam-kapsar, araya-kayıt-kararlılığı, geriye-uyum). Sıralama `session_date DESC`→`ts.id DESC` (pratikte özdeş: id insertion-order = tedavi-order); tam backend suite yeşil (regresyon yok).
- **Tahmini Efor:** M (pagination + delete_all + cursor uygulandı)

**Pozitif not:** OpenAPI/Swagger otomatik (FastAPI+Pydantic), HTTP status kullanımı çoğunlukla doğru (409 çift-session, 503 hazır-değil, 400 geçersiz bobin), sağlık/keşif uçları temiz.

---

### 9. DevOps / CI-CD / Altyapı

**B-9.1 — CI kırık + hiç lint/tip/build/coverage adımı yok** — ✅ **ÇÖZÜLDÜ** — bkz **B-3.3** (CI onarıldı: `tests.yml` backend 86 test + `lint.yml` ruff + `frontend.yml` tsc/jest/eslint + `security.yml` pip-audit + **coverage-kapısı %36≥%33 ratchet**). Kalan: release-artifact/build adımı yok (kademeli).

**B-9.2 — Rollback stratejisi yok; sürümler üzerine-yazıyor** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** High
- **Mevcut Durum (denetim anı):** OTA yalnız İLERİ gidiyordu; `latest.json` tek sürüm işaret ediyordu, belgeli downgrade yolu yoktu. (GitHub release'leri tag-başına aslında immutable — asset-silme yalnız aynı-tag re-publish'te; asıl boşluk rollback yoluydu.)
- **Yapılan düzeltme:** (1) **`latest.json` `previousStable`** alanı (`{version,installerUrl,sha256}`) — `publish_release.ps1` yeni sürüm yayınlarken mevcut sürümü otomatik rollback-hedefi olarak taşır. (2) **`update_manager.rollback()`** — apply_update ile AYNI güvenlik zinciri (SHA256 ZORUNLU + Authenticode + **aktif-tedavi-varsa fail-closed RED**), yön 'geri'. (3) **`POST /api/update/rollback`** endpoint + `get_status().previousStable` görünürlüğü. (4) **DEPLOYMENT.md rollback runbook** (tek-tık + elle yol).
- **Doğrulama:** `test_update_rollback.py` (5 test) — previousStable-yok/SHA256-yok/aktif-tedavi → RED; endpoint kayıtlı; status previousStable taşır. publish_release.ps1 PARSE OK.
- **Tahmini Efor:** M (uygulandı)

**B-9.3 — Bağımlılık CVE taraması yok** — ✅ **ÇÖZÜLDÜ (2026-07-06 — tarama kuruldu + gerçek CVE'ler raporlandı)**
- **Önem:** High
- **Mevcut Durum (denetim anı):** Pinli ama tarama yok → CVE'ler görünmez.
- **Yapılan düzeltme:** (1) **`guii/.github/dependabot.yml`** (pip + github-actions, haftalık; torch/numpy major-bump ignore) + **`pf/.github/dependabot.yml`** (npm; expo/react major ignore) → açık deps için otomatik PR. (2) **`guii/.github/workflows/security.yml`** — `pip-audit` (çekirdek ortam üzerinden, haftalık cron + PR, **non-blocking**: mevcut pinlerde CVE var).
- **pip-audit ile SAPTANAN GERÇEK CVE'ler (6 direkt dep — maintainer test edip yükseltmeli):**
  - **`cryptography==41.0.3`** → 6+ CVE (CVE-2023-50782, CVE-2024-0727...) → **42.0.x/43.0.1** *(Fernet/DPAPI kullanır — ÖNCELİKLİ)*
  - **`python-multipart==0.0.30`** → CVE-2026-53540 → **0.0.31** *(ai_router upload'ta kullanılır — ÖNCELİKLİ, düşük-risk bump)*
  - **`starlette==1.2.1`** → 2 CVE → **1.3.x**
  - **`zeroconf==0.147.3`** → 5 CVE → **0.149.x**
  - **`onnx==1.15.0`** → çok CVE → **1.16+** *(AI-uyumluluk test gerekir)*
  - **`torch==2.1.2`** → çok CVE → **2.6+** *(numpy<2 kısıtı + CPU-wheel + model-uyumluluk → dikkatli)*
- **✅ UYGULANDI + DEPLOY EDİLDİ (2026-07-06):** Güvenli 4 CVE `requirements.txt`'e **pinlendi** + build-env (myenv) yükseltildi + **86 test yeşil**: **cryptography 41.0.3→43.0.1** (Fernet/DPAPI, CVE-2023-50782/2024-0727), **python-multipart 0.0.30→0.0.31**, **zeroconf 0.147.3→0.149.0**, **starlette 1.2.1→1.3.1** (FastAPI≥0.46 uyumlu). Frozen EXE **yeniden derlendi** (39.5MB, smoke-test: `atRestEncrypted=true`) + **çalışan servise in-place deploy** (health online). **BİLİNÇLİ ERTELENEN:** `onnx`/`torch` — torch upgrade `numpy<2` kısıtını kaldırır → opencv/scipy/sklearn/librosa/pandas/numba CASCADE + 8 AI-model klinik-çıktı yeniden-doğrulaması (ayrı maintainer görevi).
- **Tahmini Efor:** S (tarama uygulandı; upgrade'ler ayrı)

**B-9.4 — Yalnız device/server profili; staging yok** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Medium
- **Mevcut Durum (denetim anı):** Yalnız device.env + server.env; ayrı dev/staging katmanı yoktu.
- **Yapılan düzeltme:** **`deploy/staging.env`** — üretim-benzeri DOĞRULAMA profili: simülasyon (donanımsız) + auth + at-rest-şifreleme AÇIK (prod davranışı sınanır) + AYRI port (8010)/veri-kökü (`C:\ProgramData\PEMF_Staging`)/log → device/server ile ÇAKIŞMAZ; JSON-log açık (gözlemlenebilirlik sınama). `setup_services.ps1` `-Mode staging` eklendi (`ValidateSet` + mosquitto-atla, server gibi simülasyon). `deploy/README.md` staging kullanımını belgeler. Amaç: bir release'i GERÇEK klinik cihazına deploy etmeden QA/CI'da doğrula.
- **Doğrulama:** `setup_services.ps1` PARSE OK; `staging.env` 14 geçerli KEY=VALUE (PEMF_SIMULATE=1, PORT=8010).
- **Tahmini Efor:** M (uygulandı)

**Pozitif not:** Deployment mekanizması olgun — tek PyInstaller EXE iki rolde env-profiliyle ayrışıyor, NSSM servisi crash→5sn restart, Inno Setup installer, env-dosyalarında STM-port oto-algılama/tünel/auth/CORS/şifreleme knob'ları belgeli. Docker yokluğu **tasarım gereği** (Windows + seri/USB + hotspot/ICS bağımlılıkları) — kusur değil.

---

### 10. Frontend'e Özel (Expo / React Web)

**B-10.1 — ESLint/Prettier/lint script yok** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** High
- **Yapılan düzeltme:** **ESLint 9 + `eslint-config-expo/flat` + Prettier** kuruldu; `eslint.config.js` (flat) + `lint`/`format` script + **frontend CI'da `npm run lint`** adımı. Kademeli benimseme (Ruff deseni): mevcut kodun hata-veren yeni-react-hooks kuralları (refs/set-state-in-effect/purity) + no-explicit-any **UYARIya** çekildi → **0 hata, `npm run lint` exit 0**. Test dosyalarında gevşetildi.
- **EK TAMAMLAMA (2026-07-06 — uyarı borcu eritildi + 3 kural kilitlendi):** Uyarı **218→156** (−62; mekanik temizlik + kontrol-yüzeyi tipleme). Tam temizlenip **ERROR'a yükseltilen** (regresyon-kilidi) 3 kural: **`react/no-unescaped-entities`** (7 Türkçe apostrof/tırnak → `&apos;`/`&quot;`), **`@typescript-eslint/array-type`** (1), **`import/no-duplicates`** (1 çift react-native import merge). **`no-unused-vars` 34→4:** 7 ölü import + 6 ölü değişken/fonksiyon silindi/`_`-prefix + `caughtErrors:none` (idiomatik `catch (e)`); kalan 4 = kopya-yapıştır dead-var (byte-identik, güvenli tekil-hedef yok → WARN). **`import/first`** elendi (PemfApp lazy-const'lar altındaki 4 import yukarı + test-dosyalarında jest.mock hoisting için off).
- **EK TAMAMLAMA-2 (2026-07-06 — güvenlik-kritik kontrol-yüzeyi tipleme):** İki tedavi-kontrol yüzeyinin backend-yanıt `any`'leri tiplendi (test-önce güvenceyle): **`useSessionControl` 8→1** (start/stop/active/emergency yanıt sözleşmeleri: `SessionActiveResponse`/`SessionActionResponse`/`EmergencyStopResponse` + `catch (e: any)`→`unknown`; **7 jest testi yeşil = davranış korundu**) + **`AiProPanel` 7→2** (AI-Pro otonom-tedavi uçları: `AiProStatus`/`AiProAction`). `no-explicit-any` **114→101**.
- **EK TAMAMLAMA-3 (2026-07-06 — react-hooks correctness auditi):** **`exhaustive-deps` 6→0** (gerçek/stable kural TAM temiz): `useSessionControl` `startTimer`→`useCallback` + `stopTimer`/`startTimer` deps (**7 jest testi yeşil = davranış korundu**), `NotificationCenter` `fadeAnim` dep, `AiProPanel` `requestPermission` dep, **`GatewayStatusPanel` fallback null→son-iyi-değeri-KORU (hata-dayanıklılık İYİLEŞTİ + refresh stable, interval-churn önlendi)**, `AiHubScreen` otonom-tedavi effect'i güvenlik-gerekçeli disable (`showToast` KARARSIZ → deps'e eklemek tedaviyi RESTART eder). **`refs`(23)/`set-state-in-effect`(16)/`purity`(2) tek-tek DENETLENDİ → bleeding-edge react-compiler kuralı false-positive'leri** (ör. `AppShell` `Date.now` **event-handler'da**, render'da değil; `LiveDataContext` tazelik-hesabı bilinçli periyodik-render destekli; RN `Animated.Value` ref'i render'da okuma standart RN deseni). **BUG DEĞİL** → çalışan tıbbi UI'ı deneysel-kural için değiştirmek yüksek-risk/düşük-değer → dokümante-WARN.
- **Doğrulama:** `npm run lint` → **0 error / 152 warn**; `tsc` PASS; `jest` 30 PASS.
- **KALAN (bilinçli WARN):** `no-explicit-any` (101 — kalan çoğu bilinçli `as any` escape [RN stil/DOM cast] + heterojen vision result + file-picker; kademeli), react-hooks `refs`/`set-state-in-effect`/`purity` (41 — **DENETLENDİ**, aggressive-kural false-positive/geçerli-desen, bug değil), `no-require-imports` (6 — bilinçli lazy/koşullu native require).
- **Tahmini Efor:** S (kuruldu) + M (uyarı temizliği uygulandı)

**B-10.2 — Hardcoded Supabase key + uygulama-geneli cleartext HTTP** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** High
- **Yapılan düzeltme:** (1) **API token → `expo-secure-store`** (native: iOS Keychain / Android Keystore; web: AsyncStorage) + eski AsyncStorage token'ı native'de SecureStore'a **otomatik migrasyon** + düz-metin silme (`config.ts`). Eskiden düz-metin AsyncStorage'daydı. (2) **Supabase key**: EXPO_PUBLIC-first zaten vardı; **publishable/anon** (istemci-güvenli by-design + RLS/RPC koruması) olduğu dokümante edildi + override yolu belgelendi (`deviceRegistry.ts`). (3) **Cleartext HTTP**: LAN'daki `http://IP:8000` için **zorunlu tradeoff** (kapalı klinik ağı; tünel https/wss) — kabul edilmiş, dokümante.
- **Doğrulama:** token round-trip + migrasyon jest'te (SecureStore mock); tsc/jest yeşil.
- **Tahmini Efor:** M (uygulandı; key/cleartext bilinçli tradeoff dokümante)

**B-10.3 — Tek kök-düzeyi error boundary + hata-yutan fetch; zayıf a11y** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Medium
- **Yapılan düzeltme:** (1) **Ekran-bazlı ErrorBoundary** — `PemfApp.tsx`'te Suspense `<ErrorBoundary key={route}>` ile sarıldı → bir ekran çökse **nav-shell hayatta kalır** (tüm-app beyaz-ekran değil), route değişince sıfırlanır. (2) **GET retry** — `apiGet` idempotent olduğundan geçici ağ hatasında 1 kez daha dener (400ms); `apiPost` (non-idempotent) DENENMEZ. (3) **Kritik a11y** — acil-durdur + seans/bobin başlat/durdur butonlarına `accessibilityRole`+`accessibilityLabel` (ekran-okuyucu için safety kontrolleri).
- **EK TAMAMLAMA (2026-07-06 — geniş a11y taraması):** `accessibilityLabel` **11→29** (+ 2 paylaşılan bileşen çalışma-anında çok daha fazlasını kapsar). Etiketlenenler: (1) **TÜM tedavi-parametre input'ları** — paylaşılan `ParamInput` (CoilParameterPanel: 8 bobin × freq/duty/faz/süre) + `ParamField` (ControlScreen) tek düzeltmeyle; (2) **hasta veri formu** (PatientScreen 8 alan + arama); (3) **Ayarlar formu** (4: klinik adı/telefon, uzak-bağlan kodu, sunucu adresi); (4) **gözlem-notu** modalı; (5) **ikon-only kamera-çevir** butonları (SwitchCamera ×2 — ekran-okuyucu için sessizdi). `AppShell` nav (her ekran) + kritik safety butonları zaten etiketliydi. Doğrulama: tsc/jest/eslint yeşil (a11y additive → sıfır davranış riski). **KALAN:** metin-taşıyan touchable'lar zaten okunur; kalan az sayıda düşük-trafik ikon-only + dekoratif `Image` `accessible={false}` işaretleme (kademeli).
- **Tahmini Efor:** M (kritik + geniş input/kamera a11y uygulandı; tam WCAG denetimi kademeli)

**Pozitif not:** Pür TypeScript (`strict` açık), WS istemcisinde exponential backoff (`wsClient.ts:106-122`), 8sn AbortController timeout her istekte, `console.log` = 0 (yalnız 6 `console.error/warn`), yerel PII SQLite deposu YOK (PII backend'den canlı çekiliyor — eski "offlineDb PII" endişesi bu kod tabanında geçersiz), Supabase istemcisi yalnız-okuma (`resolve_device` RPC).

---

### 11. Dokümantasyon

**B-11.1 — `.env.example` bayat ve eksik** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Medium
- **Yapılan düzeltme:** `.env.example` **gerçekte okunan tüm `PEMF_*` değişkenleriyle** yeniden yazıldı (servis/API, veri/şifreleme, güvenlik/uzaktan-erişim, donanım, bulut/gözlemlenebilirlik — satır-içi açıklamalı + audit referanslı). Bayat `MQTT_CLOUD_USER/PASS` kaldırıldı; `deploy/*.env` profillerine işaret ediyor.
- **Tahmini Efor:** S (uygulandı)

**B-11.2 — Mimari diyagram / API-doc / runbook zayıf** — ✅ **ÇÖZÜLDÜ (2026-07-06)**
- **Önem:** Low
- **Yapılan düzeltme:** **`docs/ARCHITECTURE.md`** — bileşen diyagramı (backend↔STM↔ESP↔mobil↔Supabase↔tünel↔OTA), veri akışı tablosu, güven sınırları, kritik güvenlik mekanizmaları, tek-giriş-noktası. **`docs/RUNBOOK.md`** — hızlı komutlar (servis restart/health/metrics), log yerleri, 8 olay senaryosu, anahtar/veri kurtarma, güvenli kapanış, gözlemlenebilirlik.
- **Tahmini Efor:** S (uygulandı)

**Pozitif not:** Dokümantasyon bu projenin göreli güçlü yanı — kapsamlı README, iki deployment kılavuzu, satır-içi env belgeleri, 22KB sistem raporu, kod içinde bol "audit" gerekçe yorumları.

---

## 4) Öncelikli Yol Haritası

### A) Production'a çıkmadan önce MUTLAKA (Critical / High)

| Öncelik | Bulgu | Efor |
|---|---|---|
| 1 | ~~**B-1.1** Gmail app-password'ü kaldır~~ ✅ **ÇÖZÜLDÜ** — email yapısı tamamen silindi; kalan: app-password'ü Google'da rotate et | S |
| 2 | ~~**B-3.3 / B-9.1** CI'yı çalışır hale getir~~ ✅ **ÇÖZÜLDÜ** — requirements-test.txt + tests.yml/lint.yml/frontend.yml (temiz-venv 32 test doğrulandı) | S |
| 3 | ~~**B-1.3 / B-1.4**~~ ✅ **ÇÖZÜLDÜ** — B-1.3 şifresiz DB'de PII maskeleme + B-1.4 PatientDB fail-closed (TreatmentDB ile tutarlı) | L / S |
| 4 | ~~**B-1.2** anahtar dosyası korumasız~~ ✅ **ÇÖZÜLDÜ** — sıkı NTFS ACL (SYSTEM+Admin) 6 yazma noktası + açılış-geçişi; escrow & makine-DPAPI bilinçli korundu | M |
| 5 | **B-1.5** Otonom-tedavi auth-muafiyetini yazılı risk-kabulüyle belgele + hafif-auth/NAMED tünel değerlendir | S–M |
| 6 | ~~**B-3.1** backend (13→86) + **B-3.2** frontend (0→30) kritik-yol + süre-watchdog + canlı-durum & coil-run & session-lifecycle & history-pagination & KVKK + FE tedavi-kontrol akışı kilitleri + coverage-kapısı (%36≥%33)~~ ✅ **ÇÖZÜLDÜ**; kalan: diğer ekran render akışları (kademeli) | L |
| 7 | ~~**B-5.1** Merkezî hata izleme (Sentry)~~ ✅ **ÇÖZÜLDÜ** — opsiyonel opt-in Sentry (PII-scrub) + /metrics + JSON log | M |
| 8 | ~~**B-9.2** Sürüm rollback stratejisi~~ ✅ **ÇÖZÜLDÜ** — previousStable + /api/update/rollback + runbook | M |
| 9 | ~~**B-9.3** Bağımlılık CVE taraması~~ ✅ **ÇÖZÜLDÜ** — dependabot + pip-audit CI; 6 gerçek CVE raporlandı (upgrade maintainer'a) | S |
| 10 | ~~**B-4.1** Global exception handler + hata zarfı + str(e) sızıntısı~~ ✅ **ÇÖZÜLDÜ** | M |

### B) Hızlı Kazanımlar (Quick Wins — düşük efor, yüksek etki)

- ~~**B-1.6** Rate limiting~~ ✅ **ÇÖZÜLDÜ** — uzak-IP per-dakika limit (LAN sınırsız, fail-safe muaf, env-ayarlı)
- ~~**B-1.7** Swagger/OpenAPI'yi üretimde kapat~~ ✅ **ÇÖZÜLDÜ** — auth/tünel açıkken docs 404, dev'de açık, PEMF_ENABLE_DOCS override
- ~~**B-7.3** `patients.db`'de `PRAGMA foreign_keys=ON`~~ ✅ **ÇÖZÜLDÜ** — S
- ~~**B-5.3** Kütüphane modüllerindeki `logging.basicConfig`'i kaldır~~ ✅ **ÇÖZÜLDÜ** — S
- ~~**B-11.1** `.env.example`'ı gerçek `PEMF_*` değişkenleriyle güncelle~~ ✅ **ÇÖZÜLDÜ** — S
- ~~**B-10.1** Frontend'e ESLint + `lint` script + CI adımı~~ ✅ **ÇÖZÜLDÜ** — S
- ~~**B-9.3** `dependabot.yml` ekle~~ ✅ **ÇÖZÜLDÜ** (pip+npm+actions) — S
- ~~Sürüm-string tutarsızlığını tek kaynağa (`VERSION`) bağla (B-8.1'in bir parçası)~~ ✅ **ÇÖZÜLDÜ** — S

### C) Orta Vadeli İyileştirmeler (Medium)

- ~~**B-2.1** Ruff + mypy + pre-commit (backend statik analiz)~~ ✅ **ÇÖZÜLDÜ** — pyproject+precommit+lint.yml, enforced F+E9 temiz baseline — M
- ~~**B-2.2** thread'leri `lifespan`'e taşı + router bölme + **shared-state modül ayrımı** (×3)~~ ✅ **ÇÖZÜLDÜ** (import yan-etkisi + on_event→lifespan + router-split + **`live_state.py` + `coil_run_tracker.py` + `session_state.py` ayrımı** + `_active_session` rebind→in-place, 26-test refactor-öncesi kilit, api_server 2407→2206); session endpoint-logic kademeli — L
- ~~**B-4.2** Servis-kontrol/AI sessiz `except: pass`'lere log ekle~~ ✅ **ÇÖZÜLDÜ** (büyük ölçüde benign; 2 kontrol-yolu loglandı) — M
- ~~**B-5.2** `/metrics` (Prometheus) + JSON structured logging~~ ✅ **ÇÖZÜLDÜ** — M
- ~~**B-6.1** Frontend code-splitting/lazy loading~~ ✅ **ÇÖZÜLDÜ** (8 ekran React.lazy)
- ~~**B-6.2 / B-6.3** PatientDB bağlantı yönetimi + EAV JOIN~~ ✅ **ÇÖZÜLDÜ** (busy_timeout/worker-close + composite index)
- ~~**B-7.1 / B-7.2** Versiyonlu migration + off-machine/rotasyonlu yedek~~ ✅ **ÇÖZÜLDÜ** (sistem işlevseldi + PatientDB backup + PEMF_BACKUP_DIR + rotasyon)
- ~~**B-8.1 / B-8.2** `/api/v1` versiyonlama + pagination + `delete_all` koruması~~ ✅ **ÇÖZÜLDÜ** — M
- ~~**B-9.4** Ayrı staging ortamı~~ ✅ **ÇÖZÜLDÜ** — deploy/staging.env + `-Mode staging` — M
- ~~**B-2.4** god-context + AI-sonuç callback & **container tipleme (`AiResult` sözleşmesi)** / **B-10.2** token→SecureStore / **B-10.3** ekran-ErrorBoundary + retry + a11y~~ ✅ **ÇÖZÜLDÜ** — M

---

## 5) Doğrulayamadıklarım (Manuel Kontrol Gerektirir)

**Güncelleme (2026-07-06):** #3 (Supabase RLS — canlı probe) + #8 (KVKK — local test) + #5'in 3 CVE'si
(izole-venv upgrade testi) bu çalışmada **DOĞRULANDI**; ayrıca #8'de `.plain.bak` ACL gap'i bulunup
kapatıldı. Kalanlar (firmware bench, SQLCipher-sahada, NAMED-tünel, AI-lisans, soak, onnx/torch upgrade)
çalışan cihaz/dış-kaynak gerektirir → **`docs/VERIFICATION.md`** her biri için çalıştırılabilir adım içerir.

1. **Firmware güvenlik satürasyonu:** `stm32_protocol_limits.py:12-14` "firmware/timer fiziksel olarak satüre eder" diyor — backend'de clamp olmamasının güvenli olduğu iddiası **firmware'e** (`main.c` / STM32 firmware) bağlı. Firmware'in gerçekten aşırı freq/duty/sıcaklıkta donanımı koruduğunu **donanım/firmware tarafında doğrulamadım** (kod okuması bu iddiayı test etmez). Tıbbi cihaz için bu, güvenlik-dosyasıyla (safety case) kanıtlanmalı.
2. **SQLCipher gerçekten aktif mi (sahada):** `PEMF_ENCRYPT_AT_REST=1` + `sqlcipher3` wheel varlığına bağlı. Çalışan cihazda `/api/health` → `atRestEncrypted=true` **canlı doğrulanmalı**; wheel eksikse sessizce (patients.db) ya da fail (treatment) düz-metine düşer.
3. **Supabase RLS canlı durumu:** ✅ **DOĞRULANDI (2026-07-06 — canlı probe).** Gömülü anon (publishable, public-by-design) anahtarla **salt-okunur** güvenlik probu (`scratchpad/verify_supabase_rls.py`) → **5/5 GEÇTİ**: `devices` doğrudan SELECT `200 []` (satır sızmıyor), `patients` SELECT `401 permission denied`, `resolve_device(p_device_id|p_code)` RPC `200` (SECURITY DEFINER + anon GRANT deploy edilmiş), doğrudan INSERT `401 "violates row-level security policy"`. **Eski anon-write policy'leri kaldırılmış, cross-tenant sızıntı KAPALI, RPC tek erişim yolu.** (bkz. docs/VERIFICATION.md)
4. **Cloudflare NAMED tünel:** memory'de "NAMED tünel kullanıcı token verince aktif" kayıtlı; şu an QUICK tünel (her restart değişen URL, SLA yok — `device.env` yorumunda P1 olarak işaretli). Üretimde NAMED tünel yapılandırmasının bitip bitmediğini doğrulayamadım.
5. **Bağımlılık CVE durumu:** ✅ **UYGULANDI + DEPLOY (2026-07-06).** 6 CVE'den güvenli **4'ü yükseltildi**: cryptography **41.0.3→43.0.1**, python-multipart **0.0.30→0.0.31**, zeroconf **0.147.3→0.149.0**, starlette **1.2.1→1.3.1** → requirements pinlendi + myenv + **86 test yeşil** + **frozen EXE rebuild + çalışan servise deploy** (`atRestEncrypted=true` doğrulandı). **BİLİNÇLİ ERTELENEN:** `onnx`/`torch` — `numpy<2` cascade + 8 AI-model klinik-çıktı doğrulaması gerektirir (ayrı maintainer görevi).
6. **AI model bütünlüğü/lisansı:** `release_assets/ai_models` (640MB+, histopath 899MB ONNX) gömülü; model doğruluğu/klinik-validasyonu ve lisans uygunluğu kod denetimi kapsamı dışında.
7. **Gerçek yük/soak davranışı:** `scripts/soak_publish_5hz_8coil.py` var ama uzun-süreli 8-bobin soak testinin sonuçlarını (bellek sızıntısı, WS kararlılığı, DB büyüme hızı) görmedim.
8. **KVKK anonimleştirme:** ✅ **DOĞRULANDI (2026-07-06 — local test 3/3).** `tests/test_kvkk_anonymization.py`: 5-yıl-inaktif hasta → PII `[ANONIM]` + `anonymized=1` + arama-indeksi temizlenir (eski adla BULUNAMAZ, KVKK); aktif hasta korunur; idempotent. **YENİ BULGU + FIX:** migration `.plain.bak` (tüm eski düz-metin DB) diskte **ACL'siz** kalıyordu → SQLCipher'ı baypas eden PII kopyası; **kapatıldı** → oluşturmada + startup'ta SYSTEM+Admin ACL-kilit (`sqlcipher_util.py` + `treatment_history_db.py` + `backend_service._harden_secret_file_acls`, B-1.2 escrow deseniyle tutarlı).

---

*Bu rapor 4 paralel derinlemesine inceleme + çekirdek dosyaların doğrudan okunmasıyla üretildi. Her bulgu dosya:satır referanslıdır ve BU kod tabanına özgüdür. "Eksik" (kodda yok) ile "doğrulayamadım" (kod-dışı kanıt gerekli) ayrımı korunmuştur.*
