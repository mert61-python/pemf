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
- Bobin-başı **süre auto-stop**; A/B geçişlerinde **dead-time** (~500 ns, shoot-through koruması); duty **slew-rate** sınırlayıcı + `tpp-1` clamp.

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

Bilinen (önceden var olan) uyarılar: 4 adet `-Wsign-compare` (`int i < NUM_COILS`).

## ⚠️ Dikkat
- **Termal/sıcaklık kesme mantığı bu firmware'de YOK** — termal koruma sensör/ESP tarafındadır. Sahip bunu bilerek böyle bıraktı.
- Güvenlik-clamp'leri **hasta güvenliğidir** — zayıflatma. Python tarafı bilinçli olarak duty satüre etmez (firmware doyurur). Testler: [`../tests/`](../tests/README.md) `test_stm32_protocol_limits.py`.

---
İlgili: [controllers/](../controllers/README.md) · [utils/stm32_*](../utils/README.md) · [tests/](../tests/README.md) · [mimari](../docs/ARCHITECTURE.md)
