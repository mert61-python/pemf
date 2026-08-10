# firmware/ — STM32 Bobin-Sürücü Firmware'i

Klinik cihazının 5 STM32 bobinini süren gömülü firmware. Backend seri porttan bu firmware'e komut yollar.

## Dosya
| Dosya | İçerik |
|---|---|
| `main.c` | **v2.2.0 (~1240 satır)** — tek dosya firmware |

- **MCU:** STM32F429ZI (STM32F4, Nucleo-144), SYSCLK 168 MHz.
- **Ne sürer:** 5-kanal **yazılım DDS** bipolar tam-köprü bobin PWM. TIM1 @50 kHz ISR, BSRR ile 10 GPIO'yu (bobin-başı IN_A/IN_B) yazılımla sürer; 100 Hz PWM, bobin-başı bağımsız faz.
- **Protokol:** USART3 @115200 (ST-Link VCP) ikili protokol — 88-byte `BinaryCmdPacket_t` (`0xAA 0x55` + duty/phase/freq/duration[5] + `ref_ms` + CRC32), yanıt `STM_OK`/`STM_NACK`/`STM_READY`. Backend tarafı: [`../utils/stm32_transport.py`](../utils/README.md) + [`../controllers/hardware_controller.py`](../controllers/README.md).
- **ESP bobinler (6-8):** ESP32-S3 / ESP8266 **slave**, PB1'deki master sync-pulse ile senkron. ⚠️ ESP firmware'i (`CoilController.cpp`) **bu repoda değil**.

## Güvenlik mantığı (firmware içinde)
- Aralık clamp'leri: `DUTY_MIN` / `FREQ_MIN..FREQ_MAX` / faz `0..360` / `DURATION_MAX_MINUTES 9999` + CRC + NACK.
- **Watchdog "Ölü Adam Devresi":** herhangi bobin aktif + seri >1500 ms yoksa → tüm duty 0.
- Bobin-başı **süre auto-stop**; A/B geçişlerinde **dead-time** (shoot-through koruması); duty **slew-rate** sınırlayıcı + `tpp-1` clamp.
- ⚠️ **Dead-time süresi ÖLÇÜLMEMİŞTİR.** `DDS_DEADTIME_NOP_ITERS` (=21) `volatile` bir NOP
  döngüsüdür; gerçek süre `-O` seviyesine, FLASH bekleme durumlarına ve ART hızlandırıcıya
  bağlıdır (kaba tahmin ~0.75–1.25 µs). Daha önce belgelerde **üç farklı ve yanlış** değer
  yazıyordu (40 µs / 500 ns / kod). Bu, tam-köprüye karşı **tek yazılım korumasıdır** — MCU'da
  donanımsal dead-time üreteci yoktur. Değiştirmeden önce **osiloskopla ölçün**: IN_A düşen
  kenarı ↔ IN_B yükselen kenarı arası, MOSFET/sürücünün turn-off gecikmesinden büyük olmalı.

## Fault işleyici yaması (`stm32f4xx_it.c`) — ELLE UYGULANMALI

Bu depo **yalnız `main.c`** tutar; CubeMX projesinin `Core/Src/stm32f4xx_it.c` dosyası burada
değildir. Fault işleyicileri (`HardFault` / `MemManage` / `BusFault` / `UsageFault`) o dosyada
tanımlıdır ve **boş `while(1)` döngüsüne girer** → main() durur, 1500 ms'lik ölü-adam kontrolü
bir daha çalışmaz, bobinler enerjili kalır. `main.c` bunları **tanımlayamaz** (çift-sembol link
hatası; `arm-none-eabi-ld` ile doğrulandı).

Çözüm: `main.c` `PEMF_ForceAllCoilOutputsLow()` fonksiyonunu **dışa açar**; aşağıdaki yamayı
`stm32f4xx_it.c` içindeki **USER CODE bloklarına** ekleyin (CubeMX yeniden-üretimde korur).

```c
/* USER CODE BEGIN PFP */
extern void PEMF_ForceAllCoilOutputsLow(void);
/* USER CODE END PFP */
```

Ardından **dört** işleyicinin `USER CODE BEGIN <ad>_IRQn 0` bloğuna (marker adları:
`HardFault`, `MemoryManagement`, `BusFault`, `UsageFault`):

```c
  PEMF_ForceAllCoilOutputsLow();   /* önce bobinleri kes */
  NVIC_SystemReset();              /* sonra MCU'yu resetle */
```

Reset sonrası `g_pwm_started = 0` ve `Coil_GpioInit` tüm pinleri LOW başlattığı için
kendiliğinden yeniden ateşleme olmaz.

> **IWDG bilinçli olarak EKLENMEDİ.** Bağımsız donanım watchdog'u main() döngüsünün her turda
> süre sınırına uymasını gerektirir; yanlış timeout tedavi ortasında MCU resetine yol açar.
> Tezgâh ölçümü isteyen ayrı bir iştir.

## Derleme doğrulaması

`main.c` tek başına derlenmez (HAL + CMSIS başlıkları CubeMX projesindedir). Sözdizimi/tip
kontrolü için:

```powershell
arm-none-eabi-gcc -c -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard `
  -DUSE_HAL_DRIVER -DSTM32F429xx -Wall -Wextra -O2 `
  -I<proje>\Core\Inc -I<proje>\Drivers\STM32F4xx_HAL_Driver\Inc `
  -I<proje>\Drivers\CMSIS\Include -I<proje>\Drivers\CMSIS\Device\ST\STM32F4xx\Include `
  firmware\main.c -o main.o
```

**Beklenen sonuç: SIFIR uyarı.** (Daha önce 4 adet `-Wsign-compare` "bilinen uyarı" olarak
kabul ediliyordu — `for (int i = 0; i < NUM_COILS; i++)` ile `NUM_COILS`'un `5U` olması
karşılaştırması. Denetim 2026-08-04'te döngü sayaçları `uint32_t`'ye çevrildi; artık
`-Wall -Wextra` temiz. Uyarıları sıfırda tutun: gürültü, gerçek bir uyarıyı görünmez yapar.)

## Bilinen sınırlar (denetim 2026-08-04)

Aşağıdakiler **kusur olarak biliniyor ve bilinçli olarak kod değişikliği yapılmadı.** Amaç, sonraki
okuyucunun bunları "zaten hallolmuş" sanmaması.

### Süre sınırı tek başına bir güvenlik sınırı DEĞİL (#69)
Bobinin `dur_min` süresi dolunca firmware duty'yi sıfırlar ve `g_start_ms[i]`'yi 0'lar. Ancak ISR'ın
shadow→active bloğu "duty>0 ve `g_start_ms==0` ise süreyi başlat" der.

**Mekanizma (dikkat — sık yanlış anlatılıyor):** bobin çalışırken `g_start_ms` sıfır *değildir*,
dolayısıyla keep-alive paketleri sayaca **dokunmaz**; süre normal işler ve dolduğunda auto-stop
bobini kapatır. Sorun ondan *sonra* başlar: auto-stop `g_start_ms`'i 0'lar, host ise ölü-adam
watchdog'u (1500 ms) yüzünden aynı paketi (duty>0) 2 Hz göndermeye **devam etmek zorundadır** →
bir sonraki paket "kapalıyken açıldı" sayılıp süreyi baştan başlatır. Net sonuç: sınır tedaviyi
**sonlandırmaz**, süre-dolar/yeniden-başlar döngüsüne sokar. Enerjilemeyi gerçekten sınırlayan tek mekanizma host tarafındaki
`controllers/hardware_controller.py` → `_coil_deadline`'dır; **silinirse bobin süresiz enerjili
kalır.** Regresyon kapısı: `tests/test_stm32_source_parity.py::test_host_tarafi_sure_deadlineI_hala_uygulaniyor`.

Firmware'de düzeltilmedi çünkü keep-alive'ı "yeni tedavi"den ayırmak 88 baytlık **sabit** pakete
sıra-numarası/başlat-bayrağı eklemeyi gerektirir (firmware + backend + simülatör üçünü birden
değiştiren protokol değişikliği). "Süre doldu" mandalı alternatifi ise hekimin aynı parametrelerle
yeniden başlat demesini sessizce etkisiz kılabilirdi — klinik bir cihazda kötü bir başarısızlık biçimi.

### Brown-out / PVD yapılandırılmıyor (#71)
`SystemClock_Config` yalnız HSE+PLL kurar; **BOR seviyesi (option byte) ve PVD kesmesi
ayarlanmıyor.** Besleme düşerken MCU tanımsız bir bölgede çalışabilir: GPIO'lar periyot ortasında
donarsa tam-köprü tek yönde DC olarak enerjili kalır (`PEMF_ForceAllCoilOutputsLow` yalnız
çağrılırsa yardımcı olur). Doğru çözüm, BOR'u option byte'tan `BOR_LEVEL_3`'e almak ve PVD ISR'ında
`PEMF_ForceAllCoilOutputsLow()` çağırmaktır.

Burada kod eklenmedi çünkü bu depoda **gerçek CubeMX HAL başlıkları yok**. Derleme doğrulaması,
denetim sırasında geçici olarak yazılan asgari bir **stub-HAL** ile yapıldı (`arm-none-eabi-gcc
-mcpu=cortex-m4 -O2 -Wall -Wextra -Wsign-compare` → 0 uyarı). ⚠️ O stub depoda DEĞİLDİR ve
bilerek öyle bırakıldı: sahte bir HAL'i depoya koymak, gerçek API yüzeyiyle karıştırılma riski
taşır. Stub yalnızca *bizim kodumuzun kendi iç tutarlılığını* sınar; `HAL_PWR_ConfigPVD` /
`HAL_FLASHEx_OBProgram` gibi çağrıların imzalarını **doğrulayamaz**. Denetlenmemiş bir güç-yönetimi çağrısı eklemek, doğrulanmış bir
düzeltmeden daha risklidir. Bu madde donanım erişimi olan bir oturuma bırakıldı.

## ⚠️ Dikkat
- **Termal/sıcaklık kesme mantığı bu firmware'de YOK.**

  > ⚠️ **DÜZELTME 2026-08-09 (denetim, Tier 2).** Burada önceden *"termal koruma sensör/ESP
  > tarafındadır"* yazıyordu. **Bu ifade 1-5 numaralı bobinler için DOĞRU DEĞİLDİ** ve yanlış
  > güvence veriyordu. Ölçülen durum:
  >
  > | Bobin | Sürücü | Sıcaklık ölçümü | Termal kesme |
  > |---|---|---|---|
  > | 1-5 | STM32 (binary paket) | **YOK** — pakette sıcaklık alanı yok, STM sıcaklık yayınlamaz | **YOK** |
  > | 6-8 | ESP32 (MQTT) | var (`pemf/coil/<id>/sensors` → `object_temp`) | yalnız arayüz eşiği |
  >
  > Tek kesme mantığı bir React bileşenindedir (`CoilParameterPanel.tsx`,
  > `SAFE_TEMP_CUTOFF = 48 °C`) ve `objectTemp` üzerinden çalışır. 1-5 için bu değer **hiç
  > gelmediğinden** (`live_state` varsayılanı `0.0`) koşul **hiçbir zaman** sağlanamaz — yani
  > 8 bobinin 5'i hastanın üzerinde **hiçbir sıcaklık koruması olmadan** enerjilenir.
  >
  > Yanlış güvence, korumasızlıktan tehlikelidir: bu satıra bakan biri korumanın var olduğunu
  > sanıp donanım tarafında önlem almayı erteler. **Gerçek çözüm donanımdadır** — 1-5 için
  > sıcaklık sensörü + STM telemetrisi + firmware tarafında kesme. O yapılana kadar bu sınır
  > BİLİNEREK taşınmalı ve kullanıcı arayüzü de "ölçülmüyor" demelidir (bkz.
  > `CoilParameterPanel` sıcaklık rozeti).
- Güvenlik-clamp'leri **hasta güvenliğidir** — zayıflatma. Python tarafı bilinçli olarak duty satüre etmez (firmware doyurur). Testler: [`../tests/`](../tests/README.md) `test_stm32_protocol_limits.py`.

---
İlgili: [controllers/](../controllers/README.md) · [utils/stm32_*](../utils/README.md) · [tests/](../tests/README.md) · [mimari](../docs/ARCHITECTURE.md)
