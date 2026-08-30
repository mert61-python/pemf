# Güncelleme Altyapısı Denetimi — 2026-08-23

> **Kapsam:** "güncelleme altyapısını detaylı incele, eksik veya bug hatasını bul; client ve mobil
> taraf için ayrı ayrı" (sahip talebi). Salt-okunur denetim: hiçbir dosya değiştirilmedi, hiçbir
> build/test koşturulmadı, port 8000'e ve hasta verisine dokunulmadı.

## Yöntem ve güvenilirlik

8 bağımsız mercek (mobil servis · mobil arayüz · mobil native indirme/kurulum · launcher
self-update · istemci paket güncellemesi · yayın zinciri/manifest · güvenlik · hata modları),
**87 dosya** okundu, **44 ajan**, 1161 araç çağrısı.

Ham 53 bulgu tekilleştirildi ve **çekişmeli hakem**den geçirildi: her hakem bulguyu *çürütmekle*
görevlendirildi, kanıtlayamadığında bulgu elenir (kötümser varsayılan). P0/P1 bulgular iki bağımsız
hakeme gitti.

| Durum | Adet | Anlamı |
|---|---|---|
| **DOĞRULANDI** | 8 | Tüm hakemler kodu açıp iddiayı doğruladı |
| **ŞÜPHELİ** | 5 | Hakemler bölündü — mekanizma doğru, etki tartışmalı |
| **ÇÜRÜTÜLDÜ** | 5 | Başka bir katman zaten engelliyor / alıntı hatalı |
| Hakem bütçesi dışında | 24 | P0–P2, kod alıntılı ama **doğrulanmadı** |
| P3 (hakemsiz) | 11 | Küçük |

⚠️ **"Hakem bütçesi dışında" = doğrulanmadı.** Bu bölümdeki bulgular kod alıntısı taşıyor ama
çürütme denemesinden geçmedi; işleme almadan önce tek tek doğrulanmalı. Çürütülen 5 bulgunun
ikisi tam da bu sınıftandı (mekanizma doğru, etki gerçek değil) — oran düşük değil.

---

## 🔴 P0 — TIBBİ GÜVENLİK: Inno kurulumu bobinleri enerjili bırakıyor

**Dosya:** `build_tools/PEMF_Backend_Setup.iss:269` · **iki hakem de P0 dedi** · *bu rapor
yazarken elle de doğrulandı.*

Kurulum, çalışan backend'i öldürmeden önce bobinleri durdurmuyor.

```pascal
Exec('sc.exe', 'query PemfBackend', ...);
if ResultCode <> 1060 then          // servis KURULU ise
begin
  Exec('sc.exe', 'stop PemfBackend', ...);   // ← bobin STOP'a giden TEK yol
  ...                                        // 34×500 ms bekleme
end;                                         // ← blok BURADA kapanıyor
Exec('taskkill.exe', '/F /IM PEMF_Backend.exe', ...);   // ← KOŞULSUZ
```

**Launcher kurulumu olan makinede `PemfBackend` servisi yoktur** → `sc query` 1060 döner →
graceful blok **tamamen atlanır** → geriye yalnız sinyalsiz `taskkill /F` kalır.
`TerminateProcess` sinyal göndermez, dolayısıyla `backend_service.py`'nin `_safe_stop_outputs`
yolu koşmaz: **STM kuyruk-flush'ı ve ESP bobinlerine MQTT STOP yayını yapılmaz.**

Bobin 1–5 firmware'in ölü-adam devresiyle ~1500 ms'de düşer. **Bobin 6–8'in link-watchdog'u
yoktur** (`scripts/pemf_teardown.ps1:72-73` bunu zaten belgeliyor) → seans süresi boyunca
(20–120 dk) hastanın üzerinde enerjili kalır.

**Bu deponun kendi standardının ihlali.** Kardeş NSIS yolu doğru yapıyor —
`launcher/app/windows/hooks.nsi:72`:

```nsis
nsExec::Exec 'powershell ... Invoke-RestMethod -Uri http://127.0.0.1:$2/api/hardware/emergency_stop -Method POST ...'
Sleep 1800
... taskkill /F /IM PEMF_Backend.exe /T
```

`.iss` dosyasında `emergency_stop` **sıfır kez** geçiyor (elle doğrulandı).

**İkinci alt-durum (servis kurulu olsa bile):** bekleme döngüsü
`tasklist /FI "IMAGENAME eq PEMF_Backend.exe"` ile **imaj adına** bakıyor; servis sürecini
launcher'ınkinden ayırt edemez. Yabancı bir `PEMF_Backend.exe` varken döngü asla `Break` etmez,
34×500 ms boşa yanar ve yine 269. satır çalışır.

**Neden mevcut test yakalamıyor:** `tests/test_inno_kurulum_bobin_guvenligi.py:71-79` yalnız
*sırayı* (`graceful < kill`) ve aradaki `Sleep`'i denetliyor. Servis-yok yolunda graceful'ün **hiç
koşmadığını** görmüyor — bu regresyon testten geçer.

**Öneri:** `hooks.nsi:21-76`'daki E-stop bloğunun aynısını `CurStepChanged(ssInstall)` başına
taşı: `backend.port` oku → portu doğrula → `POST /api/hardware/emergency_stop` → ~1800 ms bekle →
**ancak sonra** `taskkill /F`. Aynı sıra kaldırma yolunda da uygulanmalı. Testi
"servis YOKKEN de E-stop atılıyor mu" ölçecek biçimde genişlet.

---

# CLIENT (launcher) TARAFI

## Doğrulanan

### C1. Profil paketi güncelleme kararını kalıcı olarak dondurabiliyor
`launcher/core/src/extract.rs:44` — *iki ayrı mercek aynı bulguyu getirdi, hakemler doğruladı
(önem P1↔P3 arası tartışmalı)*

```rust
const PROFILE_FORBIDDEN_TOP: [&str; 7] = [
    "runtime", "cache", "installed_profiles.json", "pending_install.json",
    "backend.port", "selfupdate_attempt.json", "auth_session.bin",
];
```

Listede **`installed_packages.json` yok** — oysa güncelleme kararının tamamı o dosyadan geliyor
(`flow.rs:852` → `read_installed_packages`, `flow.rs:875-882` sha karşılaştırması). Profil zip'leri
kurulum **köküne** açılıyor (`flow.rs:493`).

Kök seviyeye manifest sha'larını içeren bir `installed_packages.json` koyan profil zip'i, cihazı
sonsuza dek "güncel" gösterir. **`min_supported_version` geri çağırması da etkisiz kalır** —
`zorunlu` bayrağı yalnız rollout erken-dönüşünü ezer, sha kıyaslarını değil. Yani bobin-güvenliği
düzeltmesi taşıyan zorunlu bir yayın o cihaza hiç ulaşmaz.

`install_id.txt` (rollout dilimi) ve `backup_dir.txt` (yedek hedefi) de listede yok.
`selfupdate_attempt.json` listeye **tam bu gerekçeyle** eklenmiş — sınıf biliniyor, liste eskimiş.

**Öneri:** üç dosyayı ekle. Kalıcı çözüm: yasak-liste yerine **izin-listesi** (profil paketleri
`ai_models/` önekiyle sınırlansın) — yeni durum dosyası eklenince unutmak yapısal olarak imkânsız
hâle gelir.

### C2. Geri alınan güncelleme her açılışta yeniden deneniyor (döngü)
`launcher/app/src/main.rs:833` — *iki hakem de doğruladı (P2)*

Sağlık kapısı düşünce güncelleme geri alınıyor ama **deneme sayacı yok**; kod yorumu bunu açıkça
kabul ediyor: *"kayıtlar yazılmadığı için disk 'bilinmiyor'da kalır; sonraki açılış yeniden dener"*.

Yapısal doğrulamayı geçen ama backend'i başlatamayan bir yayında: **her açılışta** backend
öldürülür, ~1,19 GB deps yeniden açılır, `start_and_wait` 180 sn boşuna beklenir, geri alınır.
Klinik her açılışta dakikalarca bloklanır; çıkış yolu yalnız yayıncının manifest'e `rollout: 0`
yazmasıdır.

Launcher self-update'inde bu koruma **var** (`MAX_SELFUPDATE_ATTEMPTS = 2`,
`selfupdate_attempt.json`) — runtime yolunda karşılığı yok.

### C3. Çevrimdışı açılan makine bir daha güncelleme kontrolü yapmıyor
`launcher/app/ui/index.html:1988` — *iki hakem de P1 dedi*

`bootNetwork`'ün çevrimdışı dalı `return` ediyor; `startUpdateWatch()` ise o `return`'ün
**altında** (satır 2021) ve depoda başka hiçbir yerden çağrılmıyor.

Klinik PC'si açılış anında internetsizse (router dalgalanması yeterli) `guncellemeTimer` hiç
kurulmaz. **Ağ geri gelse bile** makine açık kaldığı sürece manifest bir daha çekilmez: ne
ön-indirme, ne bildirim, ne de `min_supported_version` geri çağırması o cihaza ulaşır.

Bu, 2026-08-16'da kapatılan "hep-açık makine güncelleme almıyor" sınıfının **açık kalan yarısı**.

**Öneri:** `startUpdateWatch()`'i çevrimdışı dalında da (return'den önce) çağır; `recheckUpdates`
zaten hatayı sessizce yutuyor, ağ gelince kendini toparlar.

## Şüpheli (hakemler bölündü — karar sahibin)

### C4. `auto=false` olunca self-update tamamen sessiz duruyor
`launcher/app/ui/index.html:1776` — *1 hakem gerçek, 1 hakem değil*

`trySelfUpdate` `u.auto === false` iken hiçbir bildirim üretmeden `return false` yapıyor. Oysa Rust
tarafının yorumları bildirimin gösterildiğini iddia ediyor (`main.rs:396`, `install.rs:914`:
*"bildirim kalır ama sessiz kurulum durur"*). `rollout_bekliyor` alanı arayüzde hiç okunmuyor.

Sonuç: deneme sınırı dolduğunda veya rollout dilimi açılmamışken cihaz launcher güncellemesini bir
daha otomatik almaz ve kullanıcıya bunu söyleyen tek satır bile çıkmaz.

### C5. Sağlık kapısı yalnız "süreç ayakta" ölçüyor, `dbReady` yok sayılıyor
`launcher/core/src/backend.rs:117` — *1 hakem P1, 1 hakem "eklenmemeli"*

Kapı = HTTP 200 + nonce. Backend aynı yanıtta `dbReady` yayınlıyor (`system_router.py:274`) ve
`api_server.py:2305` **seans başlatmayı** tam o alana bağlıyor (503).

Yani DB'yi bozan bir yayın: backend açılır, 200 döner, launcher "sağlıklı" der, sha kaydedilir,
`runtime.old` **silinir**. Klinik hiçbir seans başlatamaz ve otomatik geri dönüş yolu kalmamıştır.

⚠️ **Karşı görüş ciddi:** `wait_for_health`'e kapı olarak eklenmesi *E-stop yolunu düşürür* —
DB bozukken bile acil durdurma çalışmalıdır. İkinci hakemin önerisi daha güvenli:
`guncellemeyi_onayla`dan **hemen önce** tek seferlik gövde okuması, `dbReady=false` ise geri al
(ya da en azından operatöre uyar).

## Doğrulanmamış (P2 — kod alıntılı, hakemden geçmedi)

| # | Dosya | Özet |
|---|---|---|
| C6 | `main.rs:1240` | `apply_self_update` **kurulum kilidini almıyor** (kardeş akışların hepsi alıyor). İkinci pencere kurulum yaparken NSIS `/S` onun backend'ini öldürür. |
| C7 | `index.html:1073` | 6 saatlik periyodik tur **launcher** güncellemesini hiç değerlendirmiyor — yalnız runtime planına bakıyor. Hep-açık makine launcher yamasını ne alır ne duyar. |
| C8 | `flow.rs:74` | Yerel dosya hataları (`rename`, `write`) "geçici ağ hatası" sayılıyor → tek bir AV kilidi **6 kez tam ≤1,4 GB yeniden indirme** tetikliyor; her denemede tamamlanmış `.part` siliniyor. |
| C9 | `flow.rs:1025` | Kesintiden kalan `runtime.new` disk kapısından **önce** temizlenmiyor → güncelleme kalıcı "Yetersiz disk alanı" ile reddedilebilir (artığı silecek olan şey güncellemenin kendisi). |
| C10 | `flow.rs:1080` | `app_yedegi: true` yedek gerçekten alınmadan **koşulsuz** set ediliyor → geri alma hiçbir şey yapmadan "eski sürüme dönüldü" diyor. |
| C11 | `flow.rs:583` | App katmanı takası sırasında kapanma için **kurtarma yolu yok**; `yarim_takasi_kurtar` yalnız tam-takas senaryosunu kapsıyor. Cihaz "kurulu değil" görünür, sağlam yedek yetim kalır. |
| C12 | `flow.rs:488` | `install_profiles` model açılımından önce sha kaydını geçersiz kılmıyor → yarıda kesilen "Onar" **bozuk modeli 'güncel' bırakıyor**; AI analizi anlaşılmaz hatayla düşer. Kardeş yol (`flow.rs:1162`) doğru yapıyor. |
| C13 | `flow.rs:116` | Manifest'te `size` eksik/0 ise plan asla `cached` olmaz → güncelleme sonsuza kadar ön-indirilir ama **hiç kurulmaz**. |
| C14 | `hooks.nsi:152` | Kaldırma silme listesi eskimiş (`installed_packages.json`, `install_id.txt`, `backup_dir.txt`, `runtime.old/new/bozuk` yok) → özyinelemesiz `RMDir` başarısız, GB'larca artık kalır. Dosyanın kendi kuralı bunu yasaklıyor. |

## P3 (client)

- `main.rs:1283` — indirme bittikten sonra basılan **İptal yok sayılıyor**, kurulum yine yapılır.
- `main.rs:1345` — indirilen setup.exe `%TEMP%`'te birikiyor (batch yalnız kendini siliyor).
- `install.rs:833` — `_app_roots.json` temizleme filtresi **boş kök girdisini** elemiyor; boş bir
  kök tüm `runtime/` ağacını yedeğe taşıtır.
- `index.html:1975` — upstream'siz hotspot'ta 'Başlat' düğmesi her açılışta ~20 sn kilitli
  (`getaddrinfo` asılıyor, duvar-saati tavanı 20 sn).

---

# MOBİL TARAF

## Doğrulanan

### M1. APK indirme adresinde hiçbir şema/host pinlemesi yok
`pf/src/services/mobileUpdate.ts:76` ve `:335` — *iki hakem de doğruladı*

```ts
if (!a?.url || !a?.versionCode || !a?.size) return { varMi: false, sebep: "eksik_alan" };
```

Tek denetim **varlık** kontrolü. `surum.url` hiç doğrulanmadan indiriciye veriliyor: https
zorunluluğu yok, host allowlist yok, repo-yolu pini yok. Uygulamada `usesCleartextTraffic="true"`
olduğu için **`http://` adresi gerçekten indirilir**.

**Masaüstü ikizi bunu açıkça yapıyor** — `launcher/core/src/net.rs:163`
`validate_download_source()` + `ALLOWED_HOSTS` + `UPDATE_REPO_PATH` pini. Aynı depoda API istemcisi
de kapılı (`apiClient.ts:146` `isCleartextAllowed`, *"düz HTTP yalnız yerel ağa"*). Güncelleme yolu
tek kapısız kanal.

Depo **public** ve `mobile` bloğu manifest'e **elle** yazılıyor (aşağıda Y3) — yani yanlışlıkla ya
da kasten değiştirilebilir.

### M2. İndirmenin HTTP durum kodu hiç denetlenmiyor
`pf/src/services/mobileUpdate.ts:350`

```ts
const sonuc = await dl.downloadAsync();
if (!sonuc?.uri) return { ok: false, hata: "indirme" };   // status YOK
```

Native katman durum kodunu zaten veriyor (`putInt("status", response.code)`) ve gövde **durumdan
bağımsız olarak** dosyaya yazılıyor.

Manifest'teki varlık silinmiş/yanlış etikete taşınmışsa (yayında yaşanmış bir durum) telefon 404
HTML gövdesini APK olarak diske yazar, boyut kapısına takılır ve kullanıcıya *"bağlantınızı
kontrol edip tekrar deneyin"* der — **tekrar denemek asla işe yaramaz.** Devam eden indirmede 416
gövdesi kısmi dosyanın sonuna eklenir.

## Şüpheli

### M3. Devam (resume) kimliğinde sha256 yok
`pf/src/services/mobileUpdate.ts:300` — *1 hakem P2, 1 hakem "bugün tetiklenmiyor"*

`ayniIs` yalnız `versionCode + url` karşılaştırıyor. Varlık aynı URL'de değişirse (`--clobber`),
yarım dosyaya devam eden telefon **eski + yeni bayt karışımı** bir APK üretir ve toplam boyut
tam tutar → boyut kapısı bunu asla eleyemez. `MobilSurum.sha256` kod tabanında **hiçbir yerde
okunmuyor**.

## Doğrulanmamış (P2 — kod alıntılı, hakemden geçmedi)

| # | Dosya | Özet |
|---|---|---|
| **M4** | `MobileUpdateBanner.tsx:23` | ⚠️ **Seans kapısı yalnız `activeTreatment.isActive`e bakıyor** — bobinler seanssız da çalışır. Deponun kendi ölçüsü daha geniş: `GlobalEmergencyStop.tsx:35` ve `useApkGuncelleme.ts:61` (`is_active \|\| hardware_running`). Bobin hastanın üzerinde enerjiliyken güncelleme bandı çizilebilir. |
| M5 | `AppShell.tsx:374` | **İki bağımsız bant** aynı APK güncellemesi için montajlı: `UpdateBanner` (tarayıcıya çıkarır, eski `mobil` dalı) + `MobileUpdateBanner` (uygulama içi). `UpdateBanner`'da seans kapısı **hiç yok**. |
| M6 | `MobileUpdateGate.tsx:123` | Başarısız indirmeden sonra 'Şimdilik devam et' bandı **tüm açılış boyunca susturuyor** — güncellemeyi deneyen kullanıcı, hiç denemeyenden az imkânla kalıyor. |
| M7 | `mobileUpdate.ts:361` | Kurulumdan sonra APK önbellekten **hiç silinmiyor** — her yayında ~128 MB kalıcı birikiyor. |
| M8 | `mobileUpdate.ts:77` | `versionCode` sayıya çevrilemezse kapı **fail-open** (NaN karşılaştırması false) → manifest'teki tek yazım hatası tüm telefonlarda sonsuz güncelleme döngüsü açar ve erteleme bayrağı da tutmaz. |
| M9 | `mobileUpdate.ts:312` | Hazır-dosya hızlı yolu yalnız `versionCode + size` eşleştiriyor → aynı sürüm koduyla yeniden yayınlanan düzeltilmiş APK hiç indirilmez. |
| M10 | `mobileUpdate.ts:240` | Tek-yazıcı koruması `versionCode\|url` anahtarına, hedef dosya yalnız `versionCode`a bağlı → aynı dosyaya iki eşzamanlı yazıcı açılabilir. |
| M11 | `mobileUpdate.ts:354` | APK, manifest'te sha256 **varken** doğrulamasız kuruluyor. Yayın manifesti (`_mobile_note`) *"SHA256 doğrular"* diye iddia ediyor — iddia gerçek değil. Güncelleme zincirinde sha ile doğrulanmayan **tek varlık** APK. |
| M12 | `MobileUpdateBanner.tsx:51` | `numberOfLines={3}` kancanın **eylem söyleyen** mesajlarını kırpıyor; aynı metin kapıda tam gösteriliyor. |

## P3 (mobil)

- `mobileUpdate.ts:412` — `kurulumuBaslat` tekilleştirmesi `finally`'de kimlik denetimsiz
  temizleniyor (indirme tarafında aynı desen **doğru** yazılmış: `if (_suren === durum)`).
- `SurumFarkiBanner.tsx:96` — kapatma **diske** yazılıyor; modülün geri kalanı (`atlandiMi`,
  `gizli`) bilerek yalnız bellekte. *"Kalıcı susturma yok"* değişmezi tek yüzeyde deliniyor.
- `SurumFarkiBanner.tsx:58` — aynı manifest her soğuk açılışta **üç kez** çekiliyor (kapı + iki
  bant); `guncellemeVarMi`'de zaman aşımı yok (kıyasla `services/updates.ts` 8 sn abort kullanıyor).
- `ApkInstallerModule.kt:77` — dosya yoksa dönen `false`, "izin yok" ile karışıyor → kullanıcıya
  **zaten verdiği** izni vermesi söyleniyor.
- `apk_installer_paths.xml:6` — FileProvider gereğinden fazla dizin açıyor (`files/` kökü),
  `apkKur` keyfi yol kabul ediyor. Bugün somut sızıntı yok; beyan koddan geniş.

---

# YAYIN ZİNCİRİ

### Y1. Runbook sürümsüz varlık adları yüklüyor, site sürümlü ad bekliyor → 404
`BUILD.md:368` — *iki hakem de doğruladı*

Runbook `PEMFVetClient-Setup.exe` ve `PEMF_Vet_Mobil.apk` yüklüyor; site adı **sürümden türetiyor**
(`config.ts:136`, `:169` → `PEMFVetClient-Setup-1.9.34.exe`). Hiçbir betik sürümlü kopyayı
üretmiyor.

Runbook harfiyen izlenirse **her iki indirme butonu da 404** verir. APK yarısı 2026-08-22'de
gerçekten yaşandı (`test_site_indirme_varligi_URETILDI.py` bunu ölçülmüş arıza olarak kaydediyor)
ama runbook düzeltilmedi ve **EXE tarafında hiç kapı yok**.

### Y2. Runbook manifest'i APK'dan **önce** yayınlıyor
`BUILD.md:364` — manifest'in kendi notu tersini şart koşuyor: *"APK'yı yükledikten SONRA burayı
güncelleyin — ters sırada client'lar 404 alır."* §6'da `mobile.android` bloğunu güncelleyen
**hiçbir adım yok**. Sonuç ya sessiz donma (OTA önceki versionCode'da kalır) ya da 404.

### Y3. `mobile` bloğu URL doğrulaması olmadan taşınıyor, CI kapısı bu bloğu gezmiyor
`scripts/make_manifest.py:367` — `CARRY_ONLY = ("launcher", "mobile")` bloğu içindeki `url` hiç
incelenmeden yeni manifest'e yazılıyor. Yayın öncesi tek kapı olan regresyon testi
(`manifest.rs:461`) yalnız `runtimes` + `models` geziyor.

`launcher.installer_url` hem CI'da hem istemcide pinli; **mobil tek kapısız kanal** (M1 ile
birleşince uçtan uca hiçbir kapı yok).

### Y4. Site launcher sürümünü kilitleyen kapı yok — üstelik kod var olmayan bir kapıyı anlatıyor
`pemf-vet-web/src/config.ts:134` — yorum *"check-legal-config.mjs testi ikisinin tutarlılığını
ayrıca kilitler"* diyor. O betik yalnız COMPANY bloğundaki placeholder'ları tarıyor, **hiçbir sürüm
alanını okumuyor**. Android tarafı gerçekten kapılı (`test_version_visibility.py`) ama
`windowsTag`/`CLIENT.version` için kapı yok.

Yorum sahte güvence verdiği için denetimde bu ayrışma "kapılı" sanılıyor.

### Y5. `--allow-missing-mobile` bayrağı işlevsiz (P3)
`make_manifest.py:435` — koşulun ikinci yarısı **hiçbir zaman doğru olamaz** (taşıma kodu satır
367'de `manifest["mobile"]`ı zaten doldurmuş oluyor). Testi bayrağı hiç geçirmeden çağırıp EXIT=0
bekliyor — yani testin kendisi bayrağın gereksizliğini kanıtlıyor.

---

# ORTAK / SINIR DIŞI

- **`servers/sync_worker.py:544` (P2)** — cihaz-registry anon tablo-fallback'i filo envanteri
  sürüm alanlarını ayıklamıyor. RPC'siz kurulumlarda heartbeat kalıcı ölür → `tunnel_url` bayatlar
  ve **geri çağırmanın dayandığı filo envanteri hiç dolmaz** ("hangi klinik hangi sürümde?"
  sorusu cevapsız kalır). RPC yolunda geriye-uyum var, tablo yolunda yok.
- **`servers/update_router.py:28` (P3)** — `/api/update/apply` ve `/rollback` `enforce_privileged`
  taşımıyor; LAN auth-muaf olduğu için eski kanal (`PEMF_LEGACY_EXE_UPDATE=1`) açıkken hotspot'taki
  her cihaz kimliksiz kurulum/geri-alma tetikleyebilir. Kod arbitrari değil (SHA256 + Authenticode
  doğrulanıyor, aktif tedavide reddediliyor) — bu yüzden P0 değil.

---

# ÇÜRÜTÜLENLER (yeniden açmayın)

Hakemler bu beş bulguyu kod okuyarak eledi:

1. **"Hazır-dosya hızlı yolu bozuk önbelleği sonsuza dek kullanır"** — zararın oluşması için gereken
   üç koşulun her biri başka katmanca kapatılmış; senaryo ulaşılamıyor.
2. **"`mevcutVersionCode()` app.json okuyor, gerçek kaynak gradle — ayrışık APK sahaya çıkar"** —
   mekanizma doğru, **etki** çürütüldü: build hattı (`sync_versions.ps1`) bunu engelliyor.
   *(Yine de kapı eksikliği gerçek — aşağıya bakın.)*
3. **"APK sha256 doğrulanmıyor → saldırı zinciri"** — kod gözlemi doğru (M11 olarak duruyor), ama
   iddia edilen saldırı zinciri ve önerilen çözüm çürütüldü.
4. **"İndirme arka planda biterse Android kurulum niyetini sessizce engeller"** — hem tetikleme
   mekanizması hem etki doğrulanamadı.
5. **"BUILD.md 'betik blokları ÜRETİR' diyor ama yalnız TAŞIR"** — dayanak alıntısı hatalıydı;
   BUILD.md:186 aslında *"taşır/üretir"* diyor.

---

# DENETİM SIRASINDA DÜZELTİLENLER

- **Sürüm bandı yanlış alarmı (sahadan bildirildi).** `SurumFarkiBanner` telefon sürümünü (2.3.x)
  cihaz sürümüyle (1.9.x) kıyaslıyordu — ayrı şemalar, hiçbir zaman eşit olamazlar → tam güncel
  sistemde bile uyarı çıkıyordu. Ölçü, güncelleme altyapısının kaynağına (yayınlanmış son mobil
  sürüm) çevrildi. 6 test + mutasyon doğrulaması. → **mobile 2.3.22**
- **Mobil sürüm tek-kaynak ayrışması** (denetimin bulgusu, kaynağı bu oturumun kendi
  düzenlemesiydi): `app.json` 2.3.22/29 iken `versions.json` ve `build.gradle` 2.3.21/28'de
  kalmıştı. `versions.json` tek-kaynağından `sync_versions.ps1` ile hizalandı; site
  `androidVersion` ve CHANGELOG güncellendi. `test_version_visibility.py` 12/12 yeşil,
  `sync_versions -Check` temiz.

---

# İKİNCİ TUR: doğrulanmamış bulgular hakemden geçirildi

Raporun ilk hâlinde "hakem bütçesi dışında" kalan 24 bulgu ikinci bir çekişmeli tura sokuldu
(her biri 2 bağımsız hakem, çürütme görevli). Sonuç:

| Durum | Bulgular |
|---|---|
| **DOĞRULANDI** | C6, C9, C11 (P1) · C8 (P2) · C14, M7, M12, Y5 (P3) |
| **ŞÜPHELİ** | C7, C10, C12, M5, M8, M11, O2 |
| **ÇÜRÜTÜLDÜ** | C13, M6, **M9**, **M10**, **Y3**, **Y4**, O1 |

⚠️ Çürütülenlerin gerekçeleri kayda değer: **M9/M10** (önbellek/yarış) için "iddia edilen etkiye
giden yol bu depoda ulaşılamaz"; **Y3** (make_manifest URL doğrulaması) ve **Y4** (site kapısı)
için "kod-olgusu doğru ama yük taşıyan iddia kodla çürütülüyor" — Y4'te `windowsTag` için bir kapı
gerçekten VAR. Bu beş bulguya **dokunulmadı**; "düzeltilmiş" olsalardı gereksiz risk alınmış olurdu.

---

# UYGULANAN DÜZELTMELER (2026-08-23)

Aşağıdakiler kırmızı-önce test → düzeltme → **iki yönlü mutasyon doğrulaması** disipliniyle yapıldı.

### 🔴 Canlı üretim arızası — onarıldı
**Sitedeki "Windows için indir" butonu 404 veriyordu.** Y1'in kağıt üstündeki değil, *yaşayan*
hâli: 1.9.34 yayınında `launcher-v1.9.34` etiketine yalnız sürümsüz `PEMFVetClient-Setup.exe`
yüklenmişti; site adı etiketten türetiyor (`PEMFVetClient-Setup-1.9.34.exe`). Yerelde üretilmiş
sürümlü kopya yayındaki ikiliyle **bayt-bayt aynı** olduğu doğrulandı ve aynı etikete ek ad olarak
yüklendi (silme yok). Doğrulandı: HTTP 206, sha `9bce6a7dcf32`, 2.965.445 bayt.

### Client
- **C3** — çevrimdışı açılışta `startUpdateWatch()` erken-return'ün altında kalıyordu; artık
  çevrimdışı dalda da başlıyor. Ağ geri gelince makine kendini toparlar.
- **C6** — `apply_self_update` kurulum kilidini almıyordu (yıkıcı akışlar arasında **tek** kilitsiz
  akış). Kilit eklendi. ⚠️ Bu hata ikinci kez olduğu için kalıcı kapı yazıldı:
  `tests/test_kurulum_kilidi_tum_akislarda.py` beş akışın hepsini parametrik denetler ve
  `let _ = ...` (anında düşen bağ) tuzağını ayrıca ölçer.
- **C9 + C11** — `yarim_takasi_kurtar` iki kesinti sınıfını görmüyordu: (a) yetim `runtime.new`
  disk kapısının istediği alanı işgal ediyordu → kalıcı "Yetersiz disk alanı"; (b) app-katmanı
  takasının ortasında kesinti kurtarılmıyordu → cihaz "kurulu değil" görünüp ~1,46 GB yeniden
  indiriliyordu. İkisi de kapatıldı; `runtime.old` (geri dönüş yolu) korunuyor ve "çalışan
  kurulumda hiçbir şey yapma" sözleşmesi bozulmadı (karşıt-kanıt testleri yeşil).
- **C8** — yerel dosya hataları "geçici ağ hatası" sayılıyordu; en kötüsü **tamamlanmış**
  indirmenin `rename`inde düşmesiydi (6 deneme × 1,19 GB ≈ 7 GB boşuna trafik). Yeni
  `NetError::LocalIo` varyantı kalıcı sayılıyor; gerçek ağ hataları (`Io`) geçici KALDI.
- **C14** — NSIS kaldırma listesi üçüncü kez geride kalmıştı; üç kök durum dosyası +
  `runtime.new/old/bozuk` eklendi.

### Mobil
- **M1** — indirme kaynağı pinlendi (`kaynakGuvenli`, masaüstü `net.rs` paritesi): https zorunlu,
  repo-yolu pinli `github.com` veya sayılmış nesne depoları, yol-kaçışı reddi. ⚠️ Yol-kaçışı
  denetimi **ham metin** üzerinde yapılır: `URL` ayrıştırıcısı `\` karakterini sessizce `/`'a
  çeviriyor, yani ayrıştırılmış yolu denetlemek o vakayı hiç göremiyordu (ölçülerek bulundu).
- **M2** — indirmenin HTTP durum kodu denetleniyor; 2xx dışı artık ayrı `sunucu` hatası ve arayüz
  "bağlantınızı kontrol edin" yerine doğru şeyi söylüyor (o mesaj kullanıcıyı işe yaramayacak bir
  döngüye sokuyordu).
- **M4** — iki güncelleme bandının seans kapısı dar ölçüdeydi (`activeTreatment.isActive`);
  bobinler seanssız da çalışır. Ortak `useDonanimCalisiyor()` kancasına çıkarıldı ve **ikisi
  birden** bağlandı (tek dosyayı düzeltmek deponun 1 numaralı hata desenini yeniden üretirdi).
- **M7** — indirilen APK'lar önbellekte birikiyordu (~128 MB/yayın, sonunda güncellemenin kendini
  engellemesine varır); eski paketler indirme başlangıcında temizleniyor.
- **M12** — bant mesajlarındaki `numberOfLines={3}` kırpması kaldırıldı (kesilen kısım tam da
  kullanıcıya ne yapacağını söyleyen cümleydi).
- **Sürüm bandı yanlış alarmı** (sahadan bildirildi) — ölçü artık yayınlanmış son mobil sürüm.

### Yayın zinciri
- **Y1 + Y2** — runbook düzeltildi: her varlık **iki adla** yüklenir (sürümsüz = makine/OTA,
  sürümlü = site), manifest'in mobil bloğu APK'dan **sonra** tazelenir, site **en son** deploy
  edilir.
- **Yeni kapı:** `scripts/site_indirme_dogrula.py` — sitenin ürettiği her indirme adresine
  gerçekten bakar ve yayın akışının **son adımı**dır. ⚠️ Yerel testler "üretildi mi"yi ölçer;
  1.9.34 arızasında dosya üretilmişti ama **yüklenmemişti** — o boşluğu yalnız bu betik kapatır.
  Ayrıca `test_site_indirme_varligi_URETILDI.py`ye Windows ikizi eklendi (APK tarafı korunuyordu,
  EXE tarafında hiç kapı yoktu) ve betiğin runbook'ta çağrıldığı testle kilitlendi.
- **Y5** — `--allow-missing-mobile` kapısı ULAŞILAMAZDI (koşulun ikinci yarısı hiçbir zaman doğru
  olamıyordu); kapı gerçekten ölçülebilir hâle getirildi ve testi bayrağı fiilen kullanacak
  biçimde düzeltildi.

**Doğrulama:** mobil 555/555 + tsc temiz · Rust 209 birim + 11 kesinti senaryosu dâhil tüm çalışma
alanı yeşil · backend 1640 test yeşil. Her düzeltme için mutasyon (korumayı kaldır → kırmızı)
ayrıca koşuldu.

---

# ÖNERİLEN SIRA

1. ✅ 🔴 **P0 — `.iss` E-stop — KAPATILDI** (ayrıntı aşağıda).
2. **C5 (sağlık kapısı `dbReady`)** — açık kalan tek madde. Karşı görüş ciddi:
   `wait_for_health`e kapı olarak eklemek E-stop yolunu düşürür; doğrusu `guncellemeyi_onayla`dan
   önce tek seferlik gövde okumasıdır. Sahip kararı.

## Şüpheli 7 maddenin tamamı karara bağlandı (üçüncü geçiş)

Hakemler bölündüğü için her biri kodla tek tek doğrulandı; **altısı gerçek çıktı ve kapatıldı**.

| # | Karar | Ne yapıldı |
|---|---|---|
| **M5** | gerçek (kısmen) | `UpdateBanner` hiçbir seans/bobin kapısı tanımıyordu → `useDonanimCalisiyor` eklendi. ⚠️ Kanal KALDIRILMADI: 2026-08-09 denetimi "APK sideload bildirimi kalır" diye açıkça karar vermiş; o karar sahibin. Ölçüm: kanal canlı ama içerik ölü (`apkUrl` boş) — yani tuzak uykuda, `publish_release.ps1 -Branch mobil` onu silahlandırabilir. |
| **C10** | gerçek | `app_yedegi: true` koşulsuz set ediliyordu → geri alma hiçbir şey yapmadan "eski sürüme dönüldü" diyordu. Kayıt artık gerçeği yansıtıyor (`app_katmanini_degistir` yedeğin alınıp alınmadığını döner), `app_degisti` alanı ayrıldı ve yedeksiz geri alma artık **hata döner**. |
| **C12** | gerçek | `install_profiles` model açılımından önce sha kaydını geçersiz kılmıyordu (kardeş yol yapıyordu) → yarıda kesilen "Onar" bozuk modeli kalıcı "güncel" bırakıyordu. |
| **C7** | gerçek | 6 saatlik tur launcher güncellemesini hiç değerlendirmiyordu → **bildirim** eklendi. ⚠️ Kurulum EKLENMEDİ: turun kendi sözleşmesi "uygulamaz, yalnız indirir ve bildirir" diyor; kurulum seansı keserdi. |
| **C4** | gerçek | `auto === false` dalı sessizce dönüyordu; Rust yorumları "bildirim kalır" diye iddia ederken hiçbir bildirim yoktu. Aynı metinle kapatıldı. |
| **M8** | gerçek | `versionCode` NaN fail-open'ı kapatıldı; sürüm alanları sert doğrulanıyor ve **normalize edilmiş** değer dönüyor (ham metin dosya adına ve erteleme anahtarına giriyordu). |
| **M11** | gerçek | APK artık kurulumdan önce **SHA256 ile doğrulanıyor**. ⚠️ Eski gerekçe ("128 MB'ın hash'i mobilde pratik değil") doğruydu ama sonucu yanlıştı: hash JS'te değil **yerel modülde** 1 MB'lık tamponla akıtılarak alınıyor. Hash alınamıyorsa akış sürer (eski APK'lar kilitlenmesin). Modül başlığındaki "neden sha256 değil imza" açıklaması gerçeğe çekildi. |
| **O2** | gerçek | `/api/update/apply` ve `/rollback` yetki kapısı taşımıyordu; LAN auth-muaf olduğu için hotspot'taki her cihaz kimliksiz kurulum/geri-alma tetikleyebilirdi. `enforce_privileged` eklendi (salt-okunur `status` kasten kapısız). |

**Not:** M5 dışında hiçbiri "kısmen" değil — hepsi kodla doğrulandı. M5'te yalnız güvenlik kapısı
eklendi, kanalın kaderi sahibin kararına bırakıldı.

## C1 ve C2 de kapatıldı (aynı gün, ikinci geçiş)

**C1 — profil paketi yasak-listesi.** Altı girdi eksikti (`installed_packages.json`,
`install_id.txt`, `backup_dir.txt`, `runtime.new/old/bozuk`). ⚠️ Liste üç kez eskidiği için düzeltme
yalnız girdi eklemek olmadı: `tests/test_profil_paketi_kok_dosyalari.py` artık **adları değil
kaynağı** ölçüyor — `install_root.join("...")` ile üretilen her kök girdisi ya listede olmalı ya da
açıkça meşru sayılmalı (tek istisna `ai_models`). Kapının işlediği hemen kanıtlandı: C2 için yeni
bir durum dosyası eklediğimde testi **anında kırmızıya döndü**. İzin-listesine geçilmedi —
`extract.rs`'in kendi notu (#104) katı `ai_models/` önekinin meşru bir paketi kırabileceğini
söyleyerek yasak-listeyi bilerek seçmiş; o karara dokunmak yerine listenin eskimesi engellendi.

**C2 — geri alma döngüsü.** `MAX_RUNTIME_ATTEMPTS = 2` ve `runtime_attempt.json`, self-update'teki
desenin birebir ikizi. ⚠️ Hedef kimliği **sürüm numarası değil paket sha'ları**: aynı numara altında
farklı ikili yayınlanabildiği için numaraya bağlanan bir sayaç düzeltme yayınını da bloklardı.
Sınır dolunca yalnız otomatik kurulum durur; `needed()` **değişmez** (arızayı görünmez kılmak
arızadan beterdir), bildirim çıkar ve elle "Onar" açık kalır.

⚠️ Mekanizmayı yazmak yetmiyor — bu depoda yazılıp bağlanmamış bir mekanizma daha önce sessiz
no-op olarak kaldı (jeton). Bu yüzden `tests/test_runtime_geri_alma_dongusu_bagli.py` **üç bağlantı
noktasını birden** ölçüyor: geri almada sayaç artıyor mu, başarıda temizleniyor mu, kararda okunup
arayüze yansıyor mu. Üçü de ayrı ayrı mutasyonla doğrulandı.

## 🔴 P0 KAPATILDI — Inno kurulumu artık bobinleri güvene alıyor

Sıra düzeltmesi (2026-08-17) doğruydu ama **yetmiyordu**: graceful yol `if ResultCode <> 1060`
("servis kurulu mu?") bloğunun içindeydi, force-kill blok dışında ve koşulsuz. Launcher
dağıtımında servis yoktur → graceful tamamen atlanır → geriye yalnız sinyalsiz `taskkill /F`
kalır. Yani bobin-STOP'a giden tek yol servise bağlıydı ve tam da korunması gereken
kurulumlarda hiç çalışmıyordu. Mevcut sıra testleri bunu göremezdi (ikisi de "graceful < kill" der).

`hooks.nsi`'deki çalışan blok Pascal'a taşındı ve **ssInstall'ın en başına, servis sorgusundan
önce, koşulsuz** yerleştirildi: port oku → doğrula → `POST /api/hardware/emergency_stop` →
1800 ms bekle → ancak sonra kill.

⚠️ **Bir tuzağı kopyalamadım.** NSIS ikizi `{localappdata}`ya güvenip ayrı bir denetimde yanlış
dizine bakmıştı. Inno `PrivilegesRequired=admin` ile yükseldiği için `{localappdata}` **yükselten
hesabı** gösterir; operatör başka bir hesapsa dosya bulunamaz ve E-stop sessizce atlanırdı. Bu
yüzden varsayım yerine ölçüm: önce hızlı yol, sonra tüm kullanıcı profillerinin
`AppData\Local\PEMF Vet Client\backend.port` yolu taranıyor (admin yetkisiyle okunabilir).
Port `StrToIntDef` + 1–65535 ile doğrulanıyor — `backend.port` kullanıcı-yazılabilir bir dizinde
ve ham içeriği komut dizesine gömmek enjeksiyon ile CR/LF kaynaklı sessiz başarısızlık demekti.

**Doğrulama:** 5 yeni test (çağrı koşulsuz mu · yordam gerçekten gönderiyor mu · bekleme ≥1500 ms ·
port doğrulanıyor mu · kaldırma yolu karşı-kanıtı), **üç yönlü mutasyon** (çağrıyı kaldır,
gönderimi boşalt, beklemeyi sil — üçü de yakalandı) ve **Inno derleyicisiyle sözdizimi
doğrulaması** ("Compiling [Code] section → Successful compile"; yük çıkarılmış kopyayla, çünkü
tam paket 3,7 GB ve derlemesi dakikalar sürüyor).

✅ **Kapananlar (22):** 🔴 P0 + C1, C2, C3, C4, C6, C7, C8, C9, C10, C11, C12, C14, M1, M2, M4, M5, M7,
M8, M11, M12, Y1, Y2, Y5 + canlı 404 onarımı.
❌ **Çürütülenlere dokunulmadı (7):** C13, M6, M9, M10, Y3, Y4, O1.
⚠️ **Açık kalan (1):** C5 (sağlık kapısı `dbReady`) — kod değil **karar** meselesi ve karşı görüş
ciddi: `wait_for_health`e kapı olarak eklemek E-stop yolunu düşürür; doğrusu onaylamadan önce
tek seferlik gövde okumasıdır.

## Toplam

53 bulgu → **22 düzeltildi (P0 dâhil) · 7 çürütüldü · 1 sahip kararında · kalanlar P3/kapsam-dışı.**
Her düzeltme kırmızı-önce test → düzeltme → **iki yönlü mutasyon** ile yapıldı; üç kez mutasyon
kaçtı ve üçünde de eksik olan test yazıldı (biri kendi eklediğim durum dosyasını yakalayan kapıydı).
Son durum: backend **1676**, mobil **571**, Rust **13 süit** yeşil.
