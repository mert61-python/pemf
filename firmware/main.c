/**
 ******************************************************************************
 * @file    main.c
 * @brief   STM32F4 — 5-Kanal Yazılımsal DDS Bipolar Full Bridge PWM Kontrolörü
 * @version 2.2.0 (Software DDS — Bipolar Full Bridge + ref_ms Senkron Desteği)
 *
 * ============================================================================
 * MİMARİ ÖZET
 * ============================================================================
 *
 *  ┌───────────────────────────────────────────────────────────────────────┐
 *  │  YAZILIMSAL DDS BİPOLAR FULL BRIDGE                                 │
 *  │                                                                     │
 *  │  TIM1 (50 kHz Kesme Kaynağı) — APB2, 168 MHz                       │
 *  │    Yalnızca Update Interrupt üretir — PWM kanalı KULLANILMAZ        │
 *  │    Her kesmede yazılımsal DDS ile 5 bobinin GPIO çıkışı üretilir    │
 *  │                                                                     │
 *  │  GPIO Çıkışları (Push-Pull, doğrudan BSRR ile sürülür):            │
 *  │    PC8  (IN_A Bobin 1)   PD12 (IN_B Bobin 1)                      │
 *  │    PC9  (IN_A Bobin 2)   PE10 (IN_B Bobin 2)                      │
 *  │    PD10 (IN_A Bobin 3)   PD11 (IN_B Bobin 3)                      │
 *  │    PC6  (IN_A Bobin 4)   PC7  (IN_B Bobin 4)                      │
 *  │    PA8  (IN_A Bobin 5)   PA9  (IN_B Bobin 5)                      │
 *  │                                                                     │
 *  │  Her bobin BAĞIMSIZ faz kaydırmasına sahiptir!                      │
 *  │  Dead Time: A/B geçişinde NOP döngüsü (DDS_DEADTIME_NOP_ITERS) — ÖLÇÜLMEMİŞ  │
 *  └───────────────────────────────────────────────────────────────────────┘
 *
 *  ┌───────────────────────────────────────────────────────────────────────┐
 *  │  GLITCH-FREE GÜNCELLEME MEKANİZMASI                                 │
 *  │                                                                     │
 *  │  PC ──UART──► ISR State Machine ──► g_shadow (main döngüsü)        │
 *  │                                           │                         │
 *  │                       DDS Periyot Başı    │ (her 500 tick = 10ms)   │
 *  │                                           ▼                         │
 *  │                        g_shadow.pending==1 → g_active              │
 *  │                           → duty_ticks[] + phase_ticks[] hesapla   │
 *  │                                                                     │
 *  │  Her 50kHz kesmede:                                                 │
 *  │    → Faz ofsetli tick hesapla                                       │
 *  │    → Bipolar A/B durumunu belirle                                   │
 *  │    → GPIO BSRR ile çıkışı güncelle                                 │
 *  └───────────────────────────────────────────────────────────────────────┘
 *
 * ============================================================================
 * UART PAKET FORMATI (AKTIF)
 * ============================================================================
 *
 *   BinaryCmdPacket_t (88 byte):
 *     0xAA 0x55
 *     float duty[5]
 *     float phase[5]
 *     float freq[5]
 *     uint32_t duration[5]
 *     uint16_t ref_ms
 *     uint32_t crc32
 *
 *   d      = Duty cycle    : >= 0.0 (float ratio; üst limit yok, timer tick
 * saturasyonu fiziksel sınırı uygular) — 5 bobin p      = Faz açısı     : 0.0
 * – 360.0 (float, derece)                    — 5 bobin f      = Frekans  : 1.0
 *  – FREQ_MAX (float, Hz)                     — 5 bobin dur    = Süre (dakika)
 * : 0 – DURATION_MAX_MINUTES                        — 5 bobin ref_ms = Periyot
 * içi zaman ofseti (int, 0 – period_ms-1) Python tarafından time.monotonic() %
 * 1000 olarak hesaplanır. STM32, g_dds_tick'i bu değere göre hizalar (Sorun 1b
 * fix).
 *
 *   GUI handshake/ping de aynı binary formatta sıfır-duty paket gönderir.
 *   Paket geçerli ve CRC doğruysa STM32 "STM_OK" ACK mesajı döndürür.
 *
 * ============================================================================
 * DDS PARAMETRE HESABI
 * ============================================================================
 *
 *   SYSCLK = 168 MHz
 *   APB2   = 84  MHz (÷2)  →  TIM1 Saat = 168 MHz (×2)
 *
 *   TIM1 (Kesme Kaynağı):
 *     PSC=167, ARR=19 → 168MHz / 168 / 20 = 50 kHz
 *
 *   DDS Yazılımsal PWM:
 *     TICKS_PER_PERIOD = 50000 / 100 = 500  (100 Hz PWM çıkışı)
 *     Duty çözünürlüğü: 1/500 = 0.2%
 *     Faz çözünürlüğü : 360°/500 = 0.72°
 *
 * ============================================================================
 * DONANIM PIN HARİTASI (STM32F429ZI Nucleo-144) — Software DDS
 * ============================================================================
 *
 *   USART3  TX → PD8  (AF7)   USART3  RX → PD9  (AF7)
 *   [ST-Link VCP → USART3 — LattePanda USB kablo ile doğrudan erişim]
 *   PC8   → GPIO OUT (IN_A Bobin 1)   PD12  → GPIO OUT (IN_B Bobin 1)
 *   PC9   → GPIO OUT (IN_A Bobin 2)   PE10  → GPIO OUT (IN_B Bobin 2)
 *   PD10  → GPIO OUT (IN_A Bobin 3)   PD11  → GPIO OUT (IN_B Bobin 3)
 *   PC6   → GPIO OUT (IN_A Bobin 4)   PC7   → GPIO OUT (IN_B Bobin 4)
 *   PA8   → GPIO OUT (IN_A Bobin 5)   PA9   → GPIO OUT (IN_B Bobin 5)
 *   LED   → PB0
 *
 ******************************************************************************
 */

#include "main.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ============================================================================
 * SABİTLER
 * ============================================================================
 */

/**
 * @defgroup DDSConfig Yazılımsal DDS Konfigürasyonu
 * @{
 */

/**
 * TIM1 Kesme Kaynağı (APB2 timer saati: 168 MHz)
 *   PSC=167  → Timer tick = 168MHz / 168 = 1 MHz
 *   ARR=19   → Kesme = 1MHz / 20 = 50 kHz (20 µs periyot)
 */
#define DDS_TIMER_PSC 167U
#define DDS_TIMER_ARR 19U

/** DDS Yazılımsal PWM Parametreleri */
#define DDS_ISR_HZ 50000.0f  /**< TIM1 update interrupt frekansi (Hz) */
#define DDS_PWM_FREQ_HZ 100U /**< Hedef PWM frekansı (Hz) */
#define DDS_TICKS_PER_PERIOD                                                   \
  (50000U / DDS_PWM_FREQ_HZ) /**< = 500 tick/periyot */
#define DDS_MIN_TICKS_PER_PERIOD                                               \
  2.0f /**< Nyquist/teknik alt sinir: periyot basina en az 2 tick */
#define DDS_DEAD_TIME_TICKS                                                    \
  0U /**< TICK bazli yazilimsal dead-time KULLANILMIYOR (0). Gercek dead-time A/B
      *   gecisinde NOP dongusuyle uygulanir → DDS_DEADTIME_NOP_ITERS. */
/**
 * A/B tam-kopru gecisinde uygulanan dead-time NOP dongusu iterasyon sayisi.
 *
 * ⚠️ DENETIM 2026-08-04: bu deger koda gomulu SIHIRLI bir sayiydi (21) ve BELGELER UC FARKLI
 * DEGER soyluyordu: dosya basligi "2 tick x 20us = 40us", satir-ici yorum ve README ise
 * "~500 ns". Ucu de kodla uyusmuyordu.
 *
 * GERCEK SURE OLCULMEMISTIR ve bu koddan HESAPLANAMAZ: dongu sayaci `volatile` oldugu icin her
 * iterasyon bellek load/store yapar; sure -O seviyesine, FLASH_LATENCY_5 bekleme durumlarina ve
 * ART hizlandirici isabet/kacirmasina baglidir. Kaba tahmin ~6-10 cevrim/iterasyon → 168 MHz'de
 * 21 iterasyon ≈ 0.75-1.25 us. Yani gercek deger belgelenen 500 ns'den BUYUK (guvenli yon: daha
 * fazla dead-time = shoot-through riski daha dusuk) ama 40 us'ten cok KUCUK.
 *
 * ⚠️ Bu, tam-kopruye karsi TEK yazilim korumasidir (MCU'da donanimsal dead-time ureteci YOK).
 * Degistirmeden once OSILOSKOPLA olcun: IN_A dusen kenari ile IN_B yukselen kenari arasindaki
 * sure, kullanilan MOSFET/surucunun veri sayfasindaki turn-off gecikmesinden BUYUK olmalidir.
 */
#define DDS_DEADTIME_NOP_ITERS 21U
#define DDS_MAX_DUTY_SLEW                                                      \
  25 /**< Periyot başı max duty değişimi (tick) — 100 Hz referans değeri */
#define DDS_SLEW_FULLSCALE_S                                                   \
  0.2f /**< Tam-ölçek (0↔%100) duty rampasının hedef SÜRESİ, saniye.           \
        *   slew = tpp / (freq * bu) → ramp süresi frekanstan BAĞIMSIZ.        \
        *   100 Hz'de 500/(100*0.2) = 25 tick = eski sabitin AYNISI.           \
        *   (DENETİM P0: sabit 25, 1 Hz'de STOP'u ~16.7 dk geciktiriyordu.) */

/** @} */

/** Bobin sayısı */
#define NUM_COILS 5U

/** UART RX tampon boyutu (bayt) */
#define UART_RX_BUF_SZ 128U

/**
 * @defgroup SafetyLimits Güvenlik Sınırları
 * @{
 */
#define DUTY_MIN 0.0f        /**< Minimum duty cycle (Kapalı durum) */
#define PHASE_DEG_MIN 0.0f   /**< Minimum faz açısı */
#define PHASE_DEG_MAX 360.0f /**< Maksimum faz açısı */
#define FREQ_MIN 1.0f        /**< Minimum frekans (Hz) */
#define FREQ_MAX                                                               \
  (DDS_ISR_HZ / DDS_MIN_TICKS_PER_PERIOD) /**< Teknik DDS maksimumu: 50kHz ISR \
                                             / 2 = 25kHz */
#define DURATION_MAX_MINUTES                                                   \
  9999U                 /**< GUI manuel/otomatik sure ust siniriyle uyumlu */
#define REF_MS_MAX 999U /**< GUI time.monotonic() % 1000 gonderir */
/** @} */

/* ============================================================================
 * TİP TANIMLAMALARI
 * ============================================================================
 */

/** Tek bir bobinin çalışma parametresi */
typedef struct {
  float duty;       /**< Duty cycle: >= 0.00 ratio; üst limit yok */
  float phase;      /**< Faz açısı : 0.0  – 360.0 derece */
  float freq;       /**< Frekans (Hz): FREQ_MIN - FREQ_MAX */
  uint32_t dur_min; /**< Süre (dakika): 0 = süresiz */
} CoilParam_t;

/**
 * 5 bobinin parametre seti.
 * volatile: ISR ve main arasında paylaşıldığı için zorunlu.
 */
typedef struct {
  CoilParam_t coil[NUM_COILS];
  volatile uint8_t pending; /**< 1 = ISR'da uygulanmayı bekliyor */
  uint8_t ref_ms_valid;     /**< [FIX-1b] 1 = ref_ms bloğu parse edildi */
  uint16_t ref_ms;          /**< [FIX-1b] 0 .. 999, g_dds_tick hizalama için */
} CoilParamSet_t;

/** Bir bobinin A/B GPIO çıkış tanımı
 *  NOT: Ana projenin main.h'i ile çakışmayı önlemek için PEMF_ önekli
 *  kendi typedef'imizi kullanıyoruz. */
typedef struct PEMF_CoilGPIO_Tag {
  GPIO_TypeDef *const portA; /**< IN_A (pozitif faz) portu — pointer */
  uint16_t const pinA;       /**< IN_A pin maskesi */
  GPIO_TypeDef *const portB; /**< IN_B (negatif faz) portu — pointer */
  uint16_t const pinB;       /**< IN_B pin maskesi */
} PEMF_CoilGPIO_t;

/** UART alım durum makinesi durumları */
typedef enum { RX_IDLE = 0, RX_WAIT_HEADER2, RX_DATA } UartRxState_t;

#pragma pack(push, 1)
typedef struct {
  uint8_t header[2]; // 0xAA, 0x55
  float duty[NUM_COILS];
  float phase[NUM_COILS];
  float freq[NUM_COILS];
  uint32_t duration[NUM_COILS];
  uint16_t ref_ms;
  uint32_t crc32;
} BinaryCmdPacket_t;
#pragma pack(pop)

#define BINARY_PKT_SIZE sizeof(BinaryCmdPacket_t) // 88 byte

uint32_t calculate_crc32(const uint8_t *data, size_t length) {
  uint32_t crc = 0xFFFFFFFF;
  for (size_t i = 0; i < length; i++) {
    crc ^= data[i];
    for (int j = 0; j < 8; j++) {
      if (crc & 1) {
        crc = (crc >> 1) ^ 0xEDB88320;
      } else {
        crc >>= 1;
      }
    }
  }
  return crc ^ 0xFFFFFFFF;
}

/* ============================================================================
 * PERİFERİ HANDLELERİ
 * ============================================================================
 */
TIM_HandleTypeDef
    htim1; /**< 50 kHz DDS kesme kaynağı (TIM8 artık kullanılmıyor) */
UART_HandleTypeDef
    huart3; /**< PC bağlantısı @ 115200 baud — ST-Link VCP (PD8/PD9 USART3) */

/* ============================================================================
 * BOBİN GPIO HARİTASI
 * ============================================================================
 *
 * Her bobinin iki yarı-köprü çıkışı (IN_A / IN_B) doğrudan GPIO olarak sürülür.
 * Timer OC kanalları KULLANILMAZ — tüm dalga formu yazılımsal DDS ile üretilir.
 */
static const PEMF_CoilGPIO_t coil_gpio[NUM_COILS] = {
    [0] = {.portA = GPIOC,
           .pinA = GPIO_PIN_8,
           .portB = GPIOD,
           .pinB = GPIO_PIN_12}, /* Bobin 1: PC8  (A), PD12 (B) */
    [1] = {.portA = GPIOC,
           .pinA = GPIO_PIN_9,
           .portB = GPIOE,
           .pinB = GPIO_PIN_10}, /* Bobin 2: PC9  (A), PE10 (B) */
    [2] = {.portA = GPIOD,
           .pinA = GPIO_PIN_10,
           .portB = GPIOD,
           .pinB = GPIO_PIN_11}, /* Bobin 3: PD10 (A), PD11 (B) */
    [3] = {.portA = GPIOC,
           .pinA = GPIO_PIN_6,
           .portB = GPIOC,
           .pinB = GPIO_PIN_7}, /* Bobin 4: PC6  (A), PC7  (B) */
    [4] = {.portA = GPIOA,
           .pinA = GPIO_PIN_8,
           .portB = GPIOA,
           .pinB = GPIO_PIN_9}, /* Bobin 5: PA8  (A), PA9  (B) */
};

/* ============================================================================
 * SHADOW (GÖLGE) DEĞİŞKENLER
 * ----------------------------------------------------------------------------
 * g_shadow  : main() veya UART ISR tarafından yazılır
 *             TIM1 Update ISR tarafından okunur
 * g_active  : YALNIZCA TIM1 Update ISR içinde YAZILIR (donanıma son uygulanan değerler),
 *             ama main() döngüsünde OKUNUR (süre auto-stop + ölü-adam watchdog kapısı)
 *             → volatile ZORUNLU (bkz. tanımındaki DENETİM notu)
 * ============================================================================
 */
static volatile CoilParamSet_t g_shadow = {
    .coil = {{.duty = 0.0f, .phase = 0.0f, .freq = 100.0f, .dur_min = 0},
             {.duty = 0.0f, .phase = 0.0f, .freq = 100.0f, .dur_min = 0},
             {.duty = 0.0f, .phase = 0.0f, .freq = 100.0f, .dur_min = 0},
             {.duty = 0.0f, .phase = 0.0f, .freq = 100.0f, .dur_min = 0},
             {.duty = 0.0f, .phase = 0.0f, .freq = 100.0f, .dur_min = 0}},
    .pending = 0,
    .ref_ms_valid = 0,
    .ref_ms = 0};

/** ISR'ın doğrudan eriştiği aktif parametre seti.
 *
 * DENETİM 2026-08-04: `volatile` EKSİKTİ ve bu bir stil sorunu DEĞİLDİ. g_active TIM1 Update
 * ISR'ında YAZILIR (memcpy, aşağıda) ama main() `while(1)` döngüsünde OKUNUR:
 *   - süre auto-stop kontrolü : `g_active.coil[i].dur_min` / `.duty`
 *   - ÖLÜ-ADAM WATCHDOG KAPISI: `if (g_active.coil[i].duty > 0.0f) any_coil_active = 1;`
 * Derleyici, main döngüsü içinde bu değişkeni değiştiren bir şey GÖREMEZ (ISR'ı bilmez), bu yüzden
 * okumaları döngü dışına taşıyıp registera önbellekleyebilir. O anda `any_coil_active` sonsuza dek
 * 0 (başlangıç değeri) sabitlenir ve 1500 ms'lik ölü-adam kontrolü BİR DAHA ATEŞLEMEZ — sessizce,
 * hiçbir uyarı vermeden. Bugün çalışmasının tek sebebi HAL_GetTick()'in ayrı bir çeviri biriminde
 * olması (derleyici çağrı sonrası globalleri yeniden yüklemek zorunda); LTO açıldığı ya da HAL
 * inline edildiği gün bu tesadüfi koruma kaybolur. Diğer TÜM paylaşılan değişkenler (g_shadow,
 * g_dds_tick, g_tpp, g_start_ms, g_pktReady, g_rxState) zaten volatile — g_active tek istisnaydı.
 */
static volatile CoilParamSet_t g_active;

/** PWM çıkışlarının başlatılıp başlatılmadığını takip eden bayrak */
static uint8_t g_pwm_started = 0;

/* ============================================================================
 * DDS DURUM DEĞİŞKENLERİ
 * ============================================================================
 */

/** Her bobin için ayrı DDS tick sayacı (0 … tpp-1, 50kHz'de artırılır) */
static volatile uint32_t g_dds_tick[NUM_COILS] = {0, 0, 0, 0, 0};

/** Her bobinin Ticks Per Period değeri (50000 / freq) */
static volatile uint32_t g_tpp[NUM_COILS] = {500, 500, 500, 500, 500};

/** Süre kontrolü için başlangıç zamanı (systick tabanlı milisaniye) */
static volatile uint32_t g_start_ms[NUM_COILS] = {0, 0, 0, 0, 0};

/** Anlık duty tick değerleri (slew rate limiter çıkışı) */
static int32_t g_duty_ticks[NUM_COILS] = {0, 0, 0, 0, 0};

/** Hedef duty tick değerleri (slew rate limiter girişi) */
static int32_t g_target_duty_ticks[NUM_COILS] = {0, 0, 0, 0, 0};

/**
 * Periyot başına izin verilen duty değişimi (tick) — FREKANSA GÖRE ölçeklenir.
 *
 * DENETİM P0: eskiden sabit DDS_MAX_DUTY_SLEW (=25 tick/periyot) kullanılıyordu. Periyot süresi
 * 1/f olduğundan ramp SÜRESİ 1/f² ile büyüyordu: 100 Hz'de 0.1 s, 10 Hz'de 10 s, 1 Hz'de
 * ~16.7 DAKİKA. AI Pro tam da 1 Hz'de sürüyor (_AI_PRO_FREQ_HZ). Acil durdurma / süre-bitişi /
 * ölü-adam watchdog'unun hepsi yalnızca HEDEFİ sıfırlıyor, çıkış ise slew'lenmiş değere göre
 * sürüldüğü için bobin dakikalarca enerjili kalabiliyordu.
 * Yeni ölçek: slew = tpp / (f * DDS_SLEW_FULLSCALE_S) → tam-ölçek ramp süresi frekanstan
 * BAĞIMSIZ ~0.1 s. 100 Hz'de sonuç tam olarak 25'tir; nominal davranış birebir korunur.
 */
static int32_t g_slew_ticks[NUM_COILS] = {DDS_MAX_DUTY_SLEW, DDS_MAX_DUTY_SLEW,
                                          DDS_MAX_DUTY_SLEW, DDS_MAX_DUTY_SLEW,
                                          DDS_MAX_DUTY_SLEW};

/** Faz offset tick değerleri */
static int32_t g_phase_ticks[NUM_COILS] = {0, 0, 0, 0, 0};

/** Önceki bipolar durumları (0: A=0/B=1, 1: A=1/B=0) */
static uint8_t g_prev_state[NUM_COILS] = {255, 255, 255, 255, 255};

/* ============================================================================
 * DONANIM SYNC — Master Sync Pulse (PB1)
 * ============================================================================
 * Her PWM periyodunun başında (period_reset anında) PB1 HIGH yapılır.
 * DDS_SYNC_PULSE_TICKS tick sonra LOW'a çekilir.
 * ESP32/ESP8266 Slave cihazlar bu RISING kenarı EXTI kesmesiyle yakalar
 * ve kendi DDS sayaçlarını sıfırlar → mikrosaniye hassasiyetinde faz kilidi.
 * ============================================================================
 */
#define DDS_SYNC_PULSE_TICKS 5U /**< Sync pulse genişliği: 5×20µs = 100µs */
static volatile uint8_t g_sync_pulse_countdown =
    0U; /**< Kaç tick daha HIGH kalacak */

/* ============================================================================
 * UART ALIM STATE MACHINE DEĞİŞKENLERİ
 * ============================================================================
 */
static volatile uint8_t g_rxByte; /**< HAL IT hedef bayt    */
static volatile uint8_t g_rxBuf[UART_RX_BUF_SZ];
static volatile uint16_t g_rxLen = 0;
static volatile UartRxState_t g_rxState = RX_IDLE;
static volatile uint8_t g_pktBuf[BINARY_PKT_SIZE];
static volatile uint8_t g_pktReady = 0;
/* DENETIM 2026-08-04: cerceve senkronizasyonunda BAYT-ARASI ZAMAN ASIMI yoktu. Durum makinesi
 * yalnizca 0xAA/0x55 desenine ve 88-bayt sayimina dayaniyordu; bir bayt DUSERSE RX_DATA 88'i
 * doldurmak icin BIR SONRAKI paketten bayt yiyor, boylece iki paket birden bozuluyordu.
 * 115200 8N1'de 88 bayt = 7.64 ms → aralarinda 50 ms'lik bir sessizlik KESINLIKLE cerceve
 * sinirdir. Sessizlik gorulurse yarim cerceve ATILIR ve taze senkronizasyona gecilir. */
#define RX_FRAME_GAP_MS 50U
static volatile uint32_t g_rxLastByteMs = 0;

/* ============================================================================
 * FONKSİYON PROTOTİPLERİ
 * ============================================================================
 */

/* Timer Kurulum */
static void Coil_TimInit(void);         /* TIM1 → 50kHz DDS kesme kaynağı */
static void Coil_StartPwmOutputs(void); /* GPIO'ları güvenli başlangıca al */

/* UART */
static void Coil_UartInit(void);
static void Coil_UartStartReceive(void);
static void Coil_SendNack(const char *reason);
static long Coil_FloatMilliForLog(float value);
static uint8_t Coil_DecodeAndValidatePacket(const BinaryCmdPacket_t *pkt,
                                            CoilParamSet_t *out,
                                            char *nack_reason,
                                            size_t nack_reason_sz);

/* GPIO */
static void Coil_GpioInit(void);

/* Core */
void SystemClock_Config(void);
void Error_Handler(void);

/**
 * @brief  TÜM bobin çıkışlarını doğrudan BSRR ile LOW'a çeker (ISR-güvenli, yeniden-girişli).
 * @note   DIŞA AÇIK (static DEĞİL): `Core/Src/stm32f4xx_it.c` içindeki fault işleyicileri
 *         buradan çağırır — bkz. firmware/README.md "Fault işleyici yaması". Yalnız BSRR
 *         yazar; kesme/HAL/kilit gerektirmez, bu yüzden fault bağlamında güvenlidir.
 */
void PEMF_ForceAllCoilOutputsLow(void);

static void Coil_SendNack(const char *reason) {
  static char msg[160];
  int len = snprintf(msg, sizeof(msg), "-> STM_NACK: %s\r\n", reason);
  if (len < 0) {
    return;
  }
  if (len >= (int)sizeof(msg)) {
    len = (int)sizeof(msg) - 1;
  }
  HAL_UART_Transmit(&huart3, (uint8_t *)msg, (uint16_t)len, 50U);
}

static long Coil_FloatMilliForLog(float value) {
  if (!isfinite(value)) {
    return 0L;
  }
  if (value > 2147483.0f) {
    return 2147483000L;
  }
  if (value < -2147483.0f) {
    return -2147483000L;
  }
  return (long)(value * 1000.0f);
}

static uint8_t Coil_DecodeAndValidatePacket(const BinaryCmdPacket_t *pkt,
                                            CoilParamSet_t *out,
                                            char *nack_reason,
                                            size_t nack_reason_sz) {
  if (pkt == NULL || out == NULL || nack_reason == NULL ||
      nack_reason_sz == 0U) {
    return 0U;
  }

  if (pkt->header[0] != 0xAAU || pkt->header[1] != 0x55U) {
    snprintf(nack_reason, nack_reason_sz,
             "RANGE header expected=AA55 got=%02X%02X", pkt->header[0],
             pkt->header[1]);
    return 0U;
  }

  if (pkt->ref_ms > REF_MS_MAX) {
    snprintf(nack_reason, nack_reason_sz, "RANGE ref_ms value=%u min=0 max=%u",
             (unsigned)pkt->ref_ms, (unsigned)REF_MS_MAX);
    return 0U;
  }

  memset(out, 0, sizeof(*out));
  out->ref_ms_valid = 1U;
  out->ref_ms = pkt->ref_ms;

  for (uint32_t i = 0U; i < NUM_COILS; i++) {
    float duty = pkt->duty[i];
    float phase = pkt->phase[i];
    float freq = pkt->freq[i];
    uint32_t duration = pkt->duration[i];

    if (!isfinite(duty)) {
      snprintf(nack_reason, nack_reason_sz,
               "RANGE coil=%lu field=duty value=nonfinite",
               (unsigned long)(i + 1U));
      return 0U;
    }
    if (!isfinite(phase)) {
      snprintf(nack_reason, nack_reason_sz,
               "RANGE coil=%lu field=phase value=nonfinite",
               (unsigned long)(i + 1U));
      return 0U;
    }
    if (!isfinite(freq)) {
      snprintf(nack_reason, nack_reason_sz,
               "RANGE coil=%lu field=freq value=nonfinite",
               (unsigned long)(i + 1U));
      return 0U;
    }

    if (duty < DUTY_MIN) {
      snprintf(nack_reason, nack_reason_sz,
               "RANGE coil=%lu field=duty value_milli=%ld min_milli=%ld",
               (unsigned long)(i + 1U), Coil_FloatMilliForLog(duty),
               Coil_FloatMilliForLog(DUTY_MIN));
      return 0U;
    }
    if (phase < PHASE_DEG_MIN || phase > PHASE_DEG_MAX) {
      snprintf(nack_reason, nack_reason_sz,
               "RANGE coil=%lu field=phase value_milli=%ld min_milli=%ld "
               "max_milli=%ld",
               (unsigned long)(i + 1U), Coil_FloatMilliForLog(phase),
               Coil_FloatMilliForLog(PHASE_DEG_MIN),
               Coil_FloatMilliForLog(PHASE_DEG_MAX));
      return 0U;
    }
    if (freq < FREQ_MIN || freq > FREQ_MAX) {
      snprintf(nack_reason, nack_reason_sz,
               "RANGE coil=%lu field=freq value_milli=%ld min_milli=%ld "
               "max_milli=%ld",
               (unsigned long)(i + 1U), Coil_FloatMilliForLog(freq),
               Coil_FloatMilliForLog(FREQ_MIN),
               Coil_FloatMilliForLog(FREQ_MAX));
      return 0U;
    }
    if (duration > DURATION_MAX_MINUTES) {
      snprintf(nack_reason, nack_reason_sz,
               "RANGE coil=%lu field=duration value=%lu min=0 max=%lu",
               (unsigned long)(i + 1U), (unsigned long)duration,
               (unsigned long)DURATION_MAX_MINUTES);
      return 0U;
    }

    out->coil[i].duty = duty;
    out->coil[i].phase = phase;
    out->coil[i].freq = freq;
    out->coil[i].dur_min = duration;
  }

  return 1U;
}

/* ============================================================================
 * MAIN
 * ============================================================================
 */
int main(void) {
  /* HAL ve Sistem Saati */
  HAL_Init();
  SystemClock_Config();

  /* GPIO → UART → Timer sırası önemli */
  Coil_GpioInit();
  Coil_UartInit();

  /* Aktif parametreleri gölge başlangıç değerleriyle başlat */
  memcpy((void *)&g_active, (const void *)&g_shadow, sizeof(CoilParamSet_t));
  g_active.pending = 0;

  /* ---- DDS Timer'ı kur ve başlat ---- */
  Coil_TimInit();

  /* UART alımı başlat */
  Coil_UartStartReceive();

  /* Başlangıçta terminale hazır olduğumuzu basalım.
   * static: HAL_UART_Transmit_IT non-blocking olduğu için lokal buffer race
   * condition'ını önler. Blocking Transmit kullanılarak gönderimin tamamlandığı
   * garanti edilir. */
  static const char init_msg[] =
      "-> STM_READY: DDS v2.2 (5-ch + HW_SYNC@PB1) Waiting for commands...\r\n";
  HAL_UART_Transmit(&huart3, (uint8_t *)init_msg, strlen(init_msg), 200U);

  uint32_t last_communication_ms = HAL_GetTick();
  uint32_t last_ping_ms = HAL_GetTick();

  /* ===================================================================
   * ANA DÖNGÜ
   * -------------------------------------------------------------------
   * Bu döngü sadece UART paketlerini işler.
   * Tüm gerçek zamanlı DDS güncellemeleri TIM1 Update ISR'ındadır.
   * =================================================================== */
  while (1) {
    uint32_t current_time = HAL_GetTick();

    /* Python (GUI/Backend) henüz bağlantı kurmadıysa veya
     * paket gelmediyse her 2 saniyede bir ping at (Handshake Time-out önlemi)
     */
    if (g_pwm_started == 0 && (current_time - last_ping_ms >= 2000U)) {
      HAL_UART_Transmit_IT(&huart3, (uint8_t *)init_msg, strlen(init_msg));
      last_ping_ms = current_time;
    }

    if (g_pktReady) {
      uint8_t pkt_copy[BINARY_PKT_SIZE];
      __disable_irq();
      memcpy(pkt_copy, (const void *)g_pktBuf, BINARY_PKT_SIZE);
      g_pktReady =
          0; /* Local copy alindiktan sonra yeni paket kabul edilebilir */
      __enable_irq();

      BinaryCmdPacket_t pkt_local;
      memcpy(&pkt_local, pkt_copy, sizeof(pkt_local));

      // CRC Kontrolu
      uint32_t calc_crc =
          calculate_crc32((const uint8_t *)pkt_copy, BINARY_PKT_SIZE - 4);
      /* DENETIM 2026-08-04: burada `continue` vardi. Dongunun basina donmek, AYNI TURDAKI
       * sure-bitimi kontrolunu (asagida) ve 1500 ms olu-adam watchdog'unu ATLIYORDU. Guvenlik
       * kontrolleri hicbir kosulda atlanmamalidir — bozuk paket yalnizca PWM state'ine
       * dokunmamali, watchdog'u askiya ALMAMALIDIR. Artik bayrakla ilerliyoruz. */
      uint8_t pkt_ok = 1U;
      if (calc_crc != pkt_local.crc32) {
        Coil_SendNack("CRC");
        pkt_ok = 0U;
      }

      CoilParamSet_t parsed = {0};
      char nack_reason[128];
      if (pkt_ok && !Coil_DecodeAndValidatePacket(&pkt_local, &parsed, nack_reason,
                                                  sizeof(nack_reason))) {
        Coil_SendNack(nack_reason);
        pkt_ok = 0U; // bozuk/range disi paket PWM state'ine dokunamaz
      }

      if (pkt_ok) {
        last_communication_ms = current_time;

        /* [FIX-1b] ref_ms faz hizalaması ARTIK BURADA DEĞİL — TIM1 ISR'ında, `g_tpp`
         * ile AYNI kritik bölgede uygulanıyor (bkz. HAL_TIM_PeriodElapsedCallback, #65).
         * Burada yapıldığında tick YENİ frekansa, tpp ise hâlâ ESKİ frekansa göre oluyordu.
         * `ref_ms` / `ref_ms_valid` zaten `parsed` ile gölgeye taşınıyor. */

        /* İlk komut geldiğinde PWM çıkışlarını başlat */
        if (g_pwm_started == 0) {
          Coil_StartPwmOutputs();
          g_pwm_started = 1;
        }

        /* Atomik bölge: Gölge değişkenleri güncelle */
        __disable_irq();
        memcpy((void *)&g_shadow, &parsed, sizeof(CoilParamSet_t));
        g_shadow.pending = 1;
        __enable_irq();

        /* Debug/ACK Gönderimi
         * DENETIM 2026-08-04: `static ack_msg` HAL_UART_Transmit_IT ile KESME-tabanli
         * gonderiliyor; fonksiyon donduğunde baytlar HALA tampondan okunuyordur. Bir sonraki
         * paket islenirken snprintf AYNI tamponu YENIDEN yaziyordu → ucusan ACK bozuluyordu.
         * Ustelik donus degeri (HAL_BUSY) hic kontrol edilmiyordu. ACK yalnizca TANI amaclidir:
         * TX mesgulse bu turu ATLA (tamponu bozma), bosalinca bir sonraki ACK zaten gider. */
        static char ack_msg[256];
        if (huart3.gState == HAL_UART_STATE_READY) {
        int len = snprintf(
            ack_msg, sizeof(ack_msg),
            "-> STM_OK: D=%d,%d,%d,%d,%d P=%d,%d,%d,%d,%d F=%d,%d,%d,%d,%d "
            "T=%lu,%lu,%lu,%lu,%lu\r\n",
            (int)(parsed.coil[0].duty * 100), (int)(parsed.coil[1].duty * 100),
            (int)(parsed.coil[2].duty * 100), (int)(parsed.coil[3].duty * 100),
            (int)(parsed.coil[4].duty * 100), (int)(parsed.coil[0].phase),
            (int)(parsed.coil[1].phase), (int)(parsed.coil[2].phase),
            (int)(parsed.coil[3].phase), (int)(parsed.coil[4].phase),
            (int)(parsed.coil[0].freq), (int)(parsed.coil[1].freq),
            (int)(parsed.coil[2].freq), (int)(parsed.coil[3].freq),
            (int)(parsed.coil[4].freq), (unsigned long)(parsed.coil[0].dur_min),
            (unsigned long)(parsed.coil[1].dur_min),
            (unsigned long)(parsed.coil[2].dur_min),
            (unsigned long)(parsed.coil[3].dur_min),
            (unsigned long)(parsed.coil[4].dur_min));
        /* DENETIM 2026-08-04: snprintf donus degeri kontrol EDILMIYORDU. Negatif donus
         * (uint16_t)(-1) = 65535 olur ve 256 baytlik .bss tamponunun ~64 KB otesi hattan
         * disari yazilirdi; kesilme (len >= sizeof) durumunda da tampon-disi okuma olurdu.
         * Coil_SendNack bu iki durumu zaten dogru koruyor — ayni koruma buraya da. */
        if (len < 0) {
          len = 0;
        }
        if (len >= (int)sizeof(ack_msg)) {
          len = (int)sizeof(ack_msg) - 1;
        }
        if (len > 0) {
          (void)HAL_UART_Transmit_IT(&huart3, (uint8_t *)ack_msg, (uint16_t)len);
        }
        }

        HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_0);
      }
    }

    /* Süre (Duration) Kontrolü */
    if (g_pwm_started) {
      uint8_t duration_stopped = 0;

      for (uint32_t i = 0U; i < NUM_COILS; i++) {
        uint32_t dur_min = g_active.coil[i].dur_min;
        uint32_t start_ms = g_start_ms[i];

        if (dur_min > 0 && start_ms > 0 && g_active.coil[i].duty > 0.0f) {
          uint32_t elapsed_ms = current_time - start_ms;
          uint32_t target_ms = dur_min * 60000U; // dakika to milisaniye

          if (elapsed_ms >= target_ms) {
            /* Süre doldu, bu bobini durdur */
            __disable_irq();
            g_shadow.coil[i].duty = 0.0f;
            g_shadow.pending = 1;
            g_start_ms[i] = 0;
            __enable_irq();
            duration_stopped = 1;
          }
        }
      }

      if (duration_stopped) {
        static char stop_msg[] =
            "-> STM_STOPPED: Sure(ler) doldu, bobinler kapatildi.\r\n";
        HAL_UART_Transmit_IT(&huart3, (uint8_t *)stop_msg, strlen(stop_msg));
      }
    }

    /* Watchdog Koruması (Ölü Adam Devresi) - Sadece en az bir bobin aktifse
     * kontrol et */
    uint8_t any_coil_active = 0;
    for (uint32_t i = 0U; i < NUM_COILS; i++) {
      if (g_active.coil[i].duty > 0.0f) {
        any_coil_active = 1;
        break;
      }
    }
    if (any_coil_active && (current_time - last_communication_ms > 1500)) {
      __disable_irq();
      for (uint32_t i = 0U; i < NUM_COILS; i++) {
        g_shadow.coil[i].duty = 0.0f;
      }
      g_shadow.pending = 1;
      __enable_irq();

      last_communication_ms = current_time;

      static char tout_msg[] =
          "-> STM_ERR: Watchdog Timeout! Baglanti koptu, bobinler 0'landi.\r\n";
      HAL_UART_Transmit_IT(&huart3, (uint8_t *)tout_msg, strlen(tout_msg));
    }
  }
}

/* ============================================================================
 * DDS TIMER BAŞLATMA — TIM1 yalnızca 50 kHz kesme kaynağı
 * ----------------------------------------------------------------------------
 * Önceki mimaride (v1.x) TIM1 ve TIM8 PWM kanalları kullanılıyordu.
 * TIM1'in tüm kanalları aynı CNT sayacını paylaştığı için bağımsız faz
 * kaydırması MÜMKÜN DEĞİLDİ.
 *
 * Yeni mimaride (v2.0 DDS):
 *   - TIM1 yalnızca 50kHz kesme üretir (PWM kanalı KULLANILMAZ)
 *   - TIM8 tamamen kaldırıldı
 *   - Her bobin için bağımsız yazılımsal DDS sayacı kullanılır
 *   - GPIO pinleri doğrudan BSRR ile sürülür
 *   - Dead time yazılımsal olarak uygulanır (DDS_DEAD_TIME_TICKS)
 *
 * Timer hesabı:
 *   168 MHz / (167+1) / (19+1) = 50 kHz (20 µs periyot)
 * ============================================================================
 */
static void Coil_TimInit(void) {
  __HAL_RCC_TIM1_CLK_ENABLE();

  /* TIM1: Base timer olarak yapılandır (PWM kanalı YOK) */
  htim1.Instance = TIM1;
  htim1.Init.Prescaler = DDS_TIMER_PSC;
  htim1.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim1.Init.Period = DDS_TIMER_ARR;
  htim1.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim1.Init.RepetitionCounter = 0U;
  htim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
  if (HAL_TIM_Base_Init(&htim1) != HAL_OK) {
    Error_Handler();
  }

  /* NVIC: En yüksek öncelik — 50kHz ISR jitter'ı minimize et */
  HAL_NVIC_SetPriority(TIM1_UP_TIM10_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(TIM1_UP_TIM10_IRQn);

  /* Timer'ı hemen başlat.
   * g_pwm_started=0 iken ISR sadece DDS sayacını artırır,
   * GPIO çıkışı üretmez. Bu sayede ilk UART paketi geldiğinde
   * faz sayacı zaten çalışıyor olur ve geçiş sorunsuz olur. */
  HAL_TIM_Base_Start_IT(&htim1);
}

/* ============================================================================
 * PWM ÇIKIŞLARINI BAŞLAT
 * ============================================================================
 * İlk UART paketi geldiğinde çağrılır. Tüm bobin GPIO'larını güvenli
 * LOW durumuna alır. g_pwm_started bayrağı main() içinde set edilir.
 * ============================================================================
 */
static void Coil_StartPwmOutputs(void) {
  /* Tüm çıkışları güvenli LOW durumuna al */
  for (uint32_t i = 0U; i < NUM_COILS; i++) {
    coil_gpio[i].portA->BSRR = (uint32_t)coil_gpio[i].pinA << 16U;
    coil_gpio[i].portB->BSRR = (uint32_t)coil_gpio[i].pinB << 16U;
  }
  /* g_pwm_started = 1 → main() tarafından bu fonksiyondan hemen sonra yapılır
   */
}

/* ============================================================================
 * DDS 50 kHz KESME CALLBACK'İ  ←  TIM1 Update ISR
 * ============================================================================
 *
 * HAL tarafından TIM1_UP_TIM10_IRQHandler → HAL_TIM_IRQHandler → bu callback
 * şeklinde çağrılır. Her 20 µs'de bir çalışır (50 kHz).
 *
 * İşlem akışı:
 *   1. g_dds_tick sayacını artır (0 … 499, 100 Hz → 500 tick/periyot)
 *   2. Periyot başında (tick reset to 0):
 *      a. Shadow → Active parametre transferi
 *      b. Float → int32 tick dönüşümü (faz + duty)
 *      c. Duty slew rate limiter uygula
 *   3. Her tick'te (50 kHz):
 *      a. 5 bobinin faz-ofsetli bipolar dalga durumunu hesapla
 *      b. GPIO BSRR ile çıkışı atomik güncelle
 *
 * Tam bipolar dalga formu, geçişlerde NOP gecikmesi ile:
 *
 *   adj = (tick - phase_offset) mod TICKS_PER_PERIOD
 *
 *   [0, duty)          → A=HIGH, B=LOW   (pozitif yön)
 *   [duty, period)     → A=LOW,  B=HIGH  (negatif yön)
 *
 * Not: dead-time A/B geçiş anında NOP döngüsüyle uygulanır (süre ÖLÇÜLMEMİŞ).
 *
 * CPU yükü: ~120 cycle / 3360 available = ~%3.6
 *   ⚠️ Bu rakam KARARLI-DURUM (her tick koşan) yolu içindir: tick/slew/BSRR bloğu.
 *   `g_shadow.pending` uygulanan blok (tpp + duty-tick + faz-tick + ref_ms hizalaması, bobin
 *   başına float bölme) BUNA DAHİL DEĞİLDİR ve belirgin biçimde daha ağırdır — ama YALNIZCA
 *   yeni bir parametre seti geldiğinde (host 2 Hz keep-alive) koşar, 50 kHz'de değil.
 *   Ölçülmemiştir; DDS zamanlaması şüpheli olursa önce burası ölçülmeli.
 * ============================================================================
 */
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim) {
  /* Yalnızca TIM1 için işlem yap */
  if (htim->Instance != TIM1) {
    return;
  }

  /* ---- Ortak Shadow → Active Transfer ---- */
  if (g_shadow.pending) {
    memcpy((void *)&g_active, (const void *)&g_shadow, sizeof(CoilParamSet_t));
    g_active.pending = 0;
    ((volatile CoilParamSet_t *)&g_shadow)->pending = 0;

    /* Float'tan tick'e dönüşüm */
    for (uint32_t i = 0U; i < NUM_COILS; i++) {
      float f = g_active.coil[i].freq;
      if (f < FREQ_MIN)
        f = FREQ_MIN;
      if (f > FREQ_MAX)
        f = FREQ_MAX;
      /* [FIX-1c] ⚠️ DENETİM 2026-08-17 — BAYAT DUTY TICK'İ (frekans ARTIŞI).
       *
       * `g_duty_ticks[i]` bir TICK SAYISIdır ve yalnız `g_tpp[i]`ye göre anlam taşır. Eskiden
       * `g_tpp[i]` burada güncellenirken fiili duty tick'i ESKİ periyodun ölçeğinde bırakılıyor,
       * `tpp-1` güvenlik klempi ise YALNIZ aşağıdaki `if (period_reset)` bloğunda uygulanıyordu.
       * Frekans ARTTIĞINDA (tpp küçülür) iki sonuç doğuyordu:
       *   (a) bayat `g_duty_ticks >= yeni tpp` → `state = (adj < duty)` her tick'te 1 → IN_A
       *       sürekli HIGH: 1 Hz %50 → 2 Hz geçişinde ~1000 ms KESİNTİSİZ tek-polarite sürüş
       *       (meşru zarf 250-500 ms). ESP'lere giden `ref_ms` hizalaması tick'i periyot
       *       ORTASINDAN başlattığı için klemp bir sonraki periyot başına kadar devreye girmiyordu.
       *   (b) ilk `period_reset`'te klemp duty'yi `tpp-1` (=%99,8) yapıyor → bobin, operatörün
       *       İSTEMEDİĞİ bir duty ile sürülüyor ve aşağı-slew ile 15-19 periyotta iniyor.
       * Yani hekimin girdiği parametreye SADAKAT kayboluyordu.
       *
       * Düzeltme, bu dosyanın [FIX-1b] notundaki ilkeyle aynı: tpp, duty-tick, faz-tick ve
       * dds-tick'in HEPSİ aynı parametre setinden, TEK kritik bölgede türetilir — ayrışma
       * imkânsız. `g_duty_ticks` o ailenin yeniden ölçeklenmeyen tek üyesiydi.
       *
       * ⚠️ Enerjiyi ARTIRAN yönün slew ile sınırlanması (inrush/EMI) DEĞİŞMEDİ: burada yalnız
       * mevcut ORAN korunur, hedefe yaklaşma yine `period_reset` içindeki slew ile olur.
       * ⚠️ TEZGÂHTA DOĞRULANMADI (denetim ortamında donanım yok). Kilit:
       * `tests/test_firmware_frekans_artisi_duty.py` (ISR modeli + yapısal kapı). */
      const uint32_t eski_tpp = g_tpp[i];
      g_tpp[i] = (uint32_t)(50000.0f / f);
      if ((eski_tpp > 0U) && (g_tpp[i] != eski_tpp) && (g_duty_ticks[i] > 0)) {
        /* Oranı koru: duty_ticks / tpp sabit kalsın. */
        g_duty_ticks[i] =
            (int32_t)(((float)g_duty_ticks[i] / (float)eski_tpp) * (float)g_tpp[i]);
      }
      /* Güvenlik klempini ANINDA uygula — `period_reset`'i BEKLEMEDEN (etki (a) tam buradaydı). */
      {
        int32_t max_d_now = (int32_t)(g_tpp[i] - 1U) - (int32_t)DDS_DEAD_TIME_TICKS;
        if (max_d_now < 0)
          max_d_now = 0;
        if (g_duty_ticks[i] > max_d_now)
          g_duty_ticks[i] = max_d_now;
        if (g_duty_ticks[i] < 0)
          g_duty_ticks[i] = 0;
      }

      float tpp_f = (float)g_tpp[i];

      /* Duty → tick */
      float d = g_active.coil[i].duty;
      if (d < DUTY_MIN)
        d = DUTY_MIN;
      g_target_duty_ticks[i] = (int32_t)(d * tpp_f);

      /* Slew adımını periyoda ölçekle → ramp SÜRESİ frekanstan bağımsız (bkz. g_slew_ticks). */
      {
        float slew_f = tpp_f / (f * DDS_SLEW_FULLSCALE_S);
        int32_t slew_i = (int32_t)slew_f;
        if (slew_i < 1)
          slew_i = 1; /* en az 1 tick/periyot (çok yüksek frekansta tpp küçülür) */
        g_slew_ticks[i] = slew_i;
      }

      /* Faz → tick */
      float p = g_active.coil[i].phase;
      if (p < PHASE_DEG_MIN)
        p = PHASE_DEG_MIN;
      if (p > PHASE_DEG_MAX)
        p = PHASE_DEG_MAX;
      g_phase_ticks[i] = (int32_t)((p / 360.0f) * tpp_f);

      /* [FIX-1b] HW_SYNC faz hizalaması — ⚠️ DENETİM 2026-08-04 (#65): BURAYA TAŞINDI.
       * Eskiden main() döngüsünde, paket ayrıştırılır ayrıştırılmaz `g_dds_tick[i]`
       * yazılıyordu; ama `g_tpp[i]` YALNIZCA burada (pending uygulanınca) güncelleniyor.
       * Arada 50 kHz'lik ISR çalışırsa tick YENİ frekansa göre, tpp ise HÂLÂ ESKİ frekansa
       * göredir. Örnek: bobin 25 kHz'de (tpp=2) iken 1 Hz komutu gelir (yeni tpp=50000);
       * main new_tick=30000 yazar, ISR `30001 >= 2` görüp tick'i 0'lar → HİZALAMA KAYBOLUR
       * ve üstelik `period_reset` tetiklenip ESP slave'lerine SAHTE bir PB1 sync darbesi gider.
       * Artık tpp, duty-tick, faz-tick ve dds-tick'in HEPSİ aynı parametre setinden, tek
       * kritik bölgede türetiliyor — ayrışma imkânsız. (Formül main'de kopyalanmış olduğu için
       * daha önce zaten bir kez sürüklenmişti: main tamsayı, ISR float bölme yapıyordu.) */
      if (g_active.ref_ms_valid) {
        uint32_t period_ms = (uint32_t)(1000.0f / f);
        if (period_ms == 0U)
          period_ms = 1U; /* >1 kHz: ms çözünürlüklü senkron etkisiz — protokolün doğal sınırı */
        uint32_t tpp_u = g_tpp[i];
        if (tpp_u == 0U)
          tpp_u = 1U;
        uint32_t new_tick =
            (((uint32_t)g_active.ref_ms % period_ms) * tpp_u) / period_ms;
        if (new_tick >= tpp_u)
          new_tick = tpp_u - 1U;
        g_dds_tick[i] = new_tick;
      }

      /* Süre takibi resetlemesi (yeni komut geldiğinde)
       *
       * ⚠️ DENETİM 2026-08-04 (#69) — BU SAYAÇ TEK BAŞINA BİR GÜVENLİK SINIRI DEĞİLDİR.
       *
       * DİKKAT (aynı denetimde düzeltilen yanlış anlatım): keep-alive sayacı HER SEFERİNDE
       * sıfırlamaz. Bobin çalışırken `g_start_ms[i]` sıfır DEĞİLDİR, dolayısıyla gelen keep-alive
       * paketleri sayaca DOKUNMAZ — süre normal işler ve dolduğunda auto-stop bobini kapatır.
       * Sorun ONDAN SONRA başlar: auto-stop `g_start_ms[i]`'yi 0'lar; host ise ÖLÜ-ADAM
       * watchdog'u (1500 ms) yüzünden AYNI paketi (duty>0) 2 Hz göndermeye DEVAM ETMEK
       * zorundadır → bir sonraki paket "kapalıyken açıldı" sayılıp süreyi BAŞTAN başlatır.
       * Net sonuç: sınır tedaviyi SONLANDIRMAZ, süre-dolar/yeniden-başlar DÖNGÜSÜNE sokar.
       *
       * Enerjilemeyi gerçekten sınırlayan TEK mekanizma host tarafındadır:
       * controllers/hardware_controller.py → `_coil_deadline` (bobin-başı monotonic deadline).
       * ORASI SİLİNİRSE bobin SÜRESİZ enerjili kalır — firmware "süre sınırı var" görüntüsü
       * verdiği için bu sessizce fark edilmez. Koruma: tests/test_stm32_source_parity.py
       * (`test_host_tarafi_sure_deadlineI_hala_uygulaniyor`).
       *
       * Neden burada düzeltilmedi: firmware'in keep-alive tazelemesini "yeni tedavi"den ayırt
       * edebilmesi için 88 baytlık SABİT pakete sıra-numarası/başlat-bayrağı eklemek gerekir
       * (firmware + backend + simülatör üçünü birden değiştiren protokol değişikliği).
       * "Süre doldu" mandalı alternatifi ise hekimin aynı parametrelerle YENİDEN başlat
       * demesini sessizce etkisiz kılabilirdi — klinik bir cihazda kötü bir başarısızlık biçimi.
       */
      if (g_active.coil[i].duty > 0.0f) {
        if (g_start_ms[i] == 0) {
          g_start_ms[i] =
              HAL_GetTick(); // Eğer kapalıyken yeni açıldıysa süreyi başlat
        }
      } else {
        g_start_ms[i] = 0;
      }
    }

    /* ⚠️ ref_ms hizalaması TEK ATIŞLIKTIR — `pending` gibi TÜKETİLİR.
     *
     * DENETİM 2026-08-04 (#65 REGRESYON DÜZELTMESİ): hizalama main() döngüsünden buraya
     * taşınınca `ref_ms_valid` hiçbir yerde temizlenmiyordu. Ama `pending=1` yalnız yeni bir
     * PAKET geldiğinde değil, ŞU İKİ YERDE DAHA yazılıyor:
     *   • süre auto-stop  (bobinin dur_min'i doldu → duty=0)
     *   • ölü-adam watchdog (1500 ms sessizlik → tüm duty=0)
     * Bu yollar `ref_ms_valid`'e DOKUNMAZ; bayrak son gerçek paketten 1 olarak kalırdı. Sonuç:
     * bir bobinin süresi dolduğu anda ISR, BAYAT bir `ref_ms` ile HÂLÂ ÇALIŞAN tüm bobinlerin
     * `g_dds_tick`'ini yeniden konumlandırır → tedavi ortasında FAZ SIÇRAMASI ve olası sahte/
     * kayıp PB1 sync darbesi. Çok-bobinli faz senkronu bu cihazın temel işlevi olduğundan bu
     * gerçek bir kusurdur. (Eski kodda yoktu: hizalama yalnız paket ayrıştırıldıktan hemen
     * sonra, main() içinde çalışıyordu.)
     * Bayrağı `pending` ile AYNI şekilde hem gölgede hem aktifte sıfırlıyoruz → hizalama
     * yalnızca onu taşıyan paketin uygulandığı anda, TAM BİR KEZ olur. */
    g_active.ref_ms_valid = 0U;
    ((volatile CoilParamSet_t *)&g_shadow)->ref_ms_valid = 0U;
  }

  /* ---- Bobin bazlı tick, period ve slew rate limiter ---- */
  for (uint32_t i = 0U; i < NUM_COILS; i++) {
    uint32_t tick = g_dds_tick[i] + 1U;
    uint8_t period_reset = 0;
    uint32_t tpp = g_tpp[i];

    if (tick >= tpp) {
      tick = 0U;
      period_reset = 1;
    }
    g_dds_tick[i] = tick;

    if (period_reset) {
      /* Master Sync Pulse sadece Bobin 1 (Referans) için üretilir.
       * DENETIM 2026-08-04: PB1'i HIGH yapan bu blok `g_pwm_started`'dan BAGIMSIZ calisiyordu,
       * ama darbeyi LOW'a cekecek geri sayim asagidaki `if (!g_pwm_started) return;`in
       * ARDINDA yer aliyor. Sonuc: acilistan ILK UART komutuna kadar PB1 KALICI HIGH kaliyor
       * (ESP slave'leri RISING kenar goremez) ve ilk paket geldiginde bayat sayac rastgele bir
       * tick'te esi olmayan bir DUSEN kenar uretiyordu. PWM baslamadan darbe URETME. */
      if (i == 0 && g_pwm_started) {
        GPIOB->BSRR = (uint32_t)GPIO_PIN_1; /* PB1 = HIGH */
        g_sync_pulse_countdown = DDS_SYNC_PULSE_TICKS;
      }

      /* Slew rate limiter.
       *
       * DENETİM P0 — DURDURMA RAMPAYA TABİ DEĞİLDİR: hedef 0 ise (acil durdurma, süre-bitişi,
       * ölü-adam watchdog'u, STM_NACK sonrası sıfır-duty paketi) çıkışı ANINDA kes. Eskiden
       * bu yol da rampadan geçiyordu ve 1 Hz'de bobin ~16.7 dk enerjili kalıyordu. Enerjiyi
       * ARTIRAN yön hâlâ sınırlıdır (inrush/EMI koruması) ama artık frekanstan bağımsız süreyle.
       */
      if (g_target_duty_ticks[i] <= 0) {
        g_duty_ticks[i] = 0;
      } else {
        const int32_t slew = g_slew_ticks[i];
        int32_t err = g_target_duty_ticks[i] - g_duty_ticks[i];
        if (err > slew)
          err = slew;
        if (err < -slew)
          err = -slew;
        g_duty_ticks[i] += err;
        if (g_duty_ticks[i] < 0)
          g_duty_ticks[i] = 0;
      }

      /* Duty güvenlik klempi (max tpp-1, dead time dahil) */
      int32_t max_d = (int32_t)(tpp - 1U) - (int32_t)DDS_DEAD_TIME_TICKS;
      if (g_duty_ticks[i] > max_d)
        g_duty_ticks[i] = max_d;
    }
  }

  /* ---- PWM başlatılmadıysa GPIO'ya dokunma ---- */
  if (!g_pwm_started) {
    return;
  }

  /* ---- SYNC PULSE Geri Sayım: PB1'i zamanında LOW yap ---- */
  if (g_sync_pulse_countdown > 0U) {
    g_sync_pulse_countdown--;
    if (g_sync_pulse_countdown == 0U) {
      GPIOB->BSRR = (uint32_t)GPIO_PIN_1 << 16U; /* PB1 = LOW (atomik) */
    }
  }

  /* ---- 5 bobin için tek yönlü GPIO çıkışı üret (IN_A = IN_B, dead-time
   * korumalı) ---- */
  /* DDS_DEAD_TIME_TICKS = 0: dead time yazılım değil donanım tarafında
   * uygulanıyor. */

  for (uint32_t i = 0U; i < NUM_COILS; i++) {
    /* DENETİM P0 — STOP PERİYOT SONUNU BEKLEMEZ: g_duty_ticks yalnızca periyot başında
     * (period_reset) güncellenir. Düşük frekansta periyot uzundur (1 Hz → 1 s), dolayısıyla
     * yalnız slew'e bakmak durdurmayı bir periyot kadar geciktirirdi. Hedef sıfırlanmışsa
     * (acil durdurma / süre-bitişi / ölü-adam watchdog'u) çıkışı BU tick'te kes: gecikme
     * periyottan bağımsız olarak en fazla bir ISR tick'i = 20 µs. */
    const int32_t duty = (g_target_duty_ticks[i] <= 0) ? 0 : g_duty_ticks[i];
    const int32_t tpp = (int32_t)g_tpp[i];
    const int32_t itick = (int32_t)g_dds_tick[i];

    /* Duty sıfırsa her iki çıkışı da LOW yap ve boşa al */
    if (duty <= 0) {
      if (g_prev_state[i] != 2U) {
        coil_gpio[i].portA->BSRR = (uint32_t)coil_gpio[i].pinA << 16U;
        coil_gpio[i].portB->BSRR = (uint32_t)coil_gpio[i].pinB << 16U;
        g_prev_state[i] = 2U; // 2 = IDLE (Kapalı)
      }
      continue;
    }

    /* Faz ofsetli tick hesapla */
    int32_t adj = itick - g_phase_ticks[i];
    if (adj < 0)
      adj += tpp;

    /* Bipolar dalga durumu (A=1, B=0 ile A=0, B=1 arası sürekli geçiş) */
    uint8_t state = (adj < duty) ? 1U : 0U;

    if (state != g_prev_state[i]) {
      if (state) {
        /* A=1, B=0'a geçiş: ÖNCE B'yi kapat, dead-time bekle, SONRA A'yı aç */
        coil_gpio[i].portB->BSRR = (uint32_t)coil_gpio[i].pinB << 16U;
        for (volatile uint32_t d = 0; d < DDS_DEADTIME_NOP_ITERS; d++) {
          __asm volatile("nop");
        } /* süre ÖLÇÜLMEMİŞ — bkz. DDS_DEADTIME_NOP_ITERS */
        coil_gpio[i].portA->BSRR = (uint32_t)coil_gpio[i].pinA;
      } else {
        /* A=0, B=1'e geçiş: ÖNCE A'yı kapat, dead-time bekle, SONRA B'yi aç */
        coil_gpio[i].portA->BSRR = (uint32_t)coil_gpio[i].pinA << 16U;
        for (volatile uint32_t d = 0; d < DDS_DEADTIME_NOP_ITERS; d++) {
          __asm volatile("nop");
        } /* süre ÖLÇÜLMEMİŞ — bkz. DDS_DEADTIME_NOP_ITERS */
        coil_gpio[i].portB->BSRR = (uint32_t)coil_gpio[i].pinB;
      }
      g_prev_state[i] = state;
    }
  }
}

/* ============================================================================
 * UART BAŞLATMA
 * ----------------------------------------------------------------------------
 * USART3 @ 115200 baud, 8N1, TX=PD8, RX=PD9 (STM32F429ZI Nucleo-144 ST-Link
 * VCP)
 *
 * ÖNEMLİ: Nucleo-F429ZI üzerindeki ST-Link VCP (USB-UART köprüsü) varsayılan
 * olarak USART3 (PD8/PD9) üzerine yönlendirilir. LattePanda USB kablo ile
 * doğrudan COM10 (ST-Link VCP) üzerinden haberleşmek için USART3
 * kullanılmalıdır. Harici USB-UART adaptörü GEREKMİYOR.
 * ============================================================================
 */
static void Coil_UartInit(void) {
  __HAL_RCC_USART3_CLK_ENABLE();

  huart3.Instance = USART3;
  huart3.Init.BaudRate = 115200U;
  huart3.Init.WordLength = UART_WORDLENGTH_8B;
  huart3.Init.StopBits = UART_STOPBITS_1;
  huart3.Init.Parity = UART_PARITY_NONE;
  huart3.Init.Mode = UART_MODE_TX_RX;
  huart3.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart3.Init.OverSampling = UART_OVERSAMPLING_16;

  if (HAL_UART_Init(&huart3) != HAL_OK) {
    Error_Handler();
  }

  /* ✅ NVIC AYARLARI:
   * Kesmeler aktif edilmeden UART Rx kesmesi düşmez. */
  HAL_NVIC_SetPriority(USART3_IRQn, 1, 0);
  HAL_NVIC_EnableIRQ(USART3_IRQn);
}

/* ============================================================================
 * UART ALIM BAŞLAT
 * ============================================================================
 */
static void Coil_UartStartReceive(void) {
  HAL_UART_Receive_IT(&huart3, (uint8_t *)&g_rxByte, 1U);
}

/* ============================================================================
 * UART RX TAMAMLANDI CALLBACK (ISR)
 * ----------------------------------------------------------------------------
 * Byte-by-byte interrupt tabanlı alım + durum makinesi.
 * Her byte geldiğinde HAL bu callback'i çağırır.
 *
 * Binary Protokol State Machine (BinaryCmdPacket_t — 88 byte):
 *
 *  IDLE            ──[0xAA]──► RX_WAIT_HEADER2
 *  RX_WAIT_HEADER2 ──[0x55]──► RX_DATA        (paket başladı, rxLen=2)
 *  RX_WAIT_HEADER2 ──[0xAA]──► RX_WAIT_HEADER2 (yeniden hizalanma)
 *  RX_WAIT_HEADER2 ──[diğer]──► IDLE
 *  RX_DATA         ──[veri]──► RX_DATA         (88 byte dolana kadar topla)
 *  RX_DATA         ──[88. byte]──► IDLE + g_pktReady=1
 *
 * Paket: [0xAA][0x55][5×float duty][5×float phase][5×float freq]
 *        [5×uint32 duration][uint16 ref_ms][uint32 crc32] = 88 byte
 *
 * Overrun koruması:
 *   g_pktReady == 1 iken yeni paket gelirse atlanır (drop edilir).
 *   main() paketi işleyip bayrağı temizleyince bir sonraki kabul edilir.
 * ============================================================================
 */
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
  if (huart->Instance != USART3) {
    goto rearm;
  }

  uint8_t b = (uint8_t)g_rxByte;

  /* Bayt-arasi bosluk: yarim kalmis cerceveyi BIR SONRAKI pakete karistirma (bkz. RX_FRAME_GAP_MS).
   * (uint32 cikarma HAL_GetTick wrap'inde de dogru calisir.) */
  uint32_t now_ms = HAL_GetTick();
  if (g_rxState != RX_IDLE && (now_ms - g_rxLastByteMs) > RX_FRAME_GAP_MS) {
    g_rxState = RX_IDLE;
    g_rxLen = 0;
  }
  g_rxLastByteMs = now_ms;

  switch (g_rxState) {
  case RX_IDLE:
    if (b == 0xAA) {
      g_rxBuf[0] = b;
      g_rxLen = 1;
      g_rxState = RX_WAIT_HEADER2;
    }
    break;

  case RX_WAIT_HEADER2:
    if (b == 0x55) {
      g_rxBuf[1] = b;
      g_rxLen = 2;
      g_rxState = RX_DATA;
    } else if (b == 0xAA) {
      // still wait for header 2
    } else {
      g_rxState = RX_IDLE;
    }
    break;

  case RX_DATA:
    g_rxBuf[g_rxLen++] = b;
    if (g_rxLen >= BINARY_PKT_SIZE) {
      if (!g_pktReady) {
        memcpy((void *)g_pktBuf, (const void *)g_rxBuf, BINARY_PKT_SIZE);
        g_pktReady = 1U;
      }
      g_rxState = RX_IDLE;
    }
    break;

  default:
    g_rxState = RX_IDLE;
    break;
  }

rearm:
  HAL_UART_Receive_IT(&huart3, (uint8_t *)&g_rxByte, 1U);
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart) {
  if (huart->Instance == USART3) {
    /* Eger framing, overrun vs gibi bir hata olursa kesmeyi sifirla ve tekrar
     * ac */
    __HAL_UART_CLEAR_OREFLAG(huart);
    __HAL_UART_CLEAR_NEFLAG(huart);
    __HAL_UART_CLEAR_FEFLAG(huart);
    HAL_UART_AbortReceive(huart);
    g_rxState = RX_IDLE;
    HAL_UART_Receive_IT(&huart3, (uint8_t *)&g_rxByte, 1U);
  }
}

/* custom_atof ve Coil_ParsePacket eski ASCII string parser kalıntılarıdır.
 * Aktif protokol binary BinaryCmdPacket_t (0xAA/0x55 header) kullanır.
 * Bu fonksiyonlar kaldırıldı — artık çağrılmıyor. */

/* ============================================================================
 * GPIO BAŞLATMA
 * ----------------------------------------------------------------------------
 * Yapılandırılan pinler (Software DDS — GPIO Output Mode):
 *
 *   PB0             → LED (çıkış, durum göstergesi)
 *   PD8, PD9        → USART3 TX/RX (AF7) — ST-Link VCP (COM10)
 *
 *   Bobin GPIO çıkışları (Push-Pull, başlangıçta LOW):
 *   PC7   → Bobin 4 IN_B    PC8  → Bobin 1 IN_A
 *   PC9   → Bobin 2 IN_A    PD10 → Bobin 3 IN_A
 *   PD11  → Bobin 3 IN_B
 *   PC6   → Bobin 4 IN_A
 *   PD12  → Bobin 1 IN_B    PE10 → Bobin 2 IN_B
 *
 * NOT: Önceki mimaride (v1.x) bu pinler AF modunda Timer OC kanallarına
 * bağlıydı. DDS mimarisinde (v2.0) tümü GPIO_OUTPUT_PP olarak yapılandırılır.
 * ============================================================================
 */
static void Coil_GpioInit(void) {
  /* ---- Saat Etkinleştirme ---- */
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOE_CLK_ENABLE();

  GPIO_InitTypeDef GPIO_InitStruct = {0};

  /* ---- LED: PB0 + SYNC_OUT: PB1 -- Push-Pull Çıkış ---- */
  /* PB0 = Durum LED'i (düşük hız yeterli)                                  */
  /* PB1 = MASTER SYNC PULSE ÇIKIŞI — ESP32/ESP8266 Slave'lere periyot sync */
  /*        RISING kenar: her PWM döngüsünün başını işaret eder (100Hz)      */
  /*        Sinyal: 100µs (5×20µs) HIGH, geri kalan periyot LOW             */
  GPIO_InitStruct.Pin = GPIO_PIN_0 | GPIO_PIN_1;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH; /* PB1 timing kritik → HIGH */
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0 | GPIO_PIN_1, GPIO_PIN_RESET);

  /* ---- USART3: PD8 (TX), PD9 (RX) -- AF7 ---- */
  /* Nucleo-F429ZI ST-Link VCP bu pinler üzerinden USART3'e bağlıdır. */
  GPIO_InitStruct.Pin = GPIO_PIN_8 | GPIO_PIN_9;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF7_USART3;
  HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);

  /* ---- Bobin GPIO Çıkışları (Push-Pull, başlangıçta LOW) ----
   * Tüm bobin pinleri GPIO_OUTPUT_PP olarak yapılandırılır.
   * Timer AF modu KULLANILMAZ — DDS yazılımsal olarak GPIO sürrer. */
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;

  /* PC6 (Bobin 4 A), PC7 (Bobin 4 B), PC8 (Bobin 1 A), PC9 (Bobin 2 A) */
  GPIO_InitStruct.Pin = GPIO_PIN_6 | GPIO_PIN_7 | GPIO_PIN_8 | GPIO_PIN_9;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

  /* PD10 (Bobin 3 A), PD11 (Bobin 3 B), PD12 (Bobin 1 B) */
  GPIO_InitStruct.Pin = GPIO_PIN_10 | GPIO_PIN_11 | GPIO_PIN_12;
  HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);

  /* PE10 (Bobin 2 B) */
  GPIO_InitStruct.Pin = GPIO_PIN_10;
  HAL_GPIO_Init(GPIOE, &GPIO_InitStruct);

  /* PA8 (Bobin 5 A), PA9 (Bobin 5 B) */
  GPIO_InitStruct.Pin = GPIO_PIN_8 | GPIO_PIN_9;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /* Tüm bobin çıkışlarını güvenli LOW durumuna al */
  HAL_GPIO_WritePin(GPIOC, GPIO_PIN_6 | GPIO_PIN_7 | GPIO_PIN_8 | GPIO_PIN_9,
                    GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOD, GPIO_PIN_10 | GPIO_PIN_11 | GPIO_PIN_12,
                    GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOE, GPIO_PIN_10, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8 | GPIO_PIN_9, GPIO_PIN_RESET);
}

/* ============================================================================
 * SİSTEM SAAT KONFİGÜRASYONU
 * ----------------------------------------------------------------------------
 * HSE (8 MHz bypass) + PLL → SYSCLK = 168 MHz
 *   HCLK  = 168 MHz
 *   APB1  = 42  MHz (TIM2-5 saati: 84 MHz)
 *   APB2  = 84  MHz (TIM1  saati: 168 MHz)
 * ============================================================================
 */
void SystemClock_Config(void) {
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_BYPASS;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = 4U;
  RCC_OscInitStruct.PLL.PLLN = 168U;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = 7U;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {
    Error_Handler();
  }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK |
                                RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;
  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_5) != HAL_OK) {
    Error_Handler();
  }
}

/* ============================================================================
 * HATA İŞLEYİCİ
 * ============================================================================
 */
/**
 * @brief  TÜM bobin çıkışlarını doğrudan BSRR ile LOW'a çeker.
 *
 * DENETİM P1: hata/fault yollarında bobin pinlerine DOKUNULMUYORDU. Bir HardFault'ta
 * Cortex-M varsayılan işleyicisi sonsuz döngüye girer → main() durur → 1500 ms'lik ölü-adam
 * kontrolü BİR DAHA ÇALIŞMAZ. TIM1 ISR'ı hâlâ koşuyorsa son duty sonsuza dek sürülür; ISR de
 * durursa GPIO'lar periyot ortasında DONAR ve IN_A o an HIGH ise tam-köprü tek yönde DC olarak
 * enerjili kalır. Backend'in gönderdiği sıfır-duty paketleri işlenmez, _emergency_stop_all STM
 * tarafında etkisizdir. Bu fonksiyon donanıma en yakın, kesme gerektirmeyen kesme yoludur.
 * ISR-güvenli ve yeniden-girişli: BSRR'ye yazar ve `g_prev_state[i]`'yi IDLE'a (2) çeker.
 * (DENETİM 2026-08-04: eskiden "yalnız BSRR yazar" yazıyordu; g_prev_state sıfırlaması bu
 * denetimde eklendi — bkz. gövdedeki not. Yazılan değer sabit (2U) olduğu için ISR ile
 * araya girse bile sonuç aynıdır, yani yeniden-girişlilik korunur.)
 */
void PEMF_ForceAllCoilOutputsLow(void) {
  for (uint32_t i = 0U; i < NUM_COILS; i++) {
    coil_gpio[i].portA->BSRR = (uint32_t)coil_gpio[i].pinA << 16U;
    coil_gpio[i].portB->BSRR = (uint32_t)coil_gpio[i].pinB << 16U;
    /* DENETIM 2026-08-04: g_prev_state SIFIRLANMIYORDU. ISR "yalniz durum degistiyse GPIO yaz"
     * optimizasyonu yapar (bkz. `if (state != g_prev_state[i])`); pinleri burada zorla LOW'a
     * cekip prev_state'i ESKI degerde birakmak, ISR'in "cikis zaten dogru" sanmasina ve
     * pinleri BIR DAHA surmemesine yol acar. Bugun tek cagiran yol fault-handler/Error_Handler
     * (ikisi de reset ya da sonsuz dongu) oldugu icin canli regresyon yok — ama bu, hasta
     * guvenligi kritik bir fonksiyonun "cagrildiktan sonra donulmez" varsayimina dayanmaktir
     * ve o varsayim kodda hicbir yerde zorlanmiyor. IDLE (2) = "her iki cikis LOW". */
    g_prev_state[i] = 2U;
  }
}

void Error_Handler(void) {
  /* Bobinleri ÖNCE kes, sonra kesmeleri kapat (hasta güvenliği > hata göstergesi). */
  PEMF_ForceAllCoilOutputsLow();
  __disable_irq();
  /* Hata LED'ini yak (PB0) */
  GPIOB->BSRR = (uint32_t)GPIO_PIN_0;
  while (1) { /* Sonsuz bekle */
  }
}

/* ============================================================================
 * FAULT İŞLEYİCİLERİ — bu dosyada TANIMLANMAZ (bilinçli)
 * ----------------------------------------------------------------------------
 * DENETİM P1: HardFault/MemManage/BusFault/UsageFault işleyicileri bobinleri KESMİYOR.
 * Bir HardFault'ta Cortex-M işleyicisi sonsuz döngüye girer → main() durur → 1500 ms'lik
 * ölü-adam kontrolü BİR DAHA ÇALIŞMAZ. TIM1 ISR'ı hâlâ koşuyorsa son duty sonsuza dek
 * sürülür; ISR de durursa GPIO'lar periyot ortasında DONAR ve IN_A o an HIGH ise tam-köprü
 * tek yönde DC olarak enerjili kalır.
 *
 * Bu dört işleyici CubeMX projesinde `Core/Src/stm32f4xx_it.c` içinde ZATEN TANIMLIDIR
 * (arm-none-eabi-ld ile doğrulandı: burada da tanımlanırsa
 * "multiple definition of `HardFault_Handler'" link hatası olur). Bu depo yalnız `main.c`
 * tuttuğundan düzeltme oraya taşındı: aşağıdaki `PEMF_ForceAllCoilOutputsLow()` DIŞA AÇIK
 * bırakılmıştır; `stm32f4xx_it.c` içindeki USER CODE bloklarından çağrılır.
 * Uygulanacak yama: bkz. `firmware/README.md` → "Fault işleyici yaması".
 *
 * NOT (bilinçli olarak YAPILMADI): bağımsız donanım watchdog'u (IWDG) EKLENMEDİ. IWDG,
 * main() döngüsünün her turda süre sınırına uymasını gerektirir; yanlış bir timeout seçimi
 * tedavi ortasında MCU resetine yol açar — tezgâh ölçümü isteyen ayrı bir iştir
 * (denetim raporu P1 fw-no-iwdg-no-fault-safe).
 * ============================================================================
 */

/* ============================================================================
 * IRQ HANDLER'LAR
 * ============================================================================
 */

void TIM1_UP_TIM10_IRQHandler(void) { HAL_TIM_IRQHandler(&htim1); }

#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line) {
  (void)file;
  (void)line;
}
#endif /* USE_FULL_ASSERT */

/*
 * ============================================================================
 * DDS MİMARİ NOTLARI
 * ============================================================================
 *
 * NEDEN YAZILIMSAL DDS?
 * ---------------------
 * STM32 TIM1'in CH1, CH2, CH3 kanalları aynı CNT sayacını paylaşır.
 * Bu yüzden donanımsal olarak farklı kanallara farklı faz vermek
 * İMKANSIZDIR. Yazılımsal DDS ile her bobin için bağımsız faz sayacı
 * kullanılarak bu kısıt aşılır.
 *
 * ESP32 ile AYNI MİMARİ
 * ---------------------
 * Bu DDS uygulaması, ESP32-S3 CoilController.cpp'deki
 * pwm_timer_isr() fonksiyonunun STM32 versiyonudur.
 * Aynı bipolar dalga formu, aynı dead time mantığı kullanılır.
 *
 * PERFORMANS
 * ----------
 * ISR süresi: ~140 CPU cycle (168 MHz'de ~0.8 µs)
 * Kullanılabilir süre: 3360 cycle (20 µs @ 168 MHz)
 * CPU yükü: ~%4.2
 *
 * PWM FREKANSI DEĞİŞTİRME
 * ------------------------
 * DDS_PWM_FREQ_HZ değerini değiştirin. Timer interrupt frekansı (50 kHz)
 * sabit kalır, sadece DDS_TICKS_PER_PERIOD değişir:
 *
 *   Frekans  | TICKS_PER_PERIOD | Duty Çözünürlüğü | Faz Çözünürlüğü
 *   ---------|------------------|------------------|----------------
 *    50 Hz   | 1000             | 0.1%             | 0.36°
 *   100 Hz   | 500              | 0.2%             | 0.72°
 *   200 Hz   | 250              | 0.4%             | 1.44°
 *   500 Hz   | 100              | 1.0%             | 3.6°
 *  1000 Hz   | 50               | 2.0%             | 7.2°
 *
 * ============================================================================
 */
