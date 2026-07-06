# REFACTOR_LOG — ne nereye taşındı (eşleme günlüğü)

Davranış-koruyan refactor. Her adım: kaynak → hedef + doğrulama. **Sıfır davranış değişikliği** ilkesi.

## Faz 0 — Güvenlik ağı (2026-07-06, commit `4cea676`)
- `REFACTOR_PLAN.md` + `tests/test_route_contract.py` (67-route golden-master). **Kod değişmedi** — yalnız test + plan. 87 test yeşil.

## Faz A — `system_router` (2026-07-06)

**Adım A1:** 4 status/sistem ucu `api_server.py` → **`servers/system_router.py`** (yeni `APIRouter`).

| Handler | Yol (DEĞİŞMEDİ) | Paylaşılan-state erişimi (lazy-import `servers.api_server`) |
|---|---|---|
| `system_info` | `GET /api/system/info` | `_APP_VERSION`, `state.core` |
| `gateway_status` | `GET /api/gateway/status` | `_live_state`, `_live_state_lock`, `state.core` |
| `get_dashboard_snapshot` | `GET /api/dashboard-snapshot` | `_build_ws_snapshot()` |
| `clear_notifications` | `POST /api/notifications/clear` | `_live_state`, `_live_state_lock`, `_ws_broadcast_sync()` |

- **Yöntem:** paylaşılan runtime durumu çağrı-zamanı `from servers import api_server as _api` ile okunur (circular import yok; api_server router'ı include eder, router app'i yalnız handler çağrılınca import eder).
- **api_server.py:** −77 satır (2206 → 2129). `include_router(system_router)` eklendi.
- **Doğrulama:** `py_compile` + import OK · **route-contract golden (67 route) birebir** · **87 test yeşil**.
**Adım A2:** `health` + `favicon` + `discovery` → `servers/system_router.py`. **Önce characterization:** `tests/test_status_shapes.py` (5 uç response anahtar-kümesini dondurur — özellikle `/api/health` `atRestEncrypted`/`status`, kurulum-doğrulaması için kritik).

| Handler | Yol (DEĞİŞMEDİ) | Lazy-import erişimi | Not |
|---|---|---|---|
| `health_check` | `GET /api/health` | `state.core`, `_app_data_dir()` | auth-muaf (path bazlı → korunur); shape testli |
| `favicon` | `GET /favicon.ico` | — (trivial) | auth-muaf |
| `discovery_info` | `GET /api/discovery` | `_APP_VERSION` | auth-muaf; shape testli |

- **api_server.py:** −61 satır daha. `metrics` (`GET /metrics`) BIRAKILDI (ağır coupling: `_session_lock`/`_active_session`/`_ws_lock`/`_ws_clients` → ayrı observability pass).
- **Doğrulama:** compile+import OK · route-contract (67) · **response-shape golden (health/discovery/system_info/gateway/kpi)** · **92 test yeşil**.
**Adım A3:** `kpi/summary` (~100 satır SQL) → `system_router.py`. **Byte-exact** çıkarıldı (script ile; yalnız `@app`→`@router`, lazy-import ekle, `_get_treatment_db()`→`_api._get_treatment_db()` — SQL/mantık birebir). Shape zaten `test_status_shapes.py`'de kilitli. api_server.py **−102 satır**. 92 test yeşil.

- **Kalan system-ish:** yalnız `metrics` (`GET /metrics`; ağır coupling → ayrı observability pass'te).

## Faz B — `session_router` (2026-07-06) — SAFETY-ADJACENT, dikkatli

**Önce characterization:** `tests/test_session_char.py` (2 test) — `session/notes` fallback response shape + `session/active` read-only invariant. (`session/notes` mevcut testlerde KAPSANMIYORDU.)

**Adım B1:** `session/active` + `session/notes` (+ `SessionNotesPayload`) → **`servers/session_router.py`**. Byte-exact (script + **word-boundary** `_api.` prefix — `get_active_session` gibi fonksiyon adlarını mangle etmeden).

| Handler | Yol (DEĞİŞMEDİ) | Lazy-import erişimi |
|---|---|---|
| `get_active_session` | `GET /api/session/active` | `_session_lock`, `_active_session` (**salt-okunur**; global MUTATE yok — watchdog STOP korunur) |
| `save_session_notes` | `POST /api/session/notes` | `_app_data_dir`, `_session_lock`, `_active_session`, `_sensor_sample_buffer(_lock)`, treatment-DB |

- **"Dikkatli" ile YAKALANAN regresyon:** `test_live_state::test_get_active_session_is_readonly_on_expiry`, `api_server.get_active_session`'i **doğrudan** (HTTP değil) çağırıyordu → taşınınca `AttributeError`. Test yeni konuma yönlendirildi (`session_router.get_active_session`; davranış/güvenlik-invariant birebir). `test_session_char` state-bağımsız sağlam invariant'a çevrildi.
- **api_server.py:** −89 satır. **94 test yeşil** (route-contract + shape + session-char + 9 mevcut session testi).
- **🔒 KARAR (human-review sonrası): `session/start` + `session/stop` api_server.py'de BIRAKILDI (bilinçli).** Değerlendirme: `session/start` ~170 satır, **8+ paylaşılan-global** (`state.hardware` bobin-sürer, `_session_duration_watchdog`, `_mqtt_publish`, `_get_treatment_db`, `_active_session`, `_ws_broadcast`, `_stop_session_coils`…). Bunları lazy-import ile çıkarmak → router'ın api_server iç-organına 8+ noktadan derin bağlanması = **temizlik net-negatif**. Bu cohesive safety/bobin-orkestrasyon çekirdeği; birarada tutmak DAHA temiz. (Gerçek ayrım isteniyorsa önce `session_state.py` shared-state refactor'u gerekir — ayrı, büyük iş.)

---

## SONUÇ — route-extraction fazı tamamlandı (2026-07-06)

**7 refactor commit**, hepsi davranış-birebir + characterization'lı, **94 test yeşil**:
- `system_router` (8 route) + `session_router` (2 route: active, notes) ayrıldı.
- **api_server.py: 2206 → 1881 satır (−325, −%15).**
- Safety çekirdekleri **bilinçli korundu:** session/start+stop (bobin-orkestrasyon), hardware/coil, metrics (ağır coupling). Bunlar ya cohesive-safety ya da shared-state-refactor gerektirir → naive extraction net-negatif olurdu.
- **`ai_router` (B2) — KARAR: cohesive BIRAKILDI.** Değerlendirme: 1384 satır/19 route ama HEPSİ paylaşılan çekirdeğe (`_get_or_load_model` model-cache, `_models`/`_model_lock`, `_decode_image`, `_ai_fail`) + ONNX dinamik-dispatch'e bağlı; ai/pro otonom-tedavi (bobin) safety. Alt-modüllere bölmek → her biri cache'e geri-uzanır = net-negatif. Zaten ayrı cohesive dosya (api_server değil). Gerçek ayrım = önce shared model-cache/helper refactor'u (ayrı, büyük). **session/start ile tutarlı karar.** (Monkeypatch B-2.3'te zaten `max_part_size`'a dönüşmüştü.)

## B3 güvenlik-fix (refactor DIŞI, kullanıcı kararı: ayrı) — ✅ commit `52e734b`
Ham `str(e)` istemci sızıntısı 5 noktada kesildi (api_server 4 + session_router 1); log + generic detail; HTTP status + shape KORUNDU, yalnız detail DEĞERİ değişti. Bkz. REFACTOR_BUGS.md.

## Faz E — Frontend (pf reposu, ayrı; branch `main`)

- **WIP commit'lendi** (`pf@main 2e544b6`, 57 dosya): kullanıcının frontend WIP'i (yeni hooks/test-altyapısı/config + bileşen güncellemeleri). `tsc --noEmit` + 30 jest yeşil; node_modules/build gitignore'lu. **Bu, çakışmasız refactor'ı açtı** (backend WIP-izolasyon deseniyle tutarlı).
- **Frontend güvenlik-ağı:** `tsc --noEmit` (tip) + **jest 6 suite / 30 test** (davranış).
- **F3 (any tiplendirme) — type-only, her commit tsc+30 jest yeşil:**

| Commit (pf) | Değişiklik | any |
|---|---|---|
| `e75658e` | `RealtimeChart`: 3 point-array `any` → `SensorDataPoint[]` (telemetri) | −3 |
| `17ece89` | `ControlScreen`: `coils: any[]` → `CoilStatus[]` (hardware-control) | −1 |
| `c7cd7ff` | `PatientScreen`: 4 `any` (patients/apiGet/handleEdit/handleStartSession) → `Patient`; domain `Patient.owner_email?` tamamlandı | −4 |

  - Toplam: 102 → **94 any** (temiz domain-tipi swap'ları; `canvasRef as any` = web-canvas RN workaround bırakıldı).
  - **PatientScreen'de 2 latent id-opsiyonellik** yakalandı (fetched patient'ta `id?` hep dolu ama tip gevşek): `setEditingId(p.id ?? null)` + `handleDelete(p.id!)` — runtime birebir, bug DEĞİL (tip-katılığı).
  - **Kalan ~94 — çoğu "temiz swap" DEĞİL:** AiHubScreen (57; çoğu legit platform `as any` / native-modül köprüsü), `apiPost<any>`/`apiGet<any>` response'ları (yeni response-interface gerek), `discovery.ts` (Zeroconf untyped-lib), `TreatmentHistoryScreen` (ham backend record snake_case ≠ domain `TreatmentSession` camelCase → ham-tip tanımı gerek). Bunlar ya **legit cast** (bırak) ya da **interface/raw-type yazımı** (daha büyük, ayrı iş) → naive `any→X` swap net-negatif/riskli.
  - **Somut kanıt (SystemInfoPanel araştırıldı → temiz-swap DEĞİL):** `apiGet<any>("/system/info")` `SystemInfo` ile tiplenemez — response şekli farklı (backend `pairingCode`/`tunnelUrl`/`stmConnected` döndürür, `uptime`/`totalSessions` döndürmez); üstelik tipleme sırasında **latent frontend bug** ortaya çıktı (`d.uptime` daima undefined → "Çalışma Süresi" hep 00:00:00). Bkz. `REFACTOR_BUGS.md` Faz F. `apiGet<any>` bilinçli bırakıldı (tipleme bug'ı gizler/build kırar).

## Faz F-fix — SystemInfoPanel uptime bug (kullanıcı talebi, davranış-DEĞİŞTİREN, refactor DIŞI) — ✅ commit `pf@cf43816`
Yukarıdaki latent bug, kullanıcı talebiyle ayrı bir **bug-fix** olarak düzeltildi (refactor değil — bilinçli davranış değişikliği). Uptime artık WS snapshot'taki `system.startTime`'dan istemci-tarafı hesaplanır: saf **`src/utils/uptime.ts` `formatUptime()`** (6 jest testi, TZ-bağımsız) + 1sn ticker. **Backend/EXE sözleşmesi değişmedi** (rebuild yok); `stmConnected` mount'ta bir kez (görünür davranış korundu); ölü 10sn `/system/info` poll kaldırıldı (−1 any → 93). tsc temiz, **36 jest yeşil (7 suite)**. Detay: `REFACTOR_BUGS.md` Faz F.
  - **F3 temiz-hasat SONUCU:** öncelikli yollar (telemetri/hardware-control/hasta) tiplendi (3 commit, hepsi tsc+30 jest yeşil, davranış-birebir). Kalan any'ler bilinçli bırakıldı (legit cast / interface-yazımı-gerektiren / untyped-lib). Daha ileri tipleme = response-interface tasarımı (ayrı iş; latent-bug riski taşır — SystemInfoPanel örneği).
## Faz E-fix deploy — uptime fix CANLI (2026-07-07)
`formatUptime` fix'i (`pf@cf43816`) canlı servise alındı: `expo export --platform web` → `robocopy /MIR pf/dist → "C:\Program Files\PEMF Backend\_internal\frontend\dist"` → `Restart-Service PemfBackend`. Doğrulandı: health 200, canlı sunulan `entry-c41284e5…` (yeni), `startTime` + panel etiketi deployed bundle'da. **EXE rebuild YOK** (yalnız web bundle). Detay + tuzaklar (PS5.1 ASCII, auto-mode üretim-kapısı): [[pemf-web-frontend-deploy]].

## F1 + F2 — KARAR: DEFERRED REWRITE (davranış-koruma DIŞI, bilinçli ertelendi 2026-07-07)
Kullanıcı talebiyle ikisi de **dokunmadan** derinlemesine incelendi → **ikisi de refactor değil, REWRITE** (tanımı gereği davranış değiştirir). Bu oturumun **sıfır-davranış-değişikliği** mandate'i altında yapılamaz; session/start + ai_router + SystemInfoPanel-as-any ile **aynı disiplin**. Karar: **ertele, kod dokunulmadı.**

- **F1 (LiveDataContext split):** Tek WS bağlantısı → `snapshot`/`sensorHistory`/`unreadCount`/`aiVisionData`'yı birlikte besleyen cohesive gerçek-zamanlı orkestrasyon çekirdeği (11 tüketici haritalandı). Yazarın kendi notu (LiveDataContext.tsx:430-433) bölmeyi bir **perf optimizasyonu** olarak tarif ediyor ("telemetri render'larını elemek") → split'in *amacı* re-render davranışını değiştirmek = zero-change DEĞİL. Kolay çıkarımlar (NetInfo/AppState → hook) zaten B-2.4'te yapılmış. Kalan (WS-handler + connection-orchestration) sıkı-bağlı; naive bölme provider-ağacı/effect-sırası/render-zamanlaması riski taşır (tıbbi cihaz). **Not:** tek gerçek zero-change dilim = saf yardımcı (`normalizeStmCoils`/`mergeCoilIntoSnapshot`) çıkarımı + STM-coil-normalize characterization testi — kullanıcı bunu da ertelemeyi seçti.
- **F2 (AppNavContext → expo-router):** Gerçek nav = `PemfApp` manuel `activeRoute` switch (useState) + `AppShell` alt-menü; `AppNavContext` (48 satır) yalnız `navigateTo=setActiveRoute` + `selectedPatient` paylaşıyor. expo-router SADECE bootstrap (`app/index → <PemfApp/>`, `app/_layout` Stack). File-based routing'e taşımak = nav mimarisini yeniden yaz: ekran mount/unmount, geri-tuşu, deep-link, URL, geçiş animasyonu, provider ağacı hepsi değişir. **Migration ≠ refactor.** Ayrı QA (deep-link + geri-tuş) gerektirir.

> İleride yapılırsa: **açık REWRITE** olarak, characterization testi + human-review checkpoint + (F2 için) deep-link/geri-tuş QA planıyla — bu "refactor" fazının parçası olarak DEĞİL.

## KALAN (kullanıcı aksiyonu)
- **Publish v1.5** — obje R2'de; r2.dev TR-filtreli → custom-domain/slim-GitHub teslimat kararı kullanıcıda.

> Gelecek cleanup (davranış-koruma DIŞI, ayrı iş): lazy-import edilen paylaşılan durum (`_live_state`, `_build_ws_snapshot`, `state`, `_active_session`, `_session_lock`) → `servers/live_state.py`/`session_state.py`'ye taşınmalı.
