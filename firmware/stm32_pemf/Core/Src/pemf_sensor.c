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

/**
 * ZİRVE PENCERESİ (ms) — telemetri periyodu da budur.
 *
 * SAHİP KARARI 2026-09-11: "saniyede 1 sonuç verir en yükseğini". Manyetik sensör
 * pencere boyunca SÜREKLİ örneklenir, pencere kapanınca EN BÜYÜK |B| raporlanır ve
 * biriktirici sıfırlanır. UART yükü DEĞİŞMEZ (hâlâ saniyede bir satır) — değişen,
 * o satırdaki sayının ne anlama geldiği.
 */
#define SENSOR_ZIRVE_PENCERE_MS 1000U

/* ⚠️ AYRI BİR "SICAKLIK PERİYODU" SABİTİ YOK — BİLEREK. Sıcaklık isteği zirve
 * penceresi kapanınca (`pencere_kapat`) set edilir, yani periyodu TANIMI GEREĞİ
 * `SENSOR_ZIRVE_PENCERE_MS`tir. İkinci bir sabit koymak, iki sayının sessizce
 * ayrışabildiği ve birinin hiç okunmadığı klasik "sihirli sayı ikinci yerde"
 * tuzağını açardı. MLX90614'ün termal zaman sabiti zaten saniyeler mertebesinde;
 * daha hızlı okumak I2C bütçesini yer, bilgi getirmez. */

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
 * AYAR: HALLCONF = 0xC (varsayılan) · GAIN_SEL = 0 · RES_XYZ = 0 (RES_16)
 *       OSR = 0 · DIG_FILT = 0
 *
 * ÖLÇEK (Adafruit_MLX90393.h `mlx90393_lsb_lookup[HALLCONF=0xC][GAIN_SEL=0][RES_16]`):
 *   X,Y → 0.751 µT/LSB      Z → 1.210 µT/LSB
 *
 * ============================================================================
 * ⚠️⚠️ ÖLÇEK NEDEN DEĞİŞTİ — ESKİ AYAR SAHİBİN ALANINI ÖLÇEMİYORDU
 * ============================================================================
 * Bu dosya GAIN_SEL = 7 ile başladı (0.150/0.242 µT/LSB, ESP8266 ile birebir).
 * Sahip 2026-09-11'de ölçüm bandını verdi: **"1-10 mT arası genelde, 0-5 arası
 * aşırı fazla"**. GAIN_SEL = 7 + RES_16'nın TAM ÖLÇEĞİ ise:
 *      XY = 32767 × 0.150 µT = **4,92 mT**      Z = 32767 × 0.242 µT = **7,93 mT**
 * Yani istenen bandın ÜST YARISI ÖLÇÜLEMİYORDU.
 *
 * ⚠️ VE TAŞMA SESSİZDİR: RES_16'da cihaz 19-bit sonucun ALT 16 BİTİNİ verir; aşan değer
 * KIRPILMAZ, **SARAR**. 6 mT'lik gerçek bir alan küçük ya da NEGATİF bir sayı olarak
 * okunur. Zirve mantığı bu yanlış sayıyı "maksimum" diye kilitleyebilirdi. Sarmayı
 * yazılımdan tespit etmek mümkün değildir — TEK savunma yeterli aralıktır.
 *
 * GAIN_SEL = 0 ile tam ölçek:  XY = **±24,6 mT**   Z = **±39,6 mT**
 * → sahibin bandına (≤10 mT) 2,4 kat pay; anahtarlama sırasındaki aşımlar da güvende.
 * Çözünürlük 0,751 µT = 0,00075 mT → 1 mT'lik okumada %0,08. Telemetri 3 haneye
 * yuvarlıyor (`B=%.3f`), yani ÇÖZÜNÜRLÜK KAYBI GÖRÜNMEZ.
 *
 * ⚠️ KIYASLANABİLİRLİK NOTU: bu dosyada "bu iki sayı ESP'nin ürettiği değerin
 * kaynağıdır, değiştirmek geçmişle kıyaslanabilirliği bozar" yazıyordu. Karar bilerek
 * değiştirildi: 4,92 mT üstündeki ESKİ kayıtlar ZATEN yanlıştı (sarmıştı), dolayısıyla
 * korunacak bir kıyaslanabilirlik yoktu. ESP-S3 de AYNI ayara çekildi
 * (firmware/esps3_pemf_coil/SensorManager.cpp, `MLX90393_GAIN_5X`) → iki kart aynı
 * ölçeği kullanır. ⚠️ ESP8266 firmware'i DOKUNULMADI (GAIN 1X, ±4,92 mT).
 *
 * ============================================================================
 * HIZ — SAHİP "OKUMA HIZINI MAXLA" DEDİ
 * ============================================================================
 * `mlx90393_tconv[DIG_FILT][OSR]` en küçüğü DIG_FILT = 0, OSR = 0 → **1,27 ms**
 * (eski ayar DIG_FILT=1/OSR=3 → 6,84 ms, üstüne kütüphanenin +10 ms'i = 17 ms).
 * Gürültü artar ama sinyal 1-10 mT = 1300-13000 LSB; OSR gürültüsü mertebelerce altta.
 *
 * ⚠️ 1,27 ms'i `HAL_GetTick()` ile BEKLEYEMEYİZ: tick 1 ms çözünürlüklü ve damganın
 * hemen ardından sınır geçerse "2 tick" aslında 1,0 ms olabilir → dönüşüm BİTMEDEN
 * okunur. Bu yüzden bekleme **DWT çevrim sayacıyla** (168 MHz, ~6 ns) yapılır:
 * `MLX90393_DONUSUM_US` = 1400 µs (tconv + %10 pay). DWT çalışmazsa (sayaç ilerlemiyor)
 * `MLX90393_DONUSUM_MS_YEDEK` = 3 tick'e düşülür — 3 tick ≥ 2,0 ms > 1,27 ms GARANTİ.
 *
 * Örnek periyodu ≈ 1,4 ms dönüşüm + ~1,0 ms I2C (100 kHz'de SM 2 bayt + RM 8 bayt)
 * ≈ 2,4 ms → **~425 Hz**. 100 Hz'lik bir bobin darbesinde ~4 örnek düşer; kare dalganın
 * tepesi PLATODUR (sivri uç değil) → zirve yakalanır.
 * ⚠️ I2C 100 kHz'de KALDI (400 kHz'e çıkmak kabin boyu kabloda gürültü payını yer,
 * bkz. yukarısı). Daha fazla hız gerekirse sıradaki adım BURST kipidir, hız değil.
 *
 * BÜYÜKLÜK: |B| = sqrt(x²+y²+z²) / 1000 → **mT**; pencerede EN BÜYÜĞÜ raporlanır.
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
#define MLX90393_GAIN_SEL 0U
#define MLX90393_OSR 0U
#define MLX90393_DIG_FILT 0U
#define MLX90393_LSB_XY_UT 0.751f
#define MLX90393_LSB_Z_UT 1.210f

/** SYSCLK (MHz). main.c: SYSCLK 168 MHz, APB1 = /4 = 42 MHz → aşağıdaki iddia bunu pinler. */
#define SISTEM_MHZ 168U
_Static_assert(SISTEM_MHZ == (I2C_APB1_MHZ * 4U), "SISTEM_MHZ ile APB1 bolucusu uyusmuyor");

/** Dönüşüm beklemesi (µs): tconv[DIG_FILT=0][OSR=0] = 1270 µs + %10 pay. */
#define MLX90393_DONUSUM_US 1400U
#define MLX90393_DONUSUM_CYC (MLX90393_DONUSUM_US * SISTEM_MHZ) /* 235.200 < 2^31 */

/** DWT yoksa tick yedeği. 3 tick ≥ 2,0 ms GARANTİ (> 1,27 ms tconv). */
#define MLX90393_DONUSUM_MS_YEDEK 3U

/**
 * Ham eksen bu eşiği geçerse tam ölçeğe DAYANMIŞ sayılır (int16 tam ölçek 32767).
 * ⚠️ Bu bir ERKEN UYARIDIR, sarma tespiti DEĞİL: sarmış değer küçük görünür ve
 * hiçbir eşikle yakalanamaz. Bkz. yukarıdaki GAIN_SEL gerekçesi.
 */
#define MLX90393_HAM_DOYGUNLUK 32000

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
  uint32_t tur_sayaci;    /**< KAPANAN pencere sayısı — yeniden arama zamanlaması */
  SensorDurum_t durum;
  uint32_t pencere_bitis_ms; /**< zirve penceresinin kapanış damgası (1 s) */
  uint32_t mag_hazir_ms;     /**< dönüşüm beklemesi — DWT YOKKEN tick yedeği */
  uint32_t mag_hazir_cyc;    /**< dönüşüm beklemesi — DWT çevrim hedefi (asıl yol) */
  bool sicaklik_istegi;      /**< pencere açılışında set; S_BOSTA sıcaklığı öne alır */
  bool sicaklik_taze;        /**< BU pencerede sıcaklık BAŞARIYLA okundu */
  float zirve_mt;            /**< pencere içi EN BÜYÜK |B| (mT) */
  uint32_t zirve_ornek;      /**< pencere içi geçerli örnek sayısı */
  bool zirve_doygun;         /**< pencerede en az bir örnek tam ölçeğe dayandı */
  uint16_t ardisik_hata;
  PEMF_SensorVerisi_t veri;
} SensorHat_t;

static SensorHat_t g_hat[PEMF_SENSOR_BOBIN_SAYISI];

/**
 * Hat → telemetri bobin kimliği. Sahip kararı 2026-09-11: TEK manyetik sensör I2C2'de
 * ama arayüzde **bobin 6**'da görünmeli. Gerekçe: pemf_sensor.h.
 */
static const uint8_t g_bobin_idleri[] = PEMF_SENSOR_BOBIN_IDLERI;
_Static_assert((sizeof(g_bobin_idleri) / sizeof(g_bobin_idleri[0])) == PEMF_SENSOR_BOBIN_SAYISI,
               "PEMF_SENSOR_BOBIN_IDLERI tablosu hat sayisiyla uyusmuyor");

/**
 * DWT çevrim sayacı kullanılabilir mi (açılışta ÖLÇÜLÜR, varsayılmaz).
 *
 * ⚠️ NEDEN ÖLÇÜLÜYOR: 1,27 ms'lik dönüşüm beklemesi bu sayaca dayanıyor. Sayaç
 * ilerlemezse (bazı kartlarda TRCENA açılmaz) `CYCCNT` sabit kalır, hedef ÇEVRİM
 * ASLA gelmez ve manyetik durum makinesi S_MAG_BEKLE'de SONSUZA KADAR TAKILIR —
 * ana döngü dönmeye devam ettiği için ölü-adam watchdog'u bunu YAKALAMAZ ve alan
 * telemetrisi sessizce kesilir. Sayaç ilerlemiyorsa tick yedeğine düşülür.
 */
static bool g_dwt_var = false;

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

/**
 * DWT çevrim sayacını açar ve GERÇEKTEN ilerlediğini ÖLÇER.
 * Ölçmezsek, ilerlemeyen bir sayaç manyetik okumayı sessizce sonsuza kadar durdurur.
 */
static void dwt_baslat(void) {
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CYCCNT = 0U;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  const uint32_t t0 = DWT->CYCCNT;
  for (volatile uint32_t i = 0U; i < 64U; i++) {
    __NOP();
  }
  g_dwt_var = (DWT->CYCCNT != t0);
}

/** Dönüşüm süresi doldu mu? DWT varsa µs, yoksa tick çözünürlüğünde. */
static bool mag_donusum_bitti(const SensorHat_t *h, uint32_t simdi_ms) {
  if (g_dwt_var) {
    return ((int32_t)(DWT->CYCCNT - h->mag_hazir_cyc) >= 0);
  }
  return ((int32_t)(simdi_ms - h->mag_hazir_ms) >= 0);
}

/** Ham eksen tam ölçeğe dayandı mı? (erken uyarı; sarma tespiti DEĞİL) */
static bool ham_doygun(int16_t v) {
  return (v >= MLX90393_HAM_DOYGUNLUK) || (v <= -MLX90393_HAM_DOYGUNLUK);
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
  dwt_baslat();
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
    /* ⚠️ Pencere ŞİMDİDEN başlar: 0 verilirse ilk `Poll` çağrısı pencereyi hemen
     * kapatır ve HİÇ örneği olmayan bir "tur bitti" üretir. */
    h->pencere_bitis_ms = HAL_GetTick() + SENSOR_ZIRVE_PENCERE_MS;
    h->mag_hazir_ms = 0U;
    h->mag_hazir_cyc = 0U;
    h->sicaklik_istegi = true;
    h->sicaklik_taze = false;
    h->zirve_mt = 0.0f;
    h->zirve_ornek = 0U;
    h->zirve_doygun = false;
    h->ardisik_hata = 0U;
    h->tur_sayaci = 0U;
    h->sicaklik_adres = 0U;
    h->veri.sicaklik_ok = false;
    h->veri.alan_ok = false;
    h->veri.nesne_c = 0.0f;
    h->veri.ortam_c = 0.0f;
    h->veri.alan_mt = 0.0f;
    h->veri.alan_ornek = 0U;
    h->veri.alan_doygun = false;
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

/**
 * ZİRVE PENCERESİNİ KAPAT — biriken en büyük |B|'yi rapora yansıt, biriktiriciyi sıfırla.
 *
 * ⚠️ ÖRNEK YOKSA ESKİ ZİRVE KORUNMAZ, 0.0 DA YAZILMAZ: `alan_ok=false` ile alan
 * telemetriye HİÇ girmez. Bayat bir sayıyı "bu saniyenin ölçümü" diye göndermek,
 * ölçülmeyeni 0.0 göndermekle aynı sınıf yalandır (bkz. dosya başlığı).
 */
static void pencere_kapat(SensorHat_t *h, uint32_t simdi_ms) {
  if (h->zirve_ornek > 0U) {
    h->veri.alan_mt = h->zirve_mt;
    h->veri.alan_ornek =
        (h->zirve_ornek > 65535U) ? (uint16_t)65535U : (uint16_t)h->zirve_ornek;
    h->veri.alan_doygun = h->zirve_doygun;
    h->veri.alan_ok = true;
  } else {
    h->veri.alan_ok = false;
    h->veri.alan_ornek = 0U;
    h->veri.alan_doygun = false;
  }
  h->veri.sicaklik_ok = h->sicaklik_taze;

  h->zirve_mt = 0.0f;
  h->zirve_ornek = 0U;
  h->zirve_doygun = false;
  h->sicaklik_taze = false;
  h->sicaklik_istegi = true;
  h->tur_sayaci++;

  /* Sabit adım → kayma birikmez. Uzun bir duraklamadan sonra (hat kurtarma vb.)
   * geçmişte kalan damgayı şimdiye çekmezsek pencere ARDI ARDINA kapanır. */
  h->pencere_bitis_ms += SENSOR_ZIRVE_PENCERE_MS;
  if ((int32_t)(simdi_ms - h->pencere_bitis_ms) >= 0) {
    h->pencere_bitis_ms = simdi_ms + SENSOR_ZIRVE_PENCERE_MS;
  }

  /* Sonradan takılan cihazı periyodik ara (her pencerede aramak boşa START harcar). */
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
}

/**
 * Durum makinesini BİR adım ilerletir (her çağrıda EN FAZLA bir kısa I2C işlemi).
 *
 * AKIŞ (2026-09-11 sahip kararıyla yeniden yazıldı):
 *   · Manyetik ölçüm SÜREKLİ döner: SM → (1,4 ms) → RM → zirveyi güncelle → SM …
 *     ≈ 2,4 ms/örnek ≈ 425 Hz. ESKİ hâli saniyede BİR örnek alıyordu ve bobin
 *     darbesinin neresine denk geldiği tesadüftü.
 *   · Sıcaklık saniyede bir kez araya girer (MLX90614'ün termal zaman sabiti saniyeler;
 *     hızlandırmak I2C bütçesini yer, bilgi getirmez).
 *   · Saniyelik pencere kapanınca zirve raporlanır ve `true` döner → telemetri satırı.
 *
 * @return true → pencere kapandı (telemetri basılabilir)
 */
static bool hat_ilerlet(SensorHat_t *h, uint32_t simdi_ms) {
  bool pencere_kapandi = false;
  if ((int32_t)(simdi_ms - h->pencere_bitis_ms) >= 0) {
    pencere_kapat(h, simdi_ms);
    pencere_kapandi = true;
  }

  switch (h->durum) {
  case S_BOSTA:
    /* Sıcaklık isteği varsa ÖNCE o; yoksa/sensör yoksa doğrudan manyetiğe dön. */
    if (h->sicaklik_istegi) {
      h->sicaklik_istegi = false;
      if (h->sicaklik_adres != 0U) {
        h->durum = S_TOBJ;
        break;
      }
      /* ⚠️ O BUS'TA SICAKLIK SENSÖRÜ YOK → hata SAYILMAZ (yoksa 5 turda bir hat
       * kurtarma tetikler ve AYNI bus'taki çalışan manyetik sensörü sakatlar). */
    }
    if (h->mag_adres != 0U) {
      h->durum = S_MAG_BASLAT;
    }
    break;

  case S_TOBJ: {
    if (h->sicaklik_adres == 0U) {
      h->durum = S_BOSTA;
      break;
    }
    float t = 0.0f;
    if (sicaklik_oku(h, MLX90614_RAM_TOBJ1, &t)) {
      h->veri.nesne_c = t;
      h->ardisik_hata = 0U;
      h->durum = S_TA;
    } else {
      i2c_hata_islet(h);
      h->durum = S_BOSTA; /* sıcaklık düştü → manyetiği BEKLETME */
    }
    break;
  }

  case S_TA: {
    if (h->sicaklik_adres == 0U) {
      h->durum = S_BOSTA;
      break;
    }
    float t = 0.0f;
    if (sicaklik_oku(h, MLX90614_RAM_TA, &t)) {
      h->veri.ortam_c = t;
      h->sicaklik_taze = true; /* TOBJ+TA ikisi de geldi → pencerede sıcaklık GEÇERLİ */
      h->ardisik_hata = 0U;
    } else {
      i2c_hata_islet(h);
    }
    h->durum = S_BOSTA;
    break;
  }

  case S_MAG_BASLAT:
    /* Yeniden arama pencere kapanışında yapılır — burada aramak her örnekte eksik
     * adrese boşa START atmak olurdu (bütçe + bus gürültüsü). */
    if (h->mag_adres == 0U) {
      h->durum = S_BOSTA;
      break;
    }
    if (!mag_tek_komut(h, MLX90393_KOMUT_SM)) {
      i2c_hata_islet(h);
      h->durum = S_BOSTA;
      break;
    }
    if (g_dwt_var) {
      h->mag_hazir_cyc = DWT->CYCCNT + MLX90393_DONUSUM_CYC;
    } else {
      h->mag_hazir_ms = simdi_ms + MLX90393_DONUSUM_MS_YEDEK;
    }
    h->durum = S_MAG_BEKLE;
    break;

  case S_MAG_BEKLE:
    /* ⚠️ BURADA `HAL_Delay` YOK: damgayla beklenir, ana döngü serbest kalır. */
    if (mag_donusum_bitti(h, simdi_ms)) {
      h->durum = S_MAG_OKU;
    }
    break;

  case S_MAG_OKU: {
    uint8_t komut = MLX90393_KOMUT_RM;
    uint8_t rx[7] = {0}; /* durum baytı + 6 veri baytı */
    if (i2c_yaz(h->i2c, h->mag_adres, &komut, 1U, true) &&
        i2c_oku(h->i2c, h->mag_adres, rx, sizeof(rx))) {
      const int16_t xi = (int16_t)(((uint16_t)rx[1] << 8U) | rx[2]);
      const int16_t yi = (int16_t)(((uint16_t)rx[3] << 8U) | rx[4]);
      const int16_t zi = (int16_t)(((uint16_t)rx[5] << 8U) | rx[6]);
      const float x = (float)xi * MLX90393_LSB_XY_UT;
      const float y = (float)yi * MLX90393_LSB_XY_UT;
      const float z = (float)zi * MLX90393_LSB_Z_UT;
      const float mt = sqrtf((x * x) + (y * y) + (z * z)) / 1000.0f; /* µT → mT */
      if (mt > h->zirve_mt) {
        h->zirve_mt = mt;
      }
      if (ham_doygun(xi) || ham_doygun(yi) || ham_doygun(zi)) {
        h->zirve_doygun = true;
      }
      h->zirve_ornek++;
      h->ardisik_hata = 0U;
    } else {
      i2c_hata_islet(h);
    }
    h->durum = S_BOSTA;
    break;
  }

  default:
    h->durum = S_BOSTA;
    break;
  }
  return pencere_kapandi;
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

uint32_t PEMF_Sensor_BobinId(uint32_t sira) {
  if (sira >= PEMF_SENSOR_BOBIN_SAYISI) {
    return 0U;
  }
  return (uint32_t)g_bobin_idleri[sira];
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
