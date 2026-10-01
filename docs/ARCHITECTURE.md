# PEMF Veteriner Cihazı — Mimari (audit B-11.2)

Bileşen etkileşimi, veri akışı ve güven sınırları. Kod referansları `guii/` köküne görelidir.

## Bileşen diyagramı

```
                                 ┌─────────────────────────────────────────────┐
   İNTERNET                      │   KLİNİK PC (LattePanda, Windows — bkz. not ¹) │
 ┌──────────┐   named/quick      │                                               │
 │ Mobil    │   Cloudflare       │   ┌───────────────────────────────────────┐   │
 │ (Expo    │◄──────tünel───────►│   │  PEMF_Backend.exe (frozen, bkz. not ¹)│   │
 │  RN/web) │   https/wss        │   │  FastAPI + uvicorn  :8000              │   │
 └────┬─────┘                    │   │  backend_service.py (tek giriş)        │   │
      │ LAN (aynı WiFi)          │   │   ├─ apps/backend/servers/api_server.py (REST+WS)   │   │
      │ http/ws :8000            │   │   │   ├─ ai_router / history / settings │   │
      ├─────────────────────────►│   │   │   ├─ update_router / patient_router │   │
      │                          │   │   │   └─ /metrics /ws /api/*            │   │
      │ mDNS keşif               │   │   ├─ apps/backend/controllers/hardware_controller   │   │
      │                          │   │   ├─ headless_core (STM seri sürücü)   │   │
 ┌────▼─────┐                    │   │   └─ event_bus (pub/sub)               │   │
 │ Supabase │◄──anon RPC────────►│   └──────┬──────────────┬─────────────────┘   │
 │ devices/ │   (offline-first)  │          │ USB seri     │ MQTT :1883          │
 │ patients │   RLS + SECURITY   │     ┌────▼─────┐   ┌────▼──────┐              │
 │ (RPC-only)│   DEFINER          │     │ STM32    │   │ Mosquitto │              │
 └──────────┘                    │     │ bobin1-7 │   │ (yerel)   │              │
                                 │     └──────────┘   └────┬──────┘              │
   GitHub Releases               │                         │ WiFi hotspot        │
 ┌──────────────┐  OTA           │                    ┌────▼──────┐              │
 │ pemf-update  │◄──latest.json──│                    │ ESP8266   │              │
 │ exe/mobil    │   SHA256+auth  │                    │ slot 8 YOK│              │
 └──────────────┘                │                    └───────────┘              │
                                 └───────────────────────────────────────────────┘
```

> ¹ **İki kurulum yolu var ve ikisi AYNI DEĞİL** — diyagram tek yolu anlatıyordu:
> - **(a) Installer yolu** (`build_tools/PEMF_Backend_Setup.iss` → `scripts/setup_services.ps1`):
>   `PemfBackend` adlı **NSSM servisi**, `LocalSystem` hesabıyla.
> - **(b) Launcher yolu — SAHADAKİ KURULUM** (ölçüldü 2026-09-13, `docs/LAUNCHER_SPEC.md`
>   "Açık sorular"): launcher `PEMF_Backend.exe`yi **doğrudan spawn eder**, servis kaydı
>   **YOK** (`Get-Service *PEMF*` ve `Win32_Service` boş döner); per-user
>   `%LOCALAPPDATA%\PEMF Vet Client`. `nssm stop PemfBackend` bu makinede boş döner.
>   ⚠️ Bu yolda backend `deploy/device.env`i kendi okumaz; ortam değişkenlerini launcher
>   açıkça verir (`launcher/core/src/install.rs::ENV_*`).

> **Bobin topolojisi — tek kaynak `apps/backend/servers/live_state.py::STM_COIL_IDS` /
> `ESP_COIL_IDS`:** STM32 **1-7** (bobin 6-7 faz-4 kararıyla ESP'den STM'ye taşındı),
> ESP tarafında yalnız **slot 8** kaldı; kartı **ESP8266** (`firmware/esp8266_pemf_coil`),
> **cihazı YOK, yol uykuda**. Kapı: `tests/test_bobin_topolojisi.py`.

> ⚠️ **MQTT/ESP yolu VARSAYILAN OLARAK UYKUDA** — `PEMF_ESP_ENABLED=0`
> (`live_state.py:144`). Bu hâlde MQTT dinleyicisi **hiç başlamaz** ("MQTT dinleyicisi
> ATLANDI — ESP alt sistemi kapalı", `api_server.py:1242`). Yukarıdaki diyagramın ve
> aşağıdaki tablonun ESP/MQTT satırları yalnız `PEMF_ESP_ENABLED=1` ile geçerlidir.

## Veri akışı (özet)

| Akış | Yol | Koruma |
|---|---|---|
| Canlı telemetri | ESP→MQTT *(UYKUDA)* / STM→seri → api_server `_live_state` → **WebSocket** → mobil | LAN-muaf / uzak-token |
| Bobin komutu | mobil → `/api/coil` → STM (`hardware_controller`) veya ESP (`_mqtt_publish` — *UYKUDA*) | süre-watchdog auto-stop |
| Hasta/seans | mobil → `/api/patients` `/api/session` → **SQLCipher** DB (local) | at-rest şifreli + PII maskeleme |
| Uzaktan erişim | mobil ↔ Cloudflare tünel ↔ backend; adres Supabase `devices`'ta | token + RLS + RPC-only |
| AI teşhis | mobil (foto/ses/CSV) → `/api/ai/*` → gömülü ONNX modelleri (offline) + torch CPN (scratch; opsiyonel GPU mikroservis :8100) | — |
| OTA/rollback | backend → `pemf-update/latest.json` → indir+SHA256+Authenticode → sessiz kur | fail-closed (aktif tedavi) |

## Güven sınırları

1. **LAN (güvenli)** — aynı WiFi; auth-muaf, cleartext http kabul (kapalı klinik ağı).
2. **Tünel/uzak (güvensiz)** — internet; **token ZORUNLU** (fail-closed), https/wss, rate-limit.
3. **Bulut (Supabase)** — yalnız cihaz-registry + (opsiyonel) şifreli PII; **anon tablo erişimi YOK** (RLS + SECURITY DEFINER RPC).
4. **At-rest** — hasta/tedavi DB SQLCipher; sır dosyaları DPAPI + NTFS ACL.

## Kritik güvenlik mekanizmaları

- **Süre-watchdog** (`api_server._session_duration_watchdog`) — süre dolunca donanım-STOP (firmware keep-alive tek başına durdurmaz).
- **STM disconnect / ESP alarm** → `_emergency_stop_all` (tüm transport'lar).
- **Açılış mutabakatı** (`backend_service`) — çökme sonrası tüm bobinlere STOP.
- **Tünel → auth zorla** (`_force_auth_for_tunnel`) — internete kimliksiz erişim engeli.
- **Backend tedavi safety-clamp'i YOK** (bilinçli, B-1.5; geri eklenmez) — duty'nin üst sınırı yoktur, firmware/timer doyurur. ⚠️ **Protokol-geçerlilik sınırı AYRI ve TAŞIYICIDIR** (`utils/stm32_protocol_limits`: freq 1–25000 Hz, faz 0–360°, ESP freq ≤1000 Hz): firmware aralık dışını NACK'ler; kaldırılırsa bobin sessizce sürülmez (kapı `tests/test_hc_protokol_siniri_TASIYICI.py`).

## Tek giriş noktası

`apps/backend/backend_service.py:main()` → logging + crash-handler + telemetri + ACL + DB init + HeadlessCore +
router wire + (reconcile/cloud-sync/db-maintenance/tunnel/update-checker) + uvicorn. `api_server.py`
modül-import'u yan-etkisizdir; arka-plan thread'ler **lifespan startup'ta** başlar.
