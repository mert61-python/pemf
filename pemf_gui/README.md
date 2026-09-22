# pemf_gui/ — Eski PyQt GUI Kalıntısı · **GUI ÖLÜ, config+asset SHIM CANLI**

Eski PyQt masaüstü GUI'nin paketi. GUI kaynağı (pencereler/thread'ler/stiller/main) **silindi** (headless'a
geçildi), **ama paket ölü değil** — iki parça hâlâ aktif kullanılıyor:

| Yol | Durum |
|---|---|
| `config.py` | ✅ **CANLI** — `ConfigManager` (Fernet-şifreli sırlar, keyring/DPAPI, eski-anahtar migrasyonu). Import edenler: `../apps/backend/backend_service.py`, `../apps/backend/database/patient_database.py` |
| `__init__.py` | ✅ **CANLI** — `get_icon_path()`; `resources/` ikonları `../apps/backend/utils/path_utils.py` + `../apps/backend/servers/system_router.py` (tray ikon `pemf_heart_emf_icon.ico`) tarafından kullanılır |
| `resources/` | ikonlar, resimler, `docs/Kullanim_Klavuzu.pdf` |
| (GUI pencere/entrypoint kodu) | ❌ **YOK** — silindi |

## ⚠️ Dikkat
- **Silme** — GUI olarak bayat ama **config + asset shim'i olarak canlı** (backend import ediyor).
- `scripts/check_headless_imports.py` bunu `EXCLUDED_GUI_PACKAGES`'te listeler (headless guard'ı kızdırmaz).

---
İlgili: [apps/backend/utils/secrets_manager](../apps/backend/utils/README.md) · [apps/backend/database/](../apps/backend/database/README.md) · [proje geneli](../README.md)
