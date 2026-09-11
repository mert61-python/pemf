# STM32 Sensör Telemetri Sözleşmesi

> ⚠️ **GÜNCELLEME 2026-09-11 — `stm32_pemf_unipolar` AYNA PROJESİ KALDIRILDI.**
> Sürüş kipi artık `PEMF_BOBIN_UNIPOLAR_MASKESI` ile **bobin başına** seçiliyor
> (`0x60` = bobin 1-5 bipolar, 6-7 unipolar) → ikinci bir derleme gerekmiyor.
> **TEK kaynak: `firmware/stm32_pemf`.** `scripts/stm_unipolar_senkronla.py` ve
> ayna kapısı da silindi. Aşağıdaki iki-proje anlatımı TARİHÇEDİR.


> Bu dosya `firmware/stm32_pemf/Core/Src/pemf_sensor.c`, `pemf_akim.c` ve `main.c`
> yorumlarında **adıyla referans veriliyordu ama yoktu** (2026-09-11'de yazıldı).
> Tek kaynağı budur; UART satırının biçimi değişirse ÖNCE burası değişir.

## 1. Satır biçimi

STM32 → bilgisayar, UART3 @115200 8N1, satır sonu `\r\n`:

```
-> STM_TELE: C=<bobin>[,T=<°C>][,A=<°C>][,B=<mT>][,N=<örnek>][,S=1][,I=<A>][,X=1]
```

| Alan | Anlam | Kim gönderir |
|---|---|---|
| `C` | 1-tabanlı bobin kimliği | hep |
| `T` | MLX90614 nesne sıcaklığı (°C) | bobin 6 |
| `A` | MLX90614 ortam sıcaklığı (°C) | bobin 6 |
| `B` | **son 1 saniyenin TEPE** \|B\| (mT) | bobin 6 |
| `N` | `B` tepesinin kaç örnekten türediği | `B` ile birlikte |
| `S` | `1` = ham eksen tam ölçeğe dayandı → `B` **GÜVENİLMEZ** | yalnız doygunlukta |
| `I` | ACS712-30A akımı (A, RMS) | bobin 1-5 |
| `X` | `1` = ADC tavanına dayandı → `I` **GÜVENİLMEZ** | yalnız doygunlukta |

Ayrıştırıcı: `headless_core.HeadlessCore._parse_stm_tele`.

### ⚠️ ÖLÇÜLMEYEN ALAN **HİÇ GÖNDERİLMEZ**

Bu sözleşmenin en önemli kuralı. Bir alan satırda yoksa "ölçülmedi" demektir; `0.0`
göndermek aşağı akışta **"ölçüldü, sıfır çıktı"** olarak kaydedilir. Bu depo bu arızayı
defalarca yaşadı (PDF'e "0.0 °C ölçüldü" yazdıran desen). Backend de aynı kuralı sürdürür:
`magnetic_samples` / `magnetic_saturated` anahtarları `magnetic_field` **yokken hiç
konmaz**, ve `_coil_olculen_alanlar` yalnız gerçekten gelen alanları "ölçüldü" sayar.

Aynı gerekçeyle `N` ve `S` de `B` olmadan asla gönderilmez.

### Açılış satırı

```
-> STM_SENS: C=<bobin> I2C<1|2> sicaklik=0x<adres> alan=0x<adres>[ (SENSOR YOK)]
-> STM_SENS: C=<bobin> ACS712=<hazir|YOK|kalibre-EDILEMEDI>
```

Adres `0x00` = o hatta o cihaz **bulunamadı**. "Okumuyor" ile "hiç yok" farkı telemetriden
görünmez (ikisinde de alan satıra yazılmaz) — tezgâhta saat kaybettiren fark budur.

## 2. `B` neden TEPE, neden anlık değil

Sahip kararı 2026-09-11: *"bu bobinler aynı anda açılıp kapanıyor ya bana max değer lazım…
saniyede 1 sonuç verir en yükseğini."*

Bobinler ~1-100 Hz'de birlikte anahtarlanıyor. Saniyede bir alınan **anlık** örnek darbenin
neresine denk geldiğine göre 0 ile tam alan arasında rastgele bir sayı verir; operatör bunu
"yoğunluk düştü" diye okur. Sensör artık **~425 Hz** örnekleniyor, pencere kapanınca
**en büyük** \|B\| raporlanıyor ve biriktirici sıfırlanıyor. UART yükü değişmedi.

`N` teşhis için zorunlu: ~400 beklenir. Düşmesi I2C hattının yavaşladığını söyler — o
bilgi olmadan yavaşlamış bir hat "alan düştü" gibi okunur.

**Pencerede hiç geçerli örnek yoksa `B` gönderilmez.** Bayat bir tepeyi "bu saniyenin
ölçümü" diye göndermek, ölçülmeyeni 0.0 göndermekle aynı sınıf yalandır.

## 3. MLX90393 ayarı ve ölçek

| | Değer | Kaynak |
|---|---|---|
| Adres | `0x18` (yoksa `0x0C..0x0F` taranır) | sahadaki modüller |
| HALLCONF | `0xC` (varsayılan) | — |
| GAIN_SEL | **0** | ölçüm aralığı (aşağı bak) |
| RES_XYZ | `0` (RES_16, işaretli) | ofset düzeltmesi gerektirmez |
| OSR / DIG_FILT | **0 / 0** → tconv **1,27 ms** | en hızlı |
| Ölçek | XY **0,751** µT/LSB · Z **1,210** µT/LSB | `Adafruit_MLX90393.h` `mlx90393_lsb_lookup[0][0][0]` |
| Tam ölçek | XY **±24,6 mT** · Z **±39,6 mT** | 32767 × LSB |

`|B| = sqrt(x²+y²+z²) / 1000` → mT.

### ⚠️⚠️ ARALIK BİR TERCİH DEĞİL, ZORUNLULUK

Sahip ölçüm bandını verdi: **1-10 mT arası genelde, 0-5 arası çok sık**.

İlk sürüm `GAIN_SEL=7` ile geldi (0,150/0,242 µT/LSB — ESP8266 ile birebir olsun diye).
O ayarda XY tam ölçeği **4,92 mT**, yani **istenen bandın üst yarısı ölçülemiyordu**.

Ve taşma **sessizdir**: RES_16'da cihaz 19-bit sonucun alt 16 bitini verir; aşan değer
kırpılmaz, **sarar**. 6 mT'lik gerçek bir alan küçük ya da negatif bir sayı olarak okunur.
Sarmayı yazılımdan tespit etmek **mümkün değildir** — `S=1` bayrağı bile yakalayamaz, çünkü
sarmış ham değer küçüktür. **Tek savunma yeterli aralıktır.**

Kapılar: `tests/test_stm_sensor_firmware.py::test_KRITIK_olcum_araligi_SAHIBIN_BANDINI_KAPSAR`
(fiziğin kapısı) + `..._olcek_sabitleri_ADAFRUIT_TABLOSU_ile_AYNI` (ayar↔ölçek tutarlılığı).
İkisi birlikte "tutarlı ama yetersiz" ayarı da yakalar.

### Dönüşüm beklemesi DWT ile

`HAL_GetTick()` 1 ms çözünürlüklü; damganın hemen ardından sınır geçerse "2 tick" aslında
1,0 ms olabilir → dönüşüm bitmeden okunur. Bu yüzden bekleme **DWT çevrim sayacıyla**
yapılır (168 MHz, `MLX90393_DONUSUM_US = 1400`).

⚠️ DWT'nin **gerçekten ilerlediği açılışta ölçülür**. İlerlemezse hedef çevrim asla gelmez
ve durum makinesi `S_MAG_BEKLE`de **sonsuza kadar takılır** — ana döngü dönmeye devam ettiği
için ölü-adam watchdog'u bunu yakalamaz ve alan telemetrisi sessizce kesilir. Ölçüm
başarısızsa tick yedeğine (3 tick ≥ 2,0 ms) düşülür.

## 4. Bobin eşlemesi

```c
#define PEMF_SENSOR_BOBIN_IDLERI {6U, 6U}   /* I2C1, I2C2 */
```

Sahada **tek** MLX90393 var ve o PB10/PB11'de (I2C2). Aritmetik eşleme (`ILK_BOBIN_ID + sıra`)
onu bobin **7** diye raporluyordu; sahip arayüzde **bobin 6**'da görünmesini istedi. İki hat
da 6'ya raporlar; backend **alan bazında** birleştirdiği için çakışmazlar (biri `T=/A=`,
diğeri `B=` taşır).

⚠️ **Aynı alanı iki hat da gönderirse sonuncu kazanır.** İkinci bir MLX90393 takılırsa bu
tablo ayrılmalıdır — sessizce üzerine yazılmasın.

## 5. ESP kartlarıyla kıyaslanabilirlik

| Kart | GAIN | XY tam ölçek | Durum |
|---|---|---|---|
| STM32 | `GAIN_SEL=0` | ±24,6 mT | güncel |
| ESP32-S3 | `MLX90393_GAIN_5X` | ±24,6 mT | güncel — **STM ile birebir** |
| ESP8266 | `GAIN_1X` | ±4,92 mT | **dokunulmadı** |

⚠️ ESP-S3'te ayarlar **iki yerde** uygulanır: `_initI2C()` ve `recoverI2CBus(1)` —
`begin_I2C` cihazı fabrika varsayılanına döndürdüğü için her bağlantıdan sonra yeniden
yazılmak zorunda. 2026-09-11'de yalnız birincisi güncellenmişti; yapısal kapı yakaladı.
Artık tek kaynak: `SensorManager::_yapilandirMag()`.

⚠️ **4,92 mT üstündeki ESKİ kayıtlar zaten yanlıştı** (sarmıştı). Ölçek değişimi
"geçmişle kıyaslanabilirliği bozdu" diye okunmamalı; korunacak bir kıyaslanabilirlik yoktu.

## 6. Bloklamama şartı

Ana döngü 1500 ms sessizlikte ölü-adam watchdog'unu tetikler ve **tüm bobinleri durdurur**.
Sensör kodu ana döngüyü tutarsa watchdog **sahte** bir kopuş görür → tedavi ortasında
bobinler kesilir. Bu yüzden:

- `PEMF_Sensor_Poll()` her çağrıda **en fazla bir kısa I2C işlemi** yapar,
- dönüşüm süresi **damgalanır**, `HAL_Delay` bu dosyada **hiç yoktur**,
- her bayrak beklemesi **çevrim bütçelidir** (`I2C_SPIN_BUTCESI`) — sonsuz döngü imkânsız.

Kapı: `tests/test_stm_sensor_firmware.py`.

## 7. İlgili dosyalar

- Firmware: `firmware/stm32_pemf/Core/{Inc,Src}/pemf_sensor.{h,c}`, `pemf_akim.{h,c}`
- Ayna: `firmware/stm32_pemf_unipolar/` — **elle düzenlenmez**, `scripts/stm_unipolar_senkronla.py`
- Derleme kapısı: `scripts/firmware_derle.py`
- Pin haritası: `docs/stm32-pin-haritasi.md`
- Backend: `headless_core.py` (ayrıştırıcı) · `servers/api_server.py` (işleyici) ·
  `servers/seans_alan_kaydi.py` (seans CSV)
