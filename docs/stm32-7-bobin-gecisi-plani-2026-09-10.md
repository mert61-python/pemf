# ESP'leri Devre Dışı Bırak → 7 Bobinin Tamamını STM32'den Sür

**Tarih:** 2026-09-10 · **Sahip kararı:** ESP bobinleri (6-8) kaldırılacak; bobin 6 ve 7 STM32F429ZI
tarafından sürülecek; manyetik + sıcaklık sensörleri de STM'e bağlanacak.
**Durum:** ANALİZ + PLAN. Kod yazılmadı, pin bağlanmadı. Sahip onayı bekliyor.

Bu belge, depodaki gerçek kaynak okunarak yazıldı. Her sayı ya kaynak dosyada işaretli ya da
"TAHMİN/ÖLÇÜLMELİ" olarak etiketli. Tahminleri gerçek gibi sunmuyorum.

---

## 0. En önemli üç bulgu (önce bunları oku)

### B1 — "2 ekstra PWM kanalı" diye bir ihtiyaç YOK

STM32 firmware'i **donanım PWM kanalı kullanmıyor.** TIM1 yalnızca 50 kHz *update interrupt*
kaynağıdır; bobin çıkışları o kesmenin içinde **yazılımsal DDS** ile doğrudan `GPIO->BSRR`
yazılarak üretilir:

```
main.c:958-966   "TIM1 yalnızca 50kHz kesme üretir (PWM kanalı KULLANILMAZ) · TIM8 tamamen kaldırıldı"
main.c:1307      for (i = 0; i < NUM_COILS; i++) { ... coil_gpio[i].portA->BSRR = ... }
```

Sonuç: bobin 6 ve 7 için **timer kanalı, timer çakışması, AF eşleme derdi yoktur.** Gereken tek
şey **iki adet boş GPIO pini** + `NUM_COILS` 5→7 + `coil_gpio[]` dizisine iki satır. Bu, işin
*kolay* tarafı. Zor taraf protokol ve sensör (aşağıda).

Bonus kazanç: STM DDS'i bobin başına **bağımsız faz** taşır (çözünürlük 360°/500 = 0,72°).
8266 ise sahip kararıyla **tek faz** sürülüyor ve donanım senkronunu hiç kullanmıyor
(`CoilController.cpp:63-75, 182-184`). Yani bobin 6-7 STM'e geçince kabin içi alan
süperpozisyonu için **fazlanabilir hale gelirler** — bu bir yetenek kazancıdır, kayıp değil.

### B2 — ⚠️ P0 GÜVENLİK: bobin 6-7 termal korumasız kalır

Bugün bobin 6-8'i aşırı ısınmada durduran **tek** mekanizma 8266'nın kendi yerel kilidi
(`SharedDefs.h:109`, sahip kararıyla dün 100 °C yapıldı). Zincirin geri kalanı:

| Katman | Sıcaklık limiti |
|---|---|
| Backend (`servers/`) | **YOK** — ölçüldü; safety-limit bilinçli kaldırılmıştı |
| STM32 firmware | `PEMF_NTC_TERMAL_ENABLED 0` → **derlenmiyor** (`main.c:626`), NTC'ler fiziksel bağlı değil |
| ESP8266 | 100 °C kesme + 97 °C histerezis — **çalışan tek katman** |

ESP'yi çıkarıp STM'e sıcaklık okuma + kesme **eklemeden** geçiş yapılırsa bobin 6-7 için
sistemde hiçbir termal kesme kalmaz. Bu, geçişin en kritik ön koşuludur ve tezgâhta
doğrulanmadan sahaya çıkmamalıdır.

Ayrıca bir **eşik kararı** gerekiyor: STM'in NTC bloğunda `NTC_KESME_C 48.0f` yazıyor
(`main.c:629`), sahip ise 8266 için 100 °C dedi. Bobin 6-7 STM'e taşınırken hangi eşik
geçerli olacak? Sessizce 48'e dönmek, dünkü kararı iptal eder.

### B3 — ⚠️ `.ioc` firmware'i TARİF ETMİYOR; CubeMX "Generate Code" bu işi bozar

`PEMF_UNIPOLAR.ioc` ile `main.c` **ayrışmış** durumda:

* `.ioc`, **PA8 = USB_OTG_FS_SOF** ve **PA9 = USB_OTG_FS_VBUS** diyor. `main.c` ise aynı iki pini
  **bobin 5'in IN_A/IN_B'si** olarak sürüyor (`main.c:333-335`). Doğrudan çakışma.
* Bobin pinlerinin **9'u** (`PC6 PC7 PC8 PC9 PD10 PD11 PD12 PE10 PB1`) `.ioc`'de **hiç yok**.
* `.ioc`, `TIM1 CH1-4`'ü `PE9/PE11/PE13/PE14`'e atıyor — firmware bu kanalları **kullanmıyor**
  (v1.x mimarisinden kalma artık).

Bu, geçişin en büyük **prosedürel** riski: I2C eklemenin doğal yolu "CubeMX'i aç, I2C1'i etkinleştir,
Generate Code" demektir. O tuşa basıldığı anda `MX_GPIO_Init` ve `main.c` yeniden üretilir →
elle yazılmış bobin GPIO kurulumu ve DDS kodu **silinir**, PA8/PA9 USB'ye döner.
Hafızadaki kayıt bunu zaten söylüyor: *"CubeMX Generate-Code main.c EZER"*.

**Karar:** I2C ve yeni GPIO'lar **elle** (register/HAL init fonksiyonu yazarak) eklenecek,
`Coil_GpioInit` desenini izleyerek. CubeMX'e dokunulmayacak. `.ioc` ayrışması ayrı bir temizlik
işi olarak ele alınmalı (ya `.ioc` gerçeğe hizalanır ya da "bu dosya firmware'i tarif etmez"
uyarısı dosyanın başına yazılır).

---

## 1. Mevcut durum (ölçülmüş)

### 1.1 Bobin topolojisi

| Bobin | Sürücü | Pin / yol | Sensör |
|---|---|---|---|
| 1 | STM32 | PD12 (PWM) · PC8 LOW | yok |
| 2 | STM32 | PE10 (PWM) · PC9 LOW | yok |
| 3 | STM32 | PD10 (PWM) · PD11 LOW | yok |
| 4 | STM32 | PC6 (PWM) · PC7 LOW | yok |
| 5 | STM32 | PA8 (PWM) · PA9 LOW | yok |
| 6 | ESP8266 | GPIO D5, MQTT/WiFi | MLX90614 + MLX90393 + ACS712 |
| 7 | ESP8266 | GPIO D5, MQTT/WiFi | MLX90614 + MLX90393 + ACS712 |
| 8 | (slot) | ESP_COIL_IDS'de var, fiziksel bobin YOK | — |

Fiziksel kabin: 2 alt + 2 üst + sağ duvar + sol duvar + arka kapak = **7 bobin**.
Backend 8 slot tutuyor (`live_state.py:142`), 8. slot boş.

### 1.2 ⚠️ Gerçek sensör verisinin TEK kaynağı ESP'ler

`STM_COIL_IDS` (1-5) için sıcaklık/alan/akım telemetrisi **hiç yoktur**. Seri protokol yalnız
duty/phase/freq/duration döndürür ve `api_server.py:3283-3289` bunu açıkça yazıyor. `_live_state`
başlangıç değeri `0.0` olduğu için bu bir zamanlar DB'ye "0.0 °C ölçüldü" diye yazılıyordu; şimdi
`_coil_last_telemetry` kapısı (`api_server.py:3291`) telemetri gelmeyen bobin için **hiç satır
üretmiyor**.

Bunun sonucu net: **ESP'ler kapanırsa, STM'e sensör eklenmedikçe sistemde tek bir gerçek ölçüm
kalmaz.** Etkilenen alt sistemler:

* Canlı E-alanı barı — `efield_live.py:101` çalışan bobinlerin `magneticMt` ortalamasını alıyor
* Tedavi geçmişi / PDF raporu / KPI — dakika ortalamaları (`_emit_minute_averages`)
* `CoilParameterPanel` sıcaklık göstergesi ve termal dürüstlük uyarıları
* `test_mt_dose_honesty.py` kapısının konusu olan doz dürüstlüğü

Yani "sensörler de STM'e bağlanacak" kararı **isteğe bağlı bir ek değil, geçişin zorunlu parçası.**

### 1.3 Protokol

**PC → STM (komut):** `BinaryCmdPacket_t`, `#pragma pack(1)`, **88 bayt**, 5 bobin sabit.

```
0xAA 0x55 | float duty[5] | float phase[5] | float freq[5] | uint32 duration[5] | uint16 ref_ms | uint32 crc32
   2      +      20        +      20       +      20       +        20          +      2       +      4     = 88
```

Üç yerde ayrı ayrı yazılı ve bir kapı üçünü eşliyor:

| Yer | İçerik |
|---|---|
| `firmware/.../main.c:212, 273-279` | `#define NUM_COILS 5`, struct |
| `controllers/hardware_controller.py:363` | `fmt = '<BB 5f 5f 5f 5I H'` |
| `tools/stm32_simulator.py:72-76` | `PKT_FMT`, `assert PKT_SIZE == 88`, `NUM_COILS = 5` |
| `utils/stm32_transport.py:59` | `fmt = "<BB 5f 5f 5f 5I H"` (ping/stop paketi) |
| **kapı** `tests/test_stm32_source_parity.py:92-144` | üç kaynağı eşler, 88'i pinler |

**STM → PC (ACK):** ASCII satır. `main.c:867-880` içinde format dizesi **beş `%d`** olarak elle
yazılı; tampon `static char ack_msg[256]`. Backend ayrıştırıcısı (`headless_core._parse_stm_ok`)
virgülle ayırıyor ve **uzunluktan bağımsız** — yalnız `STM_COIL_COUNT = 5` sabitiyle kırpıyor
(`headless_core.py:28, 171`). Yani backend tarafı tek sabitle 7'ye çıkar; firmware tarafındaki
format dizesi ise elle genişletilmeli.

### 1.4 ESP yolunun taşıdığı yük (kalkacak olan)

ESP bobinleri şu altyapıyı zorunlu kılıyor: Windows Mobile Hotspot (`PEMF-Gateway`, logon
Scheduled Task, oturum gerektirir), mosquitto broker, MQTT konuları, `_esp_telemetry_watchdog`
(30 s bayatlık + STOP yayını), LWT/`offline` olayı → `coil_status` yayını (dün düzeltildi),
komut ACK eşleştirme (`command_id`), bulut broker'a E-stop aynası, portal/STA kilidi mantığı,
mDNS çok-homed sorunu.

---

## 2. Önerilen pin planı

⚠️ Aşağıdaki MCU pin/AF bilgileri veri sayfasından; **ZIO/CN başlık konumlarını UM1974'ten teyit
et** — kabloyu bağlamadan önce.

### 2.1 Bobin 6 ve 7 PWM çıkışları

Unipolar kip bobin başına **tek** pin sürüyor, ama simetri ve ileride bipolar denemesi için
`coil_gpio[]` her bobin için A+B ister. Öneri, **GPIOE** bloğundan (saat zaten açık,
`Coil_GpioInit:1561` → `__HAL_RCC_GPIOE_CLK_ENABLE()`; ayrıca PE10 hâlihazırda bobin 2 için
kullanıldığından bu blok başlıklara **çıkıyor** — kanıtlı):

| Bobin | IN_A | IN_B | Not |
|---|---|---|---|
| 6 | **PE9** | **PE11** | `.ioc`'de bayat `TIM1_CH1/CH2` ataması var, firmware kullanmıyor |
| 7 | **PE13** | **PE14** | `.ioc`'de bayat `TIM1_CH3/CH4` |

Bunları seçmemin sebebi: Arduino başlığında **PWM etiketli** pinler (D6/D5/D3/D2 — teyit et),
dördü bitişik, aynı port, ve seçimleri `.ioc`'deki artık TIM1 kanal atamasının **silinmesini
zorunlu kılıyor** ki bu zaten yapılması gereken temizlik.

**Yedek set** (birincisi başlıkta çıkmıyorsa): PE7 / PE8 / PE12 / PE15.

Unipolar kipte darbelenecek bacak `PEMF_BOBIN_TERS_MASKESI` ile seçilir; bobin 6-7'nin sargı
yönü **tezgâhta ölçülmeden** maske biti belirlenemez (bkz. §6).

### 2.2 I2C — sensörler

`.ioc`'de I2C **hiç yapılandırılmamış**; sıfırdan eklenecek. F429 üç I2C taşıyor ama:

| Bus | SCL / SDA (AF4) | Durum |
|---|---|---|
| **I2C1** | **PB8 / PB9** | ✅ boş; GPIOB saati açık. (PB6/PB7 alternatifi kullanılamaz: PB7 = LD2 mavi LED) |
| **I2C2** | **PB10 / PB11** | ✅ boş; GPIOB saati açık. (PF0/PF1 alternatifi `GPIOF` saati eklemeyi gerektirir) |
| I2C3 | PA8 / PC9 | ❌ **KULLANILAMAZ** — PA8 bobin 5, PC9 bobin 2 |

İki temiz bus var. Bu, MLX90614'ün adres problemini doğrudan çözüyor (§3).

### 2.3 ACS712 akım sensörleri (bobin 6-7)

`main.c:614` NTC için beş ADC pini **ayırmış**: PA0, PA3, PA4, PC0, PC3 — ama NTC'ler hiç
bağlanmadı ve blok `PEMF_NTC_TERMAL_ENABLED 0` ile derlenmiyor.

Sıcaklık MLX90614 (I2C) ile okunacaksa **NTC yolu terk edilir** ve bu beş ADC pini serbest
kalır → ACS712'ler için fazlasıyla yeter. Terk edilmezse yeni pin gerekir: PC2 (ADC1_IN12),
PA6 (ADC1_IN6).

⚠️ Bu bir **karar** noktası: NTC bloğu ile MLX90614 aynı kesmenin iki farklı gerçeklenmesi.
İkisini birden bırakmak, iki farklı eşikle çelişen iki kesme demektir. Biri seçilmeli.
(NTC bloğu belgelenmiş bir açık P0'dır — silmeden önce kararın yazılı olması lazım.)

---

## 3. Sensör mimarisi — burada iki gerçek engel var

### 3.1 MLX90614 adresi SABİT 0x5A

Her MLX90614 fabrikadan 0x5A ile çıkar. Aynı bus'ta iki tanesi **çalışmaz**. Seçenekler:

| Yol | Kaç sıcaklık sensörü | Maliyet / risk |
|---|---|---|
| **A. İki ayrı bus** (I2C1 + I2C2) | **2** — tam olarak bobin 6-7 için yeterli | ✅ ek donanım yok, en basit |
| B. EEPROM'dan adres değiştir | 7 | MLX90614 SMBus adresi EEPROM'da; tek seferlik programlama, geri dönüşü zahmetli, yanlış yazım sensörü tuğlalaştırır |
| **C. TCA9548A 8-kanal mux** | **7** (kanal başına 1 bobin) | tek çip; 7 bobinin hepsine ölçüm istiyorsan **tek ölçeklenen yol** |

MLX90393 bu sorunu yaşamıyor: A0/A1 straplarıyla 0x0C-0x0F, yani bir bus'ta **4 tane**.

**Öneri:** kapsam bobin 6-7 ise **A** (iki bus, ek çip yok). Kapsam 7 bobinin hepsi ise **C**
(mux) — ve bu durumda I2C2 boş kalır, yedek olur.

### 3.2 ⚠️ I2C uzun kablo sevmez — bu geçişin gizli riski

Bugün sensörler ESP'nin **üstünde**, bobinin **yanında**: I2C hattı birkaç santim. STM'e taşınınca
aynı hat, PWM'lenen bobinlerin içinden geçen **65×50×50 cm** kabin boyunca uzayacak. MLX90393 alanı
ölçtüğü için **bobinin yanında kalmak zorunda** — kablo kaçınılmaz.

I2C açık-drenaj + pull-up'tır; kablo kapasitansı kenarları yuvarlar, bobin anahtarlaması hatta
gürültü kuple eder. Sonuç NACK, kilitlenmiş bus, bozuk okuma olur. Karşı önlemler:

* Bus hızını **100 kHz**'de tut (400 kHz'e çıkma)
* Pull-up'ları güçlendir (4,7k → **2,2k**), toplam kapasitansı 400 pF altında tut
* SDA/SCL'i **birlikte bükülmüş + ekranlı** çek, ekranı tek noktadan topraklat; güç kablolarından ayır
* Gerekirse **I2C bus tamponu** (P82B715 / PCA9600) — mesafeyi güvenle metrelere çıkarır
* Firmware'de **bus kurtarma** şart. 8266 bunu zaten yapıyor (`SensorManager._clearI2CBus`,
  `_isI2CBusStuck`, `_hardResetI2C`) — o mantık STM'e **taşınmalı**, sıfırdan yazılmamalı.
* Okuma **bloklamayan durum makinesi** olmalı. 8266'daki `MLX90614State` / `MLX90393State`
  deseni birebir uygun; kör bir `HAL_I2C_Mem_Read` çağrısı ana döngüyü ms'ler boyunca tutar.

⚠️ Bu, tezgâhta ölçülmeden "çalışır" denemeyecek tek kalem. Kabloyu gerçek uzunlukta çekip
bobinler **sürülürken** okuma yapılmalı; boş kabinde alınan temiz okuma kanıt değildir.

### 3.3 Sensör verisini backend'e taşıyacak yol YOK — yeni protokol gerekiyor

STM'in yukarı yönlü tek kanalı ASCII ACK satırı: `STM_READY`, `STM_OK: D=..P=..F=..T=..`,
`STM_NACK`. **Sıcaklık/alan/akım için alan yok.** Yani sensör eklemek, aynı zamanda yeni bir
telemetri çerçevesi demek:

1. Firmware: yeni satır, ör. `-> STM_TELE: C=<id>,T=<obj>,A=<amb>,B=<mT>,I=<A>` (bobin başına,
   ~1 Hz). ASCII kalması akıllıca — mevcut satır-tabanlı okuyucu ve `readline()` yolu değişmez.
2. `headless_core`: ayrıştırıcı + `hardware.stm.telemetry` olayı.
3. `api_server`: olayı `_live_state["coils"][idx]`'e yaz **ve** `_coil_last_telemetry[idx]`'i
   damgala — aksi halde DB kaydı yine üretilmez (`api_server.py:3291` kapısı).
4. `coil_status` + `sensor_data` WS yayınları (ESP yolundaki ile **aynı sözleşme**; istemci
   tarafında hiçbir şey değişmez).

Bu tasarım bilinçli: istemci ve DB, verinin ESP'den mi STM'den mi geldiğini **bilmesin**.

---

## 4. Değişecek dosyalar — atomik gruplar

### Grup A — Firmware protokolü (88 → 120 bayt), tek commit'te

`2 + 7·4·3 + 7·4 + 2 + 4 = **120 bayt**`

| Dosya | Değişiklik |
|---|---|
| `firmware/stm32_pemf/Core/Src/main.c` | `NUM_COILS 5→7`; `coil_gpio[]` +2 satır; başlık pin haritası; `Coil_GpioInit` GPIOE pinleri; ACK format dizesi (aş. uyarı); `STM_READY` metni "5-ch"→"7-ch"; `g_*[NUM_COILS]` initializer'ları (`{0,0,0,0,0}` → 7 eleman — **derleyici bunu sessizce kabul eder**, elle sayılmalı) |
| `firmware/stm32_pemf_unipolar/` | **elle düzenlenmez** → `python scripts/stm_unipolar_senkronla.py` |
| `Core/Inc/pemf_surus.h` | pin durumu bloğu + `PEMF_BOBIN_TERS_MASKESI` (bobin 6-7 bitleri tezgâh ölçümünden sonra) |
| `controllers/hardware_controller.py` | `fmt` → `'<BB 7f 7f 7f 7I H'`; `range(1, 6)` → `range(1, 8)` (**8 yer**: 48, 63, 103, 116, 261, 275, 299, 328) ve `coil_id > 5` → `> 7` (140) |
| `utils/stm32_transport.py:58-72` | ping/stop paketi `7f`; docstring |
| `tools/stm32_simulator.py:66-76` | `PKT_FMT`, `assert PKT_SIZE == 120`, `NUM_COILS = 7` |
| `headless_core.py:28` | `STM_COIL_COUNT = 5 → 7` (ayrıştırıcı zaten uzunluktan bağımsız) |

⚠️ **ACK format dizesi sürüklenme tuzağı.** `main.c:867` beş `%d` elle yazılı. Yediye çıkarken
aynı sınıf hatayı (dünkü termal mesajı, 480↔640 status buffer'ı) tekrar üretmemek için format
dizesi **döngüyle** kurulmalı ki `NUM_COILS` değiştiğinde metin kendiliğinden takip etsin.
Tampon hesabı: 7 bobin en kötü durumda ~199 bayt; `ack_msg[256]` yetiyor ama pay 2×'ten 1,3×'e
düşüyor. `snprintf` kesme koruması zaten var (`main.c:886-891`) — kaldırılmamalı.

### Grup B — Backend topolojisi

**Öneri: dizi boyutlarına DOKUNMA, yalnız kümeleri değiştir.**

```python
# servers/live_state.py:167-168
STM_COIL_IDS = set(range(1, 8))   # 1-7
ESP_COIL_IDS = set()              # ESP yolu uykuda
```

`live_state.py:175` `range(5)` → `range(7)` ve `"stm32Driven": i < 5` → `i < 7`.
`range(8)` geçen **9 yer** (WS anlık görüntüsü, E-stop, sim döngüsü, session_router) **aynı
kalır** → WS sözleşmesi bozulmaz, 8. slot `connected=False` olarak sessiz durur, ~50 ESP/MQTT
test dosyasının çoğu yeşil kalır. Bu, en az yıkıcı yol.

`ESP_COIL_IDS` boşalınca kendiliğinden no-op olanlar: `_esp_telemetry_watchdog`, E-stop ESP
havuzu, MQTT selftest, ESP komut yolu. **Silmiyoruz — uykuya alıyoruz.** Geri dönüş bir satır.

### Grup C — Frontend

`ControlScreen.tsx:632-681`: "🔌 STM32 Bobinler (1–5)" / "📶 WiFi ESP Bobinler (6–8)" ayrımı
kalkar → tek grup, `c.id <= 7`. `CoilCard.tsx:17` (`coil.id <= 5`) ve `mockData.ts:47`
(`index < 5`) güncellenir. `stm32Driven` sözleşmesi değişmez; `stmConnected` artık 7 bobinin
hepsini kapılar.

### Grup D — Kapılar (yeni/güncellenecek testler)

| Kapı | Ne pinleyecek |
|---|---|
| `test_stm32_source_parity.py` | 88 → **120**; `NUM_COILS` üç kaynakta 7 |
| YENİ `test_stm_bobin_sayisi_tek_kaynak.py` | firmware initializer'larındaki eleman sayısı == `NUM_COILS` (eksik initializer sessizce sıfırlanır — **derleyici uyarmaz**) |
| YENİ `test_stm_ack_formati_turetilmis.py` | ACK format dizesinde **sabit sayıda `%d` grubu OLMASIN** (termal mesaj kapısının aynı sınıfı) |
| YENİ `test_stm_termal_kesme_zorunlu.py` | 7 bobinin **hepsi** için derlenen bir termal kesme var; eşik sabitten türetiliyor |
| YENİ `test_bobin_topolojisi.py` | `STM_COIL_IDS ∪ ESP_COIL_IDS` çakışmasız; hiçbir bobin iki yoldan sürülmüyor; 8. slot `connected=False` |
| `test_esp8266_termal_esik.py` | ESP yolu uykuya alınırsa kapı **BAYAT** olur → koşulu güncelle, sessizce yeşile bırakma |
| `test_stm_unipolar_ayna.py` | ayna senkronu (elle düzenleme yasağı) |

Ayrıca: 284 test dosyasından **50'si** ESP/MQTT'ye, **19'u** STM sabitlerine dokunuyor. Geçişten
sonra **tam süit** koşmalı (bugün 2606 geçiyor) — hedefli koşu bu ölçekte yeterli değil.

---

## 5. ISR bütçesi — sığıyor, ama payı ölçmek lazım

TIM1 ISR periyodu **20 µs** (50 kHz), çekirdek 168 MHz → tick başına **3360 çevrim**.

| Kalem | 5 bobin | 7 bobin |
|---|---|---|
| Geçiş yok (yalnız döngü + karşılaştırma) — TAHMİN ~25 çevrim/bobin | ~0,74 µs | ~1,04 µs |
| **En kötü: hepsi aynı tick'te geçiş yapıyor** (NOP dead-time 21 iterasyon ≈ 126 çevrim + BSRR) | ~4,0 µs (%20) | **~5,6 µs (%28)** |
| Gölge→aktif transferi (7 float bölme, paket başına **1** tick) | — | ~2,4 µs, 500 ms'de bir |

⚠️ "En kötü durum" burada **normal durum**: varsayılan faz 0 olduğu için bobinlerin hepsi aynı
tick'te geçiş yapar. Yine de %28 yük 20 µs bütçesine sığıyor ve ana döngüye ~%70 kalıyor
(I2C ve UART oradan koşuyor).

⚠️ Bu sayılar **TAHMİN** — `DDS_DEADTIME_NOP_ITERS = 21`'in gerçek süresi kaynak dosyada
"ÖLÇÜLMEMİŞ" olarak işaretli (`main.c:177-191`). Tezgâhta ISR girişinde/çıkışında bir yedek
GPIO'yu toggle'layıp **skopla ölç**. %50'yi geçerse iki hazır kaçış var: fazları kaydır ya da
dead-time'ı çevrim-sayılı gerçek bir gecikmeyle değiştir.

**UART:** 120 bayt @115200 8N1 = **10,4 ms** (88 bayt = 7,6 ms). Keep-alive 500 ms
(`hardware_controller.py:82`), ölü-adam eşiği 1500 ms (`main.c:940`) → hat doluluğu %1,5'ten
%2,1'e çıkar, ölü-adam payı (3 paket) **değişmez**. Çerçeve senkronu 50 ms sessizliğe dayanıyor,
10,4 ms onun çok altında. Sorun yok.

---

## 6. Riskler ve tezgâh kabul kriterleri

| # | Risk | Kabul kriteri |
|---|---|---|
| R1 | **Bobin 6-7 termal korumasız** (§B2) | Bobini ısıt, eşikte PWM'in **gerçekten** kesildiğini ve histerezisle döndüğünü gör. Eşik değeri sahip kararıyla yazılı olsun. |
| R2 | **Sargı yönü bilinmiyor** → bobin 6-7 diğerlerini söndürebilir | `PEMF_BOBIN_TERS_MASKESI` biti, kabin merkezinde z ölçümüyle belirlenir. **Bu ölçüm hâlâ eksik** (sol + sağ duvar bobinleri). Ayrıca pankek işaret-dönmesi tuzağı: `sqrt(x²+y²)/|z| < 0,15` şartı. |
| R3 | Uzun kablo I2C'yi düşürür | Gerçek uzunlukta kablo + **bobinler sürülürken** 10 dk kesintisiz okuma, NACK/kurtarma sayacı 0 |
| R4 | ISR taşması | Skopla ISR süresi ölçümü; 7 bobin aynı fazda, en yüksek frekansta |
| R5 | CubeMX Generate-Code her şeyi ezer (§B3) | I2C **elle** eklenecek; `.ioc`'ye dokunulmayacak; ayna senkron betiği koşacak |
| R6 | Sürücü kartı uyumu — 8266 3,3 V GPIO ile sürüyordu, STM de 3,3 V | Seviye uyumlu ama **kablo uzunluğu** kenar bozar: sürücü girişine giden PWM hattı için seri direnç/tampon değerlendir; darbe kenarını skopla gör |
| R7 | Doz yeniden kalibrasyonu | Bobin 6-7'nin dalga sözleşmesi 8266'daki ile aynı 50 kHz DDS matematiği (`CoilController.cpp:341` ≡ `main.c` tpp) — ama sürücü ve pin farkı ölçülmeden aynı doz varsayılmaz. Alan probu + skop. |

---

## 7. Kazanımlar (silinen arıza sınıfları)

Bu geçiş sadece pin taşımıyor; **sahada tekrar eden bir arıza ailesini kökten kaldırıyor**:

* Hotspot düşünce bobin kayboluyor — dün düzeltilen `coil_status` yayını, portal/STA kilidi,
  %9 dinleme penceresi, 30 dk provizyon geri dönüşü: **hepsi konusuz kalır**
* `_esp_telemetry_watchdog`'ın en kötü senaryosu — *"STOP GÖNDERİLEMEDİ, bobin HÂLÂ ENERJİLİ
  olabilir"* (`api_server.py:691`) — **imkânsızlaşır**: STM'in ölü-adam watchdog'u 1500 ms
  sessizlikte bobini **kendisi** keser. Bu, ESP mimarisinin yapısal olarak veremediği garantidir.
* mDNS çok-homed kesintisi, kardeş-hotspot istemci tuzağı, MQTT `client_id` çakışması,
  bulut broker E-stop aynası: bobin yolundan çıkar
* Firmware reflash yükü: 3 kart yerine **1** kart
* ESP'lerdeki canlı WiFi sırları (`secrets_coil_*.h`) bobin yolundan çıkar

⚠️ Hotspot **kaldırılmaz**: mobil uygulamanın LAN erişimi de onu kullanıyor
(`api_server.py:252`). Değişen şey, hotspot'un artık **güvenlik-kritik** olmaması.

---

## 8. Faz planı

| Faz | İş | Çıktı |
|---|---|---|
| **0** | Sahip kararları (§9) + bobin 6-7 sargı yönü ölçümü | maske bitleri, eşik değeri, sensör kapsamı |
| **1** | Protokol 88→120 (Grup A) + simülatör + kapılar. **Sensör yok, ESP hâlâ açık.** | STM 7 bobin sürüyor; 6-7 pinleri fiziksel bağlı değil → görünür değişiklik yok, süit yeşil |
| **2** | Bobin 6-7 kablolaması + tezgâh: ISR ölçümü, darbe kenarı, alan yönü, doz | 7 bobin STM'den sürülüyor; ESP'ler hâlâ takılı ama **kullanılmıyor** |
| **3** | I2C + sensörler + `STM_TELE` çerçevesi + backend/DB yolu | gerçek telemetri geri geliyor; **termal kesme derlenip doğrulanıyor** (R1) |
| **4** | Topoloji anahtarı (Grup B) + arayüz (Grup C) | `ESP_COIL_IDS = set()`; ESP kodu uykuda, silinmiş değil |
| **5** | Yayın + saha | — |

⚠️ **Faz 3, faz 4'ten ÖNCE bitmeli.** Sırayı bozup ESP'leri önce kapatmak, bobin 6-7'yi
termal korumasız ve telemetrisiz bırakır (§B2).

⚠️ Firmware pakete **hiç girmez** → her fazda STM'e **elle reflash** (ST-Link/USB).

---

## 9. Sahibe karar soruları

1. **Sensör kapsamı:** yalnız bobin 6-7 mi (2 sensör çifti, iki I2C bus, ek çip yok), yoksa
   7 bobinin hepsi mi (TCA9548A mux gerekir)?
2. **Termal eşik:** bobin 6-7 için 8266'daki **100 °C** mi devredilecek, yoksa STM'in NTC
   bloğundaki 48 °C mi? Bobin 1-5 için de eşik uygulanacak mı?
3. **NTC yolu:** MLX90614 seçilince derleme-kapılı NTC bloğu **terk mi** edilecek (5 ADC pini
   serbest kalır) yoksa duracak mı?
4. **Akım ölçümü:** ACS712'ler bobin 6-7 için taşınacak mı, yoksa `currentA` bu bobinler için
   düşecek mi? (DB/PDF raporu bu alanı okuyor)
5. **8. slot:** tamamen kaldırılsın mı, yoksa boş/gizli kalsın mı? (öneri: kalsın — WS sözleşmesi
   ve ~50 test dosyası bozulmaz)
6. **ESP kodu:** silinsin mi, uykuya mı alınsın? (öneri: **uykuya** — geri dönüş bir satır)
