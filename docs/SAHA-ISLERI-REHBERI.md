# Saha İşleri Rehberi — sende kalan 8 iş

> **Bu belge bir İNDEKStir, ikinci kaynak değildir.** Derin adımlar kendi belgelerinde durur;
> burada **sıra**, **komut**, **kabul ölçütü** ve **tuzak** var. Bir çelişki görürsen bağlantı
> verilen belge doğrudur. (Depo dersi: belgeler sessizce bayatlıyor.)

**Önerilen sıra:** B-1 → B-2 → B-3 → B-4. Sebep: saha listesindeki (B-3) donanım senaryoları
reflash'lı cihaz ister, yoksa eski firmware'i test edersin. B-4 fiziksel, ne zaman olsa olur.

---

## B-1 · ESP32-S3 reflash  ⏱️ ~20 dk

**Neden:** crash-loop düzeltmesi ([FW-6]) kaynakta hazır, kartta değil.

⚠️ **Ayarlar bu arızanın sebebi DEĞİLDİ** — seninkiler zaten doğruydu ve restartlar yine
oluyordu. Sebep kodda, düzeltme de kodda; bu yüzden **tek çözüm reflash**.

**Ölçülmüş zincir** (`NetworkManager.cpp:531-551`, arduino-esp32 3.3.11 kaynağından):

```
NetworkTask ulaşılamayan bulut broker'ına TLS el sıkışmasında 120 sn BLOKE olur
        ↓  (bloke olduğu için statusQueue'yu boşaltamaz)
"[Warn] statusQueue dolu!"  ← senin gördüğün uyarı: SEBEP DEĞİL, BELİRTİ
        ↓
watchdog 10 sn içinde reset görmez  →  task_wdt: NetworkTask did not reset
        ↓
Aborting → Rebooting...
```

Tek bir TLS denemesi watchdog bütçesini **12 kat** aşıyordu. ⚠️ `setSocketTimeout` bu işi
görmez — o PubSubClient'in okuma zaman aşımıdır, altındaki TCP+TLS el sıkışmasını sınırlamaz.
Düzeltme iki katmanlı: önce **düz TCP yoklaması** (3 sn tavan, ölçüldü) — ulaşılamıyorsa TLS'e
hiç girilmez; girilirse el sıkışma **4 sn**'ye bağlı, her adımdan önce WDT besleniyor.

**Arduino IDE ayarları** — bunlar düzeltme değil, **bozmaman gerekenler**
(ölçülmüş, çekirdek 3.3.11 — `firmware/esps3_pemf_coil/README.md`):

| Ayar | Değer | Not |
|---|---|---|
| Board | **ESP32S3 Dev Module** | |
| **Partition Scheme** | **Minimal SPIFFS (1.9MB APP with OTA)** | ⚠️ **ZORUNLU.** Varsayılan 1,25 MB'a ikili (1,38 MB) **sığmaz**. Adında **"with OTA"** geçmeli — yoksa HTTPS OTA ölür |
| Flash Size | 16MB (128Mb) | N16R8'in gerçeği |
| PSRAM | Disabled | Firmware kullanmıyor (RAM %17) |
| Flash Mode | QIO 80MHz | |
| **Erase All Flash** | **Disabled** | ⚠️ Açarsan NVS'teki WiFi/provizyon **silinir**, kartı baştan kurarsın |

**Adımlar**
1. `firmware/esps3_pemf_coil/esps3_pemf_coil.ino` → Arduino IDE.
2. Kütüphaneler: WiFiManager (tzapu) · PubSubClient · ArduinoJson · Adafruit MLX90614 ·
   Adafruit MLX90393.
3. Kart takılı değilken **✓ Verify** ile derlemeyi doğrula (port istemez).
4. Kartı tak → **Upload**.

**Kabul ölçütü** — seri monitörde (115200):
- ✅ Açılışta **reboot döngüsü YOK**; 60 sn boyunca tek açılış satırı.
- ✅ Bulut erişilemezken bile `Rebooting` **yok** — artık önce düz TCP ile erişilebilirlik
  yoklanıyor, TLS el sıkışma 4 sn'ye sınırlı ve denemeler arasında WDT besleniyor.
- ⚠️ `[MagChk] ilk-bosta-pencere |B|=0.589 mT` satırını göreceksin. Bu **hata değil**: sensörün
  yanında sabit bir DC alan var (demir/mıknatıs). B-2'deki kalibrasyonu neden tepeden-tepeye
  yapman gerektiğinin sebebi tam olarak budur.

---

## B-2 · STM32 reflash + doz kalibrasyonu  ⏱️ ~2-3 saat (asıl iş kalibrasyon)

**Tam prosedür: [`docs/VERIFICATION.md` §16](VERIFICATION.md).** Burada yalnız özet + tuzaklar.

**Neden zorunlu:** sürüş dalgası asimetrik DC-bias'lıdan **simetrik bipolara** çevrildi. Aynı
`duty` artık **farklı alan** üretiyor → sahadaki doz eğrisi **kalibre değil**. Reflash
yapmazsan eski firmware koşar; reflash yapıp kalibre etmezsen ekrandaki mT ile gerçek alan ayrışır.

**1) Yakılabilir çıktı — CubeIDE'yi AÇMA**

```powershell
python scripts\firmware_derle.py --stm --cikti firmware_cikti
```

⚠️ CubeIDE'de **"Generate Code" `main.c`i EZER**. Bu yüzden IDE'yi hiç açma, depodan üretilen
ikiliyi yak. Betik `_printf_float` bağını da doğrular — bağlı değilse **tüm telemetri sessizce
ölür** (sıcaklık + alan + akım hepsi boş gelir, ama ACK tamsayı olduğu için cihaz sağlam görünür).

**2) Yakma (STM32CubeProgrammer):** ST-LINK → Connect → Erase & Program → `pemf.bin`,
adres **`0x08000000`**, **"Verify programming" işaretli** → Start → Disconnect → **güç döngüsü**.
Betiğin bastığı **SHA256**'yı `VERIFICATION.md`e yaz — "sahadaki cihazda depodaki kaynak mı
koşuyor" sorusunun tek kanıtı budur.

**3) Kalibrasyondan ÖNCE telemetri kapısı**
- Backend'i **simülatörsüz** çalıştır (`PEMF_SIMULATE` tanımlı olmasın).
- `GET /api/coil/7` → `transport` = **`stm32`** olmalı.
- Bobin 1'i 5 sn sür, gelen `STM_TELE` satırında `B=`, `T=`, `I=` **sayılı** olmalı.
- ⚠️ Boşsa (`B=,T=,A=,I=`) **kalibrasyona başlama** — ölçeceğin her şey sıfır olur.

**4) Doz eğrisi — ⚠️ TEPEDEN-TEPEYE, `measuredPeakMt` DEĞİL**

`measuredPeakMt` seans boyu en büyük **|B|**'dir: işaretsiz olduğu için unipolar (0→+B) ile
bipoları (−B→+B) **aynı gösterir**, üstelik yukarıdaki 0,589 mT'lik DC ofset onu doğrudan saptırır.

Doğrusu işaretli uçlardan türer ve ofset farkta sadeleşir:

```
pp_x = XP − XN      pp_y = YP − YN      pp_z = ZP − ZN
```

Her bobin (1-7) için `freq = 10 Hz`, prob bobin merkezinde ve **sabit mesafede**,
duty = 10 / 25 / 50 / 75 / 90 → tabloyu `VERIFICATION.md` §16.3'e doldur.

⚠️ Aralık ±24,6 mT'ye açıldı; eski ayar 4,92 mT'de **sessizce sarıyordu** (tespit edilemezdi).
Ham eksen uçlarının sarmadığını da kontrol et.

---

## B-3 · 164 senaryoluk saha listesi  ⏱️ dağıtılabilir

**Liste: [`docs/SAHA-TEST-LISTESI.md`](SAHA-TEST-LISTESI.md)** · 8 kademe.
Telefonda okumak için HTML sürümü:

```powershell
python scripts\saha_test_html_uret.py
```

→ `docs/saha-test-listesi.html` (MD ile senkron; ayrışırsa kapı kırmızı olur).

| Kademe | Konu | Ne zaman |
|---|---|---|
| 1 | Hasta güvenliği | **Her turda, istisnasız** |
| 2 | Güncelleme ve kurulum | En taze kod = en yüksek risk |
| 3 | Ağ ve bağlantı | Klinik gerçeği |
| 4 | Veri, AI, yetki | |
| 5 | Dayanıklılık | Sürüm turlarında |
| **6** | **MOBİL** | ⚠️ **En az bakılan katman — buraya öncelik ver** |
| 7 | Bu turun değişiklikleri | Bir kez tamamen koş |
| 8 | Bilinen açıklar | Bunlar "bulgu" değil, **doğrulanmış davranış** olmalı |

**Sıra önerisi:** Kademe 1 → 7 → 6 → gerisi. (1 güvenlik, 7 bu turda değişenler, 6 kör nokta.)

Bulguları listenin sonundaki **Bulgu kaydı** bölümüne yaz — senaryo no + ne bekledin + ne oldu.

---

## B-4 · Vault kurtarma setini makine dışına al  ⏱️ ~10 dk

**Neden:** emanetin **tek** anlamı bu. Şu an token, unseal anahtarları ve şifreli veri **aynı
makinede** — disk giderse üçü birden gider ve emanet hiçbir işe yaramaz.

```powershell
docker run --rm -v pemf-vault-veri:/veri -v "${PWD}:/cikti" alpine `
  tar czf /cikti/pemf-vault-veri.tgz -C /veri .
```

**Tam set üç parçadır:**
1. `pemf-vault-veri.tgz` (yukarıdaki çıktı)
2. `pemf-vault-kurtarma.json` (unseal anahtarları)
3. Kurtarma token'ı — `hvs.` ile başlar, **yalnız sende**. ⚠️ Değerini (kısaltılmışını bile)
   hiçbir belgeye, commit'e ya da sohbete yazma; depo PUBLIC.

⚠️ **Üçünü aynı diskte tutma.** En az biri farklı fiziksel ortamda olsun (USB + kasa, ya da
şifreli bulut). Token salt-okunurdur ve yalnız `pemf/data/klinik/hasta-anahtari` yolunu açar —
Vault'un geri kalanına erişemez, yazamaz, silemez (ölçüldü).

Detay + disk kaybı sonrası kurtarma adımları: [`docs/VAULT-ANAHTAR-EMANETI.md`](VAULT-ANAHTAR-EMANETI.md) §3.

---

## B-5 · Cloudflare NAMED tünel  ⏱️ ~20 dk (alan adı hazırsa)

### Önce: şu an ne çalışıyor (2026-09-14 ölçümü)

| Ne | Durum |
|---|---|
| `cloudflared` ikilisi | ✅ **Pakette gömülü** (54 MB) — indirme yok, internetsiz kurulumda da çalışır |
| `PEMF_ENABLE_TUNNEL` | ✅ launcher varsayılanı **`1`** → tünel zaten **AÇIK** |
| `operator.cloudflare_tunnel_token` | ⚠️ anahtar var, **değeri BOŞ** |
| `operator.tunnel_hostname` | ⚠️ anahtar var, **değeri BOŞ** |
| Beklenen sonuç | Launcher'dan açtığında **QUICK tünel**: `https://<rastgele>.trycloudflare.com` |

> ⚠️ Son satır **çıkarım**, ölçüm değil: kaynak + varsayılanlar bunu söylüyor ama canlı
> doğrulamadım. Doğrulamak için tüneli elle açmam gerekirdi; auth zorlaması **launcher
> tarafında** olduğu için elle açılan backend kimliksiz hâlde internete çıkardı — yapmadım.
> **Sen launcher'dan açıp `/api/health` → `tunnelUrl`e bakınca bir saniyede görürsün.**
>
> Dolu geliyorsa uzaktan erişim **zaten var**. NAMED'in getirdiği tek fark **sabit hostname**: QUICK
> tünelde URL **her açılışta değişir**, SLA yoktur. Klinikte telefona sabit bir adres vermek
> istiyorsan NAMED gerekir.
>
> ℹ️ Tünel açıkken launcher `PEMF_REQUIRE_AUTH=1`i **zorlar** (fail-closed) — internete açık
> bir uçta kimliksiz hasta/donanım erişimi mümkün değildir.

### ⚠️ Ön koşul: Cloudflare'de bir alan adın olmalı

NAMED tünel **kendi alan adını ister**. Alan adı nerede kayıtlı olursa olsun,
**nameserver'ları Cloudflare'e yönlendirilmiş** olmalı (Cloudflare hesabı ücretsiz).
Alan adın yoksa bu iş burada durur — o durumda QUICK tünelle devam et, kayıp yalnız
"URL değişiyor"dur.

### Adımlar

**1) Alan adını Cloudflare'e ekle** (zaten ekliyse atla)
`dash.cloudflare.com` → **Add a site** → alan adını gir → ücretsiz plan →
sana verdiği **2 nameserver**'ı alan adını aldığın yerde (GoDaddy/Natro/vb.) yaz.
Yayılma 5 dk – 24 saat. Site "Active" olunca devam.

**2) Tüneli oluştur**
`one.dash.cloudflare.com` (Zero Trust) → **Networks → Tunnels → Create a tunnel** →
**Cloudflared** seç → bir ad ver (ör. `pemf-klinik`) → **Save**.

**3) Token'ı al**
Aynı ekranda "Install and run a connector" çıkar. Windows sekmesindeki komutun içinde
`--token` sonrası uzun bir dize vardır:

```
cloudflared.exe service install eyJhIjoiXXXXXXXX...................
                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                BANA LAZIM OLAN SADECE BU KISIM
```

⚠️ **Komutu ÇALIŞTIRMA** — `service install` cloudflared'ı ayrı bir Windows servisi olarak
kurar; bizim backend tüneli kendisi başlatıyor, ikisi çakışır. Sadece **token'ı kopyala**.

Token nasıl görünmeli: `eyJ` ile başlar, **~180+ karakter**. ⚠️ Koddaki koruma 40 karakterden
kısa token'ı **yok sayar** ve sessizce QUICK tünele düşer (eski bir test artığı `"1"` yüzünden
eklendi — tünel URL'si NULL kalıyor ve uzaktan erişim çalışmıyordu).

**4) Public hostname'i bağla**
Tünel ekranında **Public Hostname → Add a public hostname**:

| Alan | Değer |
|---|---|
| Subdomain | ör. `klinik` |
| Domain | senin alan adın |
| Type | **HTTP** |
| URL | **`localhost:8000`** |

Sonuç: `klinik.senindomain.com`. **`tunnel_hostname` budur.**

**5) Bana ver, yazayım**
Token + hostname'i ilet; sır dosyasına yazarım. ⚠️ Depoya **girmez**, `pemf_secrets.json`
`operator` bölümüne DPAPI ile şifrelenmiş yazılır (makineye bağlı).

⚠️ **İKİSİ DE ŞART.** Token varken hostname boşsa kod, sabit URL'yi bilemediği için
`tunnelUrl`i **boş bırakır** — yarım yapılandırma QUICK tünelden daha kötüdür.

### Kabul ölçütü

Launcher'ı **kapat-aç** → sonra:

```powershell
curl http://127.0.0.1:8000/api/health
```

→ `tunnelUrl` = **`https://klinik.senindomain.com`** (trycloudflare **değil**).

⚠️ **Bu ölçümü elle başlattığın backend'de YAPMA.** Ben tam bu tuzağa düştüm ve "tünel yok"
diye yanlış rapor verdim — elle açılan backend launcher'ın ortamını almıyor. **Launcher'dan aç.**

---

## B-6 · Firmware güvenlik satürasyonu (tezgâh)  ⏱️ tezgâh

Bobin sürücüsünün doyum/ısınma davranışının ölçümü. B-2'deki doz eğrisiyle **aynı oturumda**
yapılabilir: aynı prob, aynı düzenek, yalnız süre uzun ve duty yüksek.

⚠️ **Termal kesme firmware'de YOK — senin kararındı.** Yani bu testte cihazı kendi kendine
korumasını bekleme; süreyi sen sınırla ve sıcaklığı `STM_TELE`'deki `T=` alanından izle.

---

## B-7 · 72 saatlik klinik soak  ⏱️ 3 gün (pasif)

```powershell
python scripts\soak_http_ws.py --port 8000 --dakika 4320 --aralik 60
```

Betik **bobin sürmez** — HTTP + WebSocket yollarını zorlar, RSS'i izler.

⚠️ Okuma tuzakları (ikisi de yaşandı):
- **AI ısınması sızıntı DEĞİL.** Health-200 anında RSS ~254 MB; AI ısınınca ~2310 MB'a çıkar
  (+%809). Betik artık RSS'in oturmasını bekliyor, ama erken bakarsan yanlış alarm verirsin.
- **İki backend açıksa RSS toplanır.** 4106 MB'lık korku tam olarak buydu. Betik artık süreç
  sayısını uyarıyor — uyarı çıkarsa önce onu çöz.

25 dakikalık koşu zaten yapıldı ve temizdi; kalan tek şey **süre**.

---

## B-8 · iOS / EAS  ⛔ BLOKE

Apple geliştirici sözleşmesi + EAS bulut koşusu gerekiyor. Yalnız EAS üzerinden derleniyor
(yerel derleme yok). Senin hariç tuttuğun C5 ile aynı blokta — sözleşme tamamlanana kadar
yapılabilecek bir şey yok.

---

## Yaparken aklında tutulacak üç şey

1. **Ölçümü doğru koşulda yap.** Launcher'dan açılan backend ile elle açtığın backend **farklı
   dünyalardır** (veri kökü, şifreleme, tünel, jeton bayrağı). Bu tuzağa bu depoda defalarca
   düşüldü — bir kez de ben düştüm ve "SQLCipher kapalı" diye yanlış rapor verdim.
2. **"Belgede öyle yazıyor" kanıt değil.** Durum satırları bayatlıyor; ölç.
3. **Bulguyu yaz, yorumlama.** Ne bekledin / ne oldu / hangi ekran. Teşhisi bana bırak.
