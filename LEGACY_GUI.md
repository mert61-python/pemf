# PyQt GUI — Karantina Durumu (Headless Geçiş)

> **Durum:** GUI devre dışı, `--gui` bayrağı arkasında karantinada. Saha doğrulaması
> sonrası (Faz 8) fiziksel olarak silinecek. Production = %100 headless.

## Çalışma modları

| Komut | Mod | PyQt yüklenir mi? |
|---|---|---|
| `python backend_service.py` | **Headless (production)** | ❌ Hayır |
| `python main.py` | Headless (otomatik backend'e yönlenir) | ❌ Hayır |
| `python main.py --gui` | Legacy GUI (geçici, geçiş dönemi) | ✅ Evet |
| `set PEMF_LEGACY_GUI=1 & python main.py` | Legacy GUI | ✅ Evet |

- `main.py` varsayılan olarak [satır 64-68](main.py#L64-L68)'te, PyQt importlarından **önce**
  `backend_service.main()`'e erken `SystemExit` ile dallanır.
- **PyInstaller EXE giriş noktası = `backend_service.py`** (main.py değil) → GUI hiç paketlenmez.

## Doğrulama

Production import zincirinin Qt-free kaldığını kanıtlamak için:

```
python scripts/check_headless_imports.py
```

`SONUÇ: YEŞİL (startup Qt-free)` ve `EXIT=0` beklenir. Bu, CI/pre-build guard'dır;
biri backend'e yanlışlıkla bir Qt importu eklerse `KIRMIZI` döner.

## Faz 8'de silinecek modüller (legacy/Qt-only)

Bunlar headless eşdeğerleriyle değiştirildi; production yolunda **kullanılmıyor**:

| Legacy (silinecek) | Headless eşdeğeri (kalacak) |
|---|---|
| `windows/` (tüm GUI) | — (React/Expo frontend) |
| `services/mosquitto_manager.py` | `services/headless_services.py` → `MosquittoSupervisor` |
| `services/network_monitor.py` | `services/headless_services.py` → `NetworkStatusService` |
| `threads/discovery_service_thread.py` | `services/headless_services.py` → `UdpDiscoveryService` |
| `utils/notification_panel.py`, `utils/responsive_*.py`, `utils/hardware_aware_mixin.py` | — |
| `model_downloader.HFModelDownloader` (QThread) | `model_downloader.download_model_sync()` (saf Python) |
| `auto_discovery.generate_qr_pixmap()` (QPixmap) | `auto_discovery.generate_qr_image_bytes()` (qrcode+PIL) |
| `headless_core.start_legacy_qt_services()` | `headless_core.start_headless_services()` |

`headless_core` bu legacy servisleri yalnızca `start_legacy_qt_services=True` ile
(default OFF) ve `try/except` koruması altında çağırır → guard-script'te "GÜVENLİ
guarded sınır" olarak görünür.
