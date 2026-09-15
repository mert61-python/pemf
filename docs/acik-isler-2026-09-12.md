# Açık İşler — `docs/` tam taraması (2026-09-12)

**Kapsam:** `docs/` altındaki 33 belgenin tamamı okundu. Bu belge "ne yapıldı"yı değil,
**yapılmayanı / kapanmayanı** listeler.

⚠️ **YÖNTEM NOTU:** belgelerin kendi "Durum:" satırlarına GÜVENİLMEDİ. Bir kısmı bayattı ve
ölçünce yanlış çıktı (§5). Aşağıdaki her satır ya kaynak koddan doğrulandı ya da
"doğrulanamadı" diye işaretlendi.

---

## 1. Sahip kararı bekleyenler (mühendislik bloke)

| # | İş | Durum | Kaynak |
|---|---|---|---|
| A1 | **Ultralytics AGPL-3.0** — ürün kapalı kaynak + ücretli, `ultralytics` AGPL. Üretim yolunda **iki** modül hâlâ `.pt` (petri, kidney_ct) | AÇIK — karar sırası: **önce hukuk**, sonra bütçe | `AGPL-KARARI.md` |
| A1a | ⚠️ A1'in asıl sorusu: modeller Ultralytics'in **önceden eğitilmiş ağırlıklarından** mı türedi? Türediyse ONNX'e taşımak sorunu ÇÖZMEZ | Avukata sorulmadı | aynı |
| A2 | `.iss` **MyAppVersion == VERSION** kapısı — çıplak `iscc.exe` koridoru yanlış etiketli kurulum üretebiliyor | Sahip teyidi bekliyor ([BLD-6]) | `denetim-bulgular-3.md` |
| A3 | Ödeme/jeton yolu — `FREE_MODE=true`, `PEMF_TIER_ENFORCED=0`, `ENTITLEMENT_ENFORCED=false` | **Üretimde hiç koşmadı.** İlk gerçek müşteride görünür olacak bulgular var | `JETON-SISTEMI.md`, `denetim-bulgular.md` 5. tur |

## 2. Donanım / tezgâh bekleyenler

| # | İş | Durum | Doğrulama |
|---|---|---|---|
| B1 | **STM bobin 1-5 termal kesme YOK** — `PEMF_NTC_TERMAL_ENABLED 0` (derleme-kapılı) | ⚠️ **AÇIK P0.** Kodda bugün de `0` olduğunu ölçtüm (`main.c:852`) | koddan |
| B2 | **Bobin 6-7 termal kesme YAPILMAYACAK** (sahip kararı) — cihaz-taraflı koruma yok, yalnız istemci interlock | Bilinçli karar; kapanmayacak | `stm32-7-bobin-gecisi-plani` |
| B3 | **STM REFLASH + doz yeniden kalibrasyonu** — DDS simetrik bipolara çevrildi, eski doz eğrisi geçersiz | Bekliyor | `DONANIM-UYUM-ANALIZI`, `VERIFICATION` §9 |
| B4 | `VERIFICATION.md` ⏳ kalemleri: §2 SQLCipher cihazda · §4 Cloudflare **NAMED** tünel · §5 CVE yükseltme · §6 model SHA bütünlüğü · §7 yük/soak · §1 firmware satürasyon | Hiçbiri kapanmadı | belge |
| B5 | §14 ikinci reflash deltası (S3 + 8266) | ⚠️ **ESP sökülü olduğu için şu an ANLAMSIZ** — ESP geri gelirse borç geri gelir | memory + plan |
| B6 | **Kabin tezgâhı** — fantom/petri 3B çerçevesi ölçüldü ama **yetmedi** (kuyu kabin dışı çıkıyor); kamera lensi taban hizasında olduğu sürece ışın düzlemi sığ kesiyor | Araştırma AI Pro bayrağı **0 kalıyor** | `arastirma-ai-pro-...` |

## 3. Mühendislik açık (kod tarafında yapılabilir)

| # | İş | Durum |
|---|---|---|
| C1 | `supabase/resolve_device_bayat_gorunur.sql` **canlı projede uygulanmadı** — dosya depoda var, uygulama sahibin elle adımı | AÇIK |
| C2 | ESP kalanları: D-1 ölü topik (SELFTEST/reset_pwm) · D-3 freq clamp · HG-5 komut-kaybı deadman · HG-6 reboot mutabakatı | ⚠️ **UYKUDA** — ESP sökülü. Kod silinmedi; ESP dönerse hepsi geri açılır |
| C3 | `esp` dalında **canlı sırlar** + depo public | ⚠️ **AÇIK P0** (sahip reddi kayıtlı) |
| C4 | Launcher spec 3 açık soru: saha kurulum dizini · servis mi süreç mi · `.dmg` karantina/notarization kapsamı | AÇIK |
| C5 | macOS notarization | Apple sözleşmesi bloke |
| C6 | Rust client'ın **Linux** portu | Kalan iş |
| C7 | `cloud_mqtt_provision` Warn-only + bayat-dosya alt kalemi · 8266 status/ack `retain=true` | Küçük, ayrı karar |

## 4. Hiç bakılmamış / doğrulanamamış katmanlar

| # | Katman | Not |
|---|---|---|
| D1 | **Mobil saha testi** | Sahibin kendi ifadesi: "oraya hiç bakmadım denebilir". Bugün `SAHA-TEST-LISTESI` Kademe 6'ya **42 senaryo** eklendi |
| D2 | **iOS / EAS** | Hiç doğrulanmadı; yalnız bulut derlemesi var |
| D3 | Canlı **HiveMQ** bulut ucu · canlı **Supabase RLS/RPC** | Denetimlerde hiç açılamadı |
| D4 | **Docker / GPU profili** | Mikroservis üretimde kapalı |
| ~~D5~~ | [FW-6] S3 WDT bütçesi | ✅ **KAPANDI 2026-09-13 — aşağıdaki EK'e bakın.** (Eski hâli: "Doğrulanamadı — Arduino kütüphane kaynakları depoda yok". ⚠️ Kaynaklar geliştirme makinesinde KURULUYDU; "depoda yok" ölçümü bırakmak için yeterli gerekçe değilmiş.) |
| D6 | Cihaz matrisi (responsive) | Plan bitti + yayınlandı; gerçek cihaz matrisi koşulmadı |

## 5. ⚠️ Belge hijyeni — ÖLÇÜLEN bayatlıklar

Bu satırlar bugün koddan doğrulandı; belgeler **yanlış** durum bildiriyor:

| Belge | Diyor | Gerçek (ölçüldü) |
|---|---|---|
| `ai-hub-gorsel-sahne-plani-2026-09-10.md` | "ONAY BEKLİYOR (kod yazılmadı)" | **YANLIŞ** — kod canlı (galeri/zoom `AiHubScreen`de 20 eşleşme; 5 adımın tamamı 2026-09-12'de bitti) |
| `stm32-7-bobin-gecisi-plani-2026-09-10.md` | "Kod yazılmadı, pin bağlanmadı" | **KISMEN YANLIŞ** — `PEMF_BOBIN_UNIPOLAR_MASKESI` (0x60) firmware'de canlı; ayna proje kaldırıldı |
| `PEMF_SISTEM_RAPORU.md` §7 | LattePanda adımları `C:\Users\merta\.conda\envs\gui\python.exe` varsayıyor | **BAYAT** — o conda ortamı makinede YOK; mimari donmuş EXE'ye geçti |
| `react_installer_gap_report.md` (2026-06-04) | "build_installer React web export adımını çalıştırmıyor" | **DÜZELMİŞ** — `build_installer.ps1:242` "React Frontend Web Export" adımı var |
| `SAHA-TEST-LISTESI.md` ↔ `saha-test-listesi.html` | — | **AYRIŞMIŞTI** (HTML 5 kademede kalmış). Bugün kapatıldı: tek kaynak Markdown + üretici betik + kapı |

> ⚠️ Bu tabloyu ayrı bir bulgu olarak okuyun: **bir belgenin "Durum" satırı kanıt değildir.**
> Beş belgeden dördü ölçünce yanlış çıktı.

---

## 6. Bugün (2026-09-12) kapatılanlar — kayıt için

- Sahibin 14 işi + 4 ev sahibi eklentisi (bkz. `sahip-istekleri-2026-09-12.md`)
- AI analizleri **hasta kimliğine** bağlandı (ad değişince geçmiş kaybolmuyor)
- **İnternet rozeti donması** — `internet` yayının içine kondu; arayüz artık okuyor
- **Yalan yeşil "İnternet Bağlantısı"** — `networkOnline` artık yalnız interneti ölçüyor
- **Kaybolan tek ağ olayı** — 60 sn'de bir yeniden yayın sigortası
- **İş 5'in üçüncü kaçağı** — Ana Ekran hayalet bobin 8 kartını çiziyor ve `/8` yazıyordu
- Saha test listesi 60 → **164 senaryo** (Kademe 6 MOBİL + Kademe 7 regresyon + Kademe 8 bilinen açıklar)

---

## 7. Önerilen sıra (bana kalsa)

1. **B1** (STM 1-5 termal) — tek sürekli, koşulsuz hasta riski. NTC bağlanır bağlanmaz bayrağı 1 yap + tezgâhta doğrula.
2. **B3** (STM reflash + doz kalibrasyonu) — sahadaki doz bugün kalibre DEĞİL.
3. **D1** (mobil saha testi) — en az bakılan katman, en ucuz kapatma. Liste hazır.
4. **A1a** (avukata ağırlık lisansı sorusu) — cevabı gelmeden A1'e mühendislik harcamak boşa gidebilir.
5. **C3** (`esp` dalı canlı sırlar) — depo public olduğu sürece açık.
6. **C1** (resolve_device SQL) — tek adım, uzaktan erişimde bayat cihaz görünmesini keser.

---
---

# EK — 2026-09-13 TURU: yapılanlar + **iki düzeltme**

Sahip kararı: *"a1, a1a, b1, b2, b6, c3, c5, c6, d4 hariç diğerlerini önerdiğin sırayla yapalım;
jeton işini sona bırak."*

## ⚠️ ÖNCE: yukarıdaki raporumun İKİ MADDESİ YANLIŞTI

Kendi kuralımı (§5: "durum satırı kanıt değil") kendi raporuma uygulamamıştım.

| Madde | Raporda | ÖLÇÜLEN gerçek |
|---|---|---|
| **C1** — `resolve_device` SQL canlıya uygulanmadı | "AÇIK" | ❌ **YANLIŞ — ZATEN UYGULANMIŞ.** Canlı fonksiyon `interval '30 days'` taşıyor, `security definer`, EXECUTE yalnız `anon`da, `PUBLIC` ACL'de YOK. Kaynak: belgedeki "sahibin elle yapacağı adım" notu hiç güncellenmemiş |
| **B4/§2** — SQLCipher | ilk ölçümümde "KAPALI" | ❌ **ÖLÇÜMÜM YANLIŞ KOŞULDAYDI.** Backend'i launcher'ın ortam değişkenleri OLMADAN elle başlatmıştım → yanlış veri kökü. Gerçek saha kökü `C:\ProgramData\PEMF_System\PEMF_GUI` ve orada `patients.db` + `pemf_treatment_history.db` **ŞİFRELİ** |

⚠️ **DERS (ikisi de aynı sınıf):** "ölç" yetmez — **doğru koşulda** ölç. Launcher backend'i
`PEMF_DATA_DIR` / `PEMF_ENCRYPT_AT_REST=1` ile başlatır; elle başlatılan backend başka bir
dünyada koşar ve ölçüm sessizce yanlış çıkar.

## ⚠️ YENİ BULGU (P0 sınıfı) — hasta verisi anahtarının makine-dışı kopyası YOK

Hasta DB'leri şifreli (iyi). Ama anahtar **tek yerde**:

```
C:\ProgramData\PEMF_System\PEMF_GUI\pemf_secrets.json → auto.sqlcipher_key
biçim: "DPAPI:…"  →  Windows DPAPI, MAKİNEYE BAĞLI
```

- `~/pemf-sirlar.pemfsec` (2026-08-19) bu anahtarı **TAŞIMIYOR** — ölçüldü: içindeki 7 kalem
  ESP `Secrets.h`, ESP `config.json`, cloud provision ve Android keystore.
- Keyring'de de yok (`PEMF_GUI/sqlcipher_key` → boş), `.sqlcipher_key` dosyası da yok.

**Sonuç:** disk/OS/profil kaybında hasta verisi **kalıcı olarak okunamaz**. Şifreli `.db`
dosyasını yedeklemek KURTARMAZ — anahtar olmadan açılmaz.

**Hazırlandı (çalıştırılmadı — nereye konacağı sahip kararı):**
`scripts/hasta_anahtari_emanet.py` · `--parmak-izi` / `--disa-aktar <kasa-yolu>` / `--dogrula`.
Depo içine yazmayı **reddeder** (depo public, dosya düz metin).

⚠️ `pemf-sirlar.pemfsec`e EKLENMEDİ, bilerek: o arşiv **parolasız** (sahip kararı 2026-08-19).

## Yapılanlar

| # | İş | Sonuç |
|---|---|---|
| **B3** | STM reflash + doz kalibrasyonu | Firmware temiz derlendi (28 kaynak, `_printf_float` BAĞLI). `--cikti` eklendi → `pemf.bin/.hex/.elf` + SHA256. Runbook: `VERIFICATION.md §16`. ⚠️ Tezgâh ölçümü sahipte |
| **D1** | Mobil saha testi | Liste hazır (Kademe 6, 42 senaryo). Koşmak sahipte |
| **C1** | `resolve_device` SQL | ✅ zaten uygulanmış (yukarıdaki düzeltme) |
| **A2** | `.iss` sürüm etiketi | `1.9.33` → `1.9.50` (17 sürüm bayattı) + çıplak-ISCC uyarısı + kapı `tests/test_iss_surum_senkron.py` (4 test, mutasyon KIRMIZI) |
| **B4 §2** | SQLCipher | ✅ sahada AÇIK ve çalışıyor — ama yukarıdaki anahtar-emaneti bulgusu |
| **B4 §3** | Supabase RLS | ✅ **canlıda yeniden doğrulandı**: 6 tablonun altısı da anon'a `401/42501`; `resolve_device` RPC çalışıyor ve geçersiz kodda `[]` dönüyor (sızıntı yok) |
| **B4 §4** | Cloudflare NAMED tünel | ⏳ **ÖLÇÜLEMEDİ.** Elle başlattığım backend'de `tunnelUrl` boştu ama o **launcher koşulu DEĞİL** — §2 ile birebir aynı tuzak, bu kez fark ettim ve iddia etmiyorum. Doğru ölçüm: uygulamayı launcher'dan aç → `GET /api/health` → `tunnelUrl` |
| **B4 §5** | CVE | ✅ düşük-riskli üçü **YAPILMIŞ** (cryptography 50.0.0 · python-multipart 0.0.31 · zeroconf 0.149.0). Kalan `onnx 1.15` + `torch 2.1.2` — model yeniden-doğrulaması ister, risk profili DÜŞÜK |
| **B4 §6** | Model bütünlüğü | ✅ `scripts/model_butunluk.py` + `ai_models_sha256.json` (56 ağırlık). **Gömülü paket 56/56 bayt-birebir.** ⚠️ Kapının ilk hâli yanlış alarm verdi (profil katmanına bakıp "14 model eksik" dedi); çözüm dosya-başına olduğu için düzeltildi |
| **B4 §7** | Soak | ⚠️ Eski betik **MQTT** üzerinden → ESP kapalıyken **hiçbir canlı yolu zorlamıyor**. Yerine `scripts/soak_http_ws.py` (HTTP+WS; bobin SÜRMEZ) |
| **C4** | Launcher açık soruları | 2/3 **ölçülerek kapandı**: kurulum dizini `%LOCALAPPDATA%\PEMF Vet Client` (per-user) · backend **SERVİS DEĞİL, SÜREÇ**. 3.'sü (`.dmg` karantina) C5'e bağlı |
| **C7** | `cloud_mqtt_provision` bayat-dosya | Üretim başarısızsa bayat dosya artık **siliniyor** — "BULUT-AYNASIZ çıkacak" uyarısı doğru oldu |
| **C2 / C7-ESP** | ESP kalemleri | ⏸️ **UYKUDA** — ESP sökülü; kod silinmedi, ESP dönerse geri açılır |
| **D3** | Canlı Supabase | ✅ yukarıda. HiveMQ yarısı ESP'ye bağlı → uykuda |
| **§5** | Belge bayatlıkları | 4 belgeye ölçülmüş durum notu düşüldü (AI Hub planı · STM 7-bobin planı · SİSTEM_RAPORU §7 · react_installer_gap_report) |

## Hâlâ açık (hariç tutulanlar dışında)

| # | İş | Neden açık |
|---|---|---|
| B4 §1 | Firmware güvenlik satürasyonu | Tezgâh |
| B4 §4 | NAMED tünel | Cloudflare token'ı sahipte |
| B4 §5 | `onnx` + `torch` yükseltmesi | 14 modülün çıktısı yeniden doğrulanmalı + EXE rebuild |
| B4 §6b | Model **lisans** envanteri | AGPL kalemi hariç tutuldu (A1) |
| B4 §7 | Uzun soak | 25 dk koşuldu; 72 saatlik klinik koşusu sahipte |
| D2 | iOS / EAS | Apple hesabı/EAS koşusu gerekir (C5 ile aynı blok) |
| ~~D5~~ | ~~FW-6 (S3 WDT)~~ | ✅ **KAPANDI 2026-09-13** — sahada reboot döngüsü olarak ortaya çıktı; kütüphane kaynakları MAKİNEDE kurulu çıktı ve ölçüldü (TLS el sıkışma 120 sn > WDT 10 sn). Düzeltildi + 5 kapı |
| **A3** | **Jeton** | Sahibin vereceği e-posta bekleniyor |

---

## EK — 2026-09-13 18:15 · P0 VERİ KAYBI: yarım göç + ACL sertleştirmesi + yedek silme

**Nasıl bulundu:** tam süitte bir kez düşen "kararsız" bir test → kod okuması → üç kaynak
düzeltmesi → ama **ürün (frozen EXE) hâlâ kaybediyordu**. Sessiz `except Exception: pass`
kaldırılıp loglama eklenince kök neden ilk koşuda çıktı.

### Ölçülen arıza zinciri

At-rest göçü yer-değiştirme penceresinde kesilirse (elektrik, kilit) diskte `db` YOK,
veri `db.plain.bak`ta kalır. Sonraki açılışta:

1. `_harden_secret_file_acls` **önce** koşuyor ve `*.plain.bak`ı `keep_current_user=False`
   ile kilitliyordu → yükseltilmemiş backend **kendi kilitlediği** dosyayı açamıyor.
2. Yarım-göç toparlaması `[Errno 13] Permission denied` ile düşüyor.
3. Şablon kopyalanıyor → klinik **boş** geçmiş görüyor.
4. Göç, şablonu şifrelerken **`os.remove(backup)`** ile o dosyayı — kliniğin **tek
   kopyasını** — siliyor, sonra yeni yedeği "GÜVENLİ-SİLİNDİ" diye logluyordu.

> Dışarıdan hiçbir hata görünmüyordu. Veri erişilemez değil, **yok edilmiş** oluyordu.

### Düzeltmeler

| # | Dosya | Değişiklik |
|---|---|---|
| 1 | `backend_service.py` | Toparlama (`_initialize_database_safe`) artık ACL sertleştirmesinden **ÖNCE** koşuyor |
| 2 | `backend_service.py` | `.plain.bak` için `keep_current_user=True` — Users/Authenticated Users yine dışarıda, **koruma kaybolmuyor** |
| 3 | `database/sqlcipher_util.py` + `treatment_history_db.py` | `os.remove(backup)` → `_yedegi_kenara_al` (zaman damgalı; **hiçbir şey silinmiyor**) |
| 4 | `database/sqlcipher_util.py` | Toparlamaya ikinci şans: EACCES'te `_kilidi_gevset` + tekrar dene (eski sürümlerin kilitlediği yedekler sahada duruyor) |
| 5 | `utils/path_utils.py` | Sessiz `except: pass` kaldırıldı — başarı da başarısızlık da **loglanıyor** |
| 6 | `scripts/build_backend_exe.ps1` | AI kapısı yetim `mosquitto` bırakıp **sonraki build'i** düşürüyordu (DLL kilidi, üstelik `exit 0`). Üç noktadan kapatıldı |

### Doğrulama

- Kaynak kapıları: `tests/test_goc_yarim_kalirsa_db_kaybolmaz.py` → **10 test**, 3 yeni kapının
  üçü de **mutasyonla KIRMIZI** ispatlandı.
- **Ürün kapısı GEÇTİ** (`scratchpad/urun_yarim_goc.py`, EXE 18:04):
  `db` = 184320 bayt (gerçek veri), 176128'lik şablon **değil**; kayıt görünüyor; logda
  `Yarim kalmis goc toparlandi (sablon kopyalanmadan once)`.

### ⚠️ Üç saat kaybettiren yöntem hatası

"Ürün toparlamıyor" diye okuduğum ilk iki tur aslında **bayat EXE** ölçüyordu (ikili 16:43,
düzeltme 16:56/17:17). Bir sonraki build bile yetmedi: PyInstaller Analysis, düzenlemeden önce
koşmuştu. Artık ürün harness'ı, doğruladığı kaynaklardan **eski** bir ikiliyi ölçmeyi reddediyor
ve pakette gerçekten ne olduğu `scratchpad/pyz_modul_oku.py` ile PYZ'den okunuyor
(EXE üzerinde düz `grep` sahte "YOK" verir — PYZ sıkıştırılmıştır).

---

# KALAN İŞLER — toparlama (2026-09-14)

> Bu bölüm **tek kaynak**tır. Aşağıdaki satırların hepsi bu tarihte ölçüldü; "belgede öyle
> yazıyor" gerekçesiyle hiçbir şey kapalı sayılmadı.

## A · BENDE — yapılabilir, blokesiz

| # | İş | Durum / ne gerekiyor |
|---|---|---|
| **A-1** | **`onnx 1.15` + `torch 2.1.2` CVE yükseltmesi** | Tek gerçek kod işi. 16 AI modülünün çıktısı yükseltme sonrası yeniden doğrulanmalı (`urun_dogrula.py` + XAI zinciri) ve EXE yeniden derlenmeli. Risk profili DÜŞÜK (model klasörü yerel, ağdan girdi almıyor) — bu yüzden bugüne ertelendi |
| **A-2** | **Model *lisans* envanteri** | Ağırlıkların lisansları listelenmemiş. AGPL kalemi senin hariç tuttuğun A1'e bağlı; geri kalanı çıkarılabilir |

## B · SENDE — bende yapılacak bir şey yok

| # | İş | Neden sende |
|---|---|---|
| **B-1** | **S3 reflash** (Arduino IDE) | [FW-6] WDT/TLS düzeltmesi kaynakta hazır; karta yazmak fiziksel |
| **B-2** | **STM reflash + doz kalibrasyonu** | `VERIFICATION.md §16`. ⚠️ Tepe-tepe (`pp_x = XP−XN`) kullan, `measuredPeakMt` **değil** — o \|B\| tabanlı ve ölçülen 0,589 mT DC ofsetiyle sapıyor |
| **B-3** | **164 senaryoluk saha listesi** | `docs/SAHA-TEST-LISTESI.md` · 8 kademe. En az bakılan katman **Kademe 6 — MOBİL** |
| **B-4** | **Vault kurtarma setini makine dışına al** | Token + unseal anahtarları şu an aynı makinede; disk kaybında ikisi birden gider. Emanetin tek anlamı bu |
| **B-5** | **Cloudflare NAMED tünel** | Token sende. Ölçüm: uygulamayı **launcher'dan** aç → `GET /api/health` → `tunnelUrl` |
| **B-6** | **Firmware güvenlik satürasyonu** | Tezgâh ölçümü |
| **B-7** | **72 saatlik klinik soak** | 25 dk koşuldu; uzun koşu klinik ortamında |
| **B-8** | **iOS / EAS** | Apple sözleşmesi + EAS koşusu (senin hariç tuttuğun C5 ile aynı blok) |

## C · ✅ JETON — AÇILDI VE ÖLÇÜLDÜ (2026-09-14)

⚠️ **ÖNCEKİ RAPORUM YANLIŞTI.** "100 jeton verilmedi" demiştim; hakkı **depoda** aramıştım,
oysa jeton Supabase'de durur. Doğru yerden ölçünce:

| | |
|---|---|
| Hesap | `aygunmert611@gmail.com` → `890c739c-28b6-4364-80b0-65c663ba01d9` |
| Yükleme | **13 Eylül 07:06** · +100 · `tur='duzeltme'` · `A3 test yuklemesi (sahip istegi 2026-09-13)` |
| Tüketim | 4 analiz: görüntü −1 · görüntü −1 · **ağır araştırma −3** · görüntü −1 = **−6** |
| **Kalan** | **94 jeton** |

Yani hem hak verilmiş hem de düşme **zaten kanıtlanmış**. O test elle bayraklı başlatılan bir
backend'le (`:8083`) yapılmış.

### Bu turda yapılan: bayrak KALICI olarak açıldı

Kurulu launcher (1.9.51, 10 Eylül) `PEMF_JETON_ENFORCED` stringini **taşımıyordu** — ikiliye
sorularak ölçüldü. Launcher backend'in ortamını **açıkça kuruyor**, dolayısıyla makineye bayrak
yazılsa bile launcher'dan açılan backend onu görmüyordu. (Bu, "backend'de altyapı var, launcher
geçirmiyor" sınıfının **yedinci** örneği.)

| Adım | Sonuç |
|---|---|
| Launcher yeniden derlendi (`cargo build --release -p pemf-vet-client`) | ✅ 1dk28sn |
| Yeni ikilide `PEMF_JETON_ENFORCED` var mı | ✅ VAR (eski ikilide YOKTU) |
| Eski launcher yedeklendi | `PEMFVetClient.exe.yedek_1.9.51_20260910` |
| Kuruldu + `PEMF_JETON_ENFORCED=1` (User ortamı) | ✅ |
| **Ölçüm:** `/api/jeton/bakiye` bayrak **1** ile | `{"etkin":true,"bilinmiyor":true,"sebep":"kimlik_yok"}` |
| **Karşıt kontrol:** aynı uç bayrak **0** ile | `{"etkin":false}` |

`bilinmiyor:kimlik_yok` **doğru davranıştır**: curl'de oturum yok. Sözleşme gereği rozet
uydurma bir sayı yazmaz, **"—"** gösterir. Sen uygulamada oturum açınca **94** göreceksin.

### Bilmen gerekenler

- **Tedavi hiçbir koşulda kapılanmaz.** `GUVENLIK_YOLLARI` (seans başlat/durdur, **acil
  durdur**, sensör okuma, cihaz kontrolü, durum) kapının **en başında** serbest — bakiye 0 olsa
  bile çalışır. Bayrağın açılması bunu değiştirmez.
- **Bakiye biterse AI analizi durur.** 94 jeton var; maliyetler: görüntü/ses/sensör **1**,
  ağır araştırma **3**, AI Pro seans **5**. Saha listesindeki (B-3) AI senaryolarını koşarken
  tükenebilir — tükenirse bu bir hata değildir, söyle, tek komutla yükleyeyim.
- **Kapatmak istersen:** `PEMF_JETON_ENFORCED` kullanıcı ortam değişkenini sil (ya da `0` yap)
  ve launcher'ı yeniden başlat. Sürüm numarası **1.9.51 olarak kaldı**; yayın hâlâ donmuş.

## D · SENİN HARİÇ TUTTUKLARIN (kapalı sayılmıyor, sıraya alınmadı)

`A1` · `A1a` · `B1` · `B2` · `B6` · `C3` · `C5` · `C6` · `D4`

## E · ⛔ YAYIN

**DONMUŞ.** Sahada tek makine var; sen "yayınla" demeden manifest/release koşturulmuyor.
Kurulu sürüm numarası **1.9.50 olarak kalıyor** (`versions.json`a dokunulmadı — dokunulsaydı
launcher yayındaki sürümü indirip yerel derlemeyi ezerdi). Bu yüzden "güncel mi?" sorusu
sürümden değil **davranıştan** yanıtlanır.

## F · BU MAKİNENİN ŞU ANKİ DURUMU (ölçüldü)

| Ne | Durum |
|---|---|
| Kurulu backend EXE | 2026-09-13 18:04 — **P0 veri kaybı düzeltmesini taşıyor** |
| Ürün kapısı (yarım göç) | ✅ kurulu ikilide GEÇTİ |
| Geniş ürün doğrulaması | ✅ GEÇTİ (7 panel, gzip, mozaik) |
| Tam süit | ✅ 2979 geçti / 6 atlandı |
| Ön yüz paketi | ✅ jeton rozeti · bobin sayısı · internet rozeti **pakette doğrulandı** |
| Base katmanı (7 dosya) | ✅ geri kondu (hotspot / servis / teardown / uninstall betikleri) |
| Sahada veri kaybı | ✅ yok — üç veri kökünde de `.plain.bak` kalıntısı YOK |
