# PEMF Vet — Backend (Headless)

Veteriner **PEMF (Pulsed Electromagnetic Field)** tedavi cihazının başsız (headless) backend servisi. FastAPI + uvicorn, **tek port (8000)**; PyInstaller ile tek-dizin `.exe`'ye derlenir, Windows'ta **NSSM servisi** olarak 7/24 çalışır. Mobil uygulama (React Native/Expo) ve web paneli bu backend'e bağlanır.

> ⚠️ **Tıbbi cihaz yazılımı.** Bu repo **yalnız kaynak kodu** içerir — AI modelleri, derleme çıktıları (`dist/`, `build/`), sanal ortamlar, dokümanlar ve sırlar **dahil DEĞİLDİR** (`.gitignore`).

## Genel Bakış
- **Giriş:** `backend_service.py` → `headless_core.py` (çekirdek) + `servers/api_server.py` (FastAPI app).
- **Donanım:** STM32 (USB seri — bobin 1–5) + ESP32 (MQTT/yerel Mosquitto — bobin 6–8).
- **Canlı veri:** WebSocket (`/ws`) — sensör / bobin / seans telemetrisi.
- **Veri:** Yerel **şifreli SQLite (SQLCipher, at-rest)**. Supabase yalnız cihaz-kaydı (uzaktan erişim için).

## Yapı
| Yol | İçerik |
|---|---|
| `backend_service.py` | Servis giriş noktası (arg/log/watchdog) |
| `headless_core.py`, `event_bus.py` | Çekirdek + olay veriyolu |
| `servers/` | `api_server.py` (REST+WS), `auth.py`, `ai_router.py`, `history_router.py`, `settings_router.py`, `tunnel_manager.py`, `sync_worker.py`, `update_manager.py`, `auto_discovery.py` |
| `controllers/` | `hardware_controller.py` (STM32/ESP bobin sürme) |
| `database/` | `patient_database.py`, `treatment_history_db.py`, `sqlcipher_util.py` |
| `ai/`, `ai_hub/` | AI teşhis/inference (hastalık, FGS, segmentasyon, em_kedi…) — modeller ayrı |
| `utils/` | `path_utils.py`, `secrets_manager.py` (tek-dosya sır yönetimi), `model_downloader.py` |
| `services/` | Mosquitto / kimlik / ağ yardımcı servisleri |
| `build_tools/` | PyInstaller `.spec` + Inno Setup `.iss` |
| `scripts/` | Build + servis kurulum + release yayınlama script'leri |
| `deploy/` | `device.env` (klinik) / `server.env` (demo/public) profilleri |

## Ana Sistemler
- **Auth:** Tünel açıkken `PEMF_REQUIRE_AUTH=1` zorunlu. Yerel/LAN **muaf**; uzak (Cloudflare header'lı) istek **token** ister (`X-API-Key` / `?token=`). Mobil, LAN'dayken token'ı otomatik alır (`GET /api/auth/token`, yalnız yerel) veya **6-haneli kodla** takas eder (`POST /api/auth/exchange`).
- **Uzaktan erişim (ücretsiz):** cloudflared **quick tünel** + Supabase cihaz-kaydı (`sync_worker`) + **6-haneli eşleştirme kodu**. Watchdog tüneli otomatik ayakta tutar (dış-URL ölü-tespiti + anında yeniden yayın dahil).
- **Oto-güncelleme (OTA):** `update_manager.py` → `pemf-update` repo'sunun `exe` branch `latest.json`'ını kontrol eder → yeni sürümde **bildirir** → operatör onayıyla (`POST /api/update/apply`) indir + **SHA256** + aktif-tedavi-yokken sessiz kur.
- **Sırlar:** `utils/secrets_manager.py` — tüm sırlar tek `pemf_secrets.json` (kritik anahtarlar **DPAPI**-şifreli). Repoda **YOK**.

## Build
```powershell
cd guii
.\scripts\build_backend_exe.ps1     # web export + PyInstaller → C:\PEMF_BUILD\dist\PEMF_Backend
# Installer (Inno Setup):
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "/DBuildOutput=C:\PEMF_BUILD\dist\PEMF_Backend" build_tools\PEMF_Backend_Setup.iss
# Sunucu profili:  ... "/DModeName=server" build_tools\PEMF_Backend_Setup.iss
```
> Modeller (~640MB) ProgramData'ya installer ile gömülür; build ortamı: tam CPython 3.10 venv (`myenv`).

## Dağıtım
- **Klinik cihaz:** `device` installer → LattePanda/PC; NSSM servisi açılışta otomatik başlar. `deploy/device.env` (tünel + auth açık).
- **Demo/public sunucu:** `server` installer + `deploy/server.env`.

## Sürüm Yayınlama (OTA)
```powershell
.\scripts\publish_release.ps1 -Branch exe   -Version 1.5.0 -AssetPath <installer.exe> -Notes '...'
.\scripts\publish_release.ps1 -Branch mobil -Version 1.0.4 -AssetPath <app.apk>       -Notes '...'
```
Kurulu cihazlar `pemf-update` manifest'inden yeni sürümü görüp güncellemeyi önerir (EXE: tek-tık onay; mobil: indir).

---
*Mobil uygulama ayrı Expo/React Native reposundadır. Release binary'leri + manifest'ler `pemf-update` reposunda (public). AI modelleri + derleme çıktıları bu repoda tutulmaz.*
