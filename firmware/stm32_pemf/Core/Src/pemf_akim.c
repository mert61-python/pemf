/**
 ******************************************************************************
 * @file    pemf_akim.c
 * @brief   Bobin 1-5 ACS712-30A akım ölçümü — ADC1, registre seviyesi, bloklamayan
 *
 * Gerekçeler, seviye uyuşmazlığı ve kalibrasyon matematiği için `pemf_akim.h` başlığını oku.
 *
 * ✅ DERLENİYOR (2026-09-11): `scripts/firmware_derle.py`. ⚠️ "Bu depoda C derlenmez" diyen
 * eski not YANLIŞTI — makinede ARM derleyicisi kuruluymuş.
 *
 * ⚠️ TEZGÂHTA DOĞRULANMADI ve **ACS712'ler HENÜZ BAĞLI DEĞİL** (arayüzde bobin 1-5 akımı
 * kısa çizgi görünüyorsa sebebi budur; açılıştaki `-> STM_SENS: C=n ACS712=...` satırı
 * hangisi olduğunu söyler). Kabul kriteri: bilinen bir yükte pens ampermetre ile STM
 * okuması %5 içinde; ayrıca bobin kapalıyken okuma < 0,15 A (offset kalibrasyonu doğru).
 ******************************************************************************
 */

#include "pemf_akim.h"

#include "main.h"
#include <math.h>

/* ============================================================================
 * PİNLER VE KANALLAR — NTC bloğundan DEVRALINDI
 * ----------------------------------------------------------------------------
 * `main.c`'deki derleme-kapılı NTC bloğu bu beş pini ADC1 için AYIRMIŞTI ama NTC'ler
 * hiç bağlanmadı ve sahip 2026-09-10'da termal kesme İSTEMEDİ → pinler serbest kaldı,
 * ACS712'ler buraya bağlanıyor.
 *
 * ⚠️ AYNI PİNİ İKİ ÇEVRE BİRİMİ KULLANAMAZ: `PEMF_NTC_TERMAL_ENABLED` 1 yapılırsa NTC
 * bloğu da ADC1'i kurar ve AYNI kanalları okur → iki okuyucu, tanımsız sonuç.
 * Bu yüzden aşağıda bir derleme-zamanı çatışma kapısı var.
 * ============================================================================
 */
#if defined(PEMF_NTC_TERMAL_ENABLED) && (PEMF_NTC_TERMAL_ENABLED != 0)
#error "PEMF_NTC_TERMAL_ENABLED ile pemf_akim.c AYNI ADC1 kanallarini kullanir (PA0 PA3 PA4 PC0 PC3). Birini secin."
#endif

/** Bobin 1..5 → ADC1 kanalı: PA0=IN0, PA3=IN3, PA4=IN4, PC0=IN10, PC3=IN13 */
static const uint8_t g_kanal[PEMF_AKIM_BOBIN_SAYISI] = {0U, 3U, 4U, 10U, 13U};
_Static_assert(sizeof(g_kanal) / sizeof(g_kanal[0]) == PEMF_AKIM_BOBIN_SAYISI,
               "g_kanal uzunlugu PEMF_AKIM_BOBIN_SAYISI ile ayrismis (eksik eleman SESSIZCE "
               "0 olur -> BASKA bir bobinin kanali okunur)");

/* ============================================================================
 * ÖLÇEK SABİTLERİ
 * ============================================================================
 */
/** ADC referansı (VDDA). Nucleo-F429ZI'de 3V3 rayı. */
#define ADC_VREF_V 3.30f
/** 12-bit ADC tam ölçek. */
#define ADC_TAM_OLCEK 4095.0f
/** ACS712-30A nominal hassasiyet (VCC = 5 V'ta). ⚠️ RATİOMETRİK → `k` ile ölçeklenir. */
#define ACS712_30A_V_PER_A 0.066f
/** ACS712 nominal 0 A çıkışı = VCC/2 (VCC = 5 V). */
#define ACS712_NOMINAL_OFFSET_V 2.50f
/**
 * Harici gerilim bölücü oranı — ⚠️ SAHİP BİLDİRİMİ 2026-09-10: **BÖLÜCÜ YOK** → 1.0.
 * Bu sabit ÖLÇÜMDE KULLANILMAZ (ölçüm `k`dan türer); yalnız aşağıdaki doygunluk
 * tavanının BELGELENMESİ için durur. 10k/20k eklenirse 0.667 yaz.
 */
#define AKIM_BOLUCU_ORANI 1.0f

/** Doygunluk eşiği: ham değer buna değerse ADC tavanına dayanmış say. */
#define ADC_DOYGUNLUK_HAM 4085U

/** Offset kalibrasyonunda kanal başına örnek sayısı (ESP'de 100). */
#define KALIBRASYON_ORNEK 100U
/** RMS penceresi: kanal başına örnek sayısı (ESP'de 10 → aynı büyüklük). */
#define RMS_ORNEK 10U

/**
 * ADC dönüşüm beklemesi için ÇEVRİM BÜTÇESİ.
 * ⚠️ NEDEN SAYAÇ: `while (!(SR & EOC))` bir ADC arızasında kartı KİLİTLER → ana döngü
 * durur → ölü-adam watchdog'u SAHTE kopuş görür → tedavi ortasında bobinler kesilir.
 * NTC bloğu da aynı deseni kullanıyordu (`main.c`, `bekle` sayacı).
 */
#define ADC_SPIN_BUTCESI 20000U

/* ============================================================================
 * DURUM
 * ============================================================================
 */
static float g_offset_v[PEMF_AKIM_BOBIN_SAYISI];
static float g_hassasiyet[PEMF_AKIM_BOBIN_SAYISI]; /**< V/A, `k` ile düzeltilmiş */
static PEMF_AkimVerisi_t g_veri[PEMF_AKIM_BOBIN_SAYISI];
static uint32_t g_sira = 0U;
static bool g_kalibre = false;

/* ============================================================================
 * REGISTRE SEVİYESİ ADC1
 * ----------------------------------------------------------------------------
 * `HAL_ADC_MODULE_ENABLED` KAPALI ve `Drivers/.../Src` içinde `stm32f4xx_hal_adc.c` YOK.
 * NTC bloğu da tam bu gerekçeyle registre seviyesindeydi — aynı desen.
 * ============================================================================
 */
static void adc_donanim_kur(void) {
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();

  /* PA0, PA3, PA4 ve PC0, PC3 → ANALOG kip (MODER = 11), pull YOK */
  GPIOA->MODER |= (3UL << (0U * 2U)) | (3UL << (3U * 2U)) | (3UL << (4U * 2U));
  GPIOA->PUPDR &= ~((3UL << (0U * 2U)) | (3UL << (3U * 2U)) | (3UL << (4U * 2U)));
  GPIOC->MODER |= (3UL << (0U * 2U)) | (3UL << (3U * 2U));
  GPIOC->PUPDR &= ~((3UL << (0U * 2U)) | (3UL << (3U * 2U)));

  RCC->APB2ENR |= RCC_APB2ENR_ADC1EN;
  ADC->CCR = (ADC->CCR & ~ADC_CCR_ADCPRE) | ADC_CCR_ADCPRE_0; /* PCLK2/4 = 21 MHz ≤ 36 MHz */
  ADC1->CR1 = 0U;                                             /* 12-bit, tek dönüşüm */
  /* Tüm kanallara EN YAVAŞ örnekleme (480 çevrim): ACS712 çıkış empedansı ~1 Ω olsa da
   * uzun kablo + PWM gürültüsü var; yavaş örnekleme örnekleme-tutma kapasitörüne zaman verir. */
  ADC1->SMPR1 = 0x07FFFFFFU;
  ADC1->SMPR2 = 0x3FFFFFFFU;
  ADC1->CR2 = ADC_CR2_ADON;
}

/** Tek dönüşüm. @return ham 0-4095, ya da 0xFFFF (bütçe doldu = ARIZA). */
static uint16_t adc_oku(uint8_t kanal) {
  ADC1->SQR3 = (uint32_t)kanal;
  ADC1->CR2 |= ADC_CR2_SWSTART;
  uint32_t butce = ADC_SPIN_BUTCESI;
  while (((ADC1->SR & ADC_SR_EOC) == 0U) && (butce > 0U)) {
    butce--;
  }
  if (butce == 0U) {
    return 0xFFFFU;
  }
  return (uint16_t)(ADC1->DR & 0x0FFFU);
}

static float ham_volt(uint16_t ham) {
  return ((float)ham / ADC_TAM_OLCEK) * ADC_VREF_V;
}

/* ============================================================================
 * KURULUM + OFFSET KALİBRASYONU
 * ============================================================================
 */
void PEMF_Akim_Init(void) {
  adc_donanim_kur();

  bool hepsi_ok = true;
  for (uint32_t i = 0U; i < PEMF_AKIM_BOBIN_SAYISI; i++) {
    g_veri[i].amper = 0.0f;
    g_veri[i].ok = false;
    g_veri[i].doygun = false;
    g_veri[i].ham = 0U;

    /* ⚠️ BOBİNLER KAPALIYKEN: offset = 0 A çıkışı. Akım varken kalibre edilirse
     * offset yanlış olur ve o bobinin TÜM ölçümleri kalıcı olarak kayar. */
    float toplam = 0.0f;
    uint32_t gecerli = 0U;
    for (uint32_t n = 0U; n < KALIBRASYON_ORNEK; n++) {
      const uint16_t ham = adc_oku(g_kanal[i]);
      if (ham == 0xFFFFU) {
        continue;
      }
      toplam += ham_volt(ham);
      gecerli++;
    }
    if (gecerli < (KALIBRASYON_ORNEK / 2U)) {
      /* Kanal okunamıyor (ADC arızası) → bu bobin için akım BİLDİRİLMEZ.
       * Sahte 0.0 A göndermek "ölçüldü" gibi kaydedilir. */
      g_offset_v[i] = 0.0f;
      g_hassasiyet[i] = 0.0f;
      hepsi_ok = false;
      continue;
    }
    g_offset_v[i] = toplam / (float)gecerli;

    /* Ratiometrik düzeltme: k = offset / (VCC/2 nominal). k, 5 V rayının gerçek değerini,
     * varsa harici bölücüyü ve sensör offset toleransını BİRDEN yakalar.
     * ⚠️ ESP'de bu k hesaplanıyor ama KULLANILMIYOR (SensorManager.cpp:508); burada kullanılır. */
    const float k = g_offset_v[i] / ACS712_NOMINAL_OFFSET_V;
    /* Makul olmayan offset (sensör yok / kısa devre / hat açık) → bildirme. Bölücüsüz beklenen
     * ~2,5 V; 10k/20k bölücüyle ~1,67 V. 0,5-3,2 V penceresi ikisini de kapsar. */
    if ((g_offset_v[i] < 0.5f) || (g_offset_v[i] > 3.2f) || (k <= 0.05f)) {
      g_hassasiyet[i] = 0.0f;
      hepsi_ok = false;
      continue;
    }
    g_hassasiyet[i] = ACS712_30A_V_PER_A * k;
  }
  g_kalibre = true;
  (void)hepsi_ok; /* kanal başına `ok` bayrağı Poll'da kuruluyor */
  g_sira = 0U;
}

/* ============================================================================
 * POLL — her çağrıda BİR kanal
 * ============================================================================
 */
bool PEMF_Akim_Poll(void) {
  if (!g_kalibre) {
    return false;
  }
  const uint32_t i = g_sira;
  PEMF_AkimVerisi_t *v = &g_veri[i];

  if (g_hassasiyet[i] <= 0.0f) {
    /* Kalibrasyon başarısız → bu bobin için akım YOK (alan telemetriye girmez). */
    v->ok = false;
    v->doygun = false;
  } else {
    float kareler = 0.0f;
    uint32_t gecerli = 0U;
    bool doygun = false;
    uint16_t son_ham = 0U;
    for (uint32_t n = 0U; n < RMS_ORNEK; n++) {
      const uint16_t ham = adc_oku(g_kanal[i]);
      if (ham == 0xFFFFU) {
        continue;
      }
      son_ham = ham;
      if (ham >= ADC_DOYGUNLUK_HAM) {
        doygun = true; /* ⚠️ ADC tavanı: bölücüsüz ~12 A üstü — sayı GÜVENİLMEZ */
      }
      const float akim = (ham_volt(ham) - g_offset_v[i]) / g_hassasiyet[i];
      kareler += akim * akim;
      gecerli++;
    }
    if (gecerli == 0U) {
      v->ok = false;
      v->doygun = false;
    } else {
      v->amper = sqrtf(kareler / (float)gecerli);
      v->ham = son_ham;
      v->doygun = doygun;
      /* Doygunken de `ok` KALIR ama `doygun` işaretlidir: üst katman sayıyı gönderirken
       * güvenilmezliği taşıyabilsin. Sessizce yanlış sayı göndermek yasak. */
      v->ok = true;
    }
  }

  g_sira++;
  if (g_sira >= PEMF_AKIM_BOBIN_SAYISI) {
    g_sira = 0U;
    return true; /* tur tamamlandı */
  }
  return false;
}

void PEMF_Akim_Oku(uint32_t sira, PEMF_AkimVerisi_t *hedef) {
  if ((sira >= PEMF_AKIM_BOBIN_SAYISI) || (hedef == 0)) {
    return;
  }
  *hedef = g_veri[sira];
}
