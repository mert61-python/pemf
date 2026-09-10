/**
 ******************************************************************************
 * @file    pemf_sensor.h
 * @brief   Bobin 6-7 I2C sensörleri — MLX90614 (sıcaklık) + MLX90393 (alan)
 *
 * SAHİP KARARI 2026-09-10: bobin 6-7 ESP8266'dan STM32'ye taşınıyor. ESP'de bu iki sensör
 * bobinin yanında duruyordu; STM'e taşınınca ölçüm yolu da buraya geliyor.
 * Plan: docs/stm32-7-bobin-gecisi-plani-2026-09-10.md · Sözleşme: docs/stm32-sensor-protokolu.md
 *
 * ============================================================================
 * NEDEN REGISTRE SEVİYESİ (HAL DEĞİL)
 * ============================================================================
 * `HAL_I2C_MODULE_ENABLED` bu projede KAPALI ve `Drivers/.../Src` içinde
 * `stm32f4xx_hal_i2c.c` **YOK** (20 HAL kaynağı var, I2C onlardan biri değil). HAL I2C'yi
 * açmak CubeF4 paketinden dosya eklemek demek; CubeMX "Generate Code" ise `main.c`'yi EZER
 * (bkz. main.c başlığı + docs/stm32-pin-haritasi.md §6). Aynı gerekçeyle NTC bloğu da
 * registre seviyesinde yazılmıştı (`Coil_NtcAdcInit`) — bu dosya o yerleşik deseni izler.
 *
 * ============================================================================
 * ⚠️ BLOKLAMAMA ŞARTI — GÜVENLİK
 * ============================================================================
 * Ana döngü UART paketlerini işler; 1500 ms sessizlikte firmware'in ölü-adam watchdog'u TÜM
 * bobinleri durdurur (main.c, `last_communication_ms`). Bu iyi bir emniyettir AMA sensör kodu
 * ana döngüyü ms'ler boyunca tutarsa watchdog SAHTE bir kopuş görüp **tedavi ortasında
 * bobinleri keser**. Bu yüzden:
 *   · `PEMF_Sensor_Poll()` her çağrıda EN FAZLA bir kısa I2C işlemi yapar,
 *   · MLX90393'ün ~17 ms dönüşüm süresi `HAL_GetTick()` damgasıyla beklenir — `delay` YOK,
 *   · her bayrak beklemesi ÇEVRİM SAYAÇLI (`I2C_SPIN_BUTCESI`), sonsuz döngü imkânsız.
 * Kapı: tests/test_stm_sensor_firmware.py
 *
 * ============================================================================
 * ⚠️ TERMAL KESME YOK — SAHİP KARARI
 * ============================================================================
 * Bu dosya sıcaklığı OKUR ve bildirir; **PWM'i durdurmaz**. Sahip 2026-09-10'da bobin 6-7 için
 * termal kesme istemedi. Kalan tek otomatik katman arayüzdeki 48 °C istemci interlock'udur
 * (`pf/src/components/domain/CoilParameterPanel.tsx:21`) ve o da ölçümün arayüze ULAŞMASINA
 * bağlıdır — bu dosyanın asıl işlevi budur. Buraya sessizce bir kesme EKLENMEZ.
 *
 * ============================================================================
 * BU DOSYADA AKIM YOK — AMA SİSTEMDE VAR
 * ============================================================================
 * ⚠️ BAYAT YORUM DÜZELTMESİ (aynı gün, ikinci karar): burada "ACS712'ler taşınmıyor"
 * yazıyordu. Sahip kararını değiştirdi → **bobin 1-5**'e ACS712-30A bağlanıyor ve akım
 * `pemf_akim.c` (ADC1) tarafından okunuyor. Bu dosya YALNIZ bobin 6-7'nin I2C sensörlerini
 * yönetir; akımla ilgisi yoktur ve bobin 6-7'de ACS712 YOKTUR.
 * Değişmeyen kural: ölçülmeyen alan telemetriye **hiç yazılmaz** — 0.0 göndermek aşağı
 * akışta "ölçüldü" olarak kaydedilir ve geçmişte PDF'e "0.0 °C ölçüldü" yazdırmıştı.
 *
 * ============================================================================
 * ⚠️ BİR BUS'TA YALNIZ BİR SENSÖR OLABİLİR
 * ============================================================================
 * Her hat İKİ cihazı da varsaymaz: açılışta ayrı ayrı yoklanır, bulunamayan **YOK**
 * işaretlenir, durumları ATLANIR ve yokluğu hata SAYILMAZ. Böylece üç kablolama da çalışır:
 *   (a) tek hatta sıcaklık + manyetik  (adresler 0x5A ↔ 0x18, çakışmazlar)
 *   (b) bir hatta YALNIZ manyetik      (sahip kablolaması, PB10/PB11)
 *   (c) iki hatta birer çift           (iki MLX90614 aynı hatta KONAMAZ: ikisi de 0x5A)
 * ⚠️ İLK ANLATIMIN DÜZELTMESİ: bu dosyada bir süre "yok olan sıcaklık sensörü her ~5
 * saniyede hat kurtarma tetikler ve aynı hattaki çalışan manyetik sensörü sakatlar"
 * yazıyordu. **YANLIŞTI** ve modelle ölçülüp düzeltildi (`test_stm_sensor_kablolama_modeli.py`):
 * `ardisik_hata` HAT BAŞINA tutulur ve BAŞARILI HER işlem onu sıfırlar. Manyetik okuma
 * çalışırken sayaç her turda 1→0 salınır, 5'e ASLA ulaşmaz → kurtarma tetiklenmez.
 * Yani o kablolama düzeltmeden ÖNCE de çalışıyordu.
 *
 * GERÇEK maliyet üç kalem — üçü de hijyen/teşhis, "çalışmıyor" değil:
 *   1. Her turda BOŞA giden bir I2C işlemi (eksik adrese START, bütçe + bus gürültüsü).
 *   2. `i2c_hata` teşhis sayacı takılı olmayan cihaz için SONSUZA kadar artar → sayaç
 *      gerçek arıza göstergesi olmaktan çıkar (tezgâh kabul kriteri "sayaç 0" idi).
 *   3. TAMAMEN BOŞ hatta (iki cihaz da yok) hiçbir başarı olmadığı için sayaç 5'e ULAŞIR
 *      ve boşuna kurtarma koşar.
 *
 * Kapı: tests/test_stm_sensor_firmware.py + test_stm_sensor_kablolama_modeli.py
 ******************************************************************************
 */
#ifndef PEMF_SENSOR_H
#define PEMF_SENSOR_H

#include <stdbool.h>
#include <stdint.h>

/** Sensörlü bobin sayısı (bobin 6 → I2C1, bobin 7 → I2C2). */
#define PEMF_SENSOR_BOBIN_SAYISI 2U

/** Sensörlü bobinlerin 1-tabanlı kimlikleri; telemetri satırındaki `C=` alanı budur. */
#define PEMF_SENSOR_ILK_BOBIN_ID 6U

/**
 * Bir bobinin sensör okumaları.
 *
 * `*_ok` false iken ilgili alan ANLAMSIZDIR ve telemetri satırına YAZILMAZ (alanı hiç
 * göndermemek, 0.0 göndermekten daha dürüsttür — bkz. dosya başlığı).
 */
typedef struct {
  float nesne_c;   /**< MLX90614 nesne (bobin yüzeyi) sıcaklığı, °C */
  float ortam_c;   /**< MLX90614 gövde/ortam sıcaklığı, °C */
  float alan_mt;   /**< MLX90393 |B| = sqrt(x²+y²+z²), **mT** (ESP ile AYNI büyüklük) */
  bool sicaklik_ok;
  bool alan_ok;
  uint16_t i2c_hata; /**< kümülatif I2C hata sayacı — teşhis; 0 beklenir */
} PEMF_SensorVerisi_t;

/**
 * I2C1 (PB8/PB9) ve I2C2 (PB10/PB11) çevre birimlerini + sensörleri hazırlar.
 * ⚠️ `Coil_GpioInit()`ten SONRA, `Coil_TimInit()`ten (50 kHz ISR) ÖNCE çağrılmalıdır.
 * Sensör yoksa sessizce başarısız olur; sürüş yolu ETKİLENMEZ (fail-safe).
 */
void PEMF_Sensor_Init(void);

/**
 * Durum makinesini ilerletir. Ana döngüden HER turda çağrılmalı.
 * @param simdi_ms `HAL_GetTick()`
 * @return true → yeni bir tam okuma tamamlandı (telemetri satırı basılabilir)
 */
bool PEMF_Sensor_Poll(uint32_t simdi_ms);

/**
 * Son okumayı kopyalar.
 * @param sira 0 = bobin 6, 1 = bobin 7
 */
void PEMF_Sensor_Oku(uint32_t sira, PEMF_SensorVerisi_t *hedef);

/**
 * Bir hatta AÇILIŞTA hangi cihazların bulunduğunu bildirir (kablolama doğrulaması).
 *
 * ⚠️ NEDEN VAR: bir bus'ta yalnız bir sensör olabilir (sahip kablolaması 2026-09-10) ve
 * "sensör okumuyor" ile "sensör hiç bulunamadı" arasındaki fark UART'tan görünmezse
 * tezgâhta saatler kaybedilir — telemetri satırı ikisinde de o alanı taşımaz.
 * `main.c` bunu açılışta `-> STM_SENS:` satırı olarak basar.
 *
 * @param sira 0 = bobin 6 (I2C1), 1 = bobin 7 (I2C2)
 * @param sicaklik_adres bulunan MLX90614 adresi, yok ise 0
 * @param alan_adres     bulunan MLX90393 adresi, yok ise 0
 */
void PEMF_Sensor_Rapor(uint32_t sira, uint8_t *sicaklik_adres, uint8_t *alan_adres);

#endif /* PEMF_SENSOR_H */
