# servers/ — FastAPI Uygulaması, Router'lar, Canlı Durum & Ağ

Backend'in **HTTP/WebSocket katmanı**. `api_server.app` = ana FastAPI uygulaması; `backend_service.py`
(kök) bunu ayağa kaldırır ve `HeadlessCore` + `HardwareController`'ı içine enjekte eder. Modül-import'u
yan-etkisizdir; arka-plan thread'ler **lifespan startup**'ta başlar.

> Mimarinin tamamı: [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md). Giriş noktası: [`../README.md`](../README.md).

## İstek akışı
```
HTTP/WS → api_server route (control_single_coil / start_session / emergency_stop …)
        → state.hardware (HardwareController) → core HW kuyruğu → STM32 seri (5 bobin)
        → ESP bobinler (6-8) paralelde _mqtt_publish ile Mosquitto'ya
Sensör telemetri: MQTT (_on_mqtt_message_api) → live_state → tampon → treatment DB (batch)
```

## Dosyalar

### Çekirdek uygulama
| Dosya | Görev |
|---|---|
| `api_server.py` | **Ana FastAPI `app`** — WS ucu, bobin-kontrol/seans/acil-durdurma/metrics route'ları, MQTT dinleyici + ESP telemetri watchdog, seans-süre & sensör-kalıcılık arka-plan döngüleri, auth/rate-limit middleware, tüm alt-router'ların `include_router()`'ı |
| `live_state.py` | Canlı cihaz durumunun tek kaynağı; WS istemci kaydı + serileştirilmiş broadcast; STM/bobin/seans/hasta canlı-güncelleme fonksiyonları |
| `session_state.py` | Aktif-seans anlık görüntüsüne küçük paylaşımlı erişim (`snapshot()`, `is_active()`) |
| `coil_run_tracker.py` | Her bobinin "coil run" yaşam döngüsü + dakika-ortalaması → run özeti (treatment DB'ye) |
| `efield_live.py` | Canlı E-alanı türetici — konum+organ seans boyunca SABİT, değişen `achieved_B`/`duty_sum` ile em_fantom ONNX **vekilini** AYRI düşük-frekanslı döngüde çağırıp önbelleğe yazar (istek yolunda çalışmaz → snapshot/WS gecikmesini artırmaz); AI paneli ile bar aynı kaynaktan okur |
| `ai_approval.py` | **Hekim onay kapısı** — AI Pro'nun önerdiği per-bobin duty/faz/organ hekim onaylamadan UYGULANMAZ; onay tek-kullanımlık (`consume()`), süreli (`TTL_S`), parametre-mühürlü ve YALNIZ bellekte (süreç yeniden başlarsa yeniden onay istenir — bilinçli) |

### Kimlik & yetki
| Dosya | Görev |
|---|---|
| `auth.py` | API-token üret/sakla/doğrula; auth-gerekli/muaf yol mantığı; güvenilir-ağ (LAN) tespiti |
| `auth_router.py` | Kayıt / giriş / şifre-sıfırlama / OAuth-kod / admin-kod uçları (e-posta+IP throttle, HTTP 429) |
| `entitlement.py` | Abonelik/araştırma-eklentisi geçidi — **flag-kapılı + FAIL-OPEN** (tedaviyi ASLA bloklamaz; güvenlik-limitlerinden bağımsız) |
| `operator_tokens.py` | Operatör kimlik jetonları — PIN doğrulanınca kısa-ömürlü jeton verilir; yazma yollarında `operator_email` gövdeden DEĞİL JETONDAN türetilir (kayıt doğru hekime atfedilir). YALNIZ bellekte, kayan-TTL, hiçbir seviyede loglanmaz |
| `jeton.py` | **Jeton (token) tüketim kapısı** — 1 jeton = 1 AI analizi; `jeton_gate` yalnız YENİ AI analizi isteğini kapılar. TİCARİ kapı, güvenlik DEĞİL: süren seansı / acil-durdurmayı / kontrolü ASLA engellemez. `PEMF_JETON_ENFORCED` KAPALIYKEN no-op; çevrimdışı yerel defter + bağlantı gelince uzlaşma (çift-düşme yok) |
| `audit_log.py` | Denetim izi (HTTP) — geri-dönüşsüz işlemleri (toplu silme, dışa/içe aktarma, operatör/PII) IP + kanıtlanmış operatörle şifreli `audit_events`'e bağlar (`treatment_history_db.denetim_yaz`). Yazım tedaviyi ENGELLEMEZ; İÇERİK yazmaz (yalnız kapsam/adet/sonuç) |

### REST router'ları
| Dosya | Görev |
|---|---|
| `patient_router.py` | Hasta CRUD (`/api/…`) — listele/ekle/sil/hepsini-sil (hasta-auth guard) |
| `session_router.py` | Aktif seans — mevcut seansı al, seans notu kaydet |
| `history_router.py` | Tedavi geçmişi (`/api/history`) — seans liste/detay, sil, not, coil-run CSV export, PDF rapor |
| `settings_router.py` | Uygulama ayarları — yükle/kaydet/güncelle |
| `system_router.py` | Sistem bilgisi, gateway durumu, dashboard, health, keşif, KPI özeti, istemci-hata log |
| `ai_router.py` | AI-inference REST + **AI-Pro kapalı-döngü bobin sürme** (`_ai_pro_loop`); `analyze_*` model uçları, lazy model cache. **Sert onay kapısı** (öner → hekim onaylar → ancak sonra `/api/ai/pro/start`) ve **kare sahipliği** (`_ai_owner_client`: AKTİF sahipli seansta YABANCI istemci kareyi lokalize edip organ/bobin süremez). **HAZIRLIK önizlemesi** (`/api/ai/pro/hazirlik/baslat`\|`/durdur`, `_ai_hazirlik_loop`): web/sunucu-kamerasını ÖNİZLEMEDE ısıtıp seçili organı lokalize eder — **bobin SÜRMEZ, seans BAŞLATMAZ**; organ konumlanınca panel öneriyi otomatik ister, `/start` önizlemeyi devralır (tek kamera). Telefon hazırlık akışının sunucu-kamera karşılığı (1.9.24 — web'in "önce /propose → 409 organ konumlandırılmadı" kapalı döngüsünü kırar). Router `jeton_gate` + `ai_queue_gate` bağımlılıklarını taşır |
| `ai_client.py` | Inference'ı harici AI mikroservisine devreden ince istemci ([`../ai_service/`](../ai_service/README.md)); `ai_service_enabled()` ise |
| `update_router.py` | OTA — `/api/update/status\|apply\|rollback` (→ `update_manager`) |

### Arka-plan işçileri
| Dosya | Görev |
|---|---|
| `update_manager.py` | Self-update motoru — GitHub `latest.json`, SHA-256 + **Authenticode** doğrulama, **aktif tedavide bloklar**, uygula/geri-al |
| `sync_worker.py` | `CloudSyncWorker` — yerel SQLite (hasta/seans) → Supabase; cihaz-registry yayını |
| `auto_discovery.py` | mDNS/Zeroconf servis ilanı (`start_mdns`/`stop_mdns`) + IP re-register |
| `tunnel_manager.py` | Cloudflare-tünel — `cloudflared` bul/indir, tünel başlat, public URL, reconnect watchdog |

## ⚠️ Güvenlik mekanizmaları (bu klasörde)
- `api_server._session_duration_watchdog` — süre dolunca **donanım-STOP** (firmware keep-alive tek başına durdurmaz).
- ESP telemetri watchdog + `emergency_stop` → tüm transport'lara STOP.
- `ai_approval.py` + `ai_router` **kare sahipliği** — otonom AI tedavisi hekim onayı olmadan başlamaz; başka bir istemci sahibin AI-Pro karesini ezip organ/parametre değiştiremez.
- `entitlement.py` ve `jeton.py` **fail-open / ticari kapı**, güvenlik-limitlerinden **bağımsız** (bilinçli) — süren seansı / acil-durdurmayı / kontrolü ASLA kapılamaz.

---
İlgili: [proje geneli](../README.md) · [mimari](../docs/ARCHITECTURE.md) · [controllers/](../controllers/README.md) · [database/](../database/README.md)
