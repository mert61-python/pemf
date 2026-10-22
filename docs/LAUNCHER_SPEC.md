# PEMF Vet Client — Launcher Sözleşmesi (yeniden yazım)

**Durum:** karar verildi · **İlk karar:** 2026-07-21

> ⚠️ Başlık uzun süre "taslak / 2026-07-21" kaldı ama gövde güncellendi: "Açık sorular"
> bölümünde **2026-09-13 ölçümleri** var. Elle yazılan durum etiketleri gövdeyle birlikte
> güncellenmez — tarih için git geçmişine bakın. Kapı: `tests/test_belge_etiketleri_bayatlamaz.py`
**Kapsam:** Windows + macOS + Linux, **tek kaynak** · **Geriye dönük uyumlu**

## Neden yeniden yazıldı (tarihçe — v1.8.0)

> ✅ **UYGULANDI — yeniden yazım BİTTİ ve sahada.** `launcher/` bir Tauri/Rust workspace:
> `launcher/Cargo.toml` → `members = ["core", "app"]`, sürüm `[workspace.package] version`;
> `launcher/core/src/` (auth.rs · backend.rs · install.rs · manifest.rs · verify.rs · …);
> `launcher/app/tauri.conf.json`; tek kaynak `versions.json` `"launcher"` → `build_tools/sync_versions.ps1` (belgeye sürüm
> numarası YAZILMAZ — bayatlar; eşlik kapısı `manifest.rs::KRITIK_L12_surum_TEK_KAYNAKLA_tutarli`). CI
> `.github/workflows/launcher.yml` `.exe` / `.dmg` / `.deb` / `.AppImage` / `.rpm` üretiyor.
> Aşağısı kararın GEREKÇESİDİR — yapılacak iş değil.

Eski launcher (`PEMFVetClient-Setup.exe`, `.deb`, `.AppImage`, `.rpm` —
`pemf-update/releases/tag/launcher-v1.8.0`) **kaynağı elimizde olmayan** bir bileşendi.
`mert61-python/pemf` deposunun hiçbir commit'inde, hiçbir branch'inde izi yoktu
(`git log --all --diff-filter=AD` → sıfır sonuç; `Cargo.toml` / `.rs` / `tauri.conf.json` /
`.nsi` / Electron bağımlılığı yok). Kaynağı olmayan bir bileşen düzeltilemez, imzalanamaz,
yeni platforma taşınamaz — macOS'in tıkanma sebebi tam olarak buydu.

## Teknoloji

**Tauri (Rust)** — ✅ seçildi ve uygulandı. Gerekçe: eski launcher ~2.9 MB (NSIS) ve release
notunda "zip crate" geçiyordu → zaten Rust. Tauri bundler tek koddan `.exe` / `.dmg` /
`.deb` / `.AppImage` / `.rpm` üretir — bugün yayında olan varlık kümesinin **tamamı**.

## Akış

```
manifest.json indir  →  profil seç (home/vet/research)  →  platforma uygun base + profil zip indir
   →  SHA256 doğrula  →  aç  →  backend'i başlat  →  /api/health bekle  →  tarayıcıyı aç
```

## Model yerleşimi — EN KRİTİK SÖZLEŞME

`apps/backend/utils/model_downloader.py::_candidate_model_roots()` model arama köklerini şu öncelikle çözer:

| # | Kök | Platform |
|---|---|---|
| 1 | `$PEMF_AI_MODELS_DIR` | hepsi |
| 2 | `%PROGRAMDATA%\PEMF_GUI\ai_models` | **yalnız Windows** (`PROGRAMDATA` yoksa atlanır) |
| 3 | `get_app_data_directory()/.ai_models` | hepsi |
| 4 | proje-yanı `release_assets/ai_models` | geliştirme |
| 5 | PyInstaller bundle içi `ai_models` | gömülü build |

`find_installed_model("ai_hub/em_kedi/X.onnx")` bu köklerin altında `<kök>/ai_hub/em_kedi/X.onnx`
arar. Profil zip'lerinin içeriği tam olarak `ai_models/ai_hub/<model>/<dosya>` biçiminde
(doğrulandı: `vet.zip` → `ai_models/ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx`).

> **Karar:** Launcher, backend'i başlatırken **`PEMF_AI_MODELS_DIR=<kurulum>/ai_models`**
> ortam değişkenini verir. Kök #1 en yüksek öncelikli ve **üç platformda da aynı** çalışır;
> kök #2 macOS/Linux'ta hiç yok. Böylece Windows'un mevcut ProgramData düzenine
> dokunmadan mac/Linux çalışır.

**Yükseltme kuralı:** Windows'ta `%PROGRAMDATA%\PEMF_GUI\ai_models` doluysa launcher onu
kullanır, profil paketini **yeniden indirmez** (2 GB'a kadar gereksiz indirme olurdu).

## Base paketi — modeller GÖMÜLMEZ

> ✅ **DURUM (ölçüldü, `pemf-app-packages/manifest.json`): tek-parça `base.zip` ARTIK YOK.**
> Paket **katmanlı** (monolit 1.9.48'de kaldırıldı). Canlı manifest `"runtimes": {}` ve
> `layers["win-x64"]` altında **`base-app.zip` 81.363.203 B (~81 MB)** +
> **`base-deps.zip` 1.487.710.488 B (~1,49 GB)** + `"rollout": 100` taşıyor.
> Aşağıdaki "1.29 GB / 6191 dosya" ölçümü TARİHSELDİR.

Yayındaki base katmanları **sıfır** `ai_models` girdisi içerir (doğrulandı; tarihsel ölçüm:
tek-parça `base.zip` 1.29 GB / 6191 dosya). Modeller yalnızca profil paketlerinden gelir.
`PEMF_Backend_onedir.spec` içindeki `PEMF_EMBED_MODELS` bayrağı bu hizayı korur (`0` = gömme).

Gömülseydi: kullanıcı aynı 2.1 GB'ı iki kez indirirdi ve profil ayrımı anlamsızlaşırdı
(vet kullanıcısında research modelleri de bulunurdu).

## manifest sözleşmesi

**v1 formatı** ad-hoc platform anahtarları kullanıyordu: `base`, `base_linux`.
⚠️ **Bugünkü format bu DEĞİL** — canlı manifest v2'dir (aşağıdaki "canlı şema"ya bakın).
O tasarımın bir kez ısırdığı kayda geçmişti (kaynak betik `pemf-app-packages/publish.ps1`
**artık YOK**; depodaki tek yayın betiği `scripts/publish_release.ps1`, manifest üretimi
`scripts/make_manifest.py` — aynı sınıf uyarı bugün o betiğin "Eksikleri mevcut manifest'ten
TAŞI" bloğunda duruyor):

> *"base-linux.zip … Eksikse Linux client sessizce Windows base.zip indirir → backend hiç çalışmaz."*

> ### ✅ DURUM 2026-09-17: bu uyarı TARİHSELDİR — v2 hedefi GERÇEKLEŞTİ
>
> Yukarıdaki alıntı **v1 formatının** tuzağını anlatır. Aşağıdaki v2 hedefi
> (*eksik anahtarda sessiz fallback YOK*) **2026-08-09'da uygulandı** ve kapıyla kilitli:
>
> ```rust
> // launcher/core/src/manifest.rs — SAHİP KARARI 2026-08-09 (Tier 1)
> assert!(!m.runtimes.contains_key(platform::LINUX_X64),
>     "linux-x64 manifest'e geri girdi — o platformda rollout freni ve self-update YOK");
> ```
>
> `mac-arm64` ve `linux-x64` manifest'ten **bilerek çıkarıldı**: o platformlarda `layers`
> yoktu → rollout freni çalışmıyordu ve self-update Windows'a özeldi, yani kurulan cihaz
> eski sürümde **kalıcı kilitleniyordu**. Client artık *"bu platform için paket yok"* deyip
> **durur**. Ölçüldü (2026-09-17): yayındaki manifest `runtimes: []`, `layers` yalnız
> `win-x64`; `pemf-update` deposunun altı release'inin hiçbirinde Linux varlığı yok.
>
> ⚠️ **`base-linux.zip`in yokluğu ARIZA DEĞİL, KARARDIR.** `DEPO-DENETIMI-2026-09-15.md`
> onu "KAYIP" diye işaretlemişti — **o bulgu yanlıştı** (bu satırı güncel sanmaktan doğdu).
>
> **Geri almak için:** paketleri CI ile üret (`linux-backend.yml`), `layers` + `rollout`
> ekle, `manifest.rs`teki iddiaları geri getir. ⚠️ `linux-backend.yml` bugün
> `permissions: contents: read` ve yalnız `upload-artifact` kullanıyor — **release'e
> yazamaz**; o adım ayrıca açılmalı.

**v2 — CANLI ŞEMA** (hedef DEĞİL; `pemf-app-packages/manifest.json`'dan alındı): açık
platform anahtarları, **eksik anahtarda sessiz fallback YOK, sert hata**. Tek-parça
`runtimes` yerine **`layers`** (app + deps) ve **`rollout`** freni var:

```json
{
  "schema": 2,
  "version": "1.9.50",
  "tag": "client-app-v1.9.50",
  "runtimes": {},
  "layers": {
    "win-x64": {
      "app":  { "url": "…/base-app.zip",  "sha256": "…", "size": 81363203,   "kind": "zip" },
      "deps": { "url": "…/base-deps.zip", "sha256": "…", "size": 1487710488, "kind": "zip" },
      "rollout": 100
    }
  },
  "models":   { "home": {…}, "vet": {…}, "research": {…} },
  "profiles": { "home": {…}, "vet": {…}, "research": {…} }
}
```

⚠️ `linux-x64` ve `mac-arm64` **bilerek yok** (yukarıdaki ✅ DURUM bloğu). `models` ve
`profiles` bölümleri canlı manifest'te AYNI varlıkları taşır.

Launcher **iki formatı da okur** (v1 → sahadaki v1.8.0 kurulumları bozulmasın).

## Backend başlatma

| Değişken | Değer |
|---|---|
| `PEMF_AI_MODELS_DIR` | `<kurulum>/ai_models` |
| `PEMF_DATA_DIR` | platform app-data (aşağıda) |
| `PEMF_API_PORT` | `8000` (varsayılan; meşgulse artır) |

Hazırlık kontrolü: `GET /api/health` (`apps/backend/servers/system_router.py`). 200 dönene kadar bekle,
sonra tarayıcıyı aç. Zaman aşımında backend log'unu göster — sessizce başarısız olma.

`get_app_data_directory()` (`apps/backend/utils/path_utils.py`) zaten üç platformu doğru çözüyor:
Windows `%APPDATA%\PEMF_GUI` (launcher `PEMF_DATA_DIR` verirse `<PEMF_DATA_DIR>\PEMF_GUI` — makine-geneli
`%PROGRAMDATA%\PEMF_System\PEMF_GUI`, yazılabilirse; seçilen kök `<kurulum>\veri_koku.txt`'e yazılır, kaldırma diyaloğu ve
NSIS KVKK iletisi onu gösterir — LN L7), macOS `~/Library/Application Support/PEMF_GUI`,
Linux `~/.local/share/PEMF_GUI`. **Launcher bunu taklit etmeli, yeniden icat etmemeli.**

**Makine-geneli veri kökünün ACL'i (Y96 · LN L8):** kök İLK kez yaratılırken yalnız paylaşılan YEREL grup (`PEMF_DATA_GROUP_SID`,
biçim `S-1-5-21-…` + bu makinenin yerel grubu — backend `file_acl` ile aynı kural) `Değiştir` alır ve SID backend'e de geçer; yerel
`Users` VERİLMEZ. Grup tanımlı değilse ek hak verilmez (tek hesap: yaratan hesap sahip). ⚠️ YLI-A3.1 (ölçüldü): bu, ikinci Windows
hesabını kendi kullanıcı köküne DÜŞÜRMEZ — `C:\ProgramData` mirası (`Users: Write (CI)`) köke yazdırır, yoklama geçer; ama backend
`<kök>\PEMF_GUI`'yi ilk hesaba kilitlediği için ikinci hesap hasta verisine erişemez (DB açılmaz — görünür arıza). Çok hesaplı klinik
kurulumda paylaşılan grup ZORUNLU (Y96); grupsuz ikinci hesabın ne yapacağı sahip kararıdır (S-YLI.1).

**Otomatik güncelleme kapısı (`aktif_seans_kapisi`):** sessiz self-update / runtime güncellemesi backend'i öldürür; önce
`/api/health` → `sessionActive` (10 sn bütçe) ve `firmwareGuncelleme.yakiliyor` sorulur — `true` ya da bilinmiyor → ERTELE.
LN L6 · İG-8.21: `backend.port`'taki dinleyici TCP kabul ediyor ama 2 sn'lik kimlik yoklamasına yanıt vermiyorsa (yük altında —
ÖLÇÜLDÜ: süreç içi Python yükünde sağlık 2 sn'yi aşıyor) backend "yok" SAYILMAZ (`backend::guncelleme_kapisi_backendi`); yalnız
port KESİN ölüyse (bağlantı reddi) ve varsayılan portta kimliği doğrulanan backend yoksa kapı serbesttir. Varsayılan port katı kalır
(yanıtsız yabancı bir servis güncellemeyi kilitlemesin).

## Firmware ↔ client uyumsuzluğunda client geri alma (Y16) — backend'in bildirdiği durum

Sahip kararı **Y16**: "client güncellenip STM güncellenmezse client geri döner" kuralını **launcher** (sağlık kapılı
geri alma, `runtime.old`) uygular. Backend client'ı geri **almaz**; eski Inno/`exe` kanalı (`update_manager.rollback()`)
bu iş için **açılmaz** (split-brain hasta DB'si riski — `update_manager.py` başlığı). D1.119 (1-H) ile backend'in ölü
`CLIENT_GERI_AL` dalı kaldırıldı.

Sözleşme (yalnız yerel/LAN istek — tünele `null`): `GET /api/health` → `firmwareGuncelleme`
(`servers/firmware_manager.durum()`):

| Alan | Anlam |
|---|---|
| `eylem` | `yok` · `bekle` · `firmware_guncelle` (açılış denetiminin kararı) |
| `gerekce` | insan-okur neden (destek için) |
| `uyum` | `true` uyumlu · `false` KESİN uyumsuz · `null` karar verilemedi (kural yok / sürüm okunamadı / manifest yok) |
| `istemciGeriAlinmali` | `true` ⇔ `uyum=false` **ve** STM bağlı **ve** ileriye (firmware güncellemesiyle) gidilemiyor — plan `bekle`, ya da plan `firmware_guncelle` ama otomatik yakma KAPALI (**Y81**, `PEMF_FW_AUTO_UPDATE` ≠ `1`) ya da bu SHA bir kez denenmiş (**Y80**) |
| `uygulandi` / `hata` | son yakma denemesi (`hata` = `"[kod] …"`, kodlar `utils/stm_yakma.py`); **Y80**: aynı SHA'lı ikili bir kez denenip kart hedef sürümü bildirmediyse `hata` "sürüm tutmadı — elle bakın: …" der ve o ikili bir daha OTOMATİK yakılmaz (kayıt `<veri kökü>\firmware_yedek\son_yakma.json`) |
| `yakiliyor` | **Y82** (yalnız-ek): `true` ⇔ oto-firmware yakma penceresi AÇIK (MCU şu an yeniden programlanıyor). Okuma anında türetilir. Launcher kapanışta bunu görürse uyarır ve yakmanın bitmesini bekler; yakıcıyı (`STM32_Programmer_CLI`) öldürmez |
| `yarimYakma` | **Y82** (yalnız-ek): `null` ya da önceki süreçte YARIDA KALAN yakmanın açılıştaki akıbeti `{sonuc, ayrinti}` — `tamamlanmis` (kart hedefi bildiriyor) · `geri_donuldu` (yedekten eski firmware geri yazıldı ve doğrulandı) · `elle` (otomatik yakma kapalı / STM bağlı değil — karta dokunulmadı; ayrıntı yedeğin yolunu söyler) · `basarisiz`. Kayıt `firmware_yedek\yarim_yakma.json`: yakmadan ÖNCE yazılır, doğrulamadan SONRA silinir |

İlk otomatik yakmanın yedeği (asıl saha firmware'i, adı `firmware_yedek\ilk_yedek.txt`'te) tutma sınırıyla (`FIRMWARE_YEDEK_TUT`)
budanmaz (**Y80**).

Launcher `istemciGeriAlinmali=true` görürse — ve yalnız o zaman — önceki çalışan sürüme sağlık kapılı geri döner.
`uyum=null` geri alma sebebi DEĞİLDİR (üç durumlu karar; bilinmeyene dayanarak hiçbir şey yapılmaz).

**Uygulandı (LN L2, Rust):** runtime güncellemesinin sağlık kapısında (`apply_runtime_update`, yeni sürüm açıldıktan SONRA,
`dbReady` denetiminden sonra, onaydan — `runtime.old` / `_app_yedek` silinmeden — ÖNCE) `backend::firmware_kararini_bekle`:
backend açılış kararını STM el sıkışmasından sonra verdiği için (`kontrol_edildi=false` iken) en çok 45 sn (`FIRMWARE_KARAR_BUTCESI`)
1 sn aralıkla yoklanır. Yalnız JSON `true` → E-stop'lu söküm → deneme sayacı (aynı hedef 2 kez geri alınınca otomatik kurulum durur) →
eski sürüme dönüş; yanıt `{"status":"rolled_back","kod":"firmware_uyumsuz"}`, arayüz "kart yazılımıyla uyumlu değil — teknik destek"
notunu gösterir. Geri alma YOK: alan yok (eski backend) · `null` (tünel) · dizge / sayı değer · bozuk gövde · bütçe içinde karar gelmedi.
⚠️ Sınır: onaylanmış (önceki açılışta kurulmuş) bir sürümde `runtime.old` yoktur — sonradan gelen `istemciGeriAlinmali=true` geri
alamaz; oturum yine `stmUyumlu` kapısıyla korunur (kanal / paket uyumsuzsa seans reddedilir).

**Uygulandı (LN L3, Rust · Y82):** `yakiliyor=true` iken (yalnız JSON `true`; alan yok = eski backend = yakmıyor) launcher backend'i
öldürmez: teardown (tracked + orphan) ve pencere kapanışı sırası **STOP → yakmanın bitmesini bekle → son oturum yakalama → kill**
(`yakmanin_bitmesini_bekle`, en çok 600 sn `YAKMA_BEKLEME_AZAMI`, 1 sn aralık; backend yanıtsızsa beklenmez). STOP beklemeye BAĞLI
değil (her yolda önce gider). Ana pencere kapanırken yakma sürüyorsa kapanış ertelenir, pencerede "Kart yazılımı (STM32) şu anda
güncelleniyor … bilgisayarı kapatmayın" notu çıkar (TR + EN, `ui.kapanisYakmaBekleniyor`) ve yakma bitince pencere kendiliğinden kapanır.
Otomatik güncelleme (self-update / runtime) yakma sürerken ertelenir (`rust.hata.guncellemeYakmaSuruyor`). Süreç öldürme listesi
`backend::ARTAKALAN_SURECLER`: `PEMF_Backend.exe` AĞAÇSIZ (`/T` yok — çocuk süreç `STM32_Programmer_CLI` ölmez), `mosquitto.exe`
yalnız kendi kökümüzden (aşağıda), `cloudflared.exe` adıyla; NSIS PREUNINSTALL kancası aynı. Azami süre dolarsa backend yine öldürülür
ama yakıcı yaşar.

## Kapanışta / kaldırmada artakalan süreçler — yalnız KENDİ mosquitto'muz (Y71 · LN L5)

Backend öldürüldükten sonra (sıra: STOP → yakma beklemesi → backend → yardımcılar; backend ÖNCE ölür, yoksa broker gözetmeni
mosquitto'yu yeniden başlatır) yardımcı süreçler kapatılır. Sebep: backend'in başlattığı `mosquitto.exe` yetim kalırsa
`runtime\…\mosquitto.exe`'yi kilitler (yeniden kurulumda "os error 32") ve 1883'ü tutar.

- **Yalnız kendi broker'ımız:** `mosquitto.exe` ADLA öldürülmez; yalnız ikilisinin yolu kurulum kökünün (`%LOCALAPPDATA%\PEMF Vet Client`
  = NSIS `$INSTDIR`) ALTINDAYSA (`backend::YALNIZ_KOKTEN_OLDURULEN`, `kok_altinda_mi`: büyük / küçük harf duyarsız, `\\?\` öneki yok
  sayılır, kardeş dizin `…\PEMF Vet Client2` sayılmaz, yolu okunamayan süreç sayılmaz). Sahadaki ESKİ kurulumun `mosquitto` Windows
  SERVİSİ (`C:\Program Files\mosquitto`, Y36) ve başka uygulamaların broker'ları DOKUNULMADAN kalır. Dosya kilidi derdi de yalnız
  kendi ikilimizden doğduğu için temizlik eksilmez. Backend'in kendi kuralıyla aynı (`headless_services._kimlik_parcasini_onar`, Y71).
- **Launcher yolu** (`kill_stray_backends(kok)`): Toolhelp32 süreç listesi + `QueryFullProcessImageNameW` → seçilen PID'ler
  `taskkill /F /PID … /T`.
- **Kaldırma yolu (Ayarlar ▸ Uygulamalar — launcher çalışmaz):** NSIS PREUNINSTALL kökü ve adı ortam değişkeniyle
  (`PEMF_KALDIRMA_KOKU` / `PEMF_KALDIRMA_AD`) PowerShell'e verir; `Win32_Process.ExecutablePath` kökle başlayan o adlı süreç durdurulur.
  ⚠️ Kaldırıcı 32-bit'tir → çocuk PowerShell de 32-bit: `Get-Process .Path` 64-bit sürecin yolunu okuyamaz (ÖLÇÜLDÜ: NULL), bu yüzden WMI.
- `PEMF_Backend.exe` ve `cloudflared.exe` bugünkü gibi adla (backend AĞAÇSIZ — L3). Unix kolu (`pkill -x`) kökü henüz süzmez
  (mac / Linux backend'i sistem mosquitto'sunu kullanabilir) — Linux dalı SONRAKİ.

## Güvenlik gereksinimleri

**Uygulama penceresinde indirme (D2.E01 WebView2 kolu · İG-6.20 · LN L9):** `on_download` işleyicisi kayıtlı (`indirme_karari`): uygulamanın kendi kökeni (`http://127.0.0.1:<port>` / `localhost`), o kökenin `blob:` adresi ve `data:` → İZİN (WebView2'nin önerdiği hedef — İndirilenler); başka http(s) adresi pencerede indirilmez, varsayılan tarayıcıda açılır; başka köken `blob:`'u ve diğer şemalar RED. Bitiş yalnız başarıyı günlüğe yazar (dosya adı yazılmaz). Gerçek WebView2'de indirme yeri / görünürlüğü TEZGÂH-2'de ölçülür.

1. **SHA256 zorunlu.** Doğrulama başarısızsa kur**ma** ve dosyayı sil.
2. **HTTPS + host pinleme.** `apps/backend/servers/update_manager.py::_ALLOWED_UPDATE_HOSTS` aynı
   listeyi kullanıyor; launcher da aynısını uygulamalı (manifest ele geçse bile keyfi
   sunucudan çalıştırılabilir kod indirilmesin).
3. **Zip-slip koruması.** Açarken her girdinin hedef yolu kurulum kökünün altında kalmalı
   (`..` ile dışarı çıkan girdi reddedilir).
4. **İmzalama.** macOS: Developer ID + notarization. Windows: Authenticode.
   Sertifikalar **yalnız CI Secrets'ta** — working tree'de değil (bkz. `.gitignore`).

## Paketleme hedefleri

| Platform | Çıktı | Runner |
|---|---|---|
| Windows | `PEMFVetClient-Setup.exe` | `windows-latest` |
| macOS | `PEMFVetClient.dmg` (arm64) | `macos-14` |
| Linux | `.deb` · `.AppImage` · `.rpm` | `ubuntu-22.04` |

## Açık sorular

- [x] **Sahadaki Windows kurulum dizini** — ÖLÇÜLDÜ (2026-09-13, kurulu makinede):
      `%LOCALAPPDATA%\PEMF Vet Client` (yani `C:\Users\<kullanıcı>\AppData\Local\PEMF Vet Client`).
      **Per-user; yönetici hakkı gerekmiyor.** Ağaç:
      `PEMFVetClient.exe` · `runtime\` (backend) · `ai_models\` (profil katmanı) ·
      `cache\` · `installed_packages.json` · `installed_profiles.json` · `install_id.txt` ·
      `auth_session.bin`.
      ⚠️ **Yükseltmede DOKUNULMAYACAKLAR:** `installed_packages.json` (dokunulursa paketler
      yeniden indirilir — bellek `pemf-yerel-test-kurulumu-yayinsiz`), `install_id.txt`,
      `auth_session.bin` (oturum düşer).
      ⚠️ **Hasta verisi burada DEĞİL:** launcher'ın backend'e verdiği kökte — `%PROGRAMDATA%\PEMF_System\PEMF_GUI` (yazılabilirse)
      ya da `%APPDATA%\PEMF_GUI` (`veri_koku.txt`, LN L7) (`patients.db`,
      `pemf_treatment_history.db`). Kaldırma tıbbi veriye dokunmaz — bu bilinçli karardır.
- [x] **Servis mi, süreç mi?** — ÖLÇÜLDÜ (2026-09-13): **SÜREÇ.** Kurulu makinede
      `Get-Service *PEMF*` ve `Win32_Service` sorgusu **hiçbir kayıt döndürmedi**; mosquitto da
      servis değil, backend'in kendi başlattığı bir alt süreç (`_internal\bin\mosquitto\`).
      Yani launcher `PEMF_Backend.exe`yi doğrudan spawn ediyor.
      ⚠️ **SONUÇ (ayrı kayıt):** `deploy/device.env` sıkılaştırmaları YALNIZ NSSM servis
      kaydında uygulanır; süreç yolunda backend `.env` dosyalarını **kendi okumaz**. Bu yüzden
      ortam değişkenleri (ör. `PEMF_ENCRYPT_AT_REST`, `PEMF_REQUIRE_AUTH`) launcher tarafından
      **açıkça** verilmek zorundadır — bkz. `launcher/core/src/install.rs::ENV_*`.
- [ ] `.dmg` içinde backend'in ilk açılışta karantina (`com.apple.quarantine`) sorunu —
      notarization kapsamı base paketini de kapsamalı mı?
      ⚠️ Bu soru **notarization'a bağlı** ve o da Apple geliştirici sözleşmesiyle bloke
      (`docs/acik-isler-2026-09-12.md` C5). Sözleşme çözülmeden ölçülemez.
