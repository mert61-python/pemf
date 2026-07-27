# PEMF Veteriner Cihazı — Backend (guii)

Bu klasör, PEMF veteriner PEMF-terapi cihazının **headless (arayüzsüz) Python backend'idir**.
FastAPI + uvicorn ile `http://0.0.0.0:8000` üzerinde çalışır; Windows'ta **NSSM** ile
`PemfBackend` adlı bir servis olarak kurulur. Donanımı (STM32 bobinler seri porttan,
ESP bobinler MQTT ile) sürer, sensörleri okur, hastaları yönetir ve **yapay zeka
teşhis modellerini** sunar. Mobil uygulama (React Native, ayrı `pf/` klasörü) bu
backend'e bağlanır.

> **Önemli:** Tüm AI modelleri artık **EXE'ye gömülüdür** (offline, self-contained).
> **Hugging Face indirme tamamen kaldırılmıştır** — internet gerekmez.

---

## 0) Arayüz — Ekran Görüntüleri

Mobil/Web arayüzü **React Native / Expo** ile tek kod tabanından **Web + Android + iOS**'te çalışır.
Üç kullanım profili — **Evcil Hayvan Sahibi · Veteriner Hekim · Araştırma Modu** — arayüzü kullanıcıya göre uyarlar.

<p align="center">
  <img src="docs/screenshots/react_login.png" width="620" alt="Giriş / Kimlik Doğrulama" /><br/>
  <em>Kimlik doğrulama (Giriş / Kayıt) — yalnız yetkili operatör; Supabase tabanlı e-posta doğrulama + şifre sıfırlama.</em>
</p>

<p align="center">
  <img src="docs/screenshots/research_welcome.png" width="215" alt="Profil seçimi" />
  <img src="docs/screenshots/research_home.png" width="215" alt="Araştırma Modu — ana ekran" />
  <img src="docs/screenshots/research_aihub.png" width="215" alt="Araştırma Modu — AI Hub" />
  <img src="docs/screenshots/ai_history.png" width="215" alt="AI Analiz Geçmişi" />
</p>
<p align="center"><em>Soldan sağa: <b>Profil Seçimi</b> (3 profil) · <b>Araştırma Modu</b> ana ekran · <b>Akıllı Teşhis</b> (Fantom Tümör / Petri Kuyu / Böbrek RNA·CT·Patoloji·Hastalık modelleri) · <b>AI Analiz Geçmişi</b> (şifreli, operatör-kapsamlı: Benim / Tüm Klinik).</em></p>

> Klinik (Veteriner) modunun ekranları — Dashboard, Tedavi Kontrol, Sensör Monitörü, KPI, Hasta Kayıtları, Tedavi Geçmişi, AI Hub — TÜBİTAK sonuç raporunda (`../tübitak/PEMF_2209B_Sonuc_Raporu.docx`, Şekil 8–16) yer alır. Ekran görüntüsü dosyaları: `docs/screenshots/`.

---

## 1) Hızlı Başlangıç — Ne Nerede?

| İhtiyaç | Yer |
|---|---|
| **Backend EXE (onedir)** | `dist/PEMF_Backend/PEMF_Backend.exe` (+ `_internal/`) |
| **Backend EXE (onefile)** | `dist/PEMF_Backend_onefile.exe` (tek dosya) |
| **Mobil uygulama (Android APK)** | `dist/PEMF_Mobil_universal.apk` |
| **Mobil uygulama (iOS IPA)** | `dist/PEMF_Mobil_iOS.ipa` (EAS bulut build; App Store/TestFlight) |
| **Build reçeteleri (spec/iss)** | `build_tools/` |
| **Dağıtım profilleri (device/server)** | `deploy/device.env`, `deploy/server.env` |
| **AI modelleri (kaynak)** | `release_assets/ai_models/` |
| **AI model KODU** | `ai_hub/<model>/` |
| **Backend kaynak kodu** | `servers/`, `ai/`, `controllers/`, `services/`, `database/`, `utils/` |
| **Mobil kaynak kodu (canlı geliştirme)** | `C:\Users\merta\pf` (ayrı React Native projesi) |
| **Mobil kaynak kodu (YEDEK kopya)** | `mobile/` (temiz snapshot — `node_modules`/build hariç, guii içinde) |
| **Web arayüzü (React web export)** | `frontend/dist/` (backend `/` kökünden servis eder) |

Build ortamı Python: `C:\Users\merta\Downloads\python-3.10.2-embed-amd64\myenv\Scripts\python.exe`

> **Build ortamı (`myenv`) yedekte YOK — ama gerekmez.** `myenv`, guii'nin **dışında**
> (`python-3.10.2-embed-amd64\myenv`, ~3 GB) bir virtualenv'dir ve `pyvenv.cfg` içinde ana
> embeddable Python'a **mutlak yolla bağlıdır** → olduğu gibi kopyalamak kırılgandır. Bunun
> yerine build ortamı `guii/requirements.txt`'ten **yeniden kurulur** (tek dosya, kilitli sürümler):
> ```bat
> :: 1) Python 3.10.2'yi kur (veya embeddable python-3.10.2-embed-amd64'ü edin)
> python -m venv C:\pemf-build\myenv
> :: 2) Paketleri kur (requirements.txt PyTorch CPU index'ini kendi içinde bildirir):
> C:\pemf-build\myenv\Scripts\python.exe -m pip install -r guii\requirements.txt
> :: 3) Artık bu python ile PyInstaller build alınır (aşağıdaki komutlar)
> ```
> `requirements.txt` = TEK kilitli bağımlılık dosyası (doğrudan bağımlılıklar, `==` ile
> myenv'e sabitli; eski requirements-service/-test/.lock birleştirildi). Yani **yedek için
> `guii` tek başına yeterli**: build ortamını, `mobile/` mobil kaynağı, `frontend/dist`
> web'i, `release_assets/ai_models` modelleri içerir.

---

## 2) EXE Nasıl Alınır (Backend)

PyInstaller ile derlenir. **Çalışma dizini `guii` OLMALI** (spec `os.getcwd()` kullanır).

### a) onedir (klasör — servis için ÖNERİLEN, hızlı başlar)
```bat
cd C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii
"C:\Users\merta\Downloads\python-3.10.2-embed-amd64\myenv\Scripts\python.exe" -m PyInstaller build_tools\PEMF_Backend_onedir.spec --noconfirm
```
**Çıktı:** `dist/PEMF_Backend/` (≈3.3 GB — EXE + `_internal/` içinde tüm modeller gömülü).

### b) onefile (tek dosya — taşıma için; ilk açılış yavaş)
```bat
cd C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii
"C:\Users\merta\Downloads\python-3.10.2-embed-amd64\myenv\Scripts\python.exe" -m PyInstaller build_tools\PEMF_Backend_onefile.spec --noconfirm
```
**Çıktı:** `dist/PEMF_Backend_onefile.exe` (≈2.3 GB tek dosya). Çalışınca içeriği `%TEMP%`'e
açtığı için **ilk başlangıç yavaştır**; sürekli çalışan servis için `onedir` tercih edin.

> İki spec de **aynı içeriği** üretir; fark paketleme (klasör vs tek dosya). Her ikisi de
> `release_assets/ai_models/**` ağacını `_internal/ai_models/`'e gömer → 19 ONNX + histopath
> dahil tüm modeller EXE içinde, offline.

---

## 3) APK Nasıl Alınır (Mobil)

Mobil uygulama **ayrı bir React Native (Expo) projesidir**: `C:\Users\merta\pf`.
APK, Android Gradle ile derlenir.

> **Yedekten derleme:** `guii/mobile/` bu projenin **temiz snapshot yedeğidir** (`node_modules`
> ve build çıktıları hariç). Yedekten sıfırdan derlemek için: `cd guii\mobile && npm install`
> (bağımlılıkları indirir) → ardından `cd android && gradlew assembleRelease ...`. Canlı
> geliştirme yine `C:\Users\merta\pf`'de yapılır; `mobile/` yalnızca guii yedeğinin
> kendi-kendine yeterli olması için tutulur.

### Universal APK (tüm Android'ler — ÖNERİLEN)
```bat
cd C:\Users\merta\pf\android
gradlew assembleRelease -PreactNativeArchitectures=armeabi-v7a,arm64-v8a,x86,x86_64
```
### Sadece arm64 (daha küçük ~60MB, yalnız arm64 telefonlar)
```bat
gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a
```
**Ham çıktı:** `C:\Users\merta\pf\android\app\build\outputs\apk\release\app-release.apk`
→ bu dosya, deliverable olarak `guii/dist/PEMF_Mobil_universal.apk`'ye kopyalanır.

Telefona kurmak için (USB + ADB):
```bat
adb install -r C:\Users\merta\pf\android\app\build\outputs\apk\release\app-release.apk
```

### iOS IPA (EAS bulut — Windows'ta yerel derlenemez)
iOS build macOS+Xcode ister → **EAS Build (Expo bulut)** ile alınır. İmzalama sertifikaları
EAS sunucusunda önbellekli (Apple Team `TNBV9TZ4TT`, 2027'ye kadar geçerli) → Apple 2FA gerekmez.
```bat
cd C:\Users\merta\pf
npx eas build --platform ios --profile production --non-interactive
```
Build bulutta ~5-40 dk sürer; biten `.ipa` `expo.dev` build sayfasından indirilip
`guii/dist/PEMF_Mobil_iOS.ipa`'ye kopyalanır. **production** profili App Store/TestFlight
dağıtımı içindir (doğrudan sideload edilmez); cihaza doğrudan kurulum için `preview` profili +
kayıtlı cihaz UDID gerekir. Bundle: `com.pemf.vet`, owner `@mert6161`.

---

## 4) Deploy / Kurulum (Backend)

Aynı EXE hem **klinik cihazı (device)** hem **sunucu (server)** için kullanılır; fark
`deploy/device.env` ve `deploy/server.env` profillerindedir (STM portu, mod, TLS vb.).

- **Yerel servise deploy (geliştirme):** `dist/PEMF_Backend`'i durdurup `C:\Program Files\PEMF Backend`'e kopyalar, servisi yeniden başlatır (yönetici gerekir). Bkz. `deploy/README.md`.
- **Servis kur/mod seç:** `scripts/setup_services.ps1` (device/server modu, NSSM ile `PemfBackend` servisi).
- **Installer üret (.exe kurulum) — DOĞRUDAN ISCC (doğrulandı 2026-07-07):** onedir build'inden sonra:
  ```bat
  cd C:\Users\merta\Downloads\python-3.10.2-embed-amd64\guii
  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build_tools\PEMF_Backend_Setup.iss
  ```
  → `build_tools/Output/PEMFBackendSetup_device_v1.5.0.exe` (~3.5 GB). Installer çalışınca eski `PemfBackend` servisini `sc stop` eder → Program Files'a kurar → ai_models'i ProgramData'ya kopyalar → `setup_services.ps1` ile servisi kurup başlatır. **Kurulum-öncesi UYARI:** eski servis durdurulsa da onun açtığı `cloudflared.exe` (tünel) çalışmaya devam edip dosyayı KİLİTLER → installer "DeleteFile kod 5" verir; yönetici PowerShell'de `taskkill /F /IM cloudflared.exe` (gerekirse `mosquitto.exe`) → "Yeniden denensin".
  > *(Not: `build_installer.ps1` **eski** `PEMF_GUI_onedir.spec` adını referans alır — güncel spec `PEMF_Backend_onedir.spec` olduğundan o script patlar; yukarıdaki doğrudan ISCC yolu geçerlidir.)*

Detaylı dağıtım: kökteki `DEPLOYMENT.md` + `deploy/README.md`.

---

## 5) Klasör Yapısı — Tek Tek

### Backend kaynak kodu
| Klasör/Dosya | İçerik |
|---|---|
| `servers/` | FastAPI uygulaması. `api_server.py` (ana app + WS + seans), `ai_router.py` (tüm AI uçları + AI Pro otonom tedavi döngüsü), `auth.py` (X-API-Key + LAN muafiyeti). |
| `ai/` | AI yardımcı katmanı. |
| `ai_hub/` | **AI model KODU** — her model kendi alt-klasöründe (`inference_*`, `cat_*`, `em_kedi` …) + wrapper'lar (ör. `catorgan_predictor.py`). *(Büyük `.onnx` kopyaları temizlendi; modeller `release_assets`'ten/bundle'dan çözülür.)* |
| `controllers/` | Donanım/iş mantığı kontrolcüleri. |
| `services/` | Servis katmanı (e-posta, bulut vb.). |
| `database/` | Yerel şifreli SQLite (hasta/seans) erişimi. |
| `utils/` | Yardımcılar. `model_downloader.py` (**yalnız yerel** model çözümü, HF yok), `secrets_manager.py`, `path_utils.py`, `coil_map.py`. |
| `firmware/` | STM32/ESP firmware ile ilgili dosyalar. |
| `config/`, `data/`, `templates/`, `web_static/`, `website/` | Konfig, veri, HTML şablon/statik + tanıtım sitesi. |
| `backend_service.py`, `headless_core.py`, `event_bus.py`, `main.c` | Servis giriş noktası + çekirdek + olay veri yolu (+ C yardımcı). |
| `requirements.txt` | TEK kilitli Python bağımlılık dosyası (Qt/QR/mediapipe/eğitim-libleri KALDIRILDI). |

### Mobil / Web arayüzü
| Klasör/Dosya | İçerik |
|---|---|
| `mobile/` | **Mobil uygulamanın YEDEK kopyası** — React Native (Expo) kaynağı (`src/`, `android/`, `assets/`, `app.json`, `package.json` …). Temiz snapshot: `node_modules` ve build çıktıları HARİÇ (yeniden üretilebilir). Sıfırdan derleme: `npm install` → `android\gradlew assembleRelease`. Canlı geliştirme `C:\Users\merta\pf`'dedir; burası guii yedeğini kendi-kendine yeterli yapar. |
| `frontend/` | **Junction (sembolik bağ) → `C:\Users\merta\pf`.** Web export bu yoldan alınır (`npx expo export --platform web`). Gerçek dosya değil — bağdır; guii yedeği için gerçek kopya `mobile/`'dadır. |
| `frontend/dist/` | **React WEB export** (backend `/` kökünden servis eder; masaüstü kısayolu `localhost:8000` bunu açar). Mobil UI değişince yeniden export alınıp `_internal/frontend/dist`'e kopyalanmalı. |
| `frontend_temp/`, `website/`, `web_static/` | Eski/yedek web export + tanıtım sitesi + statik kaynaklar (mount fallback). |

### Build / Dağıtım
| Klasör/Dosya | İçerik |
|---|---|
| `build_tools/` | **Derleme reçeteleri:** `PEMF_Backend_onedir.spec`, `PEMF_Backend_onefile.spec` (PyInstaller), `*.iss` (Inno Setup installer), `build_installer.ps1`, PyInstaller hook'ları. |
| `deploy/` | Dağıtım profilleri: `device.env`, `server.env` + `README.md`. |
| `scripts/` | `setup_services.ps1` (servis kur/mod) vb. yardımcı scriptler. |
| `release_assets/ai_models/` | **Tüm AI modellerinin kaynağı** (19 ONNX, ~2.1 GB). EXE build'i bunu `_internal/ai_models/`'e gömer; installer da ProgramData'ya kopyalayabilir. |
| `dist/` | **Deliverable çıktılar:** `PEMF_Backend/` (onedir), `PEMF_Backend_onefile.exe`, `PEMF_Mobil_universal.apk`. |
| `bin/`, `lattekurulum/` | Yardımcı ikili/kurulum dosyaları (ör. NSSM, LattePanda kurulum). |

### Doküman / Araştırma / Diğer
| Klasör/Dosya | İçerik |
|---|---|
| `docs/` | Dokümanlar + `version_info.txt` (EXE sürüm bilgisi). |
| `DEPLOYMENT.md` | Dağıtım rehberi. |
| `tübitak/` | Araştırma raporları/makaleleri (TÜBİTAK). Runtime ile ilgisi yok. |
| `dema-terapi-simülatörü/`, `buildPEMF/` | Unity tabanlı simülatör (ayrı bileşen/kaynak+build). Backend ile ilgisi yok. |
| `pemf_gui/` | Eski PyQt GUI kaynağının kalıntısı (ikonlar/resources). Headless'a geçildi; sadece ikon/versiyon için referans. |
| `tests/` | Test dosyaları. *(Mobil/web dizinleri için yukarıdaki "Mobil / Web arayüzü" bölümüne bakın.)* |
| `*.log`, `*.txt` (build_exe_*, backend_build*), `_p2boot.err`, `__MACOSX/` | Build/çalışma **logları** ve arşiv artığı — güvenle silinebilir (regenerable). |
| `architecture_report.json`, `models_size.json`, `frontend_version.json`, `VERSION` | Meta/rapor dosyaları. |

---

## 6) AI Modelleri — Nasıl Çözülür (Önemli)

- **Kaynak:** `release_assets/ai_models/` (19 ONNX). EXE build'i bunları `_internal/ai_models/`'e **gömer**.
- **Runtime çözümü:** `utils/model_downloader.download_model_sync()` şu kökleri sırayla arar:
  `PEMF_AI_MODELS_DIR` → `C:\ProgramData\PEMF_GUI\ai_models` → AppData cache → `release_assets/ai_models` → **EXE bundle (`_internal/ai_models`)**.
- **Hugging Face indirme YOK** — bulunamazsa hata verir, internetten indirmez. Bu yüzden modeller
  ya EXE'ye gömülüdür ya da ProgramData'ya (installer) kopyalanır.
- **Modeller (özet):** kedi yüz-ağrısı (FGS), segmentasyon, termal, retikülosit, hastalık; böbrek CT/RNA/CKD/histopatoloji; em_fantom/em_petri (EM alan); kedi sesi; **kedi organ 3B lokalizasyon (cat_organ)** — AI Pro otonom tedavi bunu kullanır (el-takibi kaldırıldı); em_kedi (bobin duty modeli).

---

## 7) Tipik Akış (Sıfırdan Deliverable)

```text
1. Backend değişikliği yap  →  build_tools/PEMF_Backend_onedir.spec ile EXE al  →  dist/PEMF_Backend/
   (self-contained onefile istenirse PEMF_Backend_onefile.spec)
2. Mobil değişikliği yap    →  pf/android'de gradlew assembleRelease (universal)  →  app-release.apk
                            →  dist/PEMF_Mobil_universal.apk olarak kopyala
2b. WEB arayüzü de güncellenecekse (masaüstü kısayolu = localhost:8000):
                            →  cd frontend && npx expo export --platform web  →  frontend/dist
                            →  frontend/dist'i çalışan kuruluma kopyala: _internal/frontend/dist
                               (nssm stop PemfBackend → robocopy /MIR → nssm start)  [EXE rebuild GEREKMEZ]
3. Deploy: deploy_backend.cmd (yönetici) VEYA build_installer.ps1 ile installer üret
4. Profil: device.env / server.env (klinik cihazı vs sunucu)
5. Yedek: guii klasörünü zip'le — mobil kaynak `mobile/` içinde gerçek kopya olarak durur
   (frontend/ junction'dır, yedeğe gerçek dosya olarak girmeyebilir).
```

**Dağıtım için gereken 3 şey `dist/` içindedir:** onedir EXE (veya onefile) + universal APK.
```
