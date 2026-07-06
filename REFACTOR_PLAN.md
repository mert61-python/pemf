# Davranış-Koruyan Clean Code Refactor — PLAN

**Kapsam:** `guii/` (FastAPI backend) + `frontend → C:\Users\merta\pf` (React Native/Expo)
**Tarih:** 2026-07-06
**İlke:** TIBBİ CİHAZ → **SIFIR davranış değişikliği.** Refactor ≠ rewrite. Yalnız yapı + okunabilirlik. Her güvenlik yolu **bit-birebir** aynı. Bu bir **plan**dır; henüz hiçbir refactor yapılmadı.
**Baseline:** `PEMF_SIMULATE=1` boot temiz + **86/86 test yeşil** (her commit bunu korumalı).

---

## 0. KRİTİK BULGU — task öncülünün YARISI zaten yapılmış

Task'ın verdiği hot-spot satır numaraları/iddiaları **production-hardening audit'inden (B-2.2/B-2.3/B-4.1) ÖNCEKİ** koda ait. Mevcut kodda doğruladım:

| Task iddiası | MEVCUT durum (doğrulandı) | Kalan |
|---|---|---|
| api_server import-zamanı 3 daemon thread (`:1491/:1697/:1774`) | ✅ **ZATEN `lifespan`'de** — `_start_background_threads()` (idempotent, lifespan startup'tan çağrılır). Satır 599-600 açıkça belgeliyor. Import **yan etkisiz**. | — |
| `@app.on_event` (deprecated) → lifespan | ✅ **ZATEN done** (B-2.2): `lifespan` context-manager, `app=FastAPI(lifespan=lifespan)` (satır 78,118). | — |
| ai_router `:26-46` Starlette MultiPartParser **monkeypatch** | ✅ **ZATEN kaldırılmış** (B-2.3): desteklenen `request.form(max_part_size=)` + `_allow_large_upload` dependency (satır 24-37). | — |
| Global exception handler (B-4.1) | ✅ **ZATEN var**: `@app.exception_handler(Exception/RequestValidationError)` (satır 138-151), ham traceback sızdırmıyor. | 5 nokta hâlâ `str(e)` döndürüyor (aşağıda, **davranış-değiştiren**) |

> **Sonuç:** api_server'ın import-zamanı-thread ve lifespan hedefleri + ai_router monkeypatch + global handler **KAPSAM DIŞI (bitti)**. Bunlara dokunmaya gerek yok; yeniden yapmak regresyon riski.

---

## 1. Sıcak Nokta Envanteri — KALAN gerçek işler (doğrulandı)

| # | Hedef | Ölçüm | Neden | Öncelik | Risk |
|---|---|---|---|---|---|
| **B1** | `servers/api_server.py` **domain-router bölünmesi** | 2206 satır, **26 inline route** (hardware 6, session 4, coil 2, auth 2, kpi/system/health/notifications/gateway/discovery/dashboard 1'er) | Tek dev dosya; router'lar kısmen ayrılmış (patient/history/settings/update) ama hardware/session/coil hâlâ inline | Yüksek değer | **YÜKSEK** — inline route'lar modül-globaline bağlı (`state.hardware`, `_mqtt_publish`, `_active_session`, `_session_lock`) + güvenlik yolları (emergency_stop, coil) |
| **B2** | `servers/ai_router.py` **handler ayıklama** | 1384 satır | Büyük handler'lar; monkeypatch zaten çözülmüş | Orta | Orta — ONNX dispatch (dinamik), davranış korunmalı |
| **B3** | 5 × `str(e)` sızıntısı (satır 977, 1022, 1876, 1905, 1924) | — | Global handler'a rağmen elle `detail=str(e)` | Düşük-orta | ⚠️ **DAVRANIŞ DEĞİŞİKLİĞİ** (yanıt gövdesi değişir) → refactor değil, güvenlik-fix |
| **F1** | `LiveDataContext.tsx` **god-context bölünmesi** | **458 satır** (WS + NetInfo + token + polling tek yerde) | Tek context çok iş yapıyor | Yüksek | Orta — canlı telemetri; tüketici ekranlar aynı anda güncellenmeli |
| **F2** | `AppNavContext.tsx` → expo-router **birleştirme** | 47 satır, **5+ tüketici** (PemfApp, Control, AiHub, Patient, TreatmentHistory) | expo-router'a paralel ikinci routing | Orta | Orta — navigasyon davranışı korunmalı |
| **F3** | `any` **tiplendirme** | **102 toplam** (AiHubScreen **57**, Settings 7, Control 6, TreatmentHistory/Patient/RealtimeChart 4) | Tip güvenliği yok | Düşük-orta | Düşük (tip-only, runtime yok) — ama önce **donanım-kontrol/telemetri** yolları |

---

## 2. Hedef Yapı (before → after)

### Backend
```
ÖNCE                             SONRA
servers/api_server.py (2206)     servers/api_server.py (~ince: app + lifespan + exc-handler
                                    + MQTT + state wiring + include_router)
                                 servers/system_router.py   (NEW) health/system/discovery/
                                    gateway/notifications/dashboard-snapshot  ← DÜŞÜK coupling
                                 servers/session_router.py  (NEW) session start/stop/status
                                 servers/hardware_router.py (NEW) coil control + emergency_stop
                                    ← SAFETY, en son, human-review
servers/{history,patient,          (aynen — zaten ayrı, deseni takip edilecek)
  settings,update}_router.py
servers/{live_state,session_state, ← paylaşılan state buradan (patient_router deseni:
  coil_run_tracker}.py (mevcut)      singleton getter; modül-global coupling'i buraya taşı)
servers/ai_router.py (1384)      servers/ai_router.py (ince dispatcher) + servers/ai/*.py (handler'lar)
```

### Frontend
```
LiveDataContext.tsx (458)   →   TelemetryContext (WS/sensor akışı)
                                ConnectionContext (NetInfo/token/durum)
                                SessionContext (aktif tedavi)
AppNavContext.tsx (47)      →   expo-router (useRouter/usePathname) — context kaldırılır
102× any                    →   önce CoilStatus/SensorDataPoint/ActiveTreatment tipleri
                                (donanım-kontrol/telemetri yolları), sonra AiHubScreen
```

---

## 3. Sıralama — GÜVENLİK AĞI ÖNCE

**Faz 0 — Characterization (golden-master) testleri (ÖNCE, refactor'dan bağımsız):**
Taşınacak kodun MEVCUT davranışını dondurur. Öncelik güvenlik yolları:
- `session_duration_watchdog` (süre aşımı → auto-stop) — `PEMF_SIMULATE=1`
- `emergency_stop` (fail-safe, auth-muaf) — birebir yanıt + yan etki
- coil control (start/stop/param) — payload/MQTT çıktısı snapshot
- encryption fail-closed (`_has_active_treatment` fail-closed, update reddi)
- auth-muaf uçlar (`auth.py` _EXEMPT_*) — muafiyet matrisi
- session start/stop/status — durum geçişleri
> Donanım gerektiren yol simüle edilemiyorsa **boşluk işaretlenir** (test-gap listesi).

**Faz A — düşük-risk extraction (system_router):** health/system/discovery/gateway/notifications/dashboard — az state coupling. Her route = ayrı küçük commit, path/response birebir.
**Faz B — session_router:** session start/stop/status — state coupling `session_state`'e taşınır. Characterization yeşil kalmalı.
**Faz C — ai_router handler ayıklama:** büyük handler'lar `servers/ai/*.py`'ye; dispatcher ince. ONNX dinamik-yükleme davranışı korunur.
**Faz D — hardware_router (SAFETY):** coil control + emergency_stop. **MERGE ÖNCESİ İNSAN-İNCELEME kontrol noktası.** Characterization + birebir MQTT/donanım çıktısı.
**Faz E — frontend:** F1 (context split) → F2 (appnav merge) → F3 (any tiplendirme, önce donanım/telemetri).

**Her commit:** bir refactor = bir commit; sonrasında boot + 86 test + simulate smoke YEŞİL; davranış-değişikliği ile refactor ASLA aynı commit'te.

---

## 4. Risk Notları + DOKUNMA Listesi

| Öğe | Kural |
|---|---|
| Güvenlik zarfı, `emergency_stop`, encryption fail-closed, coil transport, auth-muaf config | Yalnız **birebir-davranış characterization** + **human-review** ile; magic-number/limit'lere DOKUNMA (ayrı safety-clamp işi) |
| **`str(e)` sızıntıları (B3)** | Bu **davranış değişikliği** (yanıt gövdesi) → refactor kapsamı DIŞI. Ayrı güvenlik-fix commit'i olarak, characterization "eski gövde" → "yeni gövde" farkı açıkça işaretlenerek. **Refactor'a karıştırma.** |
| Bağımlılık upgrade | **YOK** (refactor kapsamında) |
| Public path/response şekilleri | Frontend aynı anda güncellenmedikçe **korunur** |
| Bulunan bug'lar | **Düzeltme YOK** — buggy davranış korunur, `REFACTOR_BUGS.md`'ye işaretlenir (ayrı iş) |

---

## 5. Çıktılar
1. **REFACTOR_PLAN.md** (bu dosya)
2. Characterization testleri (Faz 0) — refactor'dan önce commit
3. Refactor'lar → sıralı küçük yeşil commit'ler
4. **REFACTOR_LOG.md** — ne nereye taşındı eşlemesi
5. **REFACTOR_BUGS.md** — bulunan-ama-düzeltilmeyen bug'lar

---

## 6. ONAY BEKLEYEN KARARLAR (başlamadan)
1. **Kapsam:** "zaten yapılmış" 4 hedef (lifespan/threads/monkeypatch/global-handler) **atlanıyor** — onaylıyor musun?
2. **`str(e)` (B3):** refactor'dan **ayrı** güvenlik-fix mi (öneri), yoksa hiç dokunmayalım mı?
3. **Sıralama:** backend önce mi (B1 system→session→hardware), frontend önce mi, yoksa paralel mi?
4. **hardware_router (Faz D):** safety — human-review kontrol noktasını sen mi yapacaksın (ben PR-boyu diff sunarım)?
5. Bu iş **büyük ve çok-oturumluk** — hangi fazdan başlayayım (öneri: **Faz 0 characterization** — hiçbir şeyi bozmaz, güvenlik ağını kurar)?
