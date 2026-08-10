# build_tools/ — Derleme Reçeteleri (spec / iss / ps1 / lock)

Tüm build tarifleri. **Tam adım-adım rehber kökte: [`../BUILD.md`](../BUILD.md)** — burası dosya-referansıdır.

## Dosyalar
| Dosya | Görev |
|---|---|
| `make_base_zip.py` | Frozen backend'i (`../PEMF_BUILD/dist/PEMF_Backend`) → **`../pemf-app-packages/base.zip`** paketler (ZIP_STORED, `_internal/ai_models` HARİÇ, setup/hotspot/teardown scriptleri eklenir), doğrular, `BASEZIP_SHA`/`BASEZIP_SIZE` basar |
| `build_apk.ps1` | Android release APK — `pf\`'i kısa yola (`C:\pb`, MAX_PATH kaçışı) aynala → `gradle assembleRelease` → **`../release_assets/PEMF_Vet_Mobil.apk`** |
| `build_installer.ps1` | **Inno offline installer** (PyInstaller onedir + Inno Setup); `-Mode device\|server`; sürümü `../VERSION`/`../versions.json`'dan senkronlar |
| `sync_versions.ps1` | **`../versions.json` (tek-kaynak)** değerlerini hedef dosyalara (`pf\app.json` vb.) yazar; `build_apk.ps1`/`build_installer.ps1` otomatik çağırır; PS 5.1 için ASCII-only |
| `PEMF_Backend_onedir.spec` | PyInstaller **onedir** spec (birincil) — mosquitto, cloudflared, web `frontend/dist`, `deploy/` env, ai_models gömer |
| `PEMF_Backend_onefile.spec` | PyInstaller **onefile** spec (alternatif tek-EXE) |
| `PEMF_Backend_Setup.iss` | Inno Setup scripti → `PEMFBackendSetup_device_vX.exe` (DiskSpanning `.bin` dilimleri); `[Run]`'da `setup_services.ps1` çağırır |
| `hook-paho.mqtt.py` | PyInstaller hook — tüm `paho.mqtt` alt-modül/verisini dahil eder |
| `myenv-requirements.txt` | Gömülü Python build ortamının **pinli pip kilidi** (kurtarma için; myenv/sistem Python silindi) |
| `Output/` | **Inno installer çıktısı** — `PEMFBackendSetup_device_v1.9.5.exe` + `-1.bin`/`-2.bin` DiskSpanning dilimleri |
| `tools/Autologon64.exe` | Sysinternals Autologon (klinik mini-PC gözetimsiz oturum yardımcısı) |

## ⚠️ Dikkat
- **`build-launcher.bat` YOKtur** — launcher `npx @tauri-apps/cli build` ile derlenir (bkz. [`../launcher/README.md`](../launcher/README.md)).
- Sürüm elle değil `../versions.json`'dan; önce onu değiştir, sonra build al (`sync_versions.ps1` propagasyon yapar).

---
İlgili: [BUILD.md (ana rehber)](../BUILD.md) · [scripts/](../scripts/README.md) · [PEMF_BUILD/](../PEMF_BUILD/README.md) · [pemf-app-packages/](../pemf-app-packages/README.md)
