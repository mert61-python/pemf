# Klasör Yapısı Planı — monorepo düzeni

> Denetim: [`DEPO-DENETIMI-2026-09-15.md`](DEPO-DENETIMI-2026-09-15.md)
> Bu belge **planlama**dır; hiçbir taşıma henüz yapılmadı.

---

## Önce cevap: evet, ayrılmalı — ama tek depo içinde

"Frontend / backend / client / web sitesi ayrılsın mı?" sorusunun cevabı evet. Ama **ayrı
depolara bölmek değil** — bu, kayıtlı sahip kararına aykırı (`PEMF Tek Depo`: CI yalnız kök
`.github/`, sürüm tek `versions.json`). Ayrıca dört ürün aynı anda sürümleniyor: backend 1.9.50,
launcher 1.9.51, mobil 2.3.34 tek manifestten dağıtılıyor. Depoyu bölmek bu tek-sürüm
sözleşmesini kırar.

Doğru çözüm **monorepo düzeni**: tek depo, ama kökte sevk edilen ürünler net ayrılmış.

### ⚠️ Ama bunu ÖNCE yapmak yanlış olur

Dürüst olmak gerekirse: klasör taşımak, denetimde bulunan gerçek arızaların **hiçbirini**
çözmez. Göç kodu hâlâ beş kopya kalır, `api_server.py` hâlâ 5.139 satır olur, sır kırılganlığı
aynen durur. Klasör düzeni **gezinmeyi** ve dışarıya verdiğin izlenimi düzeltir.

Dahası: şimdi taşırsan, sonra birleştireceğin kopyaları **taşınmış hâlleriyle** birleştirmek
zorunda kalırsın — iki kat iş. Bu yüzden sıra şu:

| Sıra | İş | Neden önce |
|---|---|---|
| **1** | `pyproject.toml` + `__init__.py` | Paket sınırları tanımlanmadan taşıma yapılamaz |
| **2** | Kopyaları birleştir (göç kodu, CV modülleri) | Taşınacak dosya sayısını **azaltır** |
| **3** | Derleme çıktılarını ağaç dışına al | Taşıma sırasında 20 GB'ı sürüklemezsin |
| **4** | **Klasör düzeni** (bu belge) | Artık taşınacak şey sade |
| **5** | Dev dosyaları böl | Yeni sınırlar içinde doğal yerlerine düşer |

---

## Hedef düzen

```
guii/
├─ apps/                        ← SEVK EDİLEN ÜRÜNLER (her biri bağımsız derlenir)
│  ├─ backend/                  Python servis — frozen EXE'nin kaynağı
│  │  ├─ pemf_backend/          (paket: servers, services, database, utils, controllers)
│  │  ├─ pyproject.toml
│  │  └─ README.md
│  ├─ launcher/                 Rust/Tauri istemci  ← bugünkü launcher/
│  ├─ ui/                       React Native/Expo   ← bugünkü pf/
│  │                            (masaüstü arayüzü de buradan üretilip EXE'ye gömülüyor)
│  └─ web/                      Pazarlama sitesi    ← bugünkü pemf-vet-web/
│
├─ firmware/                    stm32_pemf · esps3_pemf_coil · esp8266_pemf_coil  (değişmiyor)
│
├─ libs/                        PAYLAŞILAN KOD — birden fazla yerden kullanılan
│  ├─ goc/                      tek göç modülü (bugün 5 kopya)
│  └─ cv_ortak/                 coord_transform · mqtt_publish · cabin_config (bugün 2-3 kopya)
│
├─ ai/                          MODELLER VE ÇIKARIM
│  ├─ hub/                      ← ai_hub/
│  ├─ service/                  ← ai_service/ (ayrı GPU servisi)
│  └─ models/                   ← release_assets/ai_models (ağırlıklar, tek kaynak)
│
├─ tools/                       GELİŞTİRİCİ ARAÇLARI
│  ├─ build/                    ← build_tools/
│  ├─ gates/                    CI kapıları (make_manifest, responsive_kapisi, …)
│  └─ ops/                      saha/operasyon betikleri (vault_emanet, firmware_derle, …)
│
├─ deploy/                      env dosyaları, docker, supabase  (değişmiyor)
├─ docs/                        (değişmiyor)
├─ tests/                       (değişmiyor — konumu değil, içeriği apps'e göre bölünebilir)
├─ .github/                     CI — TEK yer  (değişmiyor)
└─ versions.json · CHANGELOG.md · README.md · LICENSE
```

### Kökten kalkacaklar

| Bugün | Nereye | Not |
|---|---|---|
| `backend_service.py` · `headless_core.py` · `event_bus.py` | `apps/backend/pemf_backend/` | Spec'teki elle `hiddenimports` satırı gereksizleşir |
| `servers/` `services/` `database/` `utils/` `controllers/` | `apps/backend/pemf_backend/` | |
| `pf/` | `apps/ui/` | |
| `pemf-vet-web/` | `apps/web/` | |
| `launcher/` | `apps/launcher/` | |
| `ai_hub/` `ai_service/` | `ai/hub/` `ai/service/` | |
| `build_tools/` `scripts/` `tools/` | `tools/build` `tools/gates` `tools/ops` | Bugün üçü karışık: derleme kapıları `scripts/`te, operasyon aracı `build_tools/`ta |
| `PEMF_BUILD/` `firmware_cikti/` `offline dağıtım/` | **ağaç dışı** → `../pemf-build/` | Derleme çıktısı kaynakla aynı yerde durmamalı |
| `pemf-app-packages/` `release_assets/*.exe` | **ağaç dışı** → `../pemf-dist/` | Dağıtım artefaktı; GitHub Releases zaten arşiv |
| `training_archive/` | **ayrı depo** ya da Git LFS | 297 MB, 434 takipli dosya; her klon indiriyor |
| `bin/` | `tools/build/bin/` + LFS | 60 MB üçüncü-parti ikili (cloudflared 52 MB) |

> ## ⛔ SILINECEKLER LISTESI YANLISTI — düzeltme 2026-09-17
>
> Yukarıdaki tablo altı dizini silinmeye aday gösteriyordu. Her biri referans taramasıyla
> ölçüldü: **altıdan beşi CANLI.** "0 takipli dosya" ya da "son commit eski" olmak ölü
> demek **değildir** — üretilen çıktı dizinleri git'te görünmez ama **ürün onları sunar.**
>
> | Dizin | Gerçek durum | Kanıt |
> |---|---|---|
> | `frontend/` | ⛔ **CANLI — ürünün ANA React arayüzü** | `api_server.py` → `app.mount("/")`; `dist` 11 MB |
> | `dema-terapi-simülatörü/` | ⛔ **CANLI** | `api_server.py` → `app.mount("/simulator")` + spec onu **EXE'ye koyuyor** |
> | `web_static/` | ⛔ CANLI | `PEMF_Backend_onedir.spec` datas döngüsünde |
> | `lattekurulum/` | ⛔ CANLI | `build_installer.ps1` → VC++ redist hedefi |
> | `pemf_vet_landing/` | ⚠️ referanslı | `tests/test_kontrol_bayti_kapisi.py` üretilmiş çıktı olarak listeler |
> | `website/` | ✅ referanssız | tek gerçek aday (3 takipli dosya) |
>
> ⚠️ **`frontend/` silinseydi** backend `/` adresinde *"Frontend derlemesi bulunamadı!"*
> uyarısı basıp **boş sayfa** sunardı — klinikte arayüz açılmazdı ve sebebi "silinen ölü
> dizin" olarak akla gelmezdi.
>
> Kapı: `tests/test_silinecek_sanilan_dizinler_CANLI.py`

### ~~Silinecekler~~ (⚠️ bu liste YANLIŞTI — yukarıdaki düzeltmeye bakın)

| Dizin | Kanıt |
|---|---|
| `website/` `web_static/` `pemf_vet_landing/` | 3 · 3 · 13 takipli dosya, son commit 2026-08-10, canlı yolda değil |
| `frontend/` | 0 takipli dosya — yalnız üretilen `dist` aynası; `apps/ui` build çıktısı yeter |
| `ai/config.py` | Üretimde hiç import edilmiyor; tek tüketicisi donmuş arşiv → arşive taşı |
| `scripts/analyze_project.py` | Qt tarıyor; projede Qt yok |
| `scripts/ai_service_scratch_smoke_istek.py` | Depo genelinde sıfır referans |
| `dema-terapi-simülatörü/` | 8.998 dosya / 12 takipli — ayrı bir çalışma, ayrı depoya |
| `lattekurulum/` | Tek bir `VC_redist.x64.exe` — `tools/build/` altına ya da indirme adımına |

### Yeniden adlandırılacak

| Bugün | Yarın | Neden |
|---|---|---|
| `pemf_gui/` | `apps/backend/pemf_backend/config/` | **Adı yalan**: projede Qt sıfır, ama içindeki `config.py` canlı backend yolunda |
| `pf/` | `apps/ui/` | "pf" dışarıdan hiçbir şey anlatmıyor |

---

## Taşıma nasıl yapılır — büyük patlama DEĞİL

⚠️ 1.944 takipli dosyayı tek seferde taşımak, PyInstaller spec'ini, 10 CI workflow'unun yol
süzgeçlerini, 170 `.gitignore` desenini ve launcher'ın Rust yollarını **aynı anda** kırar.
Hangisinin neyi bozduğunu ayırt edemezsin.

Her faz tek başına doğrulanır ve **yeşil bitmeden sonrakine geçilmez.**

| Faz | İş | Doğrulama kapısı |
|---|---|---|
| **F0** | `git mv` ile taşı (geçmiş korunur), hiçbir içerik değiştirme | `git status` yalnız R (rename) göstersin |
| **F1** | `apps/web` + `apps/ui` (backend'e dokunmaz) | `site.yml` + `frontend.yml` yeşil |
| **F2** | `apps/launcher` | `cargo test --workspace --locked` yeşil |
| **F3** | `ai/hub` + `ai/service` | `/api/ai/hazirlik?derin=1` → 16/16 modül |
| **F4** | `apps/backend` (en riskli — spec + import kökü) | **tam süit 2979** + `urun_dogrula.py` |
| **F5** | `tools/` üçe bölünmesi | CI'ya bağlı 3 betik yolu güncel, `lint.yml` yeşil |
| **F6** | Derleme çıktıları ağaç dışına | `build_backend_exe.ps1` baştan sona yeşil + EXE ürün doğrulaması |

**Her fazda güncellenmesi gerekenler** (unutulursa sessizce kırılır):
`build_tools/PEMF_Backend_onedir.spec` (pathex + hiddenimports) · `.github/workflows/*.yml`
(`paths:` süzgeçleri) · `.gitignore` · `pyproject.toml` (`[tool.coverage] source`) ·
`tests/conftest.py` (`sys.path.insert`) · `launcher/core/src/install.rs` (paket yolları) ·
`pf/android/keystore.properties`

---

## Ne kazandırır, ne kazandırmaz

**Kazandırır**
- Depoyu ilk kez açan biri dört ürünü ve sınırlarını beş saniyede görür.
- CI `paths:` süzgeçleri gerçek sınırlara oturur → gereksiz koşu azalır.
- Paylaşılan kod (`libs/`) kopyalanmak yerine **import edilir** — göç kodunun beş kopyası
  bir daha oluşamaz.
- Derleme çıktıları ağaç dışında → depo bir daha 48 GB'a şişmez.
- Tıbbi cihaz denetiminde "yazılım öğeleri" tanımı yapılabilir hâle gelir (IEC 62304).

**Kazandırmaz — bunları ayrıca yapmak gerekir**
- Sır kırılganlığı (`skip-worktree`) taşımayla düzelmez.
- `api_server.py` 5.139 satır olarak kalır, yalnız yeri değişir.
- BLE/firmware güvenliği ayrı bir iş.
- Lisans envanteri ayrı bir iş.

---

## Önerilen ilk adım

Hepsini birden yapma. **F1 ile başla** (`apps/web` + `apps/ui`): backend'e hiç dokunmaz, iki
CI workflow'u ile doğrulanır, yanlış giderse `git mv` geri alınır. Bir fazın ne kadar sürdüğünü
ve neyi kırdığını gördükten sonra kalanına karar verirsin.
