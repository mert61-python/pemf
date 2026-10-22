# PEMF Backend — Operasyon Runbook (audit B-11.2)

Saha olay-müdahale rehberi. Klinik PC = Windows. **Sahada backend, PEMF Vet Client'ın (launcher) başlattığı
süreçtir** (`PEMFVetClient.exe` → `PEMF_Backend.exe` → `mosquitto.exe`); **`PemfBackend` Windows servisi YOKTUR**
(saha ölçümü 2026-09-30, Y36). Servis komutları (`nssm`, `PemfBackend`) yalnız Inno / `setup_services.ps1` ile servis
kurulmuş cihazlar içindir ve aşağıda AYRI gösterilir — sahada `nssm stop` hiçbir şeyi durdurmaz. **ACİL DURDUR her
kipte:** `curl.exe -X POST http://127.0.0.1:8000/api/hardware/emergency_stop` — ⚠️ **`curl.exe`** yazın: Windows
PowerShell 5.1'de çıplak `curl` = `Invoke-WebRequest` takma adıdır, `-X`'i tanımaz ve komut DÜŞER (ölçüldü). ⚠️ **Port:**
launcher 8000 doluysa backend 8001..8049'dan birini kullanır; gerçek port `%LOCALAPPDATA%\PEMF Vet Client\backend.port`
dosyasındadır (O-16.1) — aşağıdaki "Hızlı komutlar"daki tek satır portu oradan okur; dosya yoksa ya da içeriği sayı
değilse 8000'i dener.
Veri kökü `C:\ProgramData\PEMF_System\PEMF_GUI` (= `PEMF_DATA_DIR` + `\PEMF_GUI`; `PEMF_DATA_DIR` klinikte `C:\ProgramData\PEMF_System`'dir). Aşağıda `<data>` = **veri kökü**.

## Hızlı komutlar (Yönetici PowerShell)

```powershell
# ── SAHA (launcher kipi) ──
Get-Process PEMF_Backend -ErrorAction SilentlyContinue        # backend süreci ayakta mı
# ACİL DURDUR — bobinler HEMEN durur (auth-muaf). Port backend.port'tan (launcher 8000 doluysa 8001..8049); dosya yoksa
# ya da içeriği SAYI değilse 8000 (dosya kullanıcı-yazılabilir: sayı denetimi teardown'daki gibi — bozuk içerik URL'yi
# düşürür, `1@başka-adres` biçimi isteği başka adrese yollar; ölçüldü, G-14.1). Launcher'ı başlatan KULLANICININ
# oturumunda çalıştırın (başka hesapta %LOCALAPPDATA% farklıdır → 8000 denenir).
$p = "$(Get-Content "$env:LOCALAPPDATA\PEMF Vet Client\backend.port" -ErrorAction SilentlyContinue)".Trim(); if ($p -notmatch '^\d{1,5}$') { $p = '8000' }; curl.exe -X POST "http://127.0.0.1:$p/api/hardware/emergency_stop"
# Durdur: launcher penceresini kapatın — launcher ÖNCE ACİL DURDUR gönderir, SONRA backend'i sonlandırır.
# Yeniden başlat: launcher'ı kapatıp yeniden açın (⚠️ aşağıdaki FİRMWARE uyarısı).

# ── YALNIZ servis kurulumu (Inno / setup_services.ps1 — sahada YOK) ──
Get-Service PemfBackend
nssm stop PemfBackend         # graceful kapanış bobinlere STOP gönderir (servis kipinde)
nssm restart PemfBackend      # veya: Restart-Service PemfBackend
# ⚠️ FİRMWARE (Y1): oto-firmware VARSAYILAN KAPALI — backend'in her açılışı (nssm restart ya da launcher'ı yeniden
#    açma) uyumu yalnız ÖLÇER; STM'e firmware YAKMA denemesi YALNIZ ortamda açıkça PEMF_FW_AUTO_UPDATE=1 verilmişse
#    olur (sahadaki 1.9.50'de bu zincir yok). Zincir tezgâhta (Oturum 13) doğrulanmadan sahada 1 VERİLMEZ; yeniden
#    başlatmadan önce ortamda PEMF_FW_AUTO_UPDATE=1 OLMADIĞINI doğrulayın.

# Sağlık + sürüm + şifreleme durumu
curl.exe http://127.0.0.1:8000/api/health        # atRestEncrypted, pairingCode, tunnelUrl (port: yukarıdaki $p)
curl.exe http://127.0.0.1:8000/metrics           # Prometheus metrikleri

# Loglar (döndürmeli, 10MB×5) + çökme kaydı
Get-Content C:\ProgramData\PEMF_System\logs\backend_service.log -Tail 100 -Wait
Get-Content C:\ProgramData\PEMF_System\logs\crash.log -Tail 50
```

## Destek paketi (teşhis için TEK dosya)

Klinikten log istemek yerine **PII maskelenmiş tek bir zip** üretin:

```powershell
# Backend ayaktaysa (tercih edilen — hasta adları GERÇEKTEN maskelenir):
curl.exe -X POST http://127.0.0.1:8000/api/support/bundle   # base64 zip + OZET.json (port: backend.port, yukarıya bakın)

# Backend çökmüşse:
python tools\destek_paketi.py            # Masaüstüne yazar
```

İçinde: sağlık/sürüm özeti (`buildId` dâhil), log kuyrukları, denetim izi **sayım** özeti.
İçinde **YOK**: `pemf_secrets.json`, `.sqlcipher_key`, veritabanları, `kurtarma-zarfi.enc`.

⚠️ `OZET.json` içinde **UYARI** alanı varsa: şifreli veritabanı açılamamış demektir; o durumda
hasta adları maskelenmemiş olabilir — göndermeden önce `logs/` içeriğine bakın.

## Denetim izi (kim, ne zaman, kaç kayıt)

Geri dönüşsüz işlemler (toplu silme, dışa/içe aktarma, operatör ekleme-çıkarma, PII maskeleme)
şifreli DB içinde **ekleme-only** `audit_events` tablosuna yazılır — **silinemez, değiştirilemez**.

```powershell
curl http://127.0.0.1:8000/api/audit/events?limit=50
curl "http://127.0.0.1:8000/api/audit/events?event_type=ai_log.delete_all"
```

"Kayıtlarım kayboldu" çağrısında ilk bakılacak yer burasıdır.

## Log yerleri
- Servis logu: `<PEMF_LOG_DIR>\backend_service.log` (döndürmeli). `PEMF_LOG_JSON=1` → JSON.
- Çökme: `<PEMF_LOG_DIR>\crash.log` (yakalanmamış istisna + thread crash).
- NSSM stdout/stderr: NSSM yapılandırmasındaki yönlendirme.

## Olay senaryoları

| Belirti | Kontrol / Çözüm |
|---|---|
| **Mobil bağlanmıyor (LAN)** | Firewall TCP 8000 + UDP mDNS; aynı subnet? `/api/health` yerelden 200 mü? |
| **Mobil bağlanmıyor (uzak)** | `/api/health` → `tunnelUrl` dolu mu? cloudflared çalışıyor mu? `PEMF_ENABLE_TUNNEL=1`? Token istemcide var mı (401)? |
| **"Eksik API anahtarı" (401)** | LAN'da olmamalı (muaf). Uzakta: mobil bir kez LAN'a girip token çeksin (`/api/auth/token`) veya 6-haneli pairing kodu. |
| **MQTT/ESP bobinleri ölü** | ⚠️ **ÖNCE BUNU KONTROL ET:** ESP **2026-09-11'de devre dışı bırakıldı** — `PEMF_ESP_ENABLED=0` ise bobinlerin sessiz olması **arıza değil, beklenen durumdur**; kovalamayın. Bayrak `1` ise: `Get-Service mosquitto` Running? `curl /api/gateway/status`. Hotspot aktif mi (device modunda logon-task)? |
| **STM bobinleri ölü** | `PEMF_STM_PORT=auto` ST-Link'i buldu mu? Sürücü? `/api/health` → `stmConnected`. |
| **atRestEncrypted=false (beklenmedik)** | `PEMF_ENCRYPT_AT_REST=1` set mi? sqlcipher3 wheel EXE'de mi? Anahtar (`.sqlcipher_key`/keyring) okunuyor mu? PatientDB fail-closed → başlatma reddeder. |
| **Kötü güncelleme sonrası sorun** | Aşağıdaki **"Kötü güncelleme"** bölümüne bakın. ⚠️ `/api/update/rollback` **KULLANMAYIN** — o uç eski (kapatılmış) EXE kanalına aittir ve hiçbir şey yapmaz. |
| **Disk dolu / yedek** | `<data>\backups\` günlük şifreli yedek (her türden son 14: tedavi, hasta, operatör hesapları, SIRSIZ `config` / `system_settings`) + `kurtarma-zarfi.enc`. `PEMF_BACKUP_DIR` set ise off-machine kopya — orada da her türden **son 14** tutulur, eskileri cihaz siler (Y11); cihaz o dizinde yalnız kendi `pemf_<tür>_<tarih>` dosyalarını siler. Kaldırma / tam temizlik off-machine dizine dokunmaz (A-45). Her cihaz AYRI `PEMF_BACKUP_DIR` kullanmalı: dizinde başka kurulumun `.pemf_kurulum_*` işareti varsa cihaz orada HİÇ silmez ve ERROR yazar (D2-1.2). Aynı veri kökünü iki backend süreci paylaşamaz — geri yükleme / yedek alma kilitleri süreç içidir; launcher tek backend başlatır (S-D2I.6). |
| **Veri klasöründe `pemf_treatment_history.db-wal.rollback-<tarih>` / `pemf_treatment_history.db-shm.rollback-<tarih>` dosyaları** | Güncelleme sonrası veritabanı göçü GERİ ALINMIŞ: uygulama göç öncesi kopyaya dönerken canlı veritabanının `-wal` / `-shm` yan dosyalarını silmedi, kenara adlandırdı (Y100 — kapanış checkpoint'i düşmüşse son seanslar bu `-wal` dosyasındadır). Bu dosyalar otomatik SİLİNMEZ (Y128). ⚠️ Aynı klasörde `pemf_treatment_history.db.rollback.tmp` VARSA **hiçbir dosyaya DOKUNMAYIN**: geri alma yarıda kalmıştır, son seanslar kenardaki `-wal.rollback-*` dosyasında olabilir — açılış günlüğü bunu ERROR olarak yazar; teknik destek. `.rollback.tmp` YOKSA elle temizlik: (1) uygulamayı kapatın; (2) Geçmiş ekranında güncellemeden önceki son seansların göründüğünü doğrulayın — görünmüyorsa dosyalara dokunmayın, teknik destek; (3) görünüyorsa dosyaları SİLMEYİN, `<data>\backups\` altında tarihli bir klasöre TAŞIYIN; en az bir yedek döngüsü (14 gün) sonra silinebilir. |
| **Veri klasöründe `jeton_bekleyen.json.bozuk`** | Yalnız ücretlendirme AÇIKKEN (`PEMF_JETON_ENFORCED=1`) oluşabilir. `jeton_bekleyen.json` YOLDA KALAN ÖDEME defteridir: analiz teslim edilmiş ama jeton düşümü o an buluta gidememiş kayıtlar (sahip kararı 2026-10-19: "bir süre yeniden dene" — sonraki çevrimiçi istekte gönderilir; çevrimdışı analiz ve eksi bakiye YOK). Defter okunamaz hâlde bulunursa içeriği AYNEN `jeton_bekleyen.json.bozuk`'a eklenir (JSON satırı: `ozet`, `zaman`, `icerik`) ve günlüğe ERROR yazılır ("bekleyen tüketim defteri BOZUK"). Seans, ACİL DURDUR ve analiz ETKİLENMEZ; yalnız o kayıtların jetonu düşülmemiş kalır. **SİLMEYİN** ve elle düzenlemeyin: dosyayı teknik desteğe iletin — `icerik`teki `istek_id` / `miktar` kayıtları gerekirse sahiple bulutta elle uzlaştırılır (aynı `istek_id` ikinci kez düşülmez). KVKK tam temizliği (`scripts/pemf_footprint.ps1`) defterle birlikte bu dosyayı da siler. (YH C2) |
| **Saklama süresini değiştirmek (sensör / doz / olay / PII maskeleme)** | Sahada (launcher kurulumu) backend VARSAYILANLARI geçerlidir: sensör 90, doz 3650, seans olayı 365, giden kutusu 30 gün; PII maskeleme 365 gün ve klinik ONAYINA bağlı (Ayarlar → Veri Saklama); kritik olaylar (ACİL DURDUR, doz) süresiz (A-07). `deploy\device.env`deki `PEMF_RETAIN_*` satırları launcher yolunda **ETKİSİZDİR** (yalnız servis / NSSM kurulumu okur); launcher (1.9.52+) ise bu adları SÜREÇ ORTAMINDA tanımlıysa backend'e aynen geçirir (S-F2-3.2 a — varsayılan yazmaz; boş değer o adımı KAPATIR). Değiştirmek gerekiyorsa teknik destek — elle ortam değişkeni yazmayın (S-F2-3.2 · A-33). |
| **Ayarlar → Veri Saklama'da "Cihaz saati şüpheli"** | Cihaz saati son görülen saatten 1 günden fazla GERİDE ya da 45 günden fazla İLERİDE (BIOS pili / RTC arızası, cihazın uzun süre kapalı kalması). Anonimleştirme, PII maskeleme ve süresi dolan kayıtların silinmesi operatör onaylayana dek DURUR — veri kaybolmaz, yalnız bekler. Windows tarih ve saatini düzeltin, sonra aynı ekranda "Saat doğru, saklamayı sürdür" (iz: `retention.saat_onay`). Saat bir süre geride kaldıysa o sırada yazılan kayıtlar eski tarihli görünür ve onaydan sonra süreye göre işlenir (F2-1.2 · A-73). |

## Kötü güncelleme (TEK KANAL: launcher)

Cihaz yazılımını **yalnız PEMF Vet Client (launcher)** günceller. Backend'in eski
`/api/update/*` uçları kapatılmıştır (`PEMF_LEGACY_EXE_UPDATE` ile açılmadıkça); `exe/latest.json`
kanalı yayında değil, `previousStable` hiç dolmaz → **`/api/update/rollback` hiçbir şey yapmaz.**

**Klinikte (tek cihaz):**
1. Launcher zaten **sağlık kapılı**dır: yeni sürüm açılışta sağlıklı cevap vermezse eskisine
   kendi döner (`runtime.old` / `app.yedek`), paket kimliğini kaydetmez, sonraki açılışta
   önbellekten tekrar dener (**yeniden indirme yok**).
2. Sorun sağlık kapısından geçtiyse (servis ayakta ama davranış bozuk) klinikte geri alma
   **yoktur** — kurtarma yayıncı tarafındadır (aşağıya bakın). Bu arada cihazı çalışır tutmak
   için: seansı bitirin, gerekiyorsa durdurun ve yayıncıyı arayın. **Sahada (launcher kipi):** önce
   `curl.exe -X POST http://127.0.0.1:8000/api/hardware/emergency_stop` (ACİL DURDUR; port `backend.port`, "Hızlı
   komutlar"daki tek satır), sonra launcher penceresini
   kapatın (launcher da kapanırken ACİL DURDUR gönderir). **Yalnız servis kurulumunda:** `nssm stop PemfBackend`
   (graceful kapanış bobinlere STOP gönderir) — sahada servis YOK, bu komut hiçbir şeyi durdurmaz.
3. Teşhis için `runtime.bozuk` dizini varsa **silmeyin** — başarısız sürüm oradadır.

**Yayıncı tarafı (`scripts/make_manifest.py`):**

| Amaç | Bayrak | Etkisi |
|---|---|---|
| Yeni dağıtımı durdur | `--rollout 0` | Yalnız **henüz almamış** cihazlar korunur; sahadaki bozuk kurulum OLDUĞU GİBİ KALIR. |
| Sahayı zorla ilerlet (**geri çağırma**) | `--min-supported-version X.Y.Z` | Kurulu sürümü eşiğin **altında** olan her cihaz, `rollout` frenine **bakılmaksızın** güncellenir. Sürümünü söyleyemeyen kurulum da kapsama girer (fail-safe). |
| Launcher'ın kendi güncellemesini durdur | `--launcher-rollout 0` | Launcher self-update'i durur. |

⚠️ Geri çağırma **ileri** yönlüdür: düzeltilmiş bir sürüm yayınlayıp eşiği ona çekersiniz.
Eski pakete geri döndürmek için manifest'i eski paketin sha'sına yazmak gerekir; sürüm
monotonluğu olmadığı için bu **bilinçli** bir işlemdir ve yayın kaydına yazılmalıdır.

## Anahtar / veri kurtarma (KRİTİK)
- **SQLCipher anahtarı** `<data>\.sqlcipher_key` (+ keyring). **KAYBI = şifreli hasta verisi KALICI OKUNAMAZ.** ACL: yalnız SYSTEM+Administrators.
- Sırlar tek dosyada: `<data>\pemf_secrets.json` (kripto anahtarları DPAPI'li).
- **Aynı makinede yedekten dönüş**: backend'i durdur (sahada: ACİL DURDUR `curl.exe -X POST http://127.0.0.1:8000/api/hardware/emergency_stop` — port `backend.port`, "Hızlı komutlar" — + launcher'ı kapat; servis kurulumunda: servisi durdur) → `<data>\backups\pemf_*_YYYYMMDD.db` dosyasını aktif DB üzerine kopyala (aynı anahtarla şifreli) → backend'i başlat (launcher'ı aç / servisi başlat).

### Kurtarma kodu — donanım arızası / makine değişimi
Kripto anahtarları DPAPI `CRYPTPROTECT_LOCAL_MACHINE` ile **makineye bağlıdır**. Bu nedenle
anakart/disk arızasından ya da Windows yeniden kurulumundan sonra yedekler — off-site kopya
dahil — tek başına **açılamaz**. Bunun için kurulum bir kez **150-bit kurtarma kodu** üretir:

| | |
|---|---|
| **Kod nerede** | `<data>\KURTARMA-KODU.txt` (ilk yedekte oluşur). **Operatör bunu makine dışına almalı** — kasa / parola yöneticisi. Aldıktan sonra dosya silinebilir. |
| **Zarf nerede** | `<data>\backups\kurtarma-zarfi.enc` ve `PEMF_BACKUP_DIR` set ise off-site kopyada. İçinde kurtarılacak anahtarlar — `sqlcipher_key` (şifreli kurulumda) + `patient_fernet_key` (hasta alanları; at-rest kapalıyken de, D2.60) — koddan scrypt ile türetilen anahtarla şifreli. |
| **Kodu görüntüle** | `"%LOCALAPPDATA%\PEMF Vet Client\runtime\PEMF_Backend\PEMF_Backend.exe" --kurtarma --kodu-goster` (cihaz hâlâ çalışırken; Komut İstemi / cmd) |
| **Kurtarma aracı** | Sahada Python YOK: araç launcher'ın kurduğu `PEMF_Backend.exe`nin `--kurtarma` alt komutudur (D2.75). Aşağıdaki komutlar **cmd** içindir; PowerShell'de `& "$env:LOCALAPPDATA\PEMF Vet Client\runtime\PEMF_Backend\PEMF_Backend.exe" --kurtarma …` |

**Kod ve zarf ASLA aynı yerde durmamalı** — zarfın tüm koruması buna dayanır. Kod dosyası
yedek dizinine kopyalanmaz; regresyon testiyle kilitlidir.

**Yeni makinede geri yükleme:**
1. PEMF'i kur, **backend'i henüz BAŞLATMA** — launcher'ı açma (servis kurulumunda: servisi henüz BAŞLATMA);
   başlatırsan yeni bir `sqlcipher_key` üretilir ve yedekler açılmaz.
2. `"%LOCALAPPDATA%\PEMF Vet Client\runtime\PEMF_Backend\PEMF_Backend.exe" --kurtarma --zarf <yedek>\kurtarma-zarfi.enc --kod <KOD> --yaz`
   Makinede zaten anahtar varsa araç **durur** (üzerine yazmak mevcut şifreli veriyi kalıcı kaybettirir);
   gerçekten taze kurulumsa `PEMF_KURTARMA_USTUNE_YAZ=1` ile zorla.
3. En yeni yedeği kopyala: `pemf_treatment_history_<tarih>.db` → `pemf_treatment_history.db`,
   `pemf_patients_<tarih>.db` → `patients.db`  ← ⚠️ hedef ad `patients.db`; uygulama
   `pemf_patients.db` adını **hiç açmaz** (yedek dosya ön-eki ile karıştırmayın)
   Operatör hesapları: `pemf_auth_users_<tarih>.db` şifreliyse
   `"%LOCALAPPDATA%\PEMF Vet Client\runtime\PEMF_Backend\PEMF_Backend.exe" --kurtarma --hesap-yedegi <yedek>\pemf_auth_users_<tarih>.db --cikti <data>\auth_users.db`
   (2. adımdan sonra; şifresiz kurulumda `auth_users.db` adıyla kopyalamak yeter). Ayarlar: `pemf_config_<tarih>.json` →
   `config.json`, `pemf_system_settings_<tarih>.json` → `system_settings.json` — SIRSIZDIR, MQTT kullanıcı/parola ve API
   anahtarını yeniden gir.
4. Backend'i başlat: launcher'ı aç (servis kurulumunda: servisi başlat).

**Kod kaybolursa** yedekler yalnız orijinal makinede açılır. Kod, kaybı geri alınamaz tek şeydir.

## Güvenli kapanış
**Sahada (launcher kipi):** launcher penceresi kapanınca launcher ÖNCE ACİL DURDUR ucunu çağırır (STM + ESP STOP;
yanıttan sonra seri kuyruğun boşalması için ~1,6 sn bekler), SONRA backend sürecini sonlandırır. Sonlandırma
sinyalsizdir: backend'in kendi kapanış adımları bu yolda KOŞMAZ — süren seans kaydı bir sonraki açılışta kesinti
olarak kapanır; mümkünse seansı önce bitirin. **Yalnız servis kurulumunda:** servis durdurulunca backend tüm bobinlere
STOP gönderir (STM kuyruğu boşalana kadar bekler + ESP MQTT stop) ve seansı "Kesintiye Uğradı" olarak kapatır.
**Her iki kipte** elle acil-durdur: `curl.exe -X POST http://127.0.0.1:8000/api/hardware/emergency_stop` (auth-muaf,
fail-safe; port `backend.port` — "Hızlı komutlar"daki tek satır onu okur; Windows PowerShell 5.1'de çıplak `curl` DÜŞER).

## Gözlemlenebilirlik
- Metrikler: `/metrics` (Prometheus scrape; LAN-muaf). Sağlık: `/api/health`.
- Uzak hata-izleme (opsiyonel): `PEMF_SENTRY_DSN` set → Sentry (PII-scrub). Varsayılan kapalı (KVKK).
