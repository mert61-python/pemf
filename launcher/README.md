# launcher/ — İnce İstemci (Tauri v2 Rust) · "PEMF Vet Client"

Kullanıcının indirdiği **ince istemci**: manifest'i okur, `base.zip` + profil/model zip'lerini internetten
çeker, SHA doğrular, açar, frozen backend'i başlatır ve tarayıcı UI'sini açar. Kendini de günceller.
Cargo **workspace** (üye: `core` + `app`), sürüm **1.9.5**.

> Tam build+yayın: [`../BUILD.md`](../BUILD.md) §3. Sözleşme: [`../docs/LAUNCHER_SPEC.md`](../docs/LAUNCHER_SPEC.md).

## Yapı
### `core/` — `pemf-launcher-core` (UI'dan bağımsız motor)
| Dosya | Görev |
|---|---|
| `manifest.rs` | Manifest ayrıştırma + `LauncherInfo` (self-update alanları) |
| `net.rs` | Devam-ettirilebilir `.part` indirmeleri, **host-pinli**, boyut/timeout/redirect-pin |
| `verify.rs` · `extract.rs` | SHA256 doğrulama · zip açma (path-safety, zip-slip/symlink koruması) |
| `flow.rs` | Kurulum durum-makinesi: `ManifestFetched → Downloading → Reconnecting → Verifying → Cached → Extracting → StartingBackend{port} → Ready{url}` |
| `backend.rs` | Frozen backend'i çalıştır/öldür. **E-STOP (tıbbi güvenlik):** `safe_stop_coils()` sert-kill'den ÖNCE `POST /api/hardware/emergency_stop` yapar; `kill_stray_backends()` yetim süreçleri temizler (birim testi E-stop POST'unu doğrular) |
| `auth.rs` | **Supabase Auth (REST)** — client girişi. Kendi host-pini + kendi ajanı (Supabase `net::ALLOWED_HOSTS`'a **EKLENMEZ**; o liste `update_manager.py` ile eş). `Session::Debug` jetonları `***` maskeler |
| `secret_store.rs` | **"Beni hatırla"** — Windows DPAPI (`CryptProtectData`, kullanıcı kapsamı + entropi), blob `install_root/auth_session.bin`. Windows dışında **kalıcı saklama YOK** (düz metin yazılmaz) |
| `install.rs` · `platform.rs` · `lib.rs` | Kurulum yerleşimi · platform yardımcıları · API |

### `app/` — `pemf-vet-client` (Tauri v2 binary `PEMFVetClient`)
- `tauri.conf.json`: ürün "PEMF Vet Client", id `com.pemfmedical.vetclient`, **`withGlobalTauri: true` ŞART** (yoksa UI donar), frontend `./ui`, katı CSP.
- `src/main.rs` komutları: `detect_environment`, `fetch_profiles`, `install_and_launch`, `start_installed`, `repair`, `uninstall`, `get_progress`, `pause/cancel/discard`, **`apply_self_update`** (sessiz, SHA-doğrulanmış, `/S` currentUser kurulum → relaunch), **`auth_status` · `auth_login` · `auth_logout`**.
- **Oturum devri (E-özelliği sözleşmesi):** client Supabase ile giriş yapar; backend ayağa kalktıktan sonra, uygulama penceresi açılmadan **ÖNCE** `POST http://127.0.0.1:<port>/api/auth/desktop-session` ile oturumu devreder → uygulama kendi login'ini **atlar** (çift giriş yok). `DELETE` = çıkış. Jetonlar **yalnız loopback**'e gider, **loglanmaz**, UI'da gösterilmez. Backend ucu yoksa (eski `base.zip` → 404/405) sessizce geçilir.
- **Açılış sırası (P0, 2026-08-06):** `auth_status` → **yerel** ortam taraması (ekran HEMEN çizilir) → manifest **arka planda**. Manifest çekimi kısa bütçeli + duvar-saati tavanlı (`net::fetch_string_pinned_budgeted`); gelmezse client çevrimdışı moda düşer, **kurulu uygulama yine başlatılabilir**.
- **NSIS:** `windows/hooks.nsi` kaldırma-öncesi `$INSTDIR\backend.port`'u okur ve **kaldırmadan önce donanım E-stop POST'lar**; per-user kurulum, hasta DB'sini (`%APPDATA%\PEMF_GUI`, KVKK) **korur**.

## Build
```powershell
cd launcher\app
npx @tauri-apps/cli build         # cargo + NSIS
# → launcher\target\release\bundle\nsis\PEMF Vet Client_1.9.5_x64-setup.exe
# yayın için: PEMFVetClient-Setup.exe adına kopyala → gh release launcher-v1.9.5
```

## ⚠️ Dikkat
- **npm ile derlenmez** (app'te build package.json yok) → `npx @tauri-apps/cli build` (cargo).
- **AYRI yayınlanır:** base.zip/APK republish launcher binary'yi güncellemez.
- `withGlobalTauri: true` ve **E-stop-önce-kill** davranışını bozma (güvenlik + UI donması).
- **Bloklayan komutları senkron yapma:** Tauri komut varsayılanı `Blocking`'dir (gövde IPC/olay-döngüsü thread'inde koşar) → ağ/E-stop içeren komutlar `async fn` + `spawn_blocking` olmalı. `fetch_profiles` ve `uninstall` bu yüzden async'e taşındı.
- **Çevrimdışı erişilebilirlik (tıbbi):** internet yokken kurulu cihaz açılabilmeli. Kayıtlı oturum "süresi dolmuş" olsa bile kullanıcı kilitlenmez; yalnız sunucu jetonu **açıkça reddederse** (`SessionRevoked`) kayıt silinir.
- Supabase host'unu `net::ALLOWED_HOSTS`'a **EKLEME** (o liste imzasız setup indirme yetkisi demektir).
- Sürüm bump: `Cargo.toml` **ve** `tauri.conf.json` AYNI olmalı.

---
İlgili: [BUILD.md §3](../BUILD.md) · [launcher sözleşmesi](../docs/LAUNCHER_SPEC.md) · [pemf-app-packages/ (manifest)](../pemf-app-packages/README.md)
