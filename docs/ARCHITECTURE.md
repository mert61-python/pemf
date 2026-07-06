# PEMF Veteriner Cihazı — Mimari (audit B-11.2)

Bileşen etkileşimi, veri akışı ve güven sınırları. Kod referansları `guii/` köküne görelidir.

## Bileşen diyagramı

```
                                 ┌─────────────────────────────────────────────┐
   İNTERNET                      │   KLİNİK PC (LattePanda, Windows, LocalSystem) │
 ┌──────────┐   named/quick      │                                               │
 │ Mobil    │   Cloudflare       │   ┌───────────────────────────────────────┐   │
 │ (Expo    │◄──────tünel───────►│   │  PEMF_Backend.exe (frozen, NSSM servis)│   │
 │  RN/web) │   https/wss        │   │  FastAPI + uvicorn  :8000              │   │
 └────┬─────┘                    │   │  backend_service.py (tek giriş)        │   │
      │ LAN (aynı WiFi)          │   │   ├─ servers/api_server.py (REST+WS)   │   │
      │ http/ws :8000            │   │   │   ├─ ai_router / history / settings │   │
      ├─────────────────────────►│   │   │   ├─ update_router / patient_router │   │
      │                          │   │   │   └─ /metrics /ws /api/*            │   │
      │ mDNS keşif               │   │   ├─ controllers/hardware_controller   │   │
      │                          │   │   ├─ headless_core (STM seri sürücü)   │   │
 ┌────▼─────┐                    │   │   └─ event_bus (pub/sub)               │   │
 │ Supabase │◄──anon RPC────────►│   └──────┬──────────────┬─────────────────┘   │
 │ devices/ │   (offline-first)  │          │ USB seri     │ MQTT :1883          │
 │ patients │   RLS + SECURITY   │     ┌────▼─────┐   ┌────▼──────┐              │
 │ (RPC-only)│   DEFINER          │     │ STM32    │   │ Mosquitto │              │
 └──────────┘                    │     │ bobin1-5 │   │ (yerel)   │              │
                                 │     └──────────┘   └────┬──────┘              │
   GitHub Releases               │                         │ WiFi hotspot        │
 ┌──────────────┐  OTA           │                    ┌────▼──────┐              │
 │ pemf-update  │◄──latest.json──│                    │ ESP32     │              │
 │ exe/mobil    │   SHA256+auth  │                    │ bobin6-8  │              │
 └──────────────┘                │                    └───────────┘              │
                                 └───────────────────────────────────────────────┘
```

## Veri akışı (özet)

| Akış | Yol | Koruma |
|---|---|---|
| Canlı telemetri | ESP→MQTT / STM→seri → api_server `_live_state` → **WebSocket** → mobil | LAN-muaf / uzak-token |
| Bobin komutu | mobil → `/api/coil` → STM (`hardware_controller`) veya ESP (`_mqtt_publish`) | süre-watchdog auto-stop |
| Hasta/seans | mobil → `/api/patients` `/api/session` → **SQLCipher** DB (local) | at-rest şifreli + PII maskeleme |
| Uzaktan erişim | mobil ↔ Cloudflare tünel ↔ backend; adres Supabase `devices`'ta | token + RLS + RPC-only |
| AI teşhis | mobil (foto/ses/CSV) → `/api/ai/*` → gömülü ONNX modelleri (offline) | — |
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
- **Backend safety-clamp YOK** (bilinçli, B-1.5) — freq/duty/sıcaklık firmware'de satüre eder.

## Tek giriş noktası

`backend_service.py:main()` → logging + crash-handler + telemetri + ACL + DB init + HeadlessCore +
router wire + (reconcile/cloud-sync/db-maintenance/tunnel/update-checker) + uvicorn. `api_server.py`
modül-import'u yan-etkisizdir; arka-plan thread'ler **lifespan startup'ta** başlar.
