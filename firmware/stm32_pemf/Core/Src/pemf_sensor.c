/**
 ******************************************************************************
 * @file    pemf_sensor.c
 * @brief   Bobin 6-7 I2C sensör katmanı — registre seviyesi, BLOKLAMAYAN
 *
 * Gerekçeler ve güvenlik şartları için `pemf_sensor.h` başlığını oku.
 * Kayıt/sabit türetmesi: docs/stm32-sensor-protokolu.md
 *
 * ⚠️ TEZGÂHTA DOĞRULANMADI. Bu depoda C DERLENMEZ ve I2C kabloları henüz çekilmedi.
 * Ölçek sabitleri Adafruit kütüphanelerinin AYNI ayarlarından türetildi (aşağıda kaynak
 * satırlarıyla) ki üretilen sayı ESP'nin bugün kaydettiğiyle KIYASLANABİLİR olsun.
 * Kabul kriteri: aynı sensör aynı yerde, ESP ve STM okumaları %5 içinde.
 ******************************************************************************
 */

#include "pemf_sensor.h"

#include "main.h"
#include <math.h>

/* ============================================================================
 * I2C ZAMANLAMA — APB1 = 42 MHz, Standart kip 100 kHz
 * ----------------------------------------------------------------------------
 * Sistem saati main.c'de kurulu: SYSCLK 168 MHz, APB1CLKDivider = /4 → 42 MHz.
 *   CR2.FREQ  = 42        (APB1'in MHz cinsinden değeri; referans kılavuz şartı)
 *   CCR       = 42e6 / (2 * 100e3) = 210
 *   TRISE     = (1000 ns / 23.8 ns) + 1 = 43   (Sm için tr(max) = 1000 ns)
 *
 * ⚠️ 400 kHz'e ÇIKMA. Sensörler bobinin yanında, kablo kabin boyunca uzuyor (65x50x50 cm)
 * ve bobinler anahtarlanırken hatta gürültü kuple ediyor. 100 kHz + güçlü pull-up (2.2k)
 * gürültü payını korur. Bkz. plan belgesi §3.2.
 * ============================================================================
 */
#define I2C_APB1_MHZ 42U
#define I2C_CCR_100K 210U
#define I2C_TRISE_SM 43U

/**
 * Bayrak beklemesi için ÇEVRİM BÜTÇESİ.
 *
 * ⚠️ NEDEN SAYAÇ, NEDEN `HAL_Delay` DEĞİL: bu kod ana döngüden çağrılır ve ana döngü
 * 1500 ms sessizlikte ölü-adam watchdog'unu tetikler. Sonsuz `while (!(SR1 & X))` bir
 * kopuk SDA hattında kartı KİLİTLER → watchdog SAHTE kopuş görür → tedavi ortasında
 * bobinler kesilir. Bütçe, 100 kHz'de bir baytın (~90 µs) rahatça sığacağı ama arıza
 * hâlinde ~1 ms'i geçmeyecek şekilde seçildi.
 */
#define I2C_SPIN_BUTCESI 40000U

/** Üst üste bu kadar hatadan sonra hat kurtarma (9 saat darbesi + SWRST) denenir. */
#define I2C_KURTARMA_ESIGI 5U

/** Tam okuma turu periyodu (ms). ESP ~1 Hz yayınlıyordu; aynı hızda kalıyoruz. */
#define SENSOR_TUR_MS 1000U

/**
 * BULUNAMAYAN cihaz kaç turda bir yeniden aranır.
 *
 * ⚠️ NEDEN CİHAZ BAZINDA VARLIK TESPİTİ VAR (2026-09-10, sahip kablolaması):
 * Sahip PB10/PB11'e (I2C2) **yalnız manyetik sensör** bağlıyor — o bus'ta MLX90614 YOK.
 * Bu dosyanın ilk hâli her bus'ta İKİ cihazı da varsayıyordu.
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
 * Çözüm: açılışta adres yoklaması yapılır; bulunamayan cihaz **YOK** işaretlenir, onun
 * durumları ATLANIR ve yokluğu hata SAYILMAZ. Sonradan takılabilir diye periyodik yeniden
 * arama yapılır (her turda aramak, eksik adrese boşa START atıp bütçe harcar).
 */
#define SENSOR_YENIDEN_ARAMA_TUR 10U

/* ============================================================================
 * MLX90614 (sıcaklık) — SMBus, adres 0x5A (FABRİKADA SABİT)
 * ----------------------------------------------------------------------------
 * ⚠️ Adres değiştirilemez → aynı bus'ta İKİ tane çalışmaz. Bu yüzden bobin 6 I2C1'de,
 * bobin 7 I2C2'de; ikisi de 0x5A. (Alternatif TCA9548A mux'tı, sahip gerek görmedi.)
 *
 * Okuma: [S][addr+W][komut][Sr][addr+R][LSB][MSB][PEC][P]  — TEKRARLI START şart
 * (Adafruit_MLX90614 `read16` → `write_then_read(..., stop=false)`).
 * Dönüşüm: T[K] = ham * 0.02  →  °C = T[K] - 273.15   (kütüphane ile BİREBİR)
 * ============================================================================
 */
#define MLX90614_ADRES 0x5AU
#define MLX90614_RAM_TA 0x06U   /**< ortam/gövde sıcaklığı */
#define MLX90614_RAM_TOBJ1 0x07U /**< nesne sıcaklığı */
#define MLX90614_LSB_K 0.02f

/* ============================================================================
 * MLX90393 (alan) — komut tabanlı
 * ----------------------------------------------------------------------------
 * ⚠️ ADRES 0x18. Bu, MLX90393'ün "tipik" 0x0C'si DEĞİL; sahadaki modüller 0x18'de yanıt
 * veriyor (ESP kodu: `_mlxMag.begin_I2C(0x18)`, SensorManager.cpp:280) ve kütüphane
 * başlığı da bunu belgeliyor: "Can also be 0x18, depending on IC". Init sırasında
 * 0x18 → 0x0C..0x0F sırayla TARANIR ve bulunan adres kullanılır (ESP'deki
 * `_scanI2CDevices` davranışının aynısı) — modül değişirse kod değişmesin.
 *
 * AYAR (ESP ile BİREBİR; SensorManager.cpp:284-288 + kütüphane `_init`):
 *   HALLCONF = 0xC (varsayılan) · GAIN_SEL = 7 (1x) · RES_XYZ = 0 (RES_16)
 *   OSR = 3 (kütüphane varsayılanı, ESP değiştirmiyor) · DIG_FILT = 1 (ESP FILTER_1)
 *
 * ÖLÇEK (Adafruit_MLX90393.h `mlx90393_lsb_lookup[HALLCONF=0xC][GAIN_SEL=7][RES_16]`):
 *   X,Y → 0.150 µT/LSB      Z → 0.242 µT/LSB
 * ⚠️ BU İKİ SAYI ESP'NİN BUGÜN ÜRETTİĞİ DEĞERİN KAYNAĞIDIR. Değiştirmek, geçmiş
 * kayıtlarla kıyaslanabilirliği bozar (aynı sınıf tuzak: 1.9.45'te µm gap değişimi).
 *
 * DÖNÜŞÜM SÜRESİ: `mlx90393_tconv[DIG_FILT=1][OSR=3]` = 6.84 ms; kütüphane +10 ms ekliyor
 * ("Without +10ms delay measurement doesn't always seem to work") → 17 ms. Burada bu süre
 * BEKLENMEZ, damgalanır: SM gönderilir, 17 ms sonraki Poll turunda RM okunur.
 *
 * BÜYÜKLÜK: |B| = sqrt(x²+y²+z²) / 1000 → **mT**. ESP ile BİREBİR
 * (SensorManager.cpp:418-419) → `magneticMt` alanının anlamı DEĞİŞMEZ.
 * ============================================================================
 */
#define MLX90393_ADRES_VARSAYILAN 0x18U
#define MLX90393_KOMUT_SM 0x3EU /**< 0x30 | AXIS_ALL(0x0E) — tek ölçüm başlat */
#define MLX90393_KOMUT_RM 0x4EU /**< 0x40 | AXIS_ALL(0x0E) — ölçümü oku */
#define MLX90393_KOMUT_RR 0x50U
#define MLX90393_KOMUT_WR 0x60U
#define MLX90393_KOMUT_EX 0x80U
#define MLX90393_KOMUT_RT 0xF0U
#define MLX90393_CONF1 0x00U /**< GAIN_SEL bit 6:4, HALLCONF bit 3:0 */
#define MLX90393_CONF3 0x02U /**< RES_Z 10:9, RES_Y 8:7, RES_X 6:5, DIG_FILT 4:2, OSR 1:0 */
#define MLX90393_GAIN_SEL 7U
#define MLX90393_OSR 3U
#define MLX90393_DIG_FILT 1U
#define MLX90393_LSB_XY_UT 0.150f
#define MLX90393_LSB_Z_UT 0.242f
#define MLX90393_DONUSUM_MS 17U

/* ============================================================================
 * DURUM MAKİNESİ
 * ============================================================================
 */
typedef enum {
  S_BOSTA = 0,
  S_TOBJ,
  S_TA,
  S_MAG_BASLAT,
  S_MAG_BEKLE,
  S_MAG_OKU,
} SensorDurum_t;

typedef struct {
  I2C_TypeDef *i2c;
  GPIO_TypeDef *port;
  uint16_t scl_pin;
  uint16_t sda_pin;
  uint8_t mag_adres;      /**< 0 = bulunamadı (o bus'ta MLX90393 YOK) */
  uint8_t sicaklik_adres; /**< 0 = bulunamadı (o bus'ta MLX90614 YOK) */
  uint32_t tur_sayaci;    /**< yeniden arama zamanlaması */
  SensorDurum_t durum;
  uint32_t sonraki_tur_ms;
  uint32_t mag_hazir_ms;
  uint16_t ardisik_hata;
  PEMF_SensorVerisi_t veri;
} SensorHat_t;

static SensorHat_t g_hat[PEMF_SENSOR_BOBIN_SAYISI];

/* ============================================================================
 * REGISTRE SEVİYESİ I2C — hepsi ÇEVRİM BÜTÇELİ
 * ============================================================================
 */

/** Bayrak beklemesi. @return true = bayrak geldi, false = bütçe doldu (ARIZA). */
static bool i2c_bekle(volatile uint32_t *sr, uint32_t maske, bool set_olsun) {
  uint32_t butce = I2C_SPIN_BUTCESI;
  while (butce-- > 0U) {
    const bool var = ((*sr & maske) != 0U);
    if (var == set_olsun) {
      return true;
    }
  }
  return false;
}

/** Hattı temizle: STOP üret ve bayrakları düşür (arıza sonrası her zaman çağrılır). */
static void i2c_iptal(I2C_TypeDef *i2c) {
  i2c->CR1 |= I2C_CR1_STOP;
  (void)i2c->SR1;
  (void)i2c->SR2;
}

static bool i2c_start(I2C_TypeDef *i2c, uint8_t adres, bool okuma) {
  i2c->CR1 |= I2C_CR1_START;
  if (!i2c_bekle(&i2c->SR1, I2C_SR1_SB, true)) {
    return false;
  }
  i2c->DR = (uint32_t)((adres << 1U) | (okuma ? 1U : 0U));
  if (!i2c_bekle(&i2c->SR1, I2C_SR1_ADDR, true)) {
    return false; /* NACK / cihaz yok */
  }
  (void)i2c->SR1; /* ADDR temizleme: SR1 oku, sonra SR2 oku */
  (void)i2c->SR2;
  return true;
}

/** n bayt yaz. `stop` false ise TEKRARLI START için hat AÇIK bırakılır. */
static bool i2c_yaz(I2C_TypeDef *i2c, uint8_t adres, const uint8_t *veri, uint32_t n, bool stop) {
  if (!i2c_start(i2c, adres, false)) {
    i2c_iptal(i2c);
    return false;
  }
  for (uint32_t i = 0U; i < n; i++) {
    if (!i2c_bekle(&i2c->SR1, I2C_SR1_TXE, true)) {
      i2c_iptal(i2c);
      return false;
    }
    i2c->DR = veri[i];
  }
  if (!i2c_bekle(&i2c->SR1, I2C_SR1_BTF, true)) {
    i2c_iptal(i2c);
    return false;
  }
  if (stop) {
    i2c->CR1 |= I2C_CR1_STOP;
  }
  return true;
}

/**
 * n bayt oku (n >= 1). Referans kılavuzun POLLING akışı:
 *   n == 1 → ADDR'den ÖNCE ACK=0, ADDR temizle, STOP kur, RXNE bekle, oku
 *   n >= 2 → son bayttan önce ACK=0 + STOP
 */
static bool i2c_oku(I2C_TypeDef *i2c, uint8_t adres, uint8_t *veri, uint32_t n) {
  if (n == 0U) {
    return false;
  }
  i2c->CR1 |= I2C_CR1_ACK;
  i2c->CR1 |= I2C_CR1_START;
  if (!i2c_bekle(&i2c->SR1, I2C_SR1_SB, true)) {
    i2c_iptal(i2c);
    return false;
  }
  i2c->DR = (uint32_t)((adres << 1U) | 1U);
  if (!i2c_bekle(&i2c->SR1, I2C_SR1_ADDR, true)) {
    i2c_iptal(i2c);
    return false;
  }
  if (n == 1U) {
    i2c->CR1 &= ~I2C_CR1_ACK;
    (void)i2c->SR1;
    (void)i2c->SR2;
    i2c->CR1 |= I2C_CR1_STOP;
    if (!i2c_bekle(&i2c->SR1, I2C_SR1_RXNE, true)) {
      return false;
    }
    veri[0] = (uint8_t)i2c->DR;
    return true;
  }
  (void)i2c->SR1;
  (void)i2c->SR2;
  for (uint32_t i = 0U; i < n; i++) {
    if (i + 2U == n) {
      /* Sondan bir önceki bayt: ACK'i kes ve STOP'u kur (RM sonrası hat kilitlenmesin). */
      if (!i2c_bekle(&i2c->SR1, I2C_SR1_BTF, true)) {
        i2c_iptal(i2c);
        return false;
      }
      i2c->CR1 &= ~I2C_CR1_ACK;
      i2c->CR1 |= I2C_CR1_STOP;
    } else if (!i2c_bekle(&i2c->SR1, I2C_SR1_RXNE, true)) {
      i2c_iptal(i2c);
      return false;
    }
    veri[i] = (uint8_t)i2c->DR;
  }
  return true;
}

/** Yaz → TEKRARLI START → oku (SMBus/MLX90614 şartı). */
static bool i2c_yaz_sonra_oku(I2C_TypeDef *i2c, uint8_t adres, uint8_t komut, uint8_t *rx,
                              uint32_t n) {
  if (!i2c_yaz(i2c, adres, &komut, 1U, false)) {
    return false;
  }
  return i2c_oku(i2c, adres, rx, n);
}

/* ============================================================================
 * HAT KURTARMA
 * ----------------------------------------------------------------------------
 * ⚠️ BU BLOK ESP'DEN TAŞINDI, sıfırdan yazılmadı: 8266'da sahada gerçekten yaşanan
 * "takılı bus" arızası için `SensorManager::_clearI2CBus / _isI2CBusStuck / _hardResetI2C`
 * yazılmıştı. Uzun kabloda aynı arıza STM'de de olur; kurtarma OLMADAN sensör bir daha
 * geri gelmez ve sıcaklık sessizce donar.
 * Yöntem: pinleri GPIO'ya al, SCL'e 9 darbe (köle bayt ortasında kalmışsa bırakır),
 * elle STOP üret, sonra çevre birimini SWRST'le sıfırla ve yeniden kur.
 * ============================================================================
 */
static void i2c_pin_gpio(SensorHat_t *h, bool gpio_kip) {
  const uint32_t sc = (uint32_t)__builtin_ctz(h->scl_pin);
  const uint32_t sd = (uint32_t)__builtin_ctz(h->sda_pin);
  const uint32_t mod = gpio_kip ? 1U : 2U; /* 1 = output, 2 = alternate function */
  h->port->MODER = (h->port->MODER & ~((3UL << (sc * 2U)) | (3UL << (sd * 2U)))) |
                   (mod << (sc * 2U)) | (mod << (sd * 2U));
}

static void i2c_gecikme_kisa(void) {
  for (volatile uint32_t d = 0U; d < 420U; d++) { /* ~5 µs @168 MHz — 100 kHz yarım periyot */
    __asm volatile("nop");
  }
}

static void i2c_hat_kurtar(SensorHat_t *h) {
  i2c_pin_gpio(h, true);
  h->port->BSRR = (uint32_t)h->sda_pin; /* SDA serbest (open-drain → HIGH) */
  for (uint32_t i = 0U; i < 9U; i++) {
    h->port->BSRR = (uint32_t)h->scl_pin << 16U;
    i2c_gecikme_kisa();
    h->port->BSRR = (uint32_t)h->scl_pin;
    i2c_gecikme_kisa();
  }
  /* Elle STOP: SDA LOW → SCL HIGH → SDA HIGH */
  h->port->BSRR = (uint32_t)h->sda_pin << 16U;
  i2c_gecikme_kisa();
  h->port->BSRR = (uint32_t)h->scl_pin;
  i2c_gecikme_kisa();
  h->port->BSRR = (uint32_t)h->sda_pin;
  i2c_gecikme_kisa();
  i2c_pin_gpio(h, false);

  h->i2c->CR1 |= I2C_CR1_SWRST;
  h->i2c->CR1 &= ~I2C_CR1_SWRST;
  h->i2c->CR2 = I2C_APB1_MHZ;
  h->i2c->CCR = I2C_CCR_100K;
  h->i2c->TRISE = I2C_TRISE_SM;
  h->i2c->CR1 |= I2C_CR1_PE;
  h->ardisik_hata = 0U;
}

static void i2c_hata_islet(SensorHat_t *h) {
  h->veri.i2c_hata++;
  h->ardisik_hata++;
  if (h->ardisik_hata >= I2C_KURTARMA_ESIGI) {
    i2c_hat_kurtar(h);
  }
}

/* ============================================================================
 * MLX90393 yardımcıları
 * ============================================================================
 */
static bool mag_kayit_yaz(SensorHat_t *h, uint8_t kayit, uint16_t deger) {
  /* WR çerçevesi: [WR][veri MSB][veri LSB][kayit << 2] — kütüphane `writeRegister` ile aynı. */
  const uint8_t tx[4] = {MLX90393_KOMUT_WR, (uint8_t)(deger >> 8U), (uint8_t)(deger & 0xFFU),
                         (uint8_t)(kayit << 2U)};
  if (!i2c_yaz(h->i2c, h->mag_adres, tx, sizeof(tx), true)) {
    return false;
  }
  uint8_t st = 0U;
  return i2c_oku(h->i2c, h->mag_adres, &st, 1U);
}

static bool mag_kayit_oku(SensorHat_t *h, uint8_t kayit, uint16_t *deger) {
  const uint8_t tx[2] = {MLX90393_KOMUT_RR, (uint8_t)(kayit << 2U)};
  if (!i2c_yaz(h->i2c, h->mag_adres, tx, sizeof(tx), true)) {
    return false;
  }
  uint8_t rx[3] = {0};
  if (!i2c_oku(h->i2c, h->mag_adres, rx, sizeof(rx))) {
    return false;
  }
  *deger = (uint16_t)(((uint16_t)rx[1] << 8U) | rx[2]);
  return true;
}

static bool mag_tek_komut(SensorHat_t *h, uint8_t komut) {
  if (!i2c_yaz(h->i2c, h->mag_adres, &komut, 1U, true)) {
    return false;
  }
  uint8_t st = 0U;
  return i2c_oku(h->i2c, h->mag_adres, &st, 1U);
}

/** Tek adres yoklaması: cihaz ACK veriyor mu? (yazma yönünde START + adres) */
static bool cihaz_var(SensorHat_t *h, uint8_t adres) {
  if (i2c_start(h->i2c, adres, false)) {
    h->i2c->CR1 |= I2C_CR1_STOP;
    return true;
  }
  i2c_iptal(h->i2c);
  return false;
}

/** Adres tara: önce 0x18 (sahadaki modüller), sonra 0x0C..0x0F. 0 = bulunamadı. */
static uint8_t mag_adres_bul(SensorHat_t *h) {
  static const uint8_t adaylar[] = {MLX90393_ADRES_VARSAYILAN, 0x0CU, 0x0DU, 0x0EU, 0x0FU};
  for (uint32_t i = 0U; i < (sizeof(adaylar) / sizeof(adaylar[0])); i++) {
    if (cihaz_var(h, adaylar[i])) {
      return adaylar[i];
    }
  }
  return 0U;
}

static void mag_yapilandir(SensorHat_t *h) {
  (void)mag_tek_komut(h, MLX90393_KOMUT_EX);
  (void)mag_tek_komut(h, MLX90393_KOMUT_RT);

  uint16_t c1 = 0U;
  if (mag_kayit_oku(h, MLX90393_CONF1, &c1)) {
    c1 = (uint16_t)((c1 & ~0x0070U) | (MLX90393_GAIN_SEL << 4U));
    (void)mag_kayit_yaz(h, MLX90393_CONF1, c1);
  }
  uint16_t c3 = 0U;
  if (mag_kayit_oku(h, MLX90393_CONF3, &c3)) {
    /* RES_X 6:5, RES_Y 8:7, RES_Z 10:9 → hepsi RES_16 (0) · DIG_FILT 4:2 · OSR 1:0 */
    c3 = (uint16_t)(c3 & ~(0x0060U | 0x0180U | 0x0600U | 0x001CU | 0x0003U));
    c3 = (uint16_t)(c3 | (MLX90393_DIG_FILT << 2U) | MLX90393_OSR);
    (void)mag_kayit_yaz(h, MLX90393_CONF3, c3);
  }
}

/* ============================================================================
 * KURULUM
 * ============================================================================
 */
static void hat_donanim_kur(SensorHat_t *h, uint32_t af_kaydir_scl, uint32_t af_kaydir_sda) {
  const uint32_t sc = (uint32_t)__builtin_ctz(h->scl_pin);
  const uint32_t sd = (uint32_t)__builtin_ctz(h->sda_pin);
  /* AF4, open-drain, çok yüksek hız, dahili pull-up (⚠️ HARİCİ 2.2k-4.7k YİNE ŞART) */
  h->port->MODER = (h->port->MODER & ~((3UL << (sc * 2U)) | (3UL << (sd * 2U)))) |
                   (2UL << (sc * 2U)) | (2UL << (sd * 2U));
  h->port->OTYPER |= (uint32_t)(h->scl_pin | h->sda_pin);
  h->port->OSPEEDR |= (3UL << (sc * 2U)) | (3UL << (sd * 2U));
  h->port->PUPDR = (h->port->PUPDR & ~((3UL << (sc * 2U)) | (3UL << (sd * 2U)))) |
                   (1UL << (sc * 2U)) | (1UL << (sd * 2U));
  h->port->AFR[sc >> 3U] =
      (h->port->AFR[sc >> 3U] & ~(0xFUL << af_kaydir_scl)) | (4UL << af_kaydir_scl);
  h->port->AFR[sd >> 3U] =
      (h->port->AFR[sd >> 3U] & ~(0xFUL << af_kaydir_sda)) | (4UL << af_kaydir_sda);

  h->i2c->CR1 |= I2C_CR1_SWRST;
  h->i2c->CR1 &= ~I2C_CR1_SWRST;
  h->i2c->CR2 = I2C_APB1_MHZ;
  h->i2c->CCR = I2C_CCR_100K;
  h->i2c->TRISE = I2C_TRISE_SM;
  h->i2c->CR1 |= I2C_CR1_PE;
}

void PEMF_Sensor_Init(void) {
  RCC->APB1ENR |= RCC_APB1ENR_I2C1EN | RCC_APB1ENR_I2C2EN;
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /* Bobin 6 → I2C1: SCL PB8, SDA PB9   ·   Bobin 7 → I2C2: SCL PB10, SDA PB11 */
  g_hat[0].i2c = I2C1;
  g_hat[0].port = GPIOB;
  g_hat[0].scl_pin = GPIO_PIN_8;
  g_hat[0].sda_pin = GPIO_PIN_9;
  g_hat[1].i2c = I2C2;
  g_hat[1].port = GPIOB;
  g_hat[1].scl_pin = GPIO_PIN_10;
  g_hat[1].sda_pin = GPIO_PIN_11;

  for (uint32_t i = 0U; i < PEMF_SENSOR_BOBIN_SAYISI; i++) {
    SensorHat_t *h = &g_hat[i];
    h->durum = S_BOSTA;
    h->sonraki_tur_ms = 0U;
    h->mag_hazir_ms = 0U;
    h->ardisik_hata = 0U;
    h->tur_sayaci = 0U;
    h->sicaklik_adres = 0U;
    h->veri.sicaklik_ok = false;
    h->veri.alan_ok = false;
    h->veri.nesne_c = 0.0f;
    h->veri.ortam_c = 0.0f;
    h->veri.alan_mt = 0.0f;
    h->veri.i2c_hata = 0U;
  }
  /* AFR kaydırmaları: PB8/PB9 → AFR[1] bit 0/4 · PB10/PB11 → AFR[1] bit 8/12 */
  hat_donanim_kur(&g_hat[0], 0U, 4U);
  hat_donanim_kur(&g_hat[1], 8U, 12U);

  /* ⚠️ İKİ CİHAZ AYRI AYRI YOKLANIR: bir bus'ta yalnız biri olabilir (sahip kablolaması
   * 2026-09-10: PB10/PB11'de YALNIZ manyetik sensör). Bulunamayan cihazın yokluğu hata
   * SAYILMAZ; yoksa var olmayan sensör, aynı bus'taki var olanı hat kurtarmayla sakatlar. */
  for (uint32_t i = 0U; i < PEMF_SENSOR_BOBIN_SAYISI; i++) {
    g_hat[i].sicaklik_adres = cihaz_var(&g_hat[i], MLX90614_ADRES) ? MLX90614_ADRES : 0U;
    g_hat[i].mag_adres = mag_adres_bul(&g_hat[i]);
    if (g_hat[i].mag_adres != 0U) {
      mag_yapilandir(&g_hat[i]);
    }
  }
}

/* ============================================================================
 * POLL — her çağrıda EN FAZLA BİR kısa I2C işlemi
 * ============================================================================
 */
static bool sicaklik_oku(SensorHat_t *h, uint8_t ram, float *cikti) {
  uint8_t rx[3] = {0};
  if (h->sicaklik_adres == 0U) {
    return false; /* o bus'ta MLX90614 YOK — cagiran bunu HATA saymaz */
  }
  if (!i2c_yaz_sonra_oku(h->i2c, h->sicaklik_adres, ram, rx, sizeof(rx))) {
    return false;
  }
  const uint16_t ham = (uint16_t)(((uint16_t)rx[1] << 8U) | rx[0]); /* LSB önce */
  if ((ham & 0x8000U) != 0U) {
    return false; /* MLX90614 hata bayrağı */
  }
  *cikti = ((float)ham * MLX90614_LSB_K) - 273.15f;
  return true;
}

static bool hat_ilerlet(SensorHat_t *h, uint32_t simdi_ms) {
  switch (h->durum) {
  case S_BOSTA:
    if ((int32_t)(simdi_ms - h->sonraki_tur_ms) < 0) {
      return false;
    }
    h->tur_sayaci++;
    /* Sonradan takılan cihazı bul (periyodik; her turda aramak boşa START harcar). */
    if ((h->tur_sayaci % SENSOR_YENIDEN_ARAMA_TUR) == 0U) {
      if (h->sicaklik_adres == 0U) {
        h->sicaklik_adres = cihaz_var(h, MLX90614_ADRES) ? MLX90614_ADRES : 0U;
      }
      if (h->mag_adres == 0U) {
        h->mag_adres = mag_adres_bul(h);
        if (h->mag_adres != 0U) {
          mag_yapilandir(h);
        }
      }
    }
    h->durum = S_TOBJ;
    return false;

  case S_TOBJ: {
    if (h->sicaklik_adres == 0U) {
      /* ⚠️ O BUS'TA SICAKLIK SENSORU YOK → hata SAYILMAZ. Saymak, 5 turda bir hat
       * kurtarma tetikler ve AYNI bus'taki calisan manyetik sensoru sakatlar. */
      h->veri.sicaklik_ok = false;
      h->durum = S_MAG_BASLAT;
      return false;
    }
    float t = 0.0f;
    if (sicaklik_oku(h, MLX90614_RAM_TOBJ1, &t)) {
      h->veri.nesne_c = t;
      h->ardisik_hata = 0U;
      h->durum = S_TA;
    } else {
      h->veri.sicaklik_ok = false;
      i2c_hata_islet(h);
      h->durum = S_MAG_BASLAT; /* sıcaklık yoksa alanı denemeye DEVAM et */
    }
    return false;
  }

  case S_TA: {
    if (h->sicaklik_adres == 0U) {
      h->veri.sicaklik_ok = false;
      h->durum = S_MAG_BASLAT;
      return false;
    }
    float t = 0.0f;
    if (sicaklik_oku(h, MLX90614_RAM_TA, &t)) {
      h->veri.ortam_c = t;
      h->veri.sicaklik_ok = true;
    } else {
      h->veri.sicaklik_ok = false;
      i2c_hata_islet(h);
    }
    h->durum = S_MAG_BASLAT;
    return false;
  }

  case S_MAG_BASLAT:
    /* Yeniden arama S_BOSTA'da periyodik yapılır — burada tekrar aramak her turda
     * eksik adrese boşa START atmak olurdu (bütçe + bus gürültüsü). */
    if ((h->mag_adres == 0U) || !mag_tek_komut(h, MLX90393_KOMUT_SM)) {
      h->veri.alan_ok = false;
      if (h->mag_adres != 0U) {
        i2c_hata_islet(h);
      }
      h->durum = S_BOSTA;
      h->sonraki_tur_ms = simdi_ms + SENSOR_TUR_MS;
      return true; /* tur bitti (eksik de olsa) → telemetri gitsin */
    }
    h->mag_hazir_ms = simdi_ms + MLX90393_DONUSUM_MS;
    h->durum = S_MAG_BEKLE;
    return false;

  case S_MAG_BEKLE:
    /* ⚠️ BURADA `HAL_Delay` YOK: 17 ms damgayla beklenir, ana döngü serbest kalır. */
    if ((int32_t)(simdi_ms - h->mag_hazir_ms) >= 0) {
      h->durum = S_MAG_OKU;
    }
    return false;

  case S_MAG_OKU: {
    uint8_t komut = MLX90393_KOMUT_RM;
    uint8_t rx[7] = {0}; /* durum baytı + 6 veri baytı */
    bool ok = i2c_yaz(h->i2c, h->mag_adres, &komut, 1U, true) &&
              i2c_oku(h->i2c, h->mag_adres, rx, sizeof(rx));
    if (ok) {
      const int16_t xi = (int16_t)(((uint16_t)rx[1] << 8U) | rx[2]);
      const int16_t yi = (int16_t)(((uint16_t)rx[3] << 8U) | rx[4]);
      const int16_t zi = (int16_t)(((uint16_t)rx[5] << 8U) | rx[6]);
      const float x = (float)xi * MLX90393_LSB_XY_UT;
      const float y = (float)yi * MLX90393_LSB_XY_UT;
      const float z = (float)zi * MLX90393_LSB_Z_UT;
      h->veri.alan_mt = sqrtf((x * x) + (y * y) + (z * z)) / 1000.0f; /* µT → mT */
      h->veri.alan_ok = true;
      h->ardisik_hata = 0U;
    } else {
      h->veri.alan_ok = false;
      i2c_hata_islet(h);
    }
    h->durum = S_BOSTA;
    h->sonraki_tur_ms = simdi_ms + SENSOR_TUR_MS;
    return true;
  }

  default:
    h->durum = S_BOSTA;
    return false;
  }
}

bool PEMF_Sensor_Poll(uint32_t simdi_ms) {
  bool tur_bitti = false;
  for (uint32_t i = 0U; i < PEMF_SENSOR_BOBIN_SAYISI; i++) {
    if (hat_ilerlet(&g_hat[i], simdi_ms)) {
      tur_bitti = true;
    }
  }
  return tur_bitti;
}

void PEMF_Sensor_Rapor(uint32_t sira, uint8_t *sicaklik_adres, uint8_t *alan_adres) {
  if (sira >= PEMF_SENSOR_BOBIN_SAYISI) {
    return;
  }
  if (sicaklik_adres != 0) {
    *sicaklik_adres = g_hat[sira].sicaklik_adres;
  }
  if (alan_adres != 0) {
    *alan_adres = g_hat[sira].mag_adres;
  }
}

void PEMF_Sensor_Oku(uint32_t sira, PEMF_SensorVerisi_t *hedef) {
  if ((sira >= PEMF_SENSOR_BOBIN_SAYISI) || (hedef == 0)) {
    return;
  }
  *hedef = g_hat[sira].veri;
}
