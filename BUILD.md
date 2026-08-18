# PEMF Vet — Build Rehberi

Tüm build zinciri **`guii` içinde tek yerde**: kaynaklar + scriptler + build çıktıları + paketler.
`guii` klasörünü taşırsan/zip'lersen her şey birlikte gelir. (Tek istisna: APK için geçici kısa-dizin
scratch — aşağıda "MAX_PATH" bölümü.)

Sürümler (2026-08-06): **Backend/App `1.9.5`** (`VERSION`), **Mobil `2.3.3` (versionCode 10)** (`pf/app.json`),
**Launcher `1.9.9`** (`launcher/app/tauri.conf.json`).

> **TEK KAYNAK `versions.json`** — elle bu dosyaları düzenlemeyin. `versions.json`u değiştirip
> `.uild_toolssync_versions.ps1` çalıştırın; hedef dosyaları o yazar (build scriptleri de otomatik çağırır).

---

## Hızlı özet

| # | Hedef | Komut (guii kökünden) | Çıktı |
|---|-------|------------------------|-------|
| 1 | **Backend** (frozen EXE) | `.\scripts\build_backend_exe.ps1` | `PEMF_BUILD\dist\PEMF_Backend\PEMF_Backend.exe` |
| 2 | **base.zip** (client runtime) | `python build_tools\make_base_zip.py` | `pemf-app-packages\base.zip` (+ sha/size) |
| 3 | **Installer** (launcher/Tauri) | `cd launcher\app; npx @tauri-apps/cli build` | `launcher\target\release\bundle\nsis\PEMF Vet Client_1.9.9_x64-setup.exe` |
| 3b | **Installer** (Inno offline) | `.\build_tools\build_installer.ps1 [-Mode device\|server]` | Inno Setup .exe (her şeyi bundle) |
| 4 | **Web frontend** | `cd pf; npm run export:web` + mirror | `pf\dist` → `frontend\dist` + runtime |
| 5 | **Android APK** | `.\build_tools\build_apk.ps1` | `release_assets\PEMF_Vet_Mobil.apk` |

> Tüm PowerShell komutları **guii kök dizininden** çalıştırılır. Scriptler kendi konumlarından
> `guii` kökünü bulur; hard-code `C:\` yol yoktur (APK scratch hariç, o da otomatik).

---

## 0. Sıfır Makine Kurulumu — `bootstrap.ps1`

**Boş bir Windows laptopta** (hiçbir toolchain yokken) tüm build+publish araç zincirini tek komutla kurar.
Bu embeddable-python klasörünü kopyala, sonra **guii kökünden**:

```powershell
.\bootstrap.ps1                 # her şeyi kur (idempotent — tekrar çalıştırılabilir)
.\bootstrap.ps1 -SkipAndroid    # APK toolchain'i (NDK ~1GB) atla → backend+launcher+installer yeter
.\bootstrap.ps1 -SkipMsvc       # MSVC zaten kuruluysa atla
.\bootstrap.ps1 -VerifyOnly     # hiçbir şey kurma, sadece durum tablosu ver
```

- **Kurar:** Node.js (LTS), Git, GitHub CLI, JDK 17, Inno Setup 6, Rust (+`cargo-tauri`), MSVC C++ Build Tools, Android `cmdline-tools` + **NDK `27.1.12297006`** + **CMake `3.22.1`**.
- **Kurmaz:** Python — **embedded** klasörde self-contained (kök `python.exe` + `python310.zip` + tüm build-deps **pinli**). ⚠️ myenv + sistem Python **KALDIRILDI** (2026-08-01 konsolidasyon); build artık embedded'ı kullanır, sistem Python GEREKMEZ. Kilit dosya: `build_tools\myenv-requirements.txt`. Deps eksik/bozuksa geri-kur: `.\python.exe -m pip install --no-deps -r guii\build_tools\myenv-requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu` (zeroconf hariç — wheel yok, 0.148 kalır).
- **Taşınmaz:** `gh`/Vercel **oturumu** makineye özeldir → her makinede bir kez `gh auth login` (bootstrap sonunda hatırlatır).
- **Gerekir:** yönetici PowerShell (MSVC + winget için) + internet (crates.io / npm / Android CDN indirmeleri).

> **İki taşınabilirlik ayrımı — karıştırma:**
> **(a) Runtime** — frozen EXE / offline installer Python KURULU OLMADAN her makinede çalışır (✅ zaten öyle; klinik laptopuna kurulan bu).
> **(b) Build** — bu klasör *kaynağı + AI modelini + Python env'i + npm cache'i* taşır, ama derleme **araçlarını** (Node/Rust/MSVC/JDK/Android/Inno/gh) taşımaz. `bootstrap.ps1` o boşluğu doldurur → **klasör + bootstrap + internet = herhangi bir laptopta build+publish.**

### 0b. `git clone`'dan gelen makinede — `scriptsestore_assets.ps1`

Yukarıdaki (b) maddesi **klasörü kopyalayarak** taşımayı anlatır. **Git'ten** gelindiğinde bir
parça eksiktir: AI model ağırlıkları.

⚠️ **Neden git'te yoklar (ölçüldü 2026-08-18):** `release_assets/ai_models` 2.130 MB ve içinde
100 MiB'ı aşan dört dosya var (`v22_kmc_classictrio_kmc.onnx` tek başına 857 MB). GitHub tek
dosyada 100 MiB'ı **sert** reddediyor; Git LFS ise **ücretli** (public depo muafiyeti LFS'e
geçmiyor). Bu yüzden bölünme şöyle:

| Nerede | Ne |
|---|---|
| **git** | kaynak kod + yayınlanmış hiçbir pakette kopyası **olmayan** 11 küçük model (6 MB) |
| **Releases** | büyük ağırlıklar (2,1 GB) — `home.zip` / `vet.zip` / `research.zip` içinde |

`tests/test_yedek_kapsami.py` bu ayrımı kilitler: yedeği olmayan bir dosya `.gitignore`'a düşerse
ya da 100 MiB üstü bir dosya git'e girerse test kırılır.

**Boş makinede sıra:**

```powershell
git clone https://github.com/mert61-python/pemf.git guii
cd guii
.ootstrap.ps1                  # toolchain (Node/Rust/MSVC/JDK/Android/Inno/gh)
.\scriptsestore_assets.ps1     # AI model ağırlıkları (Releases'ten, SHA256 doğrulamalı)
.\scriptsuild_backend_exe.ps1  # artık derlenebilir
```

- Betik indirme adresini **manifest'ten okur**, etiketi tahmin etmez: `home.zip` bugün
  `client-app-v1.9.11`de, `vet`/`research` ise `client-app-v1.8.0`de (sha değişmeyince
  `make_manifest` eski URL'yi korur — bkz. "değişmeyen paket URL'i" kuralı).
- **SHA256 doğrulaması zorunludur ve atlanamaz:** yarım/bozuk indirme sessizce yanlış ağırlık
  kurar; bu bir tıbbi cihaz, yanlış ağırlıkla çalışan model yanlış klinik çıktı üretir.

---

## Ön koşullar (toolchain)

> Bunları elle kurmak yerine `bootstrap.ps1` (yukarıda) tek komutla halleder. Aşağıdaki tablo neyin neden gerektiğini gösterir.

| Araç | Ne için | Not |
|------|---------|-----|
| **embedded python** (klasör kökü) | Backend build + base.zip | guii'nin **üstünde** `python.exe` — self-contained, tüm deps pinli (myenv/sistem Python GEREKMEZ). Override: `scripts\build_backend_exe.ps1 -Python <path>` |
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
.\scripts\build_backend_exe.ps1              # embedded python otomatik seçilir; web TAZE export edilir
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

## 2. Katmanlı runtime paketleri (base-app.zip + base-deps.zip)

Önce **1. Backend build** yapılmış olmalı (paketler onu böler).

```powershell
python .\build_tools\make_base_zip.py
# override:      python .\build_tools\make_base_zip.py <DIST_YOLU>   (veya PEMF_DIST env)
# katman-only:   python .\build_tools\make_base_zip.py --no-monolith
#                (base.zip URETILMEZ; diskteki bayat base.zip SILINIR ki yanlislikla yayinlanmasin)
```

**KATMANLI PAKET (2026-08-08).** Eskiden tek `base.zip` (~1,32 GB) vardı ve tek satırlık bir yazı
değişikliği bile her kliniğe o boyutu indiriyordu. Ölçüldü: ~1,19 GB'ı **hiç değişmeyen**
bağımlılıklar (torch 271 MB, xgboost 137, cv2 111, llvmlite 85, ffmpeg 84, mediapipe 81, scipy 63,
mosquitto/cloudflared 60…), yalnız ~71 MB'ı bizim kodumuz. Paket ikiye ayrıldı:

| Paket | Boyut | Ne zaman değişir |
|---|---|---|
| `base-app.zip` | ~71 MB | **her sürümde** — exe + `ai_hub` .pyd + web arayüzü + scriptler |
| `base-deps.zip` | ~1,19 GB | yalnız `requirements` değişince |
| `base.zip` | ~1,32 GB | **her sürümde** — yukarıdaki ikisinin BİRLEŞİMİ, ≤1.9.12 eski client'lar için |

> ⚠️ **TEK SÜRÜM, TEK YAZILIM (2026-08-09 denetimi).** `base.zip` eskiden yalnız `--monolith`
> ile üretiliyordu ve "normalde GEREKMEZ" deniyordu. Sonuç ölçüldü: yayındaki `base.zip` ile
> `base-app`+`base-deps` **53 dosyada farklıydı — `PEMF_Backend.exe` dahil**. Yani eski client'lar
> (`runtimes`/`base` okur) ile yeni client'lar (`layers` okur) aynı sürüm numarası altında
> **farklı yazılım** alıyordu. Tıbbi cihazda bir arızanın hangi kodda olduğu bilinemez hale gelir.
> Artık `base.zip` **varsayılan olarak** her koşuda aynı dosya kümesinden üretilir ve script
> `base.zip == app+deps` eşitliğini (isim kümesi + CRC) **doğrulayıp uyuşmazsa DURUR**.

- **Çıktı:** `guii\pemf-app-packages\base-app.zip` + `base-deps.zip` + `base.zip` + ekranda
  `APPZIP_SHA/SIZE`, `DEPSZIP_SHA/SIZE` ve `BASEZIP_SHA/SIZE`.
- **Kayıp dosya kapısı:** her dosya tam bir katmana gitmeli; script toplamı doğrular ve
  uyuşmazsa **durur** (ikisine de girmeyen bir dosya kurulumdan sessizce düşerdi).
- Katman kapıları otomatik: `katmanlar KESISMIYOR`, `exe/web/ai_hub APP'te`, `torch DEPS'te`,
  `_app_roots.json var` + eski kontroller (mosquitto, ai_models hariç, **ai_hub KORUMALI**).
- **`_app_roots.json`:** app paketi kendi sınırını taşır. Launcher app katmanını yenilerken
  DİSKTEKİ eski marker'ı okuyup o kökleri siler → yeni sürümde kaldırılan dosyalar (bayat `.pyd`,
  eski web bundle parçaları) diskte yaşamaz. Sınır değişirse launcher'ı elle güncellemek gerekmez.

**manifest.json güncelle:**
- `layers.<platform>.deps` ve `layers.<platform>.app` → yeni `sha256` + `size`.
- ⚠️ **`runtimes` ve `base` girdileri KALMALI.** Onlar **≤1.9.12 eski client'lar** içindir.
  Silinirse eski client'lar kurulum yapamaz. Eski client açılışta zaten kendini günceller, sonra
  katmanlı yola geçer. **AMA BAYAT BIRAKILAMAZ:** katmanlar yenilendiğinde `base.zip` de
  yenilenmeli ve yüklenmelidir (yukarıdaki "tek sürüm, tek yazılım" notu).
- ⚠️ Manifest'i **elle düzenlemeyin** — `python scripts/make_manifest.py` üretir. Betik artık
  `layers` + `mobile` bloklarını da taşır/üretir, `rollout` geri-çekmesini korur ve şu iki
  durumda **manifest yazmadan HATA verir**: (a) önceki manifest'te olan bir bölüm kaybolacaksa,
  (b) katmanlar yeni ama tek-parça `base` eskiden taşınıyorsa.
- Doğrulama: `cargo test -p pemf-launcher-core --lib uretim_manifesti` — üretim manifestini
  gerçekten ayrıştırır, katman/url/boyut değişmezlerini ve `runtimes`'ın kaybolmadığını kontrol eder.

> Eski **çift-base gotcha'sı** (aynı sha'yı `runtimes.win-x64` 6-boşluk **ve** `base` 4-boşluk
> girintiye yazma) `make_manifest.py` kullanıldığında kendiliğinden doğru yazılır.

---

### Bozuk bir yayını geri çekmek (rollout)

Ölçek iki AYRI karardır; ikisi de `scripts/make_manifest.py` ile yönetilir:

```powershell
# runtime (base/app/deps) yayınını durdur:
python scripts/make_manifest.py --dir pemf-app-packages ... --rollout 0
# CLIENT (launcher) yayınını durdur:
python scripts/make_manifest.py --dir pemf-app-packages ... --launcher-rollout 0
```

> ⚠️ **Launcher rollout'u neden ayrı ve neden kritik (2026-08-09 denetimi):** runtime katmanlarında
> bu fren vardı ama **güncellemeyi yöneten bileşenin kendisinde yoktu** — launcher self-update'i,
> sürüm yeniyse koşulsuz, sessizce ve %100'e uygulanıyordu. Bozuk bir client yayını bir sonraki
> açılışta sahadaki **her** cihaza gider ve runtime'ın aksine **geri dönüş yolu kalmaz**: yeni
> launcher artık eskisini çalıştırmıyor. `--launcher-rollout 0` bu durumdan dönmenin TEK yoludur
> (henüz güncellememiş cihazlar durur). Yeni bir client yayınını önce `10` ile küçük bir dilime
> açıp izlemek iyi bir alışkanlıktır; cihaz dilimi kurulum kimliğinden türer, yani **kararlıdır**.
>
> ⚠️ **Otomatik geri alma (rollback) YOK:** runtime'da sağlık kapısı başarısız kurulumu eski
> sürüme döndürür, ama launcher kendini değiştirdiği için aynı şey ONUN için yapılamaz. Elimizdeki
> korumalar: deneme sayacı (sonsuz "indir-kur-geri al" döngüsünü kırar) + bu rollout anahtarı.

### Platform çıkarma / geri getirme

```powershell
python scripts/make_manifest.py --dir pemf-app-packages ... `
  --drop-platform mac-arm64 --drop-platform linux-x64
```

> ⚠️ **SAHİP KARARI 2026-08-09 — `mac-arm64` ve `linux-x64` manifest'ten ÇIKARILDI.** Sebep
> (ölçüldü): o platformlarda `layers` yoktu → **rollout freni çalışmıyordu**, ve client
> self-update'i Windows'a özel (`"Bu platformda oto-güncelleme desteklenmiyor"`) → kurulan cihaz
> **eski sürümde kalıcı olarak kilitleniyor** ve bozuk bir yayın geri çekilemiyordu. Site zaten
> "Yakında" diyordu (donanım desteği Windows-özel), yani manifest'in paket sunması tutarsızdı.
> Client artık "bu platform için paket yok" deyip **durur** — sessizce kilitli bir cihaz kurmaktansa
> açık hata.
>
> **Geri getirmek için:** paketleri CI ile üret (`linux-backend.yml` / `mac-backend.yml`,
> `workflow_dispatch` veya `backend-linux-v*` / `backend-mac-v*` tag'i), **`layers` + `rollout`
> ekle**, sonra bu iki testi güncelle: `manifest.rs::depodaki_gercek_manifest_ayristirilir` ve
> `real_artifacts.rs::uretilen_manifest_launcher_tarafindan_okunur` — ikisi de şu an platformların
> **yokluğunu** kilitliyor ki yanlışlıkla geri sızmasın. Client self-update'i yine Windows'a özel
> kalır (mac/linux için .dmg/.deb self-update yolu yazılmadı).

## 3. Installer — Launcher (Tauri, ANA dağıtım)

Kullanıcının indirdiği ince-client (base.zip'i internetten çeker).

```powershell
cd launcher\app
npx @tauri-apps/cli build          # cargo + NSIS, ~60sn (incremental)
# eşdeğer (npx sorun çıkarırsa): cargo tauri build
```

> **`MODULE_NOT_FOUND` / `requireNative` hatası alırsan — npx cache'i bozuktur, tauri değil.**
> `@tauri-apps/cli` platform binary'sini (`@tauri-apps/cli-win32-x64-msvc`) *optionalDependency*
> olarak çeker. İnternet o an kesik/throttle'lıysa npm lock'u yazar ama binary'yi indiremez ve
> **bozuk ağacı `_npx` cache'ine kalıcı olarak yazar**; sonraki her çağrı yeniden çözmeden o
> cache'i kullanır → hata sonsuza dek tekrarlar. Teşhis ve çözüm:
> ```powershell
> # Teşhis: yalnız 'cli' varsa (yanında 'cli-win32-x64-msvc' yoksa) cache bozuktur
> dir $env:LOCALAPPDATA\npm-cache\_npx\*\node_modules\@tauri-apps
> # Çözüm: bozuk girdiyi sil, npx temiz kursun
> Remove-Item -Recurse -Force $env:LOCALAPPDATA\npm-cache\_npx\81a0b12969b730e4
> npx --yes @tauri-apps/cli --version    # tauri-cli 2.11.4 yazmalı
> ```
> (Bu makinede 2026-07-31'deki ağ kesintisinde oluşmuştu; 2026-08-05'te temizlendi.)

- **Çıktı:** `launcher\target\release\bundle\nsis\PEMF Vet Client_1.9.9_x64-setup.exe`.
- **Yayın için ada kopyala:** `PEMFVetClient-Setup.exe` (site bu adı bekler) → `gh release upload launcher-v<sürüm> ... --clobber`.
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
6. **Web sitesi (yeni kullanıcılar da alsın):** `pemf-vet-web/src/config.ts` → `DOWNLOAD_HOST.windowsTag` yeni tag'e + `CLIENT.version` + `releaseDate`; sonra **push yeter** — Vercel projesi GitHub deposuna BAĞLI, `master`'a push üretim deploy'unu kendisi tetikliyor (2026-08-18'de ölçüldü: push → 17 sn'de Ready). CLI yalnız bağlantı kopmuşsa gerekir: `cd pemf-vet-web; npx vercel --prod --yes`. ⚠️ **`windowsTag` AYRI** (self-update Windows-only) → `launcherTag`'i (mac/linux/android ortak) DEĞİŞTİRME, yoksa onlar 404.
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
# 1) ONCE paketler → client-app-v1.8.0   (siradan surumde YALNIZ base-app.zip degisir)
gh release upload client-app-v1.8.0 -R mert61-python/pemf-update --clobber pemf-app-packages\base-app.zip
#    (bagimliliklar degistiyse ayrica:)  ... --clobber pemf-app-packages\base-deps.zip
# 2) paketler YUKLENDIKTEN SONRA manifest  ← SIRA ONEMLI (asagi bak)
gh release upload client-app-v1.8.0 -R mert61-python/pemf-update --clobber pemf-app-packages\manifest.json
# 3) launcher setup + APK                 → launcher-v<surum>
gh release create launcher-v1.9.13 -R mert61-python/pemf-update --title "PEMF Vet Client 1.9.13" --notes "..." PEMFVetClient-Setup.exe release_assets\PEMF_Vet_Mobil.apk
# 4) web sitesi (indirme sayfasi)
cd pemf-vet-web; git push                        # Vercel GitHub'a BAGLI -> push = uretim deploy
#   (dogrulama: npx vercel ls  ->  en ustteki Production kaydi 'Ready' olmali)
#   ⚠️ ESKI NOT DUZELTILDI (2026-08-18): burada 'git-remote YOK -> CLI sart' yaziyordu.
#      Remote eklendi ve Vercel'e baglandi; CLI ile ikinci bir deploy acmak gereksiz.
```

> ⚠️ **SIRA: paketler ÖNCE, manifest SONRA.** Manifest yeni sha'yı ilan ettiği anda tüm client'lar
> onu indirmeye çalışır. Paket henüz yüklenmemişse client 404 alır. Ters sırada yayınlama,
> yükleme süresi boyunca (1,2 GB ≈ 20 dk) sahadaki her client'ı kırar.

> **Client'lar güncellemeyi KENDİ alır (≥1.9.12).** Açılışta manifest'i diskteki
> `installed_packages.json` ile karşılaştırır; farklı olanı indirir. "Onar" gerekmez.
> Seans sürerken ertelenir. Yani yayın = dağıtım.

### Güncelleme davranışı (≥1.9.14)

| Aşama | Ne olur |
|---|---|
| Açılış, paketler İNMEMİŞ | **Arka planda** iner, ekran ele geçirilmez; kullanıcı hemen "Başlat"a basabilir |
| Açılış, paketler HAZIR | Kurulum yapılır (yalnız açma, saniyeler) |
| Kurulum | Yeni ağaç `runtime.new`'de hazırlanır → **atomik takas** → `runtime.old` yedekte bekler |
| Sağlık kapısı | Backend başlatılır (`start_and_wait` `/api/health` bekler). **Açılırsa** yedek silinir ve sha kaydedilir; **açılmazsa** eski sürüme dönülür |
| Seans sürüyorsa | Hiçbir dosyaya dokunulmaz, güncelleme ertelenir |

⚠️ **sha kaydı sağlık kapısından SONRA yazılır.** Çalışmayan bir sürüm asla "kurulu"
işaretlenmez — yoksa bir sonraki açılış onu güncel sanıp düzeltmeye çalışmazdı.

### 🔴 GERİ ÇEKME ANAHTARI (bozuk yayını durdurma)

Güncelleme otomatik uygulandığı için bozuk bir yayın bir sonraki açılışta **sahadaki her cihaza**
gider. Freni `manifest.json` → `layers.<platform>.rollout` (0-100):

```powershell
# 1) DURDUR: manifest'te rollout: 0 yap, sonra YALNIZ manifest'i yeniden yükle
gh release upload client-app-v1.8.0 -R mert61-python/pemf-update --clobber pemf-app-packages\manifest.json
# 2) Düzeltilmiş paketi yayınla, sonra kademeli aç: 10 → 50 → 100 (her adımda manifest'i yükle)
```

- `rollout: 0` → **henüz güncellememiş hiçbir cihaz almaz** (güncellemiş olanlar geri alınmaz;
  gerekirse `layers`'ı eski sha'lara geri çevirin — o zaman "yeni sürüm" olarak eskiye dönerler).
- Cihaz dilimi `install_id.txt`'ten türer → **kararlıdır**; yüzde artınca sıra sırayla gelir,
  cihazlar dilimler arasında zıplamaz.

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
├─ VERSION                     # app/backend sürümü (1.9.5) — versions.json tarafından yazılır
├─ versions.json               # ⭐ TÜM sürümlerin TEK KAYNAĞI
├─ keys/                      # 🔑 Android imzalama anahtarı YEDEĞİ (gitignore'lu — bkz. keys/README.md)
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

---

## 7. Kaynak şifreleme (opsiyonel, 2026-08-06)

⚠️ **NE KORUR, NE KORUMAZ:** çözme anahtarı üründe (frozen EXE'de) gider. Bu katman klasörü
kopyalayıp kaynağı doğrudan okumayı engeller; **tersine mühendisliği ENGELLEMEZ.** Asıl koruma
`.py → .pyd` native derlemedir (Cython/Nuitka). "Kod şifreli" demek "kaynak çıkarılamaz" demek değildir.

**Neden `ai_hub` (ölçüldü):** frozen build'de `servers/`, `database/`, `utils/` EXE'ye gömülü
`.pyc` olarak gider — diskte kaynak YOKTUR. Ama `ai_hub/` **49 dosya / 507 KB düz `.py`** olarak
`_internal/ai_hub/` altına kopyalanır; yani tüm AI çıkarım pipeline'ları okunabilir durumdadır.
Şifreleme tam olarak bu açığı hedefler.

### Kurulum (bir kez)
```powershell
copy build_tools\_static_password.example.py build_tools\_static_password.py
# içine SOURCE_PASSWORD = "..." yazın  (.gitignore'lu; keys/ ile birlikte YEDEKLEYİN)
```
⚠️ Parola kaybolursa şifrelenmiş build'ler açılamaz.

### Build akışı
```powershell
.\scripts\build_backend_exe.ps1                      # 1) EXE (spec parolayı gömer)
python build_tools\encrypt_sources.py --dry-run      # 2) neyin şifreleneceğini gör
python build_tools\encrypt_sources.py --verify       # 3) şifrele (.py → .pyenc, düz kaynak SİLİNİR)
python build_tools\make_base_zip.py                  # 4) paketle
```
- Betik **yalnız `dist` içeren yolda** çalışır → kaynak ağacını yanlışlıkla şifrelemek imkânsız.
- `__init__.py` şifrelenmez (paket keşfi bozulur).
- Şifresiz build normal çalışır: parola yoksa yükleyici sessizce devre dışı kalır.

### Doğrulandı (2026-08-06, frozen EXE üzerinde)
`_internal/ai_hub` → 49 `.pyenc`, 0 düz `.py`; dosyada `def predict` / `PhantomPredictor`
görünmüyor. EXE çalıştırıldı ve **em_fantom · disease · kidney_ct · histopath · em_petri**
uçlarının hepsi `success` döndü → runtime çözücü frozen ortamda çalışıyor.

### Kalan: `.pyd` derleme
Asıl koruma. `ai_hub` modülleri Cython ile `.pyd`'ye derlenmeli; şifreleme onun tamamlayıcısıdır.
