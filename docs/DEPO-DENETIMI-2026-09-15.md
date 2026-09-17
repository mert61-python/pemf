# Depo Denetimi — 2026-09-15

> Kapsam: `guii/` ağacının tamamı. Disk ölçümü + kod organizasyonu + yapılandırma/sır hijyeni.
> Her satır ölçüldü; "belgede öyle yazıyor" hiçbir yerde kanıt sayılmadı.

---

## 0. Yapılan iş — disk: **46,7 GB → 20,2 GB**

30.224 dosya silindi. Silinenlerin tamamı **yerelde yeniden üretilebilir** — hat kotalı
olduğu için indirme gerektiren hiçbir şeye dokunulmadı.

| Silinen | Boyut | Neden güvenli |
|---|---:|---|
| `launcher/target/debug` | 11,34 GB | Rust debug önbelleği; `cargo build` üretir |
| `PEMF_BUILD/` | 5,30 GB | PyInstaller çıktı ağacı; kurulu EXE `%LOCALAPPDATA%`'da duruyor |
| `build_tools/Output/` | 3,49 GB | `offline dağıtım/` ile **SHA256 birebir aynı** |
| `pf/android/app/build` | 2,86 GB | Gradle çıktısı |
| `release_assets/` eski kurulumlar (1.9.43–1.9.50) | 2,03 GB | Sekizi de GitHub Releases'te |
| `pemf-app-packages/research-2.zip` | 1,73 GB | **Yetim** — manifestte hiç geçmiyor |
| `git gc --prune=now` | 0,01 GB | 1453 gevşek nesne paketlendi |

**Bilerek dokunulmayanlar:** `pemf-app-packages/` kalan zip'leri (3,42 GB) ve `node_modules`
ağaçları. Geri getirmeleri **indirme** ister; 30 GB'lık hotspot kotasında ~5 GB'a mal olur.
Silme kararı sende.

### Neden 48 GB olmuştu — kök neden tek değil, beş tane

1. **Derleme çıktıları kaynak ağacının İÇİNDE.** `launcher/target`, `PEMF_BUILD`,
   `pf/android/app/build` — üçü birlikte 19,5 GB. Profesyonel yerleşimde bunlar ağacın
   dışında ya da tek bir yoksayılan dizinde toplanır.
2. **Aynı artefakt birden fazla yerde.** 3,5 GB'lık v1.9.20 offline kurulumu iki yerde
   bayt-bayt aynıydı.
3. **Her sürümün kurulumu sonsuza kadar saklanıyor.** 18 kurulum EXE'si, 2,55 GB.
4. **Dağıtım önbellekleri temizlenmiyor.** `pemf-app-packages` 5,1 GB — biri (research-2)
   hiçbir manifestte geçmiyordu.
5. **Yoksayma listesi bazı üretilmiş dizinleri kaçırıyor** — `firmware_cikti/` hâlâ
   yoksayılmıyor, `pf/android` de yoksayılmıyordu.

---

## 1. ⛔ P0 — PUBLIC depo bağlamında acil

> Depo `mert61-python/pemf` **herkese açık**. Aşağıdakiler bu bağlamda okunmalı.

### 1.1 BLE provizyon yüzeyi kimlik doğrulamasız — ve arayüz yalan söylüyor

Ölçülen kod (`firmware/esps3_pemf_coil/BLEProvisioning.cpp`):

```cpp
// Pelsiz/Şifresiz hızlı bağlantı için güvenlik ayarlarını devre dışı bıraktık.
NimBLEDevice::setMTU(256);
LOG_PRINTF("[BLE] Cihaz adı: %s, PIN: %d\n", deviceName.c_str(), DEFAULT_BLE_PASSKEY);
```

- Eşleşme, PIN ve şifreleme **bilerek kapatılmış**. Kod bunu yorumda söylüyor.
- Buna rağmen log **"PIN: 123456" yazıyor** — uygulanmayan bir PIN'i duyuran bir etiket.
  Bu, deponun kendi kayıtlı hata sınıfı: *düğme etiketi gerçeği söylemeli*.
- `DEFAULT_BLE_CMD_HMAC_KEY` **hiçbir yerde tüketilmiyor** (tüm `firmware/` tarandı; tek
  eşleşme tanımın kendisi). Yani sorun "anahtar varsayılan kalmış" değil —
  **komut imzalama hiç uygulanmamış.**

**Maruziyet — abartmadan:** BLE yayını iki koşulda açılıyor: 3 saniyelik buton basımı ve
**hiçbir WiFi ağına bağlanılamayınca otomatik** (`NetworkManager.cpp:449`). İkincisi önemli:
WiFi'ı bozan biri cihazı açık provizyon moduna zorlayabilir. Yazılabilir alanlar: WiFi SSID,
WiFi parolası, MQTT yapılandırması → cihaz saldırganın broker'ına yönlendirilebilir.

**Bugünkü gerçek risk sınırlı:** ESP bobin sürmüyor (`ESP_COIL_IDS = {8}`, 8 rezerve slot).
Yani bu **bugün hasta güvenliği açığı değil**. Ama ESP geri açılırsa yol doğrudan bobin
kontrolüne çıkar. Karar: ya BLE güvenliği açılır, ya da ESP geri gelmeden bu kapı kapatılır.

### 1.2 Bulut MQTT broker adresi HEAD'de ve geçmişte

İki takipli dosyada (`docs/PEMF_SISTEM_RAPORU.md`, `tests/test_cloud_provision.py`) ve
6 commit'lik geçmişte duruyor. `.gitleaksignore` bunları "şablon" gerekçesiyle muaf tutmuş.
Tek başına parola değil ama PUBLIC depoda **hedef adresi** ifşa ediyor ve aynı adres eşleşen
kullanıcı adı/parolayla kullanılıyor. Kimlik bilgileri döndürülmeli.

### 1.3 Gerçek sırların tek koruması `skip-worktree`

`firmware/*/Secrets.h` commit'te **şablon**, bu makinede **dolu** (gerçek WiFi + bulut MQTT
kimlik bilgileri). Ayrımı `skip-worktree` bayrağı sağlıyor — **klon-yerel**. Yeni bir klonda,
yeniden kurulumda ya da bayrak kalkarsa `git add -A` bunları PUBLIC depoya taşır. Bayrağı
kuran bir script/hook depoda yok.

Yedek kapı doğru kurulmuş: `.gitleaks.toml` içindeki `pemf-firmware-secrets-h-gercek-deger`
kuralı yer-tutucu olmayan değerleri yakalıyor, hem pre-commit hem CI'da koşuyor. **Tek
güvence o.**

### 1.4 Apple/Android imzalama anahtarları depo kökünde

`AuthKey_CWBVQNM6H7.p8`, `AuthKey_SJ75ZM76TQ.p8`, `developerID_application.cer`,
`apple-mac-cert/` (`.p12` + parolası düz metin), `keys/pemf-release.jks`.

Hepsi `.gitignore`'da — yani git'e girmemişler, bu iyi. Ama **fiziksel olarak depo kökünde
duruyorlar**; tek bir `git add -f` onları açık depoya taşır. `.gitignore:166` zaten
"Keychain/parola yöneticisi/GitHub Secrets" diyor — talimat var, uygulama yok.

---

## 2. 🟠 P1 — Ticari ürün olgunluğu

### 2.1 Bu oturumun işi CI'dan hiç geçmedi

- **18 commit** yerelde, `origin`'e push edilmemiş
- **115 değiştirilmiş + 46 takipsiz** dosya commit edilmemiş
- Bunların **14'ü yeni test dosyası** — yarım-göç veri kaybı kapısı, jeton bakiyesi,
  S3 WDT/TLS, toplu silme… **CI bu testleri hiç görmedi**
- Vault emaneti kodu (`scripts/vault_emanet.py`, `hasta_anahtari_emanet.py`) da commit dışı

CI hattı sağlam kurulmuş (ubuntu+windows matrisi, kapsam ratchet'i `fail_under=50`,
gitleaks tam geçmiş taraması, `cargo test --locked`) — ama son 3-4 günlük çalışma o
kapılardan geçmedi.

### 2.2 Paket metadatası yok

`pyproject.toml` 97 satır ve **yalnız araç ayarı**: `[project]` yok, `[build-system]` yok,
`setup.py` yok, `src/` yok. Depo kurulabilir bir Python dağıtımı değil; kök dizinin kendisi
import kökü.

Somut maliyeti: `headless_core.py` ve `event_bus.py` kökte durduğu için PyInstaller onları
keşfedemiyor ve spec'e **elle** sabitlenmişler (`PEMF_Backend_onedir.spec:401`). Ayrıca
`controllers/`, `scripts/`, `build_tools/` paket gibi import ediliyor ama `__init__.py`'leri
yok — PEP 420'ye bel bağlanmış.

⚠️ IEC 62304 açısından: yazılım öğesi tanımlama için kurulabilir bir birim ve makine-okunur
sürüm metadatası yok. Kısmi telafi var (`VERSION` + `versions.json` + CHANGELOG pre-commit
kapısı).

### 2.3 Göç kodu **beş yerde** — ve bu zaten hasta geçmişi kaybettirdi

| Yol | Fonksiyon |
|---|---|
| `database/sqlcipher_util.py` | `migrate_to_encrypted_if_needed`, `_yarim_goc_toparla`, `_tasi_yeniden_dene` |
| `database/treatment_history_db.py` | `_migrate_to_encrypted_if_needed` (inline kopya), `_run_startup_migrations_with_rollback` |
| `utils/path_utils.py` | `_sqlcipher_anahtarini_gocur`, `_kullanicidan_makineye_gocur`, `initialize_database` |
| `servers/api_server.py` | `_ai_hasta_kimliklerini_tasi_bir_kez`, `_migrate_ai_jsonl_once` |
| `pemf_gui/config.py` | `_migrate_legacy_config_dir`, `_migrate_plaintext_secrets` |

2026-09-13'te ölçülen sonuç: ilk iki kopya düzeltildi, **ürün hâlâ kaybediyordu** çünkü
üçüncü yol (şablon kopyalayıcı) önce davranıyordu. Bu kopyalama gerçek bir arızaya dönüştü.

### 2.4 Kopya kod — 470 satır bayt-bayt, 366/367 satır sürüklenmiş

| Kanıt | Dosyalar |
|---|---|
| MD5 birebir, 326 satır | `inference_em_fantom/phantom_cv/coord_transform.py` ↔ `inference_petri_dish/petri_cv/coord_transform.py` |
| MD5 birebir, 144 satır | aynı ikilinin `mqtt_publish.py`'leri |
| 367 satırın 366'sı aynı | iki `cabin_config.py` — tek fark `client_id` varsayılanı |

`coord_transform.py` koordinat dönüşümü yapıyor — yani bobin/hedef geometrisi, güvenlik-ilgili
bir hesap. Depo bu kopyalamayı **biliyor** ve kaldırmak yerine teste bağlamış
(`test_koordinat_donusumu_karakterizasyon.py`): her yeni config alanı iki dosyaya elle
eklenmek zorunda; kapı yalnızca unutulursa kırılıyor.

### 2.5 Dev dosyalar

| Satır | Dosya | Not |
|---:|---|---|
| 5.139 | `servers/api_server.py` | 96 fonksiyon, 15 sınıf, 21 route |
| 4.023 | `servers/ai_router.py` | 83 fonksiyon |
| 3.701 | `database/treatment_history_db.py` | **tek sınıfta 95 metot** — seans kaydı + coil-run + sensör batch + denetim izi + MQTT outbox + şema göçü + PII saklama |
| 1.319 | `ai_service/app.py` | |

Üretim kodunda 1000+ satırlık yalnız 4 dosya var; kalan 6'sı donmuş eğitim arşivi (lint muaf).

### 2.6 Lisans envanteri bayat

`THIRD_PARTY_LICENSES.md` 2026-08-10'da donmuş. O tarihten sonra `shap`, `grad-cam`, `timm`,
`captum`, `celldetection` eklendi. **AGPL'li `ultralytics` taşıyan bir üründe** lisans
envanterinin eksik olması ticari satışta doğrudan risk.

---

## 3. 🟡 P2 — Düzen ve hijyen

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
> | `website/` | ⛔ **SİLİNMEYECEK** | referanssız **ama** kendi `README.md`si *"silme, bırak — tarihsel referans"* diyor. v1.2 installer indirme sayfası. **Denetimi yazarken içindeki README'yi okumamışım** — karar kaydı da bir referanstır |
>
> ⚠️ **`frontend/` silinseydi** backend `/` adresinde *"Frontend derlemesi bulunamadı!"*
> uyarısı basıp **boş sayfa** sunardı — klinikte arayüz açılmazdı ve sebebi "silinen ölü
> dizin" olarak akla gelmezdi.
>
> Kapı: `tests/test_silinecek_sanilan_dizinler_CANLI.py`

### 3.1 Kökte 40 dizin, yedisi web/arayüz

`frontend/` · `pemf-vet-web/` · `pemf_gui/` · `pemf_vet_landing/` · `web_static/` ·
`website/` · `pf/`

Ölçülen canlılık:

| Dizin | Takipli | Son commit | Durum |
|---|---:|---|---|
| `pf/` | 308 | 2026-09-12 | **Canlı — tek UI kaynağı** |
| `pemf-vet-web/` | 99 | 2026-09-11 | Canlı (pazarlama sitesi) |
| `frontend/` | 0 | — | Yalnız üretilen `dist` aynası |
| `pemf_gui/` | 48 | 2026-08-10 | **Adı ölü** (Qt sıfır) ama `config.py` canlı backend yolunda |
| `pemf_vet_landing/` · `web_static/` · `website/` | 13 · 3 · 3 | 2026-08-10 | Donmuş |

Benzer durum AI tarafında: `ai/` · `ai_hub/` · `ai_service/` + `servers/ai_router.py`.
`ai/config.py` (349 satır) üretimde **hiç** import edilmiyor — tek tüketicisi donmuş arşiv.

### 3.2 `scripts/` — 23 betiğin 20'si CI dışı

CI'ya bağlı olan yalnız üçü: `check_changelog_surum.py`, `make_manifest.py`,
`responsive_kapisi.py`. Kalan ~4.750 satır yalnız elle çalışıyor — regresyon koruması yok.

Kesin ölü adaylar: `analyze_project.py` (Qt tarayıcı — projede Qt yok),
`ai_service_scratch_smoke_istek.py` (sıfır referans). Tek-seferlik olanlar:
`b_kaydi_topla.py`, `stm_workspace_kopyala.py`, `kabin_marker_a4.py`.

### 3.3 Git ağırlığı — LFS yok

`.git` 347 MB. En büyük takipli blob'lar `training_archive/` altında (297 MB, 434 takipli dosya:
70 + 45 + 40 + 32 MB'lık CSV'ler) ve `ai_hub/cat_disease/XGBoost.pkl` (50,8 MB).
**Git LFS kullanılmıyor** → her klon 347 MB indiriyor.

Ayrıca `bin/` **60 MB Windows ikilisi** (14 takipli dosya: `cloudflared.exe` 52 MB, mosquitto
DLL'leri, `nssm.exe`) doğrudan git'te duruyor ve yoksayılmıyor. Üçüncü-parti çalıştırılabilirler
sürüm kontrolüne değil, paketleme adımına ait.

⚠️ ~~`training_archive/ai_data/real_clinical_data/ecg_signals.npy` — PUBLIC bir depoda
**"gerçek klinik veri"** adlandırması ayrıca doğrulanmalı.~~

> **DÜZELTİLDİ — 2026-09-17: bu bulgu YANLIŞTI.** Ölçüldü: dizin **MIT-BIH Arrhythmia
> Database** (PhysioNet) kayıtlarını ve onlardan türetilmiş metrikleri içeriyor.
> `100.hea` başlığı standart MIT-BIH biçiminde (360 Hz, MLII + V5); CSV sütunları yalnız
> `SDNN`, `RMSSD`, `pNN50`, `LF/HF`, `mag_field_*`, `temp_*` gibi **türetilmiş** değerler —
> isim, kimlik ya da tarih sütunu **yok**. Yani hasta PII'si yok; **KVKK riski yok.**
> Dizin adı yanıltıcı: "gerçek" burada *sentetik olmayan sinyal* demek.
>
> ⚠️ **Ama yerine GERÇEK bir açık çıktı: ATIF.** Veriler PhysioNet/Zenodo'dan alınmış,
> PUBLIC depoda yeniden dağıtılıyor ve **hiçbir yerde lisans/atıf notu yoktu** — ne
> dizinde (0 dosya), ne `THIRD_PARTY_LICENSES.md`'de. Bu, B2'de kapatılan paket-atıfı
> boşluğunun **veri** karşılığıdır. Kapatıldı: dizin README'si + NOTICE'ta veri kümesi
> bölümü + `tests/test_veri_kumesi_atfi.py` (4 mutasyon).

### ~~3.4 `base-linux.zip` KAYIP~~ — ⛔ BU BULGU YANLIŞTI (düzeltme 2026-09-17)

> `base-linux.zip`in yokluğu **arıza değil, KARARDIR.**
>
> `launcher/core/src/manifest.rs` kayıtlı bir **sahip kararı** taşıyor (2026-08-09, Tier 1)
> ve yokluğu **kapıyla kilitliyor**:
>
> ```rust
> assert!(!m.runtimes.contains_key(platform::LINUX_X64),
>     "linux-x64 manifest'e geri girdi — o platformda rollout freni ve self-update YOK");
> ```
>
> Gerekçe (kararın kendi metninden): o platformlarda `layers` yoktu → rollout freni
> çalışmıyordu, self-update Windows'a özeldi → kurulan cihaz eski sürümde **kalıcı
> kilitleniyordu**. Client artık *"bu platform için paket yok"* deyip **durur** —
> sessizce kilitli cihaz kurmaktansa açık hata.
>
> **Ölçüldü 2026-09-17:** yayındaki manifest `runtimes: []`, `layers` yalnız `win-x64`;
> `pemf-update` deposunun altı release'inin hiçbirinde Linux varlığı yok (0/6).
>
> **Bulgu neden yanlış çıktı:** `docs/LAUNCHER_SPEC.md`teki *"Linux client sessizce
> Windows base.zip indirir"* uyarısını **güncel** sandım. O satır **v1 formatının**
> tarihsel tuzağını anlatıyor; hemen altındaki **v2 hedefi** (sessiz fallback yok, sert
> hata) 08-09'da zaten uygulanmış. Belgeye durum notu eklendi.
>
> ⚠️ Yan ölçüm: `linux-backend.yml` `permissions: contents: read` + yalnız
> `upload-artifact` — **release'e yazamaz.** Linux geri açılacaksa o adım da eklenmeli.

### 3.5 Bayat belgeler

| Dosya | Kanıt |
|---|---|
| `README.md:188` | *"Backend 1.9.5 · Launcher 1.9.9 · Mobil 2.3.3"* — gerçek: **1.9.50 / 1.9.51 / 2.3.34**. Aynı README'nin 49-50. satırı "tablo donmuştu, kaldırıldı" diyor → **aynı tuzağa ikinci kez** |
| `docs/PEMF_SISTEM_RAPORU.md` | İndekste "(2026-03)" — ~6 aylık |
| `docs/RUNBOOK.md` | 2026-08-15; ESP sökülmesi (09-11) sonrası güncellenmemiş |
| `frontend_version.json` | `"date": "2026-06-27"` |
| `docs/LAUNCHER_SPEC.md` | 2026-07-29 (launcher o gün 1.9.9'du, bugün 1.9.51) |

### 3.6 `firmware_cikti/` yoksayılmıyor

Firmware build çıktısı `git status`'ta kirlilik yaratıyor.

---

## 4. ✅ Sorun OLMAYANLAR — yanlış alarm çıkmasın

Bunlar bakıldı ve **temiz** çıktı; bir daha uğraşılmasın:

- **`.gitignore` şişkinliği yok.** 308 satırın %31'i Türkçe açıklama yorumu; tam tekrar
  yalnız **1 tane** (`*.plain.bak`).
- **requirements çakışması SIFIR.** İki dosyada ortak 25 paketin tamamı aynı sürümde.
  `opencv-python` ↔ `opencv-python-headless` farkı bilinçli (CI'da libGL gerekmesin).
- **`deploy/*.env` ve `.env.example` temiz** — sır yok, yalnız yapılandırma bayrakları.
- **CI'nın kendi güvenlik hijyeni iyi:** least-privilege token, pinli action'lar,
  adım-seviyesi sırlar.
- **`build_tools/source_crypto.py` kopya değil** — `utils/`den yeniden dışa aktarım,
  gerekçesi başlıkta yazılı (frozen EXE `build_tools`'u bundle'lamıyor).
- **Sır yönetimi 5 modüle bölünmüş ama kopya değil** — `vault_emanet.py` alan tanımını
  `hasta_anahtari_emanet.py`'den import ediyor.
- **Her ana dizinde dosya-başı görev tablosu içeren `README.md` var** — bu ölçekteki çoğu
  depoda bulunmayan bir olgunluk.

---

> ## ⛔ A2 · B4 · C5 — ÖLÇÜLDÜ, ÜÇÜ DE DÜZELTİLDİ (2026-09-17)
>
> ### A2 — "güvenlik-ilgili hesap" iddiası **TERSİNE DÖNDÜ**
> Kopya gerçek (MD5 aynı, doğrulandı). Ama `phantom_cv`/`petri_cv` **araştırma
> sağlayıcıları** ve `PEMF_ARASTIRMA_AIPRO=0` ile kapalı — `_arastirma_aipro_kapisi`
> **409** döndürüyor: *"bobin sürülmez."* Üstelik **bayrağın var olma sebebi tam da bu
> dosya**: `ai_pro_hedef.py:202` diyor ki `coord_transform` marker→kabin rotasyonunu
> uygulamıyor ve kedi hattıyla aynı çerçeveyi ürettiği **kanıtlanmadı**.
>
> Yani kopya kod **hiç bobin sürmüyor** ve zaten yeniden yazılmayı bekliyor. Şimdi
> birleştirmek, silinecek geometriyi birleştirmek olur. **Doğru an:** rotasyon düzeltmesi
> yapılırken — o zaman zaten tek yerde yazılır. ⚠️ Ayrıca `ai_hub` PYZ dışında sevk
> edildiği için doğrulaması **backend build** ister.
>
> ### B4 — doğru, ama ÖLÇÜT yanlıştı
> | Dosya | Satır | **Kod** | Yorum |
> |---|---|---|---|
> | `api_server.py` | 5.135 | 3.530 | %22 |
> | `ai_router.py` | 4.033 | 2.905 | %17 |
> | `treatment_history_db.py` | 3.530 | 2.888 | %9 |
>
> Satır sayısı bu depoda yanıltıcı ölçüt: yorumlar denetim geçmişini taşıyor, **özellik
> onlar**. Gerçek sorun `treatment_history_db.py` — **tek sınıfta 94 metot**.
> `api_server.py` 96 fonksiyon/15 sınıfla modül olarak kalabilir.
>
> ### C5 — iddia **BAYAT**; kalan tek madde de yapılamaz
> | | Denetim dedi | 2026-09-17 |
> |---|---|---|
> | `PEMF_BUILD` | 5,3 GB | **yok** |
> | `pf/android/app/build` | 2,86 GB | **yok** |
> | `build_tools/Output` | 3,49 GB | **yok** |
> | `launcher/target` | 11,34 GB | **6,9 GB — GERİ GELMİŞ** |
>
> Üçü zaten temiz. Asıl bulgu: **`launcher/target` silmekle çözülmüyor**, her `cargo`
> koşumunda geri geliyor (`.gitignore`da ama diskte).
>
> ⚠️ **`CARGO_TARGET_DIR` ile ağaç dışına almak YAPILMADI — ölçüldü, kırardı:**
> `.github/workflows/launcher.yml` satır **175** ve **190** `launcher/target/release/bundle`
> yolunu sabit yazıyor. Üstelik o workflow yalnız `launcher-v*` etiketiyle koşuyor —
> yani **yayın**; donmuş durumda düzeltme doğrulanamaz. Doğrulanamayan değişiklik yapılmadı.
> Disk geri kazanımı için bugünkü yol: `cd launcher && cargo clean`.

## 5. Öncelikli plan

**Hemen (senin kararın gereken):**
1. Bulut MQTT kimlik bilgilerini **döndür** (rotate) — adres PUBLIC geçmişte.
2. BLE kararı: güvenliği aç, ya da ESP geri gelmeden provizyon yolunu kapat. Bu arada
   log'daki yanıltıcı "PIN: 123456" satırını kaldır.
3. İmzalama anahtarlarını (`*.p8`, `*.cer`, `*.p12`, `*.jks`) depo kökünden çıkar.

**Bu hafta (bende yapılabilir):**
4. 18 commit + 14 yeni testi commit'le ve push et → CI kapılarından geçsin.
5. `THIRD_PARTY_LICENSES.md` yenile (AGPL yüzeyi dahil).
6. `README.md` sürüm tablosunu `versions.json`'dan **türet** — elle yazma, üçüncü kez
   bayatlamasın.
7. `firmware_cikti/` ve kalan üretilmiş dizinleri `.gitignore`'a ekle.

**Yapısal (planlanmalı, tek seferde değil):**
8. `pyproject.toml`'a `[project]` + `[build-system]` ekle; `controllers/`, `scripts/`,
   `build_tools/`'a `__init__.py`.
9. Göç kodunu **tek modüle** indir (`database/goc.py`) — beş kopya bir kez veri kaybettirdi.
10. `coord_transform.py` + `mqtt_publish.py` + `cabin_config.py` kopyalarını ortak bir
    `ai_hub/cv_ortak/` paketine al.
11. Ölü dizinleri kaldır: `ai/config.py` (arşive taşı), `website/`, `web_static/`,
    `pemf_vet_landing/` (donmuş), `pemf_gui/` → `config/` olarak yeniden adlandır.
12. `training_archive/` için Git LFS ya da ayrı depo.
13. `api_server.py` (5.139) ve `treatment_history_db.py` (95 metot) bölünmeli.

**Disk:**
14. Derleme çıktılarını kaynak ağacının dışına al (`PEMF_BUILD`, `launcher/target`).
15. Sürüm kurulumlarını yerelde biriktirme — GitHub Releases zaten arşiv.
