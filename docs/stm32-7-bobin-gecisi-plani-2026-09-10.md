# ESP'leri Devre Dışı Bırak → 7 Bobinin Tamamını STM32'den Sür

**Tarih:** 2026-09-10 · **Sahip kararı:** ESP bobinleri (6-8) kaldırılacak; bobin 6 ve 7 STM32F429ZI
tarafından sürülecek; manyetik + sıcaklık sensörleri de STM'e bağlanacak.
**Durum:** ANALİZ + PLAN. Kod yazılmadı, pin bağlanmadı. **Kapsam kararları alındı — bkz. §9.**

## Sahip kararları (2026-09-10, §9'daki sorulara yanıt)

| # | Karar |
|---|---|
| 1 | **Sensör kapsamı: yalnız bobin 6-7.** Bobin 1-5'e sensör bağlanmayacak → mux gerekmez, iki I2C bus yeterli. |
| 2 | **Termal KESME yapılmayacak** ("6 7 termal kesme boşver"). Sıcaklık **ölçülüp** gösterilecek/kaydedilecek, ama PWM'i otomatik durduran kilit STM'e eklenmeyecek. |
| 3 | **ACS712 şimdilik duracak** — bobin 6-7 için akım ölçümü taşınmıyor. |
| 4 | **8. slot kalacak** — kaldırılmıyor. |
| 5 | **ESP kodu uykuda kalacak** — silinmiyor. |
| 6 | NTC bloğu: karar 2'nin sonucu olarak **dokunulmuyor** (derleme-kapılı, ADC pinleri ayrılmış kalıyor). |

⚠️ Karar 2'nin anlamı yazılı olsun: bobin 6-7'de **cihaz-taraflı** termal kesme kalmaz. Ağdan
bağımsız çalışan koruma gider; yerine yalnızca arayüzdeki **48 °C istemci interlock'u** kalır
(Kontrol sekmesi açık + WS bağlı iken çalışır — bkz. §B2). Bu bilinçli bir sahip kararıdır;
`api_server.py`'ye ya da STM'e sessizce bir limit **geri eklenmez**.

⚠️ Karar 3'ün anlamı: bobin 6-7 için `currentA` **0.0** kalır. `_coil_last_telemetry` damgası
sıcaklık/alan geldiği için yazılır → DB satırı üretilir ve akım sütunu 0.0 olarak birikir.
Bu, geçmişte "0.0 °C ölçüldü" sahte satırını doğuran desenin aynısı. Telemetri çerçevesi
akım alanını **hiç göndermemeli** (alan yok), backend de yokluğunda akım ortalamasını
biriktirmemeli (`i_n` sayacı 0 kalsın) — bkz. §3.3.

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
sistemde hiçbir termal kesme kalmaz.

**→ SAHİP KARARI (2026-09-10): kesme eklenmeyecek** (yukarıdaki karar 2). Yani geçişten sonra
tablo şöyle olur ve **bilinçli olarak** böyle kalır:

| Katman | Bobin 1-5 (bugün) | Bobin 6-7 (bugün) | Bobin 6-7 (geçiş sonrası) |
|---|---|---|---|
| Backend | yok | yok | yok |
| STM32 firmware | yok (NTC derleme-kapılı) | — | **yok** (sahip kararı) |
| ESP8266 firmware | — | 100 °C kesme | **devre dışı** |
| **İstemci (arayüz)** | tetiklenemez — ölçüm yok | **48 °C'de STOP** | **48 °C'de STOP** |

**DÜZELTME — "hiçbir katman kalmaz" doğru değil.** Arayüzde bir **istemci-taraflı interlock**
var ve ölçüm gelen her bobinde çalışıyor:

```
pf/src/components/domain/CoilParameterPanel.tsx:21   const SAFE_TEMP_CUTOFF = 48;
pf/src/components/domain/CoilParameterPanel.tsx:143  const overheating = running && objectTemp > SAFE_TEMP_CUTOFF;
                                                     → sendCommand(false) + "otomatik durduruldu"
```

Yani bobin 6-7 sıcaklığı STM telemetrisiyle bildirmeye başladığı anda bu interlock onlara
**kendiliğinden** uygular. Kaybedilen şey *bütün* koruma değil, **cihaz-taraflı** koruma.
Farkı önemli: istemci interlock'u yalnız Kontrol sekmesindeki panel **ekranda** ve WS **bağlı**
iken çalışır; ağ koparsa ya da operatör başka sekmedeyse tetiklenmez. Cihaz-taraflı kilit ise
ağdan bağımsızdı. Geçiş sonrası bobin 6-7'de kalan **tek** otomatik katman, ağa ve açık arayüze
bağımlı olan zayıf katmandır.

⚠️ **BUGÜN VAR OLAN ÇELİŞKİ (geçişten bağımsız):** istemci 48 °C'de durduruyor, 8266 firmware'i
ise dün 100 °C'ye çekildi. Kontrol sekmesi açıkken bobin **48'de** durur — yani 100 °C kararı
pratikte çoğu zaman **hiç devreye girmiyor**. İki eşik tek bir yerden türemiyor ve bu, deponun
tekrar eden "sihirli sayı ikinci bir yere kopyalanmış" sınıfı. `SAFE_TEMP_CUTOFF` da senin
kararına hizalanmalı mı, karar senin.

`NTC_KESME_C 48.0f` (`main.c:629`) ile 8266'nın 100 °C'si arasındaki eşik seçimi ise **konusuz
kaldı** — STM'de kesme derlenmediği için orada hiçbir eşik uygulanmıyor.

⚠️ Arayüz metni de kontrol edilmeli: `CoilParameterPanel:204-215`'teki "ölçüm yok → otomatik
termal durdurma uygulanmaz" rozeti bobin 6-7'de artık **yanlış** olacak (ölçüm gelecek), ama
"bobin otomatik durduruldu" mesajı da cihazın kendini durdurduğu izlenimini vermemeli — durduran
**arayüz**. Bu ayrım operatöre görünür kalmalı.

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

**KESİNLEŞTİ (2026-09-10, sahip fiziksel kabloyu çekti).** İlk öneri PE9/PE11 idi; sahip o iki
pini kullandığı başlıkta **bulamadı** (Nucleo-144'te PE9/PE11 diğer ZIO başlığında). Fotoğrafla
doğrulanan, aynı başlıkta ve boş olan pinlere geçildi:

| Bobin | IN_A (PWM — **kablo var**) | IN_B (kablo YOK, kalıcı LOW) |
|---|---|---|
| **6** | **PE13** | PE12 |
| **7** | **PE15** | PD13 |

Dördü de GPIOD/GPIOE'de → `Coil_GpioInit` saatleri **zaten açık**, ek RCC satırı gerekmiyor.
PE12/PE15/PD13 firmware'de ve `.ioc`'de hiçbir yerde geçmiyor (doğrulandı). PE13, `.ioc`'de bayat
`TIM1_CH3` olarak duruyor — firmware o kanalı kullanmıyor, ama `.ioc` temizliğinde silinmeli.

⚠️ **Maske bobin 6-7'de KULLANILAMAZ.** Unipolar kipte maske biti dalgayı değil, darbenin çıktığı
**pini** değiştirir. IN_B'lerde (PE12/PD13) kablo olmadığı için bit set edilirse o bobin **sessizce
sürülmez**. Yön yanlış çıkarsa çözüm **bobin uçlarını fiziksel çevirmek** — sahibin bobin 1-5'te
yaptığı gibi. Maske bitleri 5 ve 6 **0** kalacak (zaten tüm maske 0x00, bkz. §2.4).

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

**→ SAHİP KARARI: ACS712 şimdilik taşınmıyor (karar 3), termal kesme de yapılmıyor (karar 2).**
Dolayısıyla bu fazda **hiçbir ADC pini kullanılmıyor**: NTC bloğu derleme-kapılı olarak olduğu
gibi duruyor, ayrılmış beş pin (PA0, PA3, PA4, PC0, PC3) ayrılmış kalıyor.

Sonradan akım ölçümü istenirse iki yol var: NTC yolu terk edilirse o beş pin serbest kalır,
edilmezse PC2 (ADC1_IN12) ve PA6 (ADC1_IN6) boş.

⚠️ İleride termal kesme istenirse o zaman bir **karar** gerekir: NTC bloğu ile MLX90614 aynı
kesmenin iki farklı gerçeklenmesi; ikisini birden bırakmak iki farklı eşikle çelişen iki kesme
demektir. (NTC bloğu belgelenmiş bir açık P0'dır — silmeden önce kararın yazılı olması lazım.)

---

### 2.4 ⚠️ Polarite maskesi 0x03 → 0x00 (sahip kararı, 2026-09-10) — ARIZA KAYDI

Sahip bildirimi (birebir): *"PEMF_BOBIN_TERS_MASKESI daha önce kullanıldı mı kullanılmamalı çünkü
ben fiziksel çevirdim bobini hep aynı pinlerde kalmalıydı PC8 PC9 PD10 PC6 VE PA8 1-5 ARASI
SIRAYLA BÖYLE BAĞLI DİĞERLERİNİ BAĞLAMİCAM ZATEN"*

**Kullanılmıştı.** `27c0743` (2026-09-08) maskeyi **0x03**'e çekti: bobin 1 → PD12/IN_B,
bobin 2 → PE10/IN_B. Gerekçe o günün tezgâh ölçümüydü (z işaretleri 1:+1,4 · 2:−4,9 · 4:+0,5 ·
5:+3,9 mT → bobin 2 ters). Düzeltme **yazılımda** yapılmıştı ve bir test kapısı 0x03'ü **pinliyordu**.

⚠️ **Sonuç:** IN_B pinleri hiç bağlanmadığı için o firmware yakıldıysa bobin 1 ve 2'nin darbesi
**bağlı olmayan** PD12/PE10'a gitti → iki bobin **hiç sürülmedi**, üstelik SESSİZCE: ACK'te duty
görünür, `running` true olur, arayüz "Aktif" der, **alan sıfırdır**.

**Yapılan:** maske `0x00`; `pemf_surus.h` + `main.c` pin blokları + `firmware/stm32_pemf/README.md`
düzeltildi; ayna `scripts/stm_unipolar_senkronla.py` ile senkronlandı; kapı
`tests/test_stm_unipolar_ayna.py` artık **0x00'ı** pinliyor ve mekanizmanın ISR'de durduğunu ayrıca
doğruluyor (IN_B'ler bir gün bağlanırsa yeniden kullanılabilir). Mutasyon (0x00→0x03) ile
**KIRMIZI olduğu kanıtlandı** (2 test). Yeni karşıt-kanıt testi, modelin maske bitini gerçekten
okuduğunu gösteriyor. 55 test yeşil.

⚠️ **REFLASH gerekli** — firmware pakete girmez. Reflash edilene kadar bobin 1-2'nin durumu
yakılı firmware'e bağlı.

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

**→ SAHİP KARARI: kapsam yalnız bobin 6-7 (karar 1) → yol A.** İki ayrı bus, ek çip YOK,
mux alınmayacak. MLX90614'ler adres programlaması gerektirmiyor: biri I2C1'de, biri I2C2'de,
ikisi de fabrika adresi 0x5A'da kalıyor. MLX90393'ler de aynı iki bus'ta 0x0C'de durabilir
(farklı bus → çakışma yok).

Bobin 1-5 sensörsüz kalıyor — `objectTemp`/`magneticMt` onlar için **0.0** kalacak ve arayüzdeki
"ölçüm yok" rozeti doğru olmaya devam edecek. İleride 7 bobinin hepsi istenirse yol **C**
(TCA9548A mux) gerekir; o zaman I2C2 yedeğe düşer.

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

1. Firmware: yeni satır, ör. `-> STM_TELE: C=<id>,T=<obj>,A=<amb>,B=<mT>` (bobin başına,
   ~1 Hz). ASCII kalması akıllıca — mevcut satır-tabanlı okuyucu ve `readline()` yolu değişmez.
   ⚠️ **Akım alanı YOK** (karar 3: ACS712 taşınmıyor). Alanı 0.0 ile doldurmak, geçmişte
   "0.0 °C ölçüldü" sahte satırını doğuran desenin aynısıdır — alan **hiç gönderilmemeli**.
2. `headless_core`: ayrıştırıcı + `hardware.stm.telemetry` olayı.
3. `api_server`: olayı `_live_state["coils"][idx]`'e yaz **ve** `_coil_last_telemetry[idx]`'i
   damgala — aksi halde DB kaydı yine üretilmez (`api_server.py:3291` kapısı).
4. `coil_status` + `sensor_data` WS yayınları (ESP yolundaki ile **aynı sözleşme**; istemci
   tarafında hiçbir şey değişmez).
5. ⚠️ Dakika-ortalaması biriktiricisi (`api_server.py:3296+`, `_minute_acc`) akım için
   `i_sum`/`i_n` tutuyor. Akım gelmeyeceği için `i_n` **0 kalmalı**; `currentA`nın
   `_live_state`'teki 0.0 başlangıç değeri "ölçüm" sayılmamalı. Bu, `_coil_last_telemetry`
   kapısının çözdüğü sorunun **alan bazında** tekrarı: bobin artık telemetri gönderiyor, ama
   yalnız **bazı** alanları gönderiyor.

Bu tasarım bilinçli: istemci ve DB, verinin ESP'den mi STM'den mi geldiğini **bilmesin**.

---

## 4. Değişecek dosyalar — atomik gruplar

### Grup A — Firmware protokolü (88 → 120 bayt), tek commit'te

`2 + 7·4·3 + 7·4 + 2 + 4 = **120 bayt**`

| Dosya | Değişiklik |
|---|---|
| `firmware/stm32_pemf/Core/Src/main.c` | `NUM_COILS 5→7`; `coil_gpio[]` +2 satır; başlık pin haritası; `Coil_GpioInit` GPIOE pinleri; ACK format dizesi (aş. uyarı); `STM_READY` metni "5-ch"→"7-ch"; `g_*[NUM_COILS]` initializer'ları (`{0,0,0,0,0}` → 7 eleman — **derleyici bunu sessizce kabul eder**, elle sayılmalı) |
| `firmware/stm32_pemf_unipolar/` | **elle düzenlenmez** → `python scripts/stm_unipolar_senkronla.py` |
| `Core/Inc/pemf_surus.h` | pin durumu bloğu (bobin 6-7 satırları). `PEMF_BOBIN_TERS_MASKESI` **0x00 KALIR** — §2.4 |
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
| YENİ `test_stm_termal_kesme_EKLENMEDI.py` | Sahip kararı 2'yi **iki yönlü** pinler: (a) STM'e sessizce bir sıcaklık limiti eklenmemiş, (b) `SAFE_TEMP_CUTOFF = 48` istemci interlock'u **duruyor** — tek kalan otomatik katman kazara silinmesin |
| YENİ `test_stm_telemetri_akim_alani_YOK.py` | `STM_TELE` çerçevesi akım alanı **taşımıyor** ve backend akım ortalamasını biriktirmiyor (karar 3; sahte-0.0 sınıfı) |
| YENİ `test_bobin_topolojisi.py` | `STM_COIL_IDS ∪ ESP_COIL_IDS` çakışmasız; hiçbir bobin iki yoldan sürülmüyor; 8. slot `connected=False` |
| `test_esp8266_termal_esik.py` | ESP kodu uykuda kalıyor (karar 5) → kapı **koşmaya devam eder** ve 100 °C'yi pinlemeyi sürdürür. ⚠️ Ama artık **ölü kodu** pinliyor: bobin sürülmediği için eşiğin saha etkisi yok. Kapının başlığına bu not düşülmeli, yoksa bir sonraki okuyan "termal koruma var" sanır. |
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
| R1 | **Bobin 6-7'de cihaz-taraflı termal kesme yok** (sahip kararı 2) | Kesme **eklenmiyor** → doğrulanacak bir kesme de yok. Doğrulanacak olan şu: sıcaklık ölçümü arayüze **ulaşıyor** ve 48 °C istemci interlock'u bobin 6-7'de **gerçekten** tetikleniyor. Bu tek kalan otomatik katman; sessizce çalışmıyor olması en kötü durum. |
| R2 | **Sargı yönü bilinmiyor** → bobin 6-7 diğerlerini söndürebilir | Kabin merkezinde z ölçümü; yanlışsa **bobin uçları fiziksel çevrilir** (maske DEĞİL — §2.1). Ölçüm hâlâ eksik (sol + sağ duvar). Pankek işaret-dönmesi tuzağı: `sqrt(x²+y²)/|z| < 0,15` şartı. |
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
| **0** | ✅ Sahip kararları alındı (bkz. başlık) · ⏳ bobin 6-7 sargı yönü ölçümü **BEKLİYOR** | maske bitleri |
| **1** | Protokol 88→120 (Grup A) + simülatör + kapılar. **Sensör yok, ESP hâlâ açık.** | STM 7 bobin sürüyor; 6-7 pinleri fiziksel bağlı değil → görünür değişiklik yok, süit yeşil |
| **2** | Bobin 6-7 kablolaması + tezgâh: ISR ölçümü, darbe kenarı, alan yönü, doz | 7 bobin STM'den sürülüyor; ESP'ler hâlâ takılı ama **kullanılmıyor** |
| **3** | I2C1+I2C2 + MLX90614/MLX90393 (yalnız bobin 6-7) + `STM_TELE` çerçevesi + backend/DB yolu | gerçek sıcaklık/alan geri geliyor; 48 °C istemci interlock'unun bobin 6-7'de tetiklendiği doğrulanıyor (R1). Termal kesme **eklenmiyor** (karar 2), ACS712 **taşınmıyor** (karar 3) |
| **4** | Topoloji anahtarı (Grup B) + arayüz (Grup C) | `ESP_COIL_IDS = set()`; ESP kodu uykuda, silinmiş değil |
| **5** | Yayın + saha | — |

⚠️ **Faz 3, faz 4'ten ÖNCE bitmeli.** Cihaz-taraflı kesme bilinçli olarak yok (karar 2);
dolayısıyla bobin 6-7'de kalan **tek** otomatik katman, sıcaklığın arayüze ulaşmasına bağlı olan
48 °C istemci interlock'u. Faz 3 bitmeden ESP'leri kapatmak o katmanı da götürür → bobin 6-7
tamamen korumasız kalır. Sıra bu yüzden pazarlık konusu değil.

⚠️ Firmware pakete **hiç girmez** → her fazda STM'e **elle reflash** (ST-Link/USB).

---

## 9. Karar soruları — ✅ YANITLANDI (2026-09-10)

Kararların tamamı belgenin başındaki tabloda. Özet: (1) sensörler yalnız bobin 6-7 → mux yok,
iki I2C bus · (2) termal **kesme yok** · (3) ACS712 şimdilik durur · (4) 8. slot kalır ·
(5) ESP kodu uykuda kalır · (6) NTC bloğuna dokunulmaz.

### Açık kalan tek girdi

**Bobin 6-7'nin sargı yönü ölçümü** (sol duvar + sağ duvar). `PEMF_BOBIN_TERS_MASKESI` biti
bundan çıkıyor; yanlış bit kabin merkezinde alanı **söndürür** ve bu sessiz bir doz hatasıdır
(`efield_live.py` `duty_sum` bobinleri birlikte sayıyor). Faz 1 bu ölçüm olmadan da yapılabilir
— maske yalnız faz 2'de (kablolama) gerekiyor.

### İleride tekrar sorulacak (bugün kapalı)

* `SAFE_TEMP_CUTOFF = 48` istemci eşiği, 8266 için verilen 100 °C kararına hizalanmalı mı?
  (bugün ikisi çelişiyor — §B2)
* Bobin 6-7'ye akım ölçümü ve/veya cihaz-taraflı termal kesme sonradan eklenecek mi?
* Bobin 1-5'e de sensör istenirse TCA9548A mux gerekir.
