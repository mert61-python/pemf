# Ölü Kod (Dead Code) Tespit ve Temizlik Raporu

**Kapsam:** `guii/` (Python backend) + `frontend → C:\Users\merta\pf` (React Native/Expo)
**Tarih:** 2026-07-06
**Yöntem:** import-grafiği reachability + `vulture` (Python) + `ts-prune`/`knip`/`depcheck` (frontend), ardından her aday için `grep` ile dinamik/koşullu referans doğrulaması.
**İlke:** Tıbbi cihaz → "temiz" = "sıfır risk". Erişilemez olduğu **kanıtlanamayan** hiçbir şey silinmedi. Bu rapor hem **plan** hem **yürütme günlüğü**dür (§7): onaylanan A/B/C **UYGULANDI (9 izole commit, 2026-07-06)**, D listesine dokunulmadı, tablolarda ✅/🔒/⏸️/🔄 ile işaretlendi.

> **Bağımsız 2. geçiş doğrulaması (2026-07-06):** Rapordaki bulgular sıfırdan bağımsız yeniden üretildi — AST import-grafiği (136 kaynak .py; 43 orphan → 36'sı `ai_hub` dinamik-dispatch [korundu], 7 non-ai_hub aday), `vulture --min-confidence 60`, ve her aday için `grep` 0-referans kontrolü. **Temel durum YEŞİL:** `PEMF_SIMULATE=1` import-smoke temiz + **86/86 test geçti** (raporun "13 test"i büyümüş). `ai/config.py`'nin canlılığı ayrıca doğrulandı (`api_server.py:953` → `from ai.hybrid_recommender import …` → paket `__init__` → `config`). **Yeni ek bulgu:** `database/session_manager.py`'de 6 referanssız ince-sarmalayıcı method (aşağıda 2B'ye eklendi). `services/mdns_service.py:153 NonUniqueNameException` = vulture yanlış-pozitifi (3 gerçek ref → **DOKUNMA**).

---

## 0. Kritik bağlam — ÖNCE OKU

- **Çalışma ağacı temiz DEĞİL.** Backend deposunda **160**, frontend deposunda (`C:\Users\merta\pf`, branch `main`) **53** commit'lenmemiş değişiklik var (devam eden `production-hardening` çalışması). Zaten silinmiş bir sürü ölü dosya da bu diff içinde (ör. `utils/config_manager.py`, `utils/email_sender.py`, `services/ble_provisioner.py`, `threads/`).
- **Sonuç:** Herhangi bir silme, **yalnızca hedef dosya `git add` edilerek** ayrı commit'e alınmalı; toplu `git commit -a` KESİNLİKLE yapılmamalı (160/53 dosyalık WIP'i içine çeker).
- Bu yüzden aşağıdaki **A** maddeleri bile "silmeye hazır" olarak işaretlendi ama **onayınız beklenerek** commit'lenmedi.

---

## 1. Giriş Noktaları (Entry Points) — reachability kökleri

| Tür | Giriş | Not |
|---|---|---|
| Servis ana | `backend_service.py::main` | NSSM servisi bunu çağırır; tüm alt sistemleri lazy `import` ile bağlar |
| Çekirdek | `headless_core.py` | Donanım + servis orkestrasyonu |
| PyInstaller | `build_tools/PEMF_Backend_onedir.spec` / `…_onefile.spec` | `hiddenimports`, `hookspath=[spec_dir]` (→ `hook-*.py` isimle bulunur), `pemf_gui` **exclude EDİLMEZ** |
| CLI araçları | `services/credential_manager.py` (`python -m …`), `scripts/*.py` | Kendileri birer giriş noktası |
| Servis PS | `scripts/install_backend_service.ps1`, `setup_services.ps1`, `start_hotspot.ps1`, `publish_release.ps1` | |
| Frontend | `expo-router/entry` (package.json `main`) → `app/` dosya-tabanlı routing (oto-kayıt) | `app/*.tsx` "import edilmiyor" görünür ama CANLI |
| Testler | `tests/*.py` | Meşru tüketici |

Import-grafiği reachability: **75 kaynak .py**, **63 erişilebilir**, **12 aday-orphan** (aşağıda birer birer çözümlendi — 8'i yanlış-pozitif).

---

## 2. Envanter Tablosu

Güven: **A** = kesin ölü + güvenli · **B** = muhtemelen ölü (onay gerek) · **C** = legacy/superseded · **D** = DOKUNMA.

### 2A. Backend — bütün-dosya orphan adayları

| **durum** | dosya | doğrulama | güven | öneri |
|---|---|---|---|---|
| ✅ **`tools/`'a taşındı** (`8558b3f`) | `ai/generate_test_data.py` | `__main__` var, standalone test-verisi üreteci; runtime import etmiyor | **C** | → `tools/generate_test_data.py` |
| ✅ **`tools/`'a taşındı** (`8558b3f`) | `utils/com_sniffer.py` | `__main__` var, seri-port debug aracı | **C** | → `tools/com_sniffer.py` |
| ✅ **`tools/`'a taşındı** (`8558b3f`) | `utils/organize_resources.py` | `__main__` var, kaynak-düzenleme build yardımcısı | **C** | → `tools/organize_resources.py` |
| ✅ **`tools/`'a taşındı** (`8558b3f`) | `utils/stm32_simulator.py` | `__main__` var; runtime `PEMF_SIMULATE` simülasyonu AYRI (`api_server.py`), bu dosya DEĞİL | **C** | → `tools/stm32_simulator.py` |

### 2B. Backend — canlı modül içindeki ölü fonksiyon/method adayları (vulture, `grep` ile 0-referans doğrulandı)

| **durum** | dosya | sembol | doğrulama |
|---|---|---|---|
| ✅ **kaldırıldı** (`413a811`) | `event_bus.py` | `_call_qt_callback` | 0 ref; PyQt→headless göçünden Qt-shim kalıntısı |
| ✅ **kaldırıldı** (`413a811`) | `event_bus.py` | `get_event_history` | 0 ref (kaynak+test); diagnostik |
| ✅ **kaldırıldı** (`413a811`) | `event_bus.py` | `get_stats` | 0 ref; diagnostik |
| ✅ **kaldırıldı** (`413a811`) | `event_bus.py` | `clear_history` | 0 ref; diagnostik |
| 🔒 **KORUNDU** (kullanıcı kararı) | `pemf_gui/__init__.py` | `get_icon_path` | Kullanıcı WIP'inde 3 kardeş helper'ı sildi ama bunu **bilinçli tuttu** → dokunulmadı |
| 🔒 **KORUNDU** (tutarlılık) | `utils/path_utils.py` | `get_icon_path` | pemf_gui eşiyle birlikte tutuldu |
| ✅ **kaldırıldı** (`bc1d047`) | `utils/production_config_manager.py` | `set_many` | 0 ref (kaynak+test) |
| ✅ **kaldırıldı** (`bc1d047`) | `utils/production_config_manager.py` | `reload` | 0 ref |
| ✅ **kaldırıldı** (`bc1d047`) | `utils/production_config_manager.py` | `get_user_config_path` | 0 ref |
| ✅ **kaldırıldı** (`bc1d047`) | `utils/production_config_manager.py` | `get_config_value` | 0 ref (rapordaki `__main__` demosu aslında YOKTU → tamamen ölü) |
| 🔒 **SAKLANDI** (öneri) | `utils/secrets_manager.py` | `set_secret` | Gelecekteki sır-yazma API'si niyetli → silinmedi |
| ✅ **kaldırıldı** (`0a7a118`) | `services/headless_services.py` | `update_bridge_status` | 0 ref; atıl HiveMQ-bridge setter'i |
| ✅ **kaldırıldı** (`f43e128`) | `database/session_manager.py` | `set_frequency`/`set_intensity`/`set_pulse_duration`/`set_treatment_duration` | 0 ref; `add_parameter` sarmalayıcıları (güvenlik/dozaj mantığı YOK) |
| ✅ **kaldırıldı** (`f43e128`) | `database/session_manager.py` | `is_session_active` / `get_current_session_id` | 0 ref; trivial yardımcı/getter |

> Not: `services/credential_manager.py:123 get_credential` vulture'da çıktı ama dosya bir **CLI aracı** (giriş noktası); iç methodu agresif silinmemeli → **D/sakla**.
> Not: `database/session_manager.py`'nin 6 sarmalayıcısı **güvenlik/dozaj mantığı içermez** (yalnız `add_parameter`'a delegasyon / alan döndürme). Yine de dozaj modülünde oldukları için **B/onay** — istenirse "seans API'si tam kalsın" diye tutulabilir.

### 2C. Frontend — bütün-dosya ölü adayları (knip/ts-prune, grep doğrulandı)

> **Not:** frontend commit'leri `pf` reposu; `chore/dead-code-cleanup` branch'inde toplandı → **`main`'e ff-merge edildi (2026-07-06)**, branch silindi. `main` çalışma-ağacı WIP'i (53) tam korundu; `tsc --noEmit` dangling-ref yok.

| **durum** | dosya | sembol | doğrulama |
|---|---|---|---|
| 🔄 **GEÇERSİZ — SİLİNMEDİ** | `src/components/domain/RemoteConnectionPanel.tsx` | tüm bileşen | Rapor "ölü" diyordu ama **artık DEĞİL**: kullanıcı aktif yeniden yazıyor (141/139 WIP) + `SettingsScreen.tsx` referans veriyor → canlı geliştirme, statik damgayı geçersiz kıldı |
| ✅ **silindi** (`a85704d`) | `src/components/visual/Sparkline.tsx` | tüm dosya | 0 importer; canlı grafik `RealtimeChart` |
| ✅ **silindi** (`a85704d`) | `src/screens/PlaceholderScreen.tsx` | tüm dosya | 0 importer; router gerçek ekranları kullanıyor |
| ✅ **silindi** (`edec423`) | `src/context/ExpertModeContext.tsx` | `ExpertModeProvider`, `useExpertMode` | 0 importer; yerine `UserModeContext` |
| ✅ **fonksiyon kaldırıldı** (`fff7df7`) | `src/services/updates.ts` | `getAppVersion` | 0 dış ref; dosya SAKLANDI (gerisi UpdateBanner'da canlı, `APP_VERSION` 4 yerde) |
| ✅ **kısmi** (`8ad811c`) + 🔒 | `src/types/domain.ts` | ✅ `CoilCommand`, `KpiStats` kaldırıldı · 🔒 `PatientSummary`/`Patient`/`TreatmentSession`/`SystemInfo`/`SensorDataPoint` **KORUNDU** | Rapor fazla agresifti: korunanlar `DashboardSnapshot`/`CoilSensorHistory`/`Patient` (CANLI) tarafından **iç-referanslı**; yalnız `CoilCommand`+`KpiStats` gerçekten 0 iç/dış ref |

### 2D. Frontend — kullanılmayan bağımlılıklar (depcheck/knip, grep doğrulandı)

> **Durum:** kullanıcı onayıyla ("yap boşver") **UYGULANDI (2026-07-06)** — `npm uninstall … --legacy-peer-deps` + `npm install -D @types/node`. Mevcut src'de 0 kullanım son kez doğrulandı (offlineDb geri gelmemiş). `pf@main` çalışma-ağacında **commit EDİLMEDİ** (senin aktif `package.json`+`package-lock.json` WIP'inle aynı dosyalar; senin dep-commit'ine dahil olacak). `tsc --noEmit` temiz.

| **durum** | bağımlılık | doğrulama | güven |
|---|---|---|---|
| ✅ **kaldırıldı** (working tree) | `uuid` | `from "uuid"` hiç yok | **A** |
| ✅ **kaldırıldı** | `@types/uuid` | `uuid` ile eşleşen | **A** |
| ✅ **kaldırıldı** | `react-native-get-random-values` | `uuid` polyfill'i; side-effect import yok | **A** |
| ✅ **kaldırıldı** | `expo-sqlite` | kaynakta 0; `offlineDb.ts` KVKK audit'te silinmiş, geri gelmemiş → emekli | **B/C** |

**Eksik bağımlılık (bug):** ✅ `@types/node@^26.1.0` **eklendi** (`tsconfig.json "types":["node"]` artık karşılanıyor; tsc node tiplerini buluyor).

---

## 3. (D) DOKUNMA Listesi — ölü GÖRÜNÜR, DEĞİLDİR

| öğe | neden dokunulmaz |
|---|---|
| **Tüm FastAPI route handler'ları** (`api_server.py`, `ai_router.py`, `history_router.py`, `patient_router.py`, `settings_router.py`, `update_router.py` — vulture'ın "unused function" dediği ~60 fonksiyon: `health_check`, `websocket_endpoint`, `analyze_*`, `control_single_coil`, `emergency_stop`, `get_kpi_summary`, …) | Decorator (`@app.get/@router.post`) ile KAYITLI; statik araç "çağrılmıyor" görür. Public API yüzeyi — frontend + OTA reposu tüketir |
| `servers/api_server.py` **middleware/exception handler'ları** (`_auth_middleware`, `_rate_limit_middleware`, `_unhandled_exception_handler`, `_validation_exception_handler`, `add_security_headers`) | ASGI middleware / `add_exception_handler` ile kayıtlı |
| **Süre-watchdog** `api_server.py:~1464` | Güvenlik: bobin süre aşımı koruması. Bilerek "pasif görünür" |
| **Acil durdurma / fail-closed / şifreleme** yolları (`emergency_stop`, `_safe_stop_outputs`, `_force_auth_for_tunnel`, `sqlcipher_util`, `file_acl`) | Güvenlik/hasta güvenliği; insan onayı olmadan asla |
| **Auth-muaf uçlar** `servers/auth.py:25-32` (`emergency_stop`, `/health`, `/discovery`, `/simulator`, `/static`…) | Bilinçli fail-safe/keşif muafiyeti (memory: sahibin açık kararı) |
| **Starlette monkeypatch** `servers/ai_router.py:26-46` | Garip görünür, KRİTİK; kaldırılırsa AI router bozulur |
| **8 ONNX model dispatcher'ları** (`ai_hub/` — zaten kapsam DIŞI) + `ai/hybrid_recommender` (dinamik `from ai.hybrid_recommender import …`) | İsim/config ile yüklenir; statik araç göremez |
| **Donanım-koşullu yollar**: `PEMF_SIMULATE` (`api_server.py:1440,1734`), STM-seri vs ESP-MQTT, `utils/coil_map.py` yönlendirmesi, `utils/stm32_protocol_limits.py` | Hangi dalın canlıda çalıştığını statik araç bilmez |
| **Package `__init__.py`'ler** (`ai`, `database`, `services`, `utils`, `pemf_gui`) | Paket işaretçisi + re-export; submodule import'u init'i çalıştırır (orphan DEĞİL) |
| `ai/config.py` | `ai/__init__.py` içinde `from . import config` → `ai.hybrid_recommender` yüklenince transitif import edilir |
| `build_tools/hook-paho.mqtt.py` | PyInstaller hook; `hookspath=[spec_dir]` ile İSİMLE bulunur, import edilmez |
| `services/credential_manager.py` | Standalone ESP provizyon CLI aracı (`python -m services.credential_manager`) — giriş noktası |
| `frontend/src/services/therapyLimits.ts` → `THERAPY_LIMITS`, `clampParam` | **Güvenlik-kritik**; modül-içi `clampTherapyParams` ile CANLI (`ControlScreen`, `CoilParameterPanel`). Yalnız fazlalık `export` sözcüğü kullanılmıyor |
| `frontend` `app/_layout.tsx`, `app/index.tsx` | Expo Router giriş noktaları — oto-kayıt |
| `expo-build-properties`, `expo-system-ui` (deps) | `app.json` plugin / native build-time; import değil |
| Pydantic modelleri (yalnız serialization/schema) | FastAPI request/response şeması olarak kullanılır |
| Test fixture'ları, `conftest.py` | Test altyapısı |

---

## 4. Özet — silinecek vs ertelenen

| Kategori | Adet | SONUÇ (2026-07-06) |
|---|---|---|
| **A** — frontend ölü dosya | 4 dosya | ✅ **3 silindi** (Sparkline, PlaceholderScreen, ExpertModeContext) · 🔄 RemoteConnectionPanel **canlıydı → SİLİNMEDİ** |
| **B** — backend ölü fonksiyon | ~17 | ✅ **15 kaldırıldı** (event_bus 4, pcm 4, headless 1, session_manager 6) · 🔒 `get_icon_path`×2 + `set_secret` **korundu** |
| **B** — frontend ölü export | 3 kalem | ✅ `getAppVersion` + `domain.ts` `CoilCommand`/`KpiStats` kaldırıldı · 🔒 5 iç-referanslı tip korundu |
| **C** — backend dev-tool | 4 dosya | ✅ **`tools/`'a taşındı** |
| **dep temizliği** (uuid kümesi, `expo-sqlite`, `@types/node`) | 5 | ✅ **UYGULANDI** (npm, working tree; senin dep-commit'inle gider) |
| **D** — DOKUNMA | ~70+ sembol | Hiç dokunulmadı |

**Uygulandı: 9 commit** (5 backend `production-hardening` + 4 frontend `pf@main`, ff-merge). **Bilinçli korundu: 8 sembol** (get_icon_path×2, set_secret, RemoteConnectionPanel, 5 domain tipi). **Ertelendi: dep temizliği** (package.json WIP sonrası tek geçişte). **D listesine hiç dokunulmadı.** Her adım tekil `git add`/`--only` (+ backend'de stash-izolasyon) → **86-test/import + tsc** ile korundu; **iki reponun da WIP'i tam korundu.**

---

## 5. Önerilen güvenli silme sırası (onaylarsanız)

Her adım = ayrı commit, yalnız ilgili dosya `git add` edilir; her commit sonrası: `python -c "import backend_service"` + `PEMF_SIMULATE=1` boot-smoke + `pytest tests` yeşil kalmalı.

1. **(A) Frontend ölü dosyalar** — `RemoteConnectionPanel.tsx`, `Sparkline.tsx`, `PlaceholderScreen.tsx` sil; `tsc --noEmit` yeşil.
2. **(A) Frontend dep kümesi** — `uuid` + `@types/uuid` + `react-native-get-random-values` `package.json`'dan çıkar.
3. **(C) Backend dev-tool orphan'lar** — `com_sniffer.py`, `organize_resources.py`, `generate_test_data.py`, `stm32_simulator.py` (silme YERİNE `tools/`e taşıma önerilir).
4. **(B) Backend ölü fonksiyonlar** — `event_bus` Qt/diagnostik 4 method, iki `get_icon_path`, `production_config_manager` 4 yardımcı, `headless_services.update_bridge_status`. (`secrets_manager.set_secret` **SAKLA**.)
5. **(B) Frontend** — `ExpertModeContext` (feature-flag teyidi sonrası), `getAppVersion`, kullanılmayan `domain.ts` tipleri.

**İnsan kararı bekleyen açık maddeler:** `expo-sqlite` gerçekten emekli mi (offlineDb yeniden gelir mi) · `set_secret` gelecekteki sır-yazma API'si olarak tutulsun mu · `event_bus` diagnostik methodları debug için tutulsun mu · `RemoteConnectionPanel.tsx` gerçekten ölü mü (aktif düzenleniyor).

---

## 7. Yürütme Günlüğü — SON DURUM (2026-07-06)

Kullanıcı onayı: **A + B + C** (C→`tools/`'a taşı). Kullanıcı ayrıca *"klasörün yedeğini aldım, bulguları uygulamaya devam et"* dedi → WIP-çakışması endişesi kalktı.

**Yöntem (temiz izolasyon):** her hedef dosyanın WIP'i `git stash push -- <dosya>` ile bir kenara alındı → ölü kod **temiz HEAD** üzerinde çıkarıldı → `git commit --only -- <dosya>` (izole, WIP-siz commit) → `git stash pop` ile WIP geri yüklendi. **Tüm pop'lar ÇAKIŞMASIZ**; 46 dosyalık staged WIP hiç dokunulmadı. (Doğrulama §6'da.)

### ✅ Uygulanan commit'ler (her biri: py_compile + import + pop-sonrası temiz)

| # | Commit | Kat. | İçerik | Δ |
|---|---|---|---|---|
| 1 | `8558b3f` | **C** | 4 dev-tool → `tools/` (`git mv`): com_sniffer, organize_resources, generate_test_data, stm32_simulator | taşındı |
| 2 | `413a811` | **B** | `event_bus`: `_call_qt_callback` (Qt-shim) + `get_event_history`/`get_stats`/`clear_history` (diagnostik) | −46 |
| 3 | `bc1d047` | **B** | `production_config_manager`: `set_many`/`reload`/`get_user_config_path`/`get_config_value` | −32 |
| 4 | `0a7a118` | **B** | `headless_services`: `update_bridge_status` (atıl HiveMQ-bridge setter'i) | −5 |
| 5 | `f43e128` | **B** | `session_manager`: 4× `set_*` sarmalayıcı + `is_session_active`/`get_current_session_id` | −24 |
| 6 | `a85704d` | **A** | `Sparkline.tsx` + `PlaceholderScreen.tsx` silindi | −59 |
| 7 | `edec423` | **A/B** | `ExpertModeContext.tsx` silindi (0 importer; `UserModeContext` yerine geçmiş) | dosya |
| 8 | `8ad811c` | **B** | `domain.ts`: `CoilCommand` + `KpiStats` (iç-referanslı 5 tip KORUNDU) | −19 |
| 9 | `fff7df7` | **B** | `updates.ts`: `getAppVersion` (dosya + `APP_VERSION` korundu) | −4 |

> Commit 6–9 = frontend (`pf` reposu). Bu dosyalar WIP'siz (temiz) olduğundan stash gerekmedi — doğrudan `git add`+commit, her biri sonrası `tsc --noEmit` temiz. Sonra `chore/dead-code-cleanup` → **`main`'e ff-merge** edildi, branch silindi.

**Kümülatif doğrulama:** backend `PEMF_SIMULATE=1` import OK + **86/86 test** (her B commit'i sonrası); frontend `tsc --noEmit` dangling-ref yok. **Toplam 9 commit** = 5 backend (`production-hardening` HEAD=`f43e128`) + 4 frontend (`pf@main` HEAD=`fff7df7`, ff-merge). Her iki reponun **çalışma-ağacı WIP'i tam korundu** (backend 46 staged; pf@main 53 değişiklik).

### ⏸️ Bilinçli UYGULANMADI (silinmedi) — gerekçesiyle

| Öğe | Neden |
|---|---|
| `get_icon_path` ×2 (pemf_gui + path_utils) | Kullanıcı `pemf_gui/__init__.py` WIP'inde 3 kardeş helper'ı sildi ama bunu **bilinçli TUTTU** → kararına saygı |
| `secrets_manager.set_secret` | **SAKLA** (gelecekteki sır-yazma API'si niyetli) |
| **`RemoteConnectionPanel.tsx`** (rapor "A/ölü" idi) | **VERDİKT GEÇERSİZ: artık ÖLÜ DEĞİL.** Kullanıcı aktif **yeniden yazıyor** (141/139 WIP) + `SettingsScreen.tsx` referans veriyor → **SİLME** |

> **Güncelleme:** dep temizliği (uuid kümesi + `expo-sqlite` çıkar / `@types/node` ekle) sonradan kullanıcı onayıyla **UYGULANDI** (§2D) — `pf@main` working tree'de, commit'lenmedi (kullanıcının dep WIP'iyle birlikte gidecek).

---

## 6. Bağımsız Doğrulama Eklentisi (2026-07-06 — ikinci geçiş)

Rapordaki bulgular bağımsız bir statik-analiz geçişiyle **çapraz doğrulandı**. Sonuç: rapor **isabetli**; aşağıdaki üç ek yalnızca güveni artırır ve iki tartışmalı kararı KANITLA teyit eder.

### 6.1 Yeşil taban (doğrulama referansı) — ÖLÇÜLDÜ
- **Doğru yorumlayıcı: `myenv/Scripts/python.exe` = Python 3.10.2** (all deps: numpy 1.26.4, cv2, fastapi, onnxruntime). Store Python 3.9 kodu **import bile edemez** (`ai_router.py:100` PEP 604 `int | None`).
- `PEMF_SIMULATE=1` import smoke → **IMPORT OK**.
- `pytest tests` → **86 passed** (raporun "13 test"i bayat; güncel süit 19 dosya). Her silme sonrası bu iki kontrol yeşil kalmalı.

### 6.2 `ai_hub/` derin canlılık kanıtı (raporda "kapsam dışı" idi → şimdi kanıtlandı)
- **15 model alt-dizininin TAMAMI LIVE.** Dispatcher `servers/ai_router.py`, route handler'ları içinde lazy `from ai_hub.X import Y`. **Güvenle-kaldırılabilir ai_hub dizini YOK.**
- **Düzeltme:** `inference_petri_dish` eski/superseded DEĞİL — `inference_em_petri` ile **zincirli** (CV frontend `petri_cv/pipeline.py:48` → EM regressor). İkisi de canlı ve birbirine bağımlı; biri silinirse `/api/ai/vision/em_petri` bozulur.
- `cat_segmentation` & `feline_reticulocytes` dizinleri `.onnx` ağırlıklarıyla canlı (`ultralytics.YOLO(path)`); yalnız içlerindeki `inference_*.py` **CLI-only** scriptleri import edilmiyor → **B** (düşük kazanç, model diziniyle shipleniyor; kaldırmayı önermiyorum).

### 6.3 İki tartışmalı kararın KANIT'la teyidi (ikisi de DOKUNMA)
- **`ai/config.py` → KEEP (D).** `ai/__init__.py`: `from . import config` + `__all__ = ["config"]`. Canlı `ai.hybrid_recommender` yüklenince paket init'i çalışır → `ai.config` transitif import edilir. (İlk grep `from ai.config` deseni aradığı için kaçırmıştı; göreli-import formu.) → **Rapordaki D sınıflandırması doğru.**
- **`services/credential_manager.py` → KEEP (D).** ESP-coil **MQTT kimlik provizyon CLI'ı** (`python -m services.credential_manager provision --all`; `get_or_create_esp_credential`, `export_esp_secrets`). `secrets_manager` (uygulama sırları) ile **superseded DEĞİL** — farklı sorumluluk (broker/donanım kimlikleri). Giriş noktası + güvenlik-adjacent. → **Silme.**

### 6.4 Net durum
**Uygulandı: 9 izole commit** (§7 — 5 backend + 4 frontend). Ölü kod kaldırıldı/`tools/`'a taşındı; her adım tekil `git add`/`--only` (+ stash-izolasyon) → **86-test/import + tsc** ile korundu, iki reponun WIP'i tam korundu. **D listesine hiç dokunulmadı.** Tek ertelenen blok: `package.json` dep temizliği (aktif lockfile WIP sonrası).
