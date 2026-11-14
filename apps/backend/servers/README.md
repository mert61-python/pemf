# servers/ — FastAPI Uygulaması, Router'lar, Canlı Durum & Ağ

Backend'in **HTTP/WebSocket katmanı**. `api_server.app` = ana FastAPI uygulaması; `backend_service.py`
(kök) bunu ayağa kaldırır ve `HeadlessCore` + `HardwareController`'ı içine enjekte eder. Modül-import'u
yan-etkisizdir; arka-plan thread'ler **lifespan startup**'ta başlar.

> Mimarinin tamamı: [`../docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md). Giriş noktası: [`../README.md`](../../../README.md).

## İstek akışı
```
HTTP/WS → api_server route (control_single_coil / start_session / emergency_stop …)
        → state.hardware (HardwareController) → core HW kuyruğu → STM32 seri (7 bobin, 121 baytlık paket)
        → ESP slotu (8) paralelde _mqtt_publish ile Mosquitto'ya
        ⚠️ 2026-09-11: ESP kartları SÖKÜLDÜ. `live_state.esp_etkin()` (PEMF_ESP_ENABLED, varsayılan 0)
          kapalıyken MQTT dinleyicisi HİÇ başlamaz ve `_mqtt_publish` yayın YAPMADAN False döner.
          Kod SİLİNMEDİ — bayrak 1 yapılınca hibrit/ESP-only kuruluma dönülür.
Sensör telemetri: MQTT (_on_mqtt_message_api) → live_state → tampon → treatment DB (batch)
```

## Dosyalar

### Çekirdek uygulama
| Dosya | Görev |
|---|---|
| `api_server.py` | **Ana FastAPI `app`** — WS ucu, bobin-kontrol/seans/acil-durdurma/metrics route'ları, MQTT dinleyici + ESP telemetri watchdog, seans-süre & sensör-kalıcılık arka-plan döngüleri, auth/rate-limit middleware, tüm alt-router'ların `include_router()`'ı **GZIP** (ADIM 5, 2026-09-12): `GZipMiddleware` + `GZIP_ASGARI_BAYT=1024` — çok panelli AI yanıtı base64 JPEG taşır ve base64 ikiliyi %33 şişirir; gzip onu geri alır (**ölçüldü: 5.917,7 KB → 4.472,6 KB, oran 0,756**). ⚠️ Kazanç YALNIZ Tauri/doğrudan :8000 yolunda (docker/web'de nginx zaten yapıyor). ⚠️ Eşiğin altındaki küçük yanıt sıkıştırılmaz (saf CPU kaybı); WebSocket etkilenmez. Kapı: `tests/test_gzip_sikistirma.py` |
| `live_state.py` | Canlı cihaz durumunun tek kaynağı; WS istemci kaydı + serileştirilmiş broadcast; STM/bobin/seans/hasta canlı-güncelleme fonksiyonları |
| `session_state.py` | Aktif-seans anlık görüntüsüne küçük paylaşımlı erişim (`snapshot()`, `is_active()`) |
| `coil_run_tracker.py` | Her bobinin "coil run" yaşam döngüsü + dakika-ortalaması → run özeti (treatment DB'ye) |
| `efield_live.py` | Canlı E-alanı — **ODAK seansında** CST E dışa aktarımları + ölçülen B kalibrasyonuyla, sürülen duty / işaretle hesaplanır ("Hesaplanan değer — E doğrudan ölçülmedi" etiketiyle; petride kuyu sıvısı içinde). ODAK dışı analiz bağlamında eski em_fantom **vekili** "yaklaşık" etiketiyle kalır. Ayrı düşük-frekanslı döngü, önbellekten okunur (snapshot / WS gecikmesini artırmaz) |
| `ai_pro_hedef.py` | **AI Pro hedef sağlayıcıları** — kapalı döngünün model-bağımsız katmanı: `kedi` (veteriner, `cat_organ` konumu), `fantom` (`phantom_cv_v3` tümörü), `petri` (`petri_cv_v2` kuyuları). **Sürüş faz / duty'si YALNIZ ODAK'tan** (`ai_hub/odak/`, mühürdeki ODAK ayarı; yoksa SÜRÜLMEZ) — hocanın `em_kedi` / `PhantomPredictor` / `PetriPredictor` modelleri sürüş kaynağı DEĞİL. Fantom sürüşü doğrulanana dek ODAK katmanında kapalı (fail-closed, TR + EN neden). Her sağlayıcı AYNI 8'li tuple sözleşmesini döndürür (`localized,x,y,z,güven,overlay,özne_var,güven_dökümü`) ve kare üstü hedef adaylarını (`targets`, kare-oranlı `pxn`), kalibrasyon yöntemini ve eğitim-aralığı işaretini üretir. ⚠️ **Kedi kodu TAŞINMADI** (geç bağlı delegasyon) → veteriner davranışı bit-bit aynı. ⚠️ Kalibrasyonsuz yöntemde güven tavanı 0,25 < eşik 0,3 → **işaretsiz hedef YAPISAL olarak reddedilir** (karar #4). ⚠️ Kedi DIŞI modelle SÜRÜŞ `PEMF_ARASTIRMA_AIPRO` bayrağına bağlı (tezgâh doğrulaması bekliyor) · ⚠️ **Kedi** AI Pro SÜRÜŞÜ de `PEMF_KEDI_AIPRO_SURUS` bayrağına bağlı (Y142, varsayılan KAPALI: kabin ↔ EM eğitim çerçevesi tezgâhta doğrulanana dek analiz / öneri görünür, başlatma / onay / bobin sürüşü 409; kapı `ai_router._kedi_aipro_surus_kapisi` + sürüş anı + `_drive_coils_ai_pro`) · Y143: araştırmada "otomatik" (0) öneri o anki SEÇİLİ hedefin kalıcı kimliğiyle mühürlenir (onay ekranında görülen = sürülen; seçili kimlik yoksa 409) |
| `sensor_kaydedici.py` | **Sensör telemetrisi yerel CSV kaydedici** (sahip kararı 2026-09-09) — kayıt HER ZAMAN açık; mevcut `pemf/coil/+/sensors` aboneliğine takılır (yeni abonelik/ağ yükü YOK). ⚠️ Hasta DB'sine YAZMAZ: ~16 MB/gün telemetri her açılış yedeğini şişirir ve tıbbi kaydın geri-yükleme süresini bozar |
| `seans_alan_kaydi.py` | **Seans boyunca ÖLÇÜLEN manyetik alanı biriktirir** ve masaüstüne seans-özel CSV yazar (sahip kararı 2026-09-11). ⚠️ İki ayrı "yoğunluk" vardır — reçete (`intensity_mt`, cihaza GÖNDERİLMEZ, yalnız kayıt) ile sensörden ölçülen değeri karıştırmayın |
| `kabin_kalibrasyonu.py` | **Kabin kalibrasyonu uçları** — sabit düzlem kalibrasyon ekranının arka ucu (araştırma profili; masaüstü + telefon + web aynı uçlar): kare al (kuyular otomatik, numaralı köşeler) → hesapla → kaydet (veri köküne + iz) → başka konumda **Doğrula** (≤ 2 cm); kamera kimliği denetimi, kör bölge, numune altlığı |
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
| `patient_router.py` | Hasta CRUD (`/api/…`) — listele/ekle/sil/hepsini-sil. Hasta-auth kapısı (`_enforce_patient_auth`) yalnız `PEMF_REQUIRE_PATIENT_AUTH=1` iken operatör jetonu ister — VARSAYILAN KAPALI: LAN'daki istemci hasta uçlarına token'sız erişir (A-01, LAN güvenilir sayılır). İstisna: hepsini-sil YALNIZ cihazın kendisinden (loopback; token da yetmez — A-03, `auth.cihazin_kendisinden_mi`) |
| `session_router.py` | Aktif seans — mevcut seansı al, seans notu kaydet |
| `history_router.py` | Tedavi geçmişi (`/api/history`) — seans liste/detay, sil, not, coil-run CSV export, PDF rapor |
| `settings_router.py` | Uygulama ayarları — yükle/kaydet/güncelle |
| `system_router.py` | Sistem bilgisi, gateway durumu, dashboard, health, keşif, KPI özeti, istemci-hata log |
| `ai_router.py` | AI-inference REST + **AI-Pro kapalı-döngü bobin sürme** (`_ai_pro_loop`); `analyze_*` model uçları, lazy model cache. **Sert onay kapısı** (öner → hekim onaylar → ancak sonra `/api/ai/pro/start`) ve **kare sahipliği** (`_ai_owner_client`: AKTİF sahipli seansta YABANCI istemci kareyi lokalize edip organ/bobin süremez). **HAZIRLIK önizlemesi** (`/api/ai/pro/hazirlik/baslat`\|`/durdur`, `_ai_hazirlik_loop`): web/sunucu-kamerasını ÖNİZLEMEDE ısıtıp seçili organı lokalize eder — **bobin SÜRMEZ, seans BAŞLATMAZ**; organ konumlanınca panel öneriyi otomatik ister, `/start` önizlemeyi devralır (tek kamera). Telefon hazırlık akışının sunucu-kamera karşılığı (1.9.24 — web'in "önce /propose → 409 organ konumlandırılmadı" kapalı döngüsünü kırar). Router `jeton_gate` + `ai_queue_gate` bağımlılıklarını taşır. **HEDEF MODELİ** (2026-09-09): `model` alanı `hazirlik/baslat` ve `propose` gövdelerinden gelir, öneri MÜHRÜNE yazılır ve `/start` onu **mühürden** okur (organ/süre ile aynı ilke — gövdeden model değiştirilemez); `/frame` de aktif modeli kullanır, gövdeden okumaz. Yeni rota AÇILMADI (route-contract sabit sayacı ve auth-muafiyet önekleri değişmedi) |
| `ai_client.py` | Inference'ı harici AI mikroservisine devreden ince istemci ([`../ai_service/`](../../../ai_service/README.md)); `ai_service_enabled()` ise |
| `update_router.py` | OTA — `/api/update/status\|apply\|rollback` (→ `update_manager`) |

### Arka-plan işçileri
| Dosya | Görev |
|---|---|
| `update_manager.py` | Self-update motoru — GitHub `latest.json`, SHA-256 + **Authenticode** doğrulama, **aktif tedavide bloklar**, uygula/geri-al |
| `sync_worker.py` | `CloudSyncWorker` — yerel SQLite (hasta/seans) → Supabase; cihaz-registry yayını |
| `auto_discovery.py` | mDNS/Zeroconf servis ilanı (`start_mdns`/`stop_mdns`) + IP re-register |
| `tunnel_manager.py` | Cloudflare-tünel — `cloudflared` bul/indir, tünel başlat, public URL, reconnect watchdog |
| `firmware_manager.py` | **STM32 firmware OTOMATİK güncellemesi** (sahip kararı 2026-09-22) — manifest → plan → indir → yak → doğrula; cihaz firmware'ini KENDİ alır (açılışta client kontrolünden SONRA). İş bölümü: KARAR [`../utils/surum_uyumu.py`](../utils/README.md), YAKMA [`../utils/stm_yakma.py`](../utils/README.md), orkestrasyon burada. ⚠️ Kural yoksa karar `None`, manifest okunamazsa BEKLE; geri alış çift yönlüdür |

## ⚠️ Güvenlik mekanizmaları (bu klasörde)
- `api_server._session_duration_watchdog` — süre dolunca **donanım-STOP** (firmware keep-alive tek başına durdurmaz).
- ESP telemetri watchdog + `emergency_stop` → tüm transport'lara STOP.
- `ai_approval.py` + `ai_router` **kare sahipliği** — otonom AI tedavisi hekim onayı olmadan başlamaz; başka bir istemci sahibin AI-Pro karesini ezip organ/parametre değiştiremez.
- `entitlement.py` ve `jeton.py` **fail-open / ticari kapı**, güvenlik-limitlerinden **bağımsız** (bilinçli) — süren seansı / acil-durdurmayı / kontrolü ASLA kapılamaz.

---
İlgili: [proje geneli](../../../README.md) · [mimari](../../../docs/ARCHITECTURE.md) · [controllers/](../controllers/README.md) · [database/](../database/README.md)
