# PEMF Vet — Build Rehberi

Tüm build zinciri **`guii` içinde tek yerde**: kaynaklar + scriptler + build çıktıları + paketler.
`guii` klasörünü taşırsan/zip'lersen her şey birlikte gelir. (Tek istisna: APK için geçici kısa-dizin
scratch — aşağıda "MAX_PATH" bölümü.)

Sürümler (2026-07-29): **Backend/App `1.8.0`** (`VERSION`), **Mobil `2.3.2` (versionCode 9)** (`pf/app.json`),
**Launcher `1.9.2`** (`launcher/app/tauri.conf.json`).

---

## Hızlı özet

| # | Hedef | Komut (guii kökünden) | Çıktı |
|---|-------|------------------------|-------|
| 1 | **Backend** (frozen EXE) | `.\scripts\build_backend_exe.ps1` | `PEMF_BUILD\dist\PEMF_Backend\PEMF_Backend.exe` |
| 2 | **base.zip** (client runtime) | `python build_tools\make_base_zip.py` | `pemf-app-packages\base.zip` (+ sha/size) |
| 3 | **Installer** (launcher/Tauri) | `cd launcher\app; npx @tauri-apps/cli build` | `launcher\target\release\bundle\nsis\PEMF Vet Client_1.9.2_x64-setup.exe` |
| 3b | **Installer** (Inno offline) | `.\build_tools\build_installer.ps1 [-Mode device\|server]` | Inno Setup .exe (her şeyi bundle) |
| 4 | **Web frontend** | `cd pf; npm run export:web` + mirror | `pf\dist` → `frontend\dist` + runtime |
| 5 | **Android APK** | `.\build_tools\build_apk.ps1` | `release_assets\PEMF_Vet_Mobil.apk` |

> Tüm PowerShell komutları **guii kök dizininden** çalıştırılır. Scriptler kendi konumlarından
> `guii` kökünü bulur; hard-code `C:\` yol yoktur (APK scratch hariç, o da otomatik).

---

## Ön koşullar (toolchain)

| Araç | Ne için | Not |
|------|---------|-----|
| **myenv** veya embeddable python | Backend build + base.zip | `myenv`, guii'nin **üstünde** (embeddable kökü). Yoksa `scripts\build_backend_exe.ps1 -Python <path>` |
| **PyInstaller** | Backend frozen EXE | Yoksa script otomatik `pip install` eder |
| **Node.js + npm + npx** | Web export + APK + launcher | `npm ci --legacy-peer-deps` |
| **Rust + cargo** (1.97+) | Launcher (Tauri) | `npx @tauri-apps/cli` (tauri-cli 2.11.4) |
| **Android SDK + NDK 27 + JDK** | APK | `ANDROID_HOME`/SDK kurulu; CMake 3.22.1 SDK'da |
| **Inno Setup (ISCC)** | Offline installer | Sadece `build_installer.ps1` için |
| **gh CLI** (authed) | Yayınlama | `mert61-python` |
| **LongPathsEnabled=1** | Backend build | Kayıt defteri açık (238<260 için ekstra güvence) |

---

## 1. Backend — frozen EXE

```powershell
.\scripts\build_backend_exe.ps1              # myenv/embeddable otomatik seçilir; web TAZE export edilir
.\scripts\build_backend_exe.ps1 -SkipWeb     # web zaten güncel frontend\dist'te ise (hızlı)
.\scripts\build_backend_exe.ps1 -BuildRoot C:\PEMF_BUILD   # derin/uzun hedefte MAX_PATH kaçışı
```

- **Çıktı:** `guii\PEMF_BUILD\dist\PEMF_Backend\PEMF_Backend.exe` (+ `_internal\` = mosquitto + cloudflared + web + ai_models 2.1GB).
- Guard: önce `check_headless_imports.py` (Qt sızıntısı KIRMIZI ise build durur).
- İzolasyon: `PYTHONNOUSERSITE=1` + `PYTHONPATH=""` (Conda/Roaming sızıntısı yok).
- **PyInstaller onedir = kendi kendine yeter** → boş Windows'ta Python KURULU OLMADAN çalışır.
- **Çıktı kökü guii içinde** (`PEMF_BUILD`); önceki `C:\PEMF_BUILD` yerine (tek-yer + taşınabilir).

**Doğrulama (temiz-makine, şart):** izole env'de farklı portta çalıştır → `/api/health` **200** olmalı.
```powershell
$env:PYTHONPATH=""; $env:PYTHONHOME=""; $env:PYTHONNOUSERSITE="1"
& .\PEMF_BUILD\dist\PEMF_Backend\PEMF_Backend.exe --port 8213
# başka pencerede:  curl http://127.0.0.1:8213/api/health   → 200
```
> ⚠️ Health endpoint'i **`/api/health`** — `/health` DEĞİL (404).

---

## 2. base.zip — client runtime paketi

Önce **1. Backend build** yapılmış olmalı (base.zip onu paketler).

```powershell
python .\build_tools\make_base_zip.py
# override: python .\build_tools\make_base_zip.py <DIST_YOLU>   (veya PEMF_DIST env)
```

- **Girdi:** `guii\PEMF_BUILD\dist\PEMF_Backend` (script `__file__`'den türetir).
- **Çıktı:** `guii\pemf-app-packages\base.zip` (ZIP_STORED, `_internal\ai_models` HARİÇ — profil-zip'lerde ayrı) + ekranda `BASEZIP_SHA` / `BASEZIP_SIZE`.
- Yapı doğrulaması otomatik (exe/mosquitto/web/setup_services + ai_models hariç kontrolü).
- **manifest.json güncelle:** `sha256` + `size` değerlerini **İKİ yere** yaz — `runtimes.win-x64` (6-boşluk girinti) **VE** `base` (4-boşluk girinti). Bu **çift-base gotcha'sı**: farklı girintiler → ayrı düzenleme gerekir (`replace_all` sadece birini yakalar).

---

## 3. Installer — Launcher (Tauri, ANA dağıtım)

Kullanıcının indirdiği ince-client (base.zip'i internetten çeker).

```powershell
cd launcher\app
npx @tauri-apps/cli build          # cargo + NSIS, ~40sn (incremental)
```

- **Çıktı:** `launcher\target\release\bundle\nsis\PEMF Vet Client_1.9.2_x64-setup.exe`.
- **Yayın için ada kopyala:** `PEMFVetClient-Setup.exe` (site bu adı bekler) → `gh release upload launcher-v1.9.2 ... --clobber`.
- ⚠️ **`withGlobalTauri: true` ŞART** (`tauri.conf.json` app bloğu). Tauri v2'de varsayılan `false` → `window.__TAURI__` enjekte edilmez → UI "Ortam algılanıyor…"da DONAR.
- ⚠️ **Launcher AYRI yayınlanır:** base.zip/APK republish launcher binary'yi GÜNCELLEMEZ. Launcher kaynağı (net.rs / index.html / main.rs) değişince EXE'yi ayrıca rebuild+reupload et.
- **Doğrulama:** binary'yi çalıştır + screencap → profil-UI (home/vet/research) geliyor mu? (Runtime-test edilmezse bug kullanıcıya ulaşır.)

### Oto-güncelleme (self-update) — client kendini günceller

Client v1.9.3'ten itibaren **açılışta kendini otomatik günceller** (kullanıcı tekrar indirip kurmaz):
- Açılışta manifest çekilir; `manifest.launcher.version` çalışan sürümden yeniyse ve `installer_url` varsa →
  yeni setup **sessizce indirilir** (host-pinli) → **SHA256 doğrulanır** → `/S` sessiz kurulur (currentUser =
  UAC yok) → uygulama otomatik yeniden başlar. Yoksa/başarısızsa normal açılış sürer.
- **İnternet yoksa** manifest çekilemez → güncelleme **sessizce atlanır**, uygulama yine açılır.
- Kod: `apply_self_update` komutu (`launcher/app/src/main.rs`) + `trySelfUpdate` (boot, `ui/index.html`) +
  `LauncherInfo.installer_url/sha256/size` (`launcher/core/src/manifest.rs`).

**Yeni launcher sürümü yayınlama (versiyon-bump disiplini):**
1. `launcher/Cargo.toml` (`[workspace.package] version`) **ve** `launcher/app/tauri.conf.json` (`version`) → yeni sürüm (örn. `1.9.4`). İKİSİ AYNI olmalı.
2. Launcher'ı derle (yukarıdaki `npx @tauri-apps/cli build`) → `PEMF Vet Client_<sürüm>_x64-setup.exe`.
3. `PEMFVetClient-Setup.exe` adına kopyala + `gh release upload launcher-v<sürüm> --clobber` (yeni tag).
4. **`pemf-app-packages/manifest.json` → `launcher` alanını güncelle:**
   ```json
   "launcher": {
     "version": "1.9.4",
     "url": "https://pemf-vet-web.vercel.app/",
     "installer_url": "https://github.com/mert61-python/pemf-update/releases/download/launcher-v1.9.4/PEMFVetClient-Setup.exe",
     "sha256": "<setup exe'nin sha256'sı>",
     "size": <setup exe boyutu>
   }
   ```
   sha256/size = yayınlanan setup exe'nin değerleri (`Get-FileHash`, `(Get-Item).Length`).
5. Manifest'i yayınla (`gh release upload client-app-v1.8.0 --clobber ... manifest.json`).
6. **Web sitesi (yeni kullanıcılar da alsın):** `pemf-vet-web/src/config.ts` → `DOWNLOAD_HOST.windowsTag` yeni tag'e + `CLIENT.version` + `releaseDate`; sonra `cd pemf-vet-web; npx vercel --prod --yes`. ⚠️ **`windowsTag` AYRI** (self-update Windows-only) → `launcherTag`'i (mac/linux/android ortak) DEĞİŞTİRME, yoksa onlar 404.
> ⚠️ **Bootstrapping:** oto-güncelleme kodu OLMAYAN eski client'lar (≤1.9.2) kendini güncelleyemez → bir kez ELLE 1.9.3+'a geçmeli (site indirmesi). 1.9.3'ten sonra tüm güncellemeler otomatik.
> ⚠️ `installer_url` YOKSA (yalnız version/url) client sadece "yeni sürüm var" bildirir (otomatik kurmaz) — geriye uyumlu.

## 3b. Installer — Inno offline (alternatif, her şeyi bundle)

```powershell
.\build_tools\build_installer.ps1                # device (varsayılan)
.\build_tools\build_installer.ps1 -Mode server   # server profili
```
- PyInstaller (onedir) + Inno Setup (`build_tools\PEMF_Backend_Setup.iss`). Sürümü `VERSION`'dan senkronlar.
- İnternetsiz tam kurulum (backend + web + ai_models gömülü). Launcher'ın aksine indirme yapmaz.

---

## 4. Web frontend (backend'in localhost:8000'de sunduğu React UI)

```powershell
cd pf
npm run export:web                 # expo export --platform web + postexport → pf\dist
```
Sonra `pf\dist`'i iki yere **mirror**'la (robocopy /MIR):
- `guii\frontend\dist` (kaynak/spec bundle),
- kurulu `runtime\PEMF_Backend\_internal\frontend\dist` (backend buradan StaticFiles ile sunar → EXE rebuild GEREKMEZ, sadece hard-refresh).

> `build_backend_exe.ps1` (-SkipWeb'siz) bu export'u zaten çalıştırır; ayrı web-deploy için yukarıdaki komut.

---

## 5. Android APK

```powershell
.\build_tools\build_apk.ps1                  # guii\pf → C:\pb aynala + assembleRelease + APK'yı geri getir
.\build_tools\build_apk.ps1 -Clean           # scratch'i sıfırdan (tam yeniden kopyala)
.\build_tools\build_apk.ps1 -RemoveScratch   # build sonrası C:\pb'yi sil (C: temiz; sonraki build yavaş)
.\build_tools\build_apk.ps1 -ShortDir C:\x   # farklı kısa kök
```

- **Çıktı:** `guii\release_assets\PEMF_Vet_Mobil.apk`.
- **NEDEN kısa-dizin (MAX_PATH):** Android CMake/ninja, obje dosyası yoluna **kaynak yolunun tamamını gömer** → yol ~2 katına çıkar. ninja `Stat()` **ANSI Win32 API** → 260 sınırını `LongPathsEnabled` açık olsa bile **aşamaz**. guii derin (58 char) → `:app:buildCMakeRelWithDebInfo` (safe-area-context codegen) patlar. **Çözüm:** kaynağı kısa köke (`C:\pb`, 5 char) aynala, orada derle.
- Script `.cxx / .gradle / .transforms`'u kopyadan **hariç tutar** (hız + kısa-kökte TAZE CMake config = kısa obje yolları). node_modules'ün ön-derlenmiş `build` JS'i KORUNUR.
- **KAYNAK guii'de kalır**; `C:\pb` yalnızca geçici build-scratch (varsayılan korunur → hızlı incremental; `-RemoveScratch` ile temizlenir).
- ⚠️ `gradlew clean` YAPMA (rnasyncstorage codegen bozulur). Script zaten clean yapmaz.

---

## 6. Yayınlama (GitHub Releases + Vercel)

```powershell
# base.zip + manifest (client runtime)  → client-app-v1.8.0
gh release upload client-app-v1.8.0 -R mert61-python/pemf-update --clobber pemf-app-packages\base.zip pemf-app-packages\manifest.json
# launcher setup + APK                  → launcher-v1.9.2
gh release upload launcher-v1.9.2  -R mert61-python/pemf-update --clobber PEMFVetClient-Setup.exe release_assets\PEMF_Vet_Mobil.apk
# web sitesi (indirme sayfası)
cd pemf-vet-web; npx vercel --prod --yes         # git-remote YOK → CLI şart
```

> ⚠️⚠️ **`--clobber` KESME TUZAĞI:** `--clobber` önce eski asset'i SİLER, sonra yenisini yükler. Büyük dosya (base.zip 1.3GB) yüklenirken süreci kesersen **asset TAMAMEN EKSİK kalır** → manifest sha'ya işaret eder ama dosya yok → **taze Windows kurulumları BOZUK**. Büyük `--clobber` yüklemesini **asla yarıda kesme**; kesersen bittikten sonra `gh release view --json assets` ile varlığını + boyutunu DOĞRULA.

---

## MAX_PATH özeti (260 karakter)

| Build | guii'den doğrudan? | Neden |
|-------|--------------------|-------|
| Backend / base.zip / Installer | ✅ **Evet** | En uzun yol 238<260 + LongPathsEnabled=1 |
| **APK** | ❌ **Hayır → kısa-dizin** | ninja/CMake ANSI 260; LongPaths işe yaramaz. `build_apk.ps1` otomatik çözer |

---

## Klasör haritası (build ile ilgili)

```
guii\
├─ VERSION                     # app/backend sürümü (1.8.0)
├─ BUILD.md                    # bu dosya
├─ scripts\
│  ├─ build_backend_exe.ps1    # (1) frozen backend → PEMF_BUILD
│  ├─ check_headless_imports.py# guard (Qt sızıntısı)
│  └─ install_backend_service.ps1
├─ build_tools\
│  ├─ make_base_zip.py         # (2) base.zip paketleyici (taşınabilir)
│  ├─ build_installer.ps1      # (3b) Inno offline installer
│  ├─ PEMF_Backend_Setup.iss   # Inno script
│  ├─ build_apk.ps1            # (5) APK (kısa-dizin otomasyonu)
│  └─ PEMF_Backend_onedir.spec # PyInstaller spec
├─ launcher\app\               # (3) Tauri client (installer) kaynağı
├─ pf\                         # mobil + web React (Expo) kaynağı
├─ frontend\dist\              # (4) web export hedefi
├─ PEMF_BUILD\dist\PEMF_Backend# (1) frozen backend çıktısı (base.zip kaynağı)
├─ pemf-app-packages\          # base.zip + manifest.json
└─ release_assets\             # PEMF_Vet_Mobil.apk
```
