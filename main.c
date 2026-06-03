/**
 ******************************************************************************
 * @file    main.c
 * @brief   STM32F4 — 4-Kanal Yazılımsal DDS Bipolar Full Bridge PWM Kontrolörü
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
 *  │    Her kesmede yazılımsal DDS ile 4 bobinin GPIO çıkışı üretilir    │
 *  │                                                                     │
 *  │  GPIO Çıkışları (Push-Pull, doğrudan BSRR ile sürülür):            │
 *  │    PC8  (IN_A Bobin 1)   PD12 (IN_B Bobin 1)                      │
 *  │    PC9  (IN_A Bobin 2)   PE10 (IN_B Bobin 2)                      │
 *  │    PD10 (IN_A Bobin 3)   PD11 (IN_B Bobin 3)                      │
 *  │    PC6  (IN_A Bobin 4)   PC7  (IN_B Bobin 4)                      │
 *  │                                                                     │
 *  │  Her bobin BAĞIMSIZ faz kaydırmasına sahiptir!                      │
 *  │  Dead Time: 2 tick × 20µs = 40µs — periyot başında her iki çıkış LOW  │
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
 * UART PAKET FORMATI
 * ============================================================================
 *
 *   ST[d0,d1,d2,d3][p0,p1,p2,p3][ref_ms]EN
 *
 *   d      = Duty cycle  : 0.01 – 0.49  (float)
 *   p      = Faz açısı   : 0.0  – 360.0 (float, derece)
 *   ref_ms = Periyot içi zaman ofseti (int, 0 – period_ms-1)
 *            Python tarafından time.monotonic() % 10 olarak hesaplanır.
 *            STM32, g_dds_tick'i bu değere göre hizalar (Sorun 1b fix).
 *            Geriye dönük uyumluluk: [ref_ms] bloğu opsiyoneldir.
 *
 *   Örnek: ST[0.25,0.30,0.20,0.40][0.0,90.0,180.0,270.0][3]EN
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
 * DONANIM PIN HARİTASI (STM32F446RE Nucleo) — Software DDS
 * ============================================================================
 *
 *   USART3  TX → PD8  (AF7)   USART3  RX → PD9  (AF7)
 *   PC8   → GPIO OUT (IN_A Bobin 1)   PD12  → GPIO OUT (IN_B Bobin 1)
 *   PC9   → GPIO OUT (IN_A Bobin 2)   PE10  → GPIO OUT (IN_B Bobin 2)
 *   PD10  → GPIO OUT (IN_A Bobin 3)   PD11  → GPIO OUT (IN_B Bobin 3)
 *   PC6   → GPIO OUT (IN_A Bobin 4)   PC7   → GPIO OUT (IN_B Bobin 4)
 *   LED   → PB0
 *
 ******************************************************************************
 */

#include "main.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

/* ============================================================================
 * SABİTLER
 * ============================================================================ */

/**
 * @defgroup DDSConfig Yazılımsal DDS Konfigürasyonu
 * @{
 */

/**
 * TIM1 Kesme Kaynağı (APB2 timer saati: 168 MHz)
 *   PSC=167  → Timer tick = 168MHz / 168 = 1 MHz
 *   ARR=19   → Kesme = 1MHz / 20 = 50 kHz (20 µs periyot)
 */
#define DDS_TIMER_PSC           167U
#define DDS_TIMER_ARR           19U

/** DDS Yazılımsal PWM Parametreleri */
#define DDS_PWM_FREQ_HZ         100U                                /**< Hedef PWM frekansı (Hz) */
#define DDS_TICKS_PER_PERIOD    (50000U / DDS_PWM_FREQ_HZ)         /**< = 500 tick/periyot */
#define DDS_DEAD_TIME_TICKS     0U                                  /**< Yazılımsal dead time (DONANIMSAL gecikme ile değiştirildi) */
#define DDS_MAX_DUTY_SLEW       25                                  /**< Periyot başı max duty değişimi (tick cinsinden) */

/** @} */

/** Bobin sayısı */
#define NUM_COILS               5U

/** UART RX tampon boyutu (bayt) */
#define UART_RX_BUF_SZ          128U

/**
 * @defgroup SafetyLimits Güvenlik Sınırları
 * @{
 */
#define DUTY_MIN                0.0f    /**< Minimum duty cycle (Kapalı durum) */
#define DUTY_MAX                0.99f   /**< Maksimum duty cycle (≤%99) */
#define PHASE_DEG_MIN           0.0f    /**< Minimum faz açısı */
#define PHASE_DEG_MAX           360.0f  /**< Maksimum faz açısı */
#define FREQ_MIN                1.0f    /**< Minimum frekans (Hz) */
#define FREQ_MAX                10000.0f/**< Maksimum frekans (Hz) */
/** @} */

/* ============================================================================
 * TİP TANIMLAMALARI
 * ============================================================================ */

/** Tek bir bobinin çalışma parametresi */
typedef struct {
    float duty;     /**< Duty cycle: 0.00 – 0.49 */
    float phase;    /**< Faz açısı : 0.0  – 360.0 derece */
    float freq;     /**< Frekans (Hz): 1.0 - 10000.0 */
    uint32_t dur_min; /**< Süre (dakika): 0 = süresiz */
} CoilParam_t;

/**
 * 4 bobinin parametre seti.
 * volatile: ISR ve main arasında paylaşıldığı için zorunlu.
 */
typedef struct {
    CoilParam_t coil[NUM_COILS];
    volatile uint8_t pending;   /**< 1 = ISR'da uygulanmayı bekliyor */
    uint8_t  ref_ms_valid;      /**< [FIX-1b] 1 = ref_ms bloğu parse edildi */
    uint8_t  ref_ms;            /**< [FIX-1b] 0 .. (period_ms-1), g_dds_tick hizalama için */
} CoilParamSet_t;

/** Bir bobinin A/B GPIO çıkış tanımı */
typedef struct {
    GPIO_TypeDef *portA;    /**< IN_A (pozitif faz) portu */
    uint16_t      pinA;     /**< IN_A pin maskesi */
    GPIO_TypeDef *portB;    /**< IN_B (negatif faz) portu */
    uint16_t      pinB;     /**< IN_B pin maskesi */
} CoilGPIO_t;

/** UART alım durum makinesi durumları */
typedef enum {
    RX_IDLE   = 0,  /**< Paket bekleniyor */
    RX_GOT_S,       /**< 'S' alındı, 'T' bekleniyor */
    RX_DATA,        /**< Veri toplanıyor (ST...E arası) */
    RX_GOT_E        /**< 'E' alındı, 'N' bekleniyor */
} UartRxState_t;

/* ============================================================================
 * PERİFERİ HANDLELERİ
 * ============================================================================ */
TIM_HandleTypeDef   htim1;     /**< 50 kHz DDS kesme kaynağı (TIM8 artık kullanılmıyor) */
UART_HandleTypeDef  huart3;    /**< PC bağlantısı @ 115200 baud */

/* ============================================================================
 * BOBİN GPIO HARİTASI
 * ============================================================================
 *
 * Her bobinin iki yarı-köprü çıkışı (IN_A / IN_B) doğrudan GPIO olarak sürülür.
 * Timer OC kanalları KULLANILMAZ — tüm dalga formu yazılımsal DDS ile üretilir.
 */
static const CoilGPIO_t coil_gpio[NUM_COILS] = {
    { GPIOC, GPIO_PIN_8,  GPIOD, GPIO_PIN_12 },  /* Bobin 1: PC8  (A), PD12 (B) */
    { GPIOC, GPIO_PIN_9,  GPIOE, GPIO_PIN_10 },  /* Bobin 2: PC9  (A), PE10 (B) */
    { GPIOD, GPIO_PIN_10, GPIOD, GPIO_PIN_11 },  /* Bobin 3: PD10 (A), PD11 (B) */
    { GPIOC, GPIO_PIN_6,  GPIOC, GPIO_PIN_7  },  /* Bobin 4: PC6  (A), PC7  (B) */
    { GPIOA, GPIO_PIN_8,  GPIOA, GPIO_PIN_9  },  /* Bobin 5: PA8  (A), PA9  (B) */
};

/* ============================================================================
 * SHADOW (GÖLGE) DEĞİŞKENLER
 * ----------------------------------------------------------------------------
 * g_shadow  : main() veya UART ISR tarafından yazılır
 *             TIM1 Update ISR tarafından okunur
 * g_active  : YALNIZCA TIM1 Update ISR içinde değiştirilir
 *             Donanıma son uygulanan değerlerdir
 * ============================================================================ */
static volatile CoilParamSet_t g_shadow = {
    .coil = {
        {.duty = 0.0f, .phase = 0.0f, .freq = 100.0f, .dur_min = 0},
        {.duty = 0.0f, .phase = 0.0f, .freq = 100.0f, .dur_min = 0},
        {.duty = 0.0f, .phase = 0.0f, .freq = 100.0f, .dur_min = 0},
        {.duty = 0.0f, .phase = 0.0f, .freq = 100.0f, .dur_min = 0},
        {.duty = 0.0f, .phase = 0.0f, .freq = 100.0f, .dur_min = 0}
    },
    .pending = 0,
    .ref_ms_valid = 0,
    .ref_ms = 0
};

/** ISR'ın doğrudan eriştiği aktif parametre seti */
static CoilParamSet_t g_active;

/** PWM çıkışlarının başlatılıp başlatılmadığını takip eden bayrak */
static uint8_t g_pwm_started = 0;

/* ============================================================================
 * DDS DURUM DEĞİŞKENLERİ
 * ============================================================================ */

/** Her bobin için ayrı DDS tick sayacı (0 … tpp-1, 50kHz'de artırılır) */
static volatile uint32_t g_dds_tick[NUM_COILS] = {0, 0, 0, 0, 0};

/** Her bobinin Ticks Per Period değeri (50000 / freq) */
static volatile uint32_t g_tpp[NUM_COILS] = {500, 500, 500, 500, 500};

/** Süre kontrolü için başlangıç zamanı (systick tabanlı milisaniye) */
static volatile uint32_t g_start_ms[NUM_COILS] = {0, 0, 0, 0, 0};

/** Anlık duty tick değerleri (slew rate limiter çıkışı) */
static int32_t g_duty_ticks[NUM_COILS]  = {0, 0, 0, 0, 0};

/** Hedef duty tick değerleri (slew rate limiter girişi) */
static int32_t g_target_duty_ticks[NUM_COILS] = {0, 0, 0, 0, 0};

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
 * ============================================================================ */
#define DDS_SYNC_PULSE_TICKS    5U      /**< Sync pulse genişliği: 5×20µs = 100µs */
static volatile uint8_t g_sync_pulse_countdown = 0U; /**< Kaç tick daha HIGH kalacak */

/* ============================================================================
 * UART ALIM STATE MACHINE DEĞİŞKENLERİ
 * ============================================================================ */
static volatile uint8_t      g_rxByte;                  /**< HAL IT hedef bayt    */
static volatile uint8_t      g_rxBuf[UART_RX_BUF_SZ];  /**< Birikim tamponu      */
static volatile uint16_t     g_rxLen    = 0;
static volatile UartRxState_t g_rxState = RX_IDLE;
static volatile uint8_t      g_pktBuf[UART_RX_BUF_SZ]; /**< Tamamlanmış paket    */
static volatile uint8_t      g_pktReady = 0;            /**< 1 = main işleyecek   */

/* ============================================================================
 * FONKSİYON PROTOTİPLERİ
 * ============================================================================ */

/* Timer Kurulum */
static void Coil_TimInit(void);         /* TIM1 → 50kHz DDS kesme kaynağı */
static void Coil_StartPwmOutputs(void); /* GPIO'ları güvenli başlangıca al */

/* UART */
static void Coil_UartInit(void);
static void Coil_UartStartReceive(void);
static uint8_t Coil_ParsePacket(const uint8_t *buf, CoilParamSet_t *out);

/* GPIO */
static void Coil_GpioInit(void);

/* Core */
void SystemClock_Config(void);
void Error_Handler(void);

/* ============================================================================
 * MAIN
 * ============================================================================ */
int main(void)
{
    /* HAL ve Sistem Saati */
    HAL_Init();
    SystemClock_Config();

    /* GPIO → UART → Timer sırası önemli */
    Coil_GpioInit();
    Coil_UartInit();

    /* Aktif parametreleri gölge başlangıç değerleriyle başlat */
    memcpy(&g_active, (const void *)&g_shadow, sizeof(CoilParamSet_t));
    g_active.pending = 0;

    /* ---- DDS Timer'ı kur ve başlat ---- */
    Coil_TimInit();

    /* UART alımı başlat */
    Coil_UartStartReceive();

    /* Başlangıçta terminale hazır olduğumuzu basalım */
    char init_msg[] = "-> STM_READY: DDS v2.2 (5-ch + HW_SYNC@PB1) Waiting for commands...\r\n";
    HAL_UART_Transmit_IT(&huart3, (uint8_t*)init_msg, strlen(init_msg));

    uint32_t last_communication_ms = HAL_GetTick();

    /* ===================================================================
     * ANA DÖNGÜ
     * -------------------------------------------------------------------
     * Bu döngü sadece UART paketlerini işler.
     * Tüm gerçek zamanlı DDS güncellemeleri TIM1 Update ISR'ındadır.
     * =================================================================== */
    while (1)
    {
        uint32_t current_time = HAL_GetTick();

        if (g_pktReady)
        {
            g_pktReady = 0;  /* Bayrağı önce temizle (overrun koruması) */
            last_communication_ms = current_time;

            CoilParamSet_t parsed = {0};
            if (Coil_ParsePacket((const uint8_t *)g_pktBuf, &parsed))
            {
                /* [FIX-1b] ref_ms_valid varsa 0. bobin üzerinden senkron ofseti hesapla */
                if (parsed.ref_ms_valid)
                {
                    uint32_t p0_freq = (uint32_t)parsed.coil[0].freq;
                    if (p0_freq == 0) p0_freq = 100;
                    uint32_t period_ms = 1000U / p0_freq;
                    if (period_ms == 0) period_ms = 1;
                    
                    uint32_t tpp = 50000U / p0_freq;
                    uint32_t new_tick  = ((uint32_t)parsed.ref_ms * tpp) / period_ms;
                    if (new_tick >= tpp) new_tick = tpp - 1U;
                    
                    __disable_irq();
                    g_dds_tick[0] = new_tick;
                    __enable_irq();
                }
                
                /* İlk komut geldiğinde PWM çıkışlarını başlat */
                if (g_pwm_started == 0)
                {
                    Coil_StartPwmOutputs();
                    g_pwm_started = 1;
                }

                /* Atomik bölge: Gölge değişkenleri güncelle */
                __disable_irq();
                memcpy((void *)&g_shadow, &parsed, sizeof(CoilParamSet_t));
                g_shadow.pending = 1;
                __enable_irq();

                /* Debug/ACK Gönderimi */
                static char ack_msg[256];
                int len = snprintf(ack_msg, sizeof(ack_msg),
                                   "-> STM_OK: D=%d,%d,%d,%d,%d P=%d,%d,%d,%d,%d F=%d,%d,%d,%d,%d T=%lu,%lu,%lu,%lu,%lu\r\n",
                                   (int)(parsed.coil[0].duty * 100),
                                   (int)(parsed.coil[1].duty * 100),
                                   (int)(parsed.coil[2].duty * 100),
                                   (int)(parsed.coil[3].duty * 100),
                                   (int)(parsed.coil[4].duty * 100),
                                   (int)(parsed.coil[0].phase),
                                   (int)(parsed.coil[1].phase),
                                   (int)(parsed.coil[2].phase),
                                   (int)(parsed.coil[3].phase),
                                   (int)(parsed.coil[4].phase),
                                   (int)(parsed.coil[0].freq),
                                   (int)(parsed.coil[1].freq),
                                   (int)(parsed.coil[2].freq),
                                   (int)(parsed.coil[3].freq),
                                   (int)(parsed.coil[4].freq),
                                   (unsigned long)(parsed.coil[0].dur_min),
                                   (unsigned long)(parsed.coil[1].dur_min),
                                   (unsigned long)(parsed.coil[2].dur_min),
                                   (unsigned long)(parsed.coil[3].dur_min),
                                   (unsigned long)(parsed.coil[4].dur_min));
                HAL_UART_Transmit_IT(&huart3, (uint8_t*)ack_msg, (uint16_t)len);

                HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_0);
            }
            else
            {
                static char err_msg[128];
                int len = snprintf(err_msg, sizeof(err_msg), "-> STM_ERR: Parse hatasi! [%s]\r\n", g_pktBuf);
                HAL_UART_Transmit_IT(&huart3, (uint8_t*)err_msg, (uint16_t)len);
            }
        }

        /* Süre (Duration) Kontrolü */
        if (g_pwm_started)
        {
            uint8_t duration_stopped = 0;
            
            for (int i = 0; i < NUM_COILS; i++) {
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
                static char stop_msg[] = "-> STM_STOPPED: Sure(ler) doldu, bobinler kapatildi.\r\n";
                HAL_UART_Transmit_IT(&huart3, (uint8_t*)stop_msg, strlen(stop_msg));
            }
        }

        /* Watchdog Koruması (Ölü Adam Devresi) - Sadece başlatıldıysa kontrol et */
        if (g_pwm_started && (current_time - last_communication_ms > 1500))
        {
            __disable_irq();
            for(int i = 0; i < NUM_COILS; i++) {
                g_shadow.coil[i].duty = 0.0f;
            }
            g_shadow.pending = 1;
            __enable_irq();

            last_communication_ms = current_time;

            static char tout_msg[] = "-> STM_ERR: Watchdog Timeout! Baglanti koptu, bobinler 0'landi.\r\n";
            HAL_UART_Transmit_IT(&huart3, (uint8_t*)tout_msg, strlen(tout_msg));
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
 * ============================================================================ */
static void Coil_TimInit(void)
{
    __HAL_RCC_TIM1_CLK_ENABLE();

    /* TIM1: Base timer olarak yapılandır (PWM kanalı YOK) */
    htim1.Instance               = TIM1;
    htim1.Init.Prescaler         = DDS_TIMER_PSC;
    htim1.Init.CounterMode       = TIM_COUNTERMODE_UP;
    htim1.Init.Period            = DDS_TIMER_ARR;
    htim1.Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    htim1.Init.RepetitionCounter = 0U;
    htim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
    if (HAL_TIM_Base_Init(&htim1) != HAL_OK) { Error_Handler(); }

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
 * ============================================================================ */
static void Coil_StartPwmOutputs(void)
{
    /* Tüm çıkışları güvenli LOW durumuna al */
    for (uint32_t i = 0U; i < NUM_COILS; i++)
    {
        coil_gpio[i].portA->BSRR = (uint32_t)coil_gpio[i].pinA << 16U;
        coil_gpio[i].portB->BSRR = (uint32_t)coil_gpio[i].pinB << 16U;
    }
    /* g_pwm_started = 1 → main() tarafından bu fonksiyondan hemen sonra yapılır */
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
 *      a. 4 bobinin faz-ofsetli bipolar dalga durumunu hesapla
 *      b. GPIO BSRR ile çıkışı atomik güncelle
 *
 * Tam bipolar dalga formu, geçişlerde NOP gecikmesi ile:
 *
 *   adj = (tick - phase_offset) mod TICKS_PER_PERIOD
 *
 *   [0, duty)          → A=HIGH, B=LOW   (pozitif yön)
 *   [duty, period)     → A=LOW,  B=HIGH  (negatif yön)
 *
 * Not: ~500 ns dead time, NOP döngüleriyle donanımsal geçiş anında uygulanır.
 *
 * CPU yükü: ~120 cycle / 3360 available = ~%3.6
 * ============================================================================ */
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    /* Yalnızca TIM1 için işlem yap */
    if (htim->Instance != TIM1) { return; }

    /* ---- Ortak Shadow → Active Transfer ---- */
    if (g_shadow.pending)
    {
        memcpy(&g_active, (const void *)&g_shadow, sizeof(CoilParamSet_t));
        g_active.pending = 0;
        ((volatile CoilParamSet_t *)&g_shadow)->pending = 0;

        /* Float'tan tick'e dönüşüm */
        for (uint32_t i = 0U; i < NUM_COILS; i++)
        {
            float f = g_active.coil[i].freq;
            if (f < FREQ_MIN) f = FREQ_MIN;
            if (f > FREQ_MAX) f = FREQ_MAX;
            g_tpp[i] = (uint32_t)(50000.0f / f);
            
            float tpp_f = (float)g_tpp[i];

            /* Duty → tick */
            float d = g_active.coil[i].duty;
            if (d < DUTY_MIN) d = DUTY_MIN;
            if (d > DUTY_MAX) d = DUTY_MAX;
            g_target_duty_ticks[i] = (int32_t)(d * tpp_f);

            /* Faz → tick */
            float p = g_active.coil[i].phase;
            if (p < PHASE_DEG_MIN) p = PHASE_DEG_MIN;
            if (p > PHASE_DEG_MAX) p = PHASE_DEG_MAX;
            g_phase_ticks[i] = (int32_t)((p / 360.0f) * tpp_f);
            
            /* Süre takibi resetlemesi (yeni komut geldiğinde) */
            if (g_active.coil[i].duty > 0.0f) {
                if (g_start_ms[i] == 0) {
                    g_start_ms[i] = HAL_GetTick(); // Eğer kapalıyken yeni açıldıysa süreyi başlat
                }
            } else {
                g_start_ms[i] = 0;
            }
        }
    }

    /* ---- Bobin bazlı tick, period ve slew rate limiter ---- */
    for (uint32_t i = 0U; i < NUM_COILS; i++)
    {
        uint32_t tick = g_dds_tick[i] + 1U;
        uint8_t period_reset = 0;
        uint32_t tpp = g_tpp[i];
        
        if (tick >= tpp)
        {
            tick = 0U;
            period_reset = 1;
        }
        g_dds_tick[i] = tick;
        
        if (period_reset)
        {
            /* Master Sync Pulse sadece Bobin 1 (Referans) için üretilir */
            if (i == 0) {
                GPIOB->BSRR = (uint32_t)GPIO_PIN_1;          /* PB1 = HIGH */
                g_sync_pulse_countdown = DDS_SYNC_PULSE_TICKS;
            }
            
            /* Slew rate limiter */
            int32_t err = g_target_duty_ticks[i] - g_duty_ticks[i];
            if (err >  DDS_MAX_DUTY_SLEW) err =  DDS_MAX_DUTY_SLEW;
            if (err < -DDS_MAX_DUTY_SLEW) err = -DDS_MAX_DUTY_SLEW;
            g_duty_ticks[i] += err;
            if (g_duty_ticks[i] < 0) g_duty_ticks[i] = 0;

            /* Duty güvenlik klempi (max tpp-1, dead time dahil) */
            int32_t max_d = (int32_t)(tpp - 1U) - (int32_t)DDS_DEAD_TIME_TICKS;
            if (g_duty_ticks[i] > max_d) g_duty_ticks[i] = max_d;
        }
    }

    /* ---- PWM başlatılmadıysa GPIO'ya dokunma ---- */
    if (!g_pwm_started) { return; }

    /* ---- SYNC PULSE Geri Sayım: PB1'i zamanında LOW yap ---- */
    if (g_sync_pulse_countdown > 0U)
    {
        g_sync_pulse_countdown--;
        if (g_sync_pulse_countdown == 0U)
        {
            GPIOB->BSRR = (uint32_t)GPIO_PIN_1 << 16U; /* PB1 = LOW (atomik) */
        }
    }

    /* ---- 4 bobin için tek yönlü GPIO çıkışı üret (IN_A = IN_B, dead-time korumalı) ---- */
    const int32_t dt = (int32_t)DDS_DEAD_TIME_TICKS;

    for (uint32_t i = 0U; i < NUM_COILS; i++)
    {
        const int32_t duty = g_duty_ticks[i];
        const int32_t tpp  = (int32_t)g_tpp[i];
        const int32_t itick = (int32_t)g_dds_tick[i];

        /* Duty sıfırsa her iki çıkışı da LOW yap ve boşa al */
        if (duty <= 0)
        {
            if (g_prev_state[i] != 2U) {
                coil_gpio[i].portA->BSRR = (uint32_t)coil_gpio[i].pinA << 16U;
                coil_gpio[i].portB->BSRR = (uint32_t)coil_gpio[i].pinB << 16U;
                g_prev_state[i] = 2U; // 2 = IDLE (Kapalı)
            }
            continue;
        }

        /* Faz ofsetli tick hesapla */
        int32_t adj = itick - g_phase_ticks[i];
        if (adj < 0) adj += tpp;

        /* Bipolar dalga durumu (A=1, B=0 ile A=0, B=1 arası sürekli geçiş) */
        uint8_t state = (adj < duty) ? 1U : 0U;

        if (state != g_prev_state[i])
        {
            if (state)
            {
                /* A=1, B=0'a geçiş: Önce B'yi kapat, 500ns bekle, A'yı aç */
                coil_gpio[i].portB->BSRR = (uint32_t)coil_gpio[i].pinB << 16U;
                for (volatile uint32_t d = 0; d < 21; d++) { __asm volatile("nop"); } /* ~500ns @ 168MHz */
                coil_gpio[i].portA->BSRR = (uint32_t)coil_gpio[i].pinA;
            }
            else
            {
                /* A=0, B=1'e geçiş: Önce A'yı kapat, 500ns bekle, B'yi aç */
                coil_gpio[i].portA->BSRR = (uint32_t)coil_gpio[i].pinA << 16U;
                for (volatile uint32_t d = 0; d < 21; d++) { __asm volatile("nop"); } /* ~500ns @ 168MHz */
                coil_gpio[i].portB->BSRR = (uint32_t)coil_gpio[i].pinB;
            }
            g_prev_state[i] = state;
        }
    }
}

/* ============================================================================
 * UART BAŞLATMA
 * ----------------------------------------------------------------------------
 * USART3 @ 115200 baud, 8N1, TX=PD8, RX=PD9 (STM32F446RE Nucleo)
 * ============================================================================ */
static void Coil_UartInit(void)
{
    __HAL_RCC_USART3_CLK_ENABLE();

    huart3.Instance          = USART3;
    huart3.Init.BaudRate     = 115200U;
    huart3.Init.WordLength   = UART_WORDLENGTH_8B;
    huart3.Init.StopBits     = UART_STOPBITS_1;
    huart3.Init.Parity       = UART_PARITY_NONE;
    huart3.Init.Mode         = UART_MODE_TX_RX;
    huart3.Init.HwFlowCtl    = UART_HWCONTROL_NONE;
    huart3.Init.OverSampling = UART_OVERSAMPLING_16;

    if (HAL_UART_Init(&huart3) != HAL_OK) { Error_Handler(); }

    /* ✅ NVIC AYARLARI EKLENDI:
     * Kesmeler aktif edilmeden UART Rx kesmesi düşmez. */
    HAL_NVIC_SetPriority(USART3_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(USART3_IRQn);
}

/* ============================================================================
 * UART ALIM BAŞLAT
 * ============================================================================ */
static void Coil_UartStartReceive(void)
{
    HAL_UART_Receive_IT(&huart3, (uint8_t *)&g_rxByte, 1U);
}

/* ============================================================================
 * UART RX TAMAMLANDI CALLBACK (ISR)
 * ----------------------------------------------------------------------------
 * Byte-by-byte interrupt tabanlı alım + durum makinesi.
 * Her byte geldiğinde HAL bu callback'i çağırır.
 *
 * Durum Makinesi:
 *
 *  IDLE ──['S']──► GOT_S
 *  GOT_S──['T']──► DATA          GOT_S──[diğer]──► IDLE
 *  DATA ──[veri]──► DATA  (tampon dolu ise → IDLE + reset)
 *  DATA ──['E']──► GOT_E
 *  GOT_E──['N']──► IDLE + g_pktReady=1
 *  GOT_E──[diğer]──► IDLE
 *
 * Overrun koruması:
 *   g_pktReady == 1 iken yeni paket gelirse atlanır.
 *   main() paketi işleyip bayrağı temizleyince bir sonraki alınır.
 * ============================================================================ */
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance != USART3) { goto rearm; }

    uint8_t b = (uint8_t)g_rxByte;

    switch (g_rxState)
    {
        /* ------- IDLE: Paket başlangıcı bekle ------- */
        case RX_IDLE:
            if (b == 'S')
            {
                g_rxLen   = 0U;
                g_rxState = RX_GOT_S;
            }
            break;

        /* ------- GOT_S: 'T' bekleniyor ------- */
        case RX_GOT_S:
            if (b == 'T')
            {
                g_rxState = RX_DATA;
                g_rxLen = 0U;
            }
            else
            {
                /* Sahte 'S' — sıfırla */
                g_rxLen   = 0U;
                g_rxState = RX_IDLE;
            }
            break;

        /* ------- DATA: Veri toplama ------- */
        case RX_DATA:
            if (b == 'E')
            {
                /* Paket sonu yaklaşıyor */
                g_rxState = RX_GOT_E;
            }
            else
            {
                if (g_rxLen < (UART_RX_BUF_SZ - 1U))
                {
                    g_rxBuf[g_rxLen++] = b;
                }
                else
                {
                    /* Tampon taşması — paketi iptal et */
                    g_rxLen   = 0U;
                    g_rxState = RX_IDLE;
                }
            }
            break;

        /* ------- GOT_E: 'N' bekleniyor ------- */
        case RX_GOT_E:
            if (b == 'N')
            {
                /* Tam paket alındı — null-terminate et */
                g_rxBuf[g_rxLen] = '\0';

                /* Önceki paket işlenmediyse yeni paketi atla (CPU koruması) */
                if (!g_pktReady)
                {
                    memcpy((void *)g_pktBuf,
                           (const void *)g_rxBuf,
                           (size_t)(g_rxLen + 1U));
                    g_pktReady = 1U;
                }
            }
            /* Her iki durumda state'i sıfırla */
            g_rxLen   = 0U;
            g_rxState = RX_IDLE;
            break;

        default:
            g_rxLen   = 0U;
            g_rxState = RX_IDLE;
            break;
    }

rearm:
    /* ⚠️ Her CALLBACK sonunda mutlaka yeniden silahlan! */
    HAL_UART_Receive_IT(&huart3, (uint8_t *)&g_rxByte, 1U);
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART3)
    {
        /* Eger framing, overrun vs gibi bir hata olursa kesmeyi sifirla ve tekrar ac */
        __HAL_UART_CLEAR_OREFLAG(huart);
        __HAL_UART_CLEAR_NEFLAG(huart);
        __HAL_UART_CLEAR_FEFLAG(huart);
        HAL_UART_AbortReceive(huart);
        g_rxState = RX_IDLE;
        HAL_UART_Receive_IT(&huart3, (uint8_t *)&g_rxByte, 1U);
    }
}

/* ============================================================================
 * PAKET AYRIŞTIRICISI (PARSER)
 * ----------------------------------------------------------------------------
 * Giriş (ST ve EN striplenmiş içerik):
 *   [d0,d1,d2,d3][p0,p1,p2,p3][ref_ms]
 *
 * Örnek giriş tamponu:
 *   "[0.25,0.30,0.20,0.40][0.0,90.0,180.0,270.0][3]"
 *
 * Ayrıştırma adımları:
 *   1. İlk '[' bul → duty bloğunu sscanf ile oku
 *   2. ']' ve ardından '[' bul → faz bloğunu sscanf ile oku
 *   3. ']' ve ardından '[' bul → ref_ms bloğunu oku (OPSİYONEL — geriye dönük uyumlu)
 *   4. Değer aralık kontrolü yap
 *   5. Geçerliyse out'a yaz
 *
 * @param buf : Null-terminated string (g_pktBuf'tan kopyalanan)
 * @param out : Başarı durumunda doldurulacak yapı
 * @return    : 1 = başarı, 0 = hata
 * ============================================================================ */
/* Basit ve C standart bağımlılığını ortadan kaldıran özel str to float fonksiyonu */
static float custom_atof(const char **s) {
    float res = 0.0f;
    float fact = 1.0f;
    const char *p = *s;

    /* Geçersiz veya boş ise dön */
    if (!p || *p == '\0') return 0.0f;

    while (*p == ' ') p++; /* boşluğu atla */

    while (*p >= '0' && *p <= '9') {
        res = res * 10.0f + (*p - '0');
        p++;
    }

    if (*p == '.') {
        p++;
        while (*p >= '0' && *p <= '9') {
            fact /= 10.0f;
            res += (*p - '0') * fact;
            p++;
        }
    }

    *s = p; // ulaşılan son noktayı döndür
    return res;
}

static uint8_t Coil_ParsePacket(const uint8_t *buf, CoilParamSet_t *out)
{
    const char *p = (const char *)buf;

    /* ---- Duty Bloğu ---- */
    const char *d_open = strchr(p, '[');
    if (!d_open) { return 0U; }
    p = d_open + 1; /* '[' atla */

    float d[NUM_COILS];
    for(int i=0; i<NUM_COILS; i++) {
        const char *oldp = p;
        d[i] = custom_atof(&p);
        if (p == oldp) return 0U; /* Geçersiz sayı parse edildiğinde 0 dön */
        if (*p == ',') p++;
    }

    /* ---- Faz Bloğu ---- */
    const char *d_close = strchr(p, ']');
    if (!d_close) { return 0U; }

    const char *p_open = strchr(d_close + 1U, '[');
    if (!p_open) { return 0U; }
    p = p_open + 1; /* '[' atla */

    float ph[NUM_COILS];
    for(int i=0; i<NUM_COILS; i++) {
        const char *oldp = p;
        ph[i] = custom_atof(&p);
        if (p == oldp) return 0U;
        if (*p == ',') p++;
    }

    /* ---- Frekans Bloğu ---- */
    const char *p_close = strchr(p, ']');
    if (!p_close) { return 0U; }

    const char *f_open = strchr(p_close + 1U, '[');
    if (!f_open) { return 0U; }
    p = f_open + 1; /* '[' atla */

    float freq[NUM_COILS];
    for(int i=0; i<NUM_COILS; i++) {
        const char *oldp = p;
        freq[i] = custom_atof(&p);
        if (p == oldp) return 0U;
        if (*p == ',') p++;
    }

    /* ---- Süre (Duration) Bloğu ---- */
    const char *f_close = strchr(p, ']');
    if (!f_close) { return 0U; }

    const char *dur_open = strchr(f_close + 1U, '[');
    if (!dur_open) { return 0U; }
    p = dur_open + 1; /* '[' atla */

    float dur[NUM_COILS];
    for(int i=0; i<NUM_COILS; i++) {
        const char *oldp = p;
        dur[i] = custom_atof(&p);
        if (p == oldp) return 0U;
        if (*p == ',') p++;
    }

    /* ---- Değer Doğrulama + Çıkış Kopyalama ---- */
    for (uint32_t i = 0U; i < NUM_COILS; i++)
    {
        if (d[i]  < DUTY_MIN       || d[i]  > DUTY_MAX)       { return 0U; }
        if (ph[i] < PHASE_DEG_MIN  || ph[i] > PHASE_DEG_MAX)  { return 0U; }
        if (freq[i] < FREQ_MIN     || freq[i] > FREQ_MAX)     { return 0U; }

        out->coil[i].duty  = d[i];
        out->coil[i].phase = ph[i];
        out->coil[i].freq  = freq[i];
        out->coil[i].dur_min = (uint32_t)dur[i];
    }

    /* ---- [FIX-1b] ref_ms Bloğu (OPSİYONEL — eski format hâlâ çalışır) ---- */
    /* Süre bloğunun ']' kapanışını bul, ardından '[ref_ms]' ara */
    out->ref_ms_valid = 0U;
    const char *p2_close = strchr(p, ']');
    if (p2_close)
    {
        const char *ref_open = strchr(p2_close + 1U, '[');
        if (ref_open)
        {
            p = ref_open + 1U;
            const char *oldp = p;
            float ref_f = custom_atof(&p);
            if (p != oldp)  /* Başarılı parse */
            {
                uint32_t period_ms = 1000U / DDS_PWM_FREQ_HZ;  /* = 10 */
                uint32_t ref_int   = (uint32_t)ref_f;
                if (ref_int < period_ms)  /* 0 .. period_ms-1 aralığı kontrolü */
                {
                    out->ref_ms       = (uint8_t)ref_int;
                    out->ref_ms_valid = 1U;
                }
            }
        }
    }

    out->pending = 1U;
    return 1U;
}

/* ============================================================================
 * GPIO BAŞLATMA
 * ----------------------------------------------------------------------------
 * Yapılandırılan pinler (Software DDS — GPIO Output Mode):
 *
 *   PB0             → LED (çıkış, durum göstergesi)
 *   PD8, PD9        → USART3 TX/RX (AF7)
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
 * ============================================================================ */
static void Coil_GpioInit(void)
{
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
    GPIO_InitStruct.Pin   = GPIO_PIN_0 | GPIO_PIN_1;
    GPIO_InitStruct.Mode  = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull  = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;  /* PB1 timing kritik → HIGH */
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0 | GPIO_PIN_1, GPIO_PIN_RESET);

    /* ---- USART3: PD8 (TX), PD9 (RX) -- AF7 ---- */
    GPIO_InitStruct.Pin       = GPIO_PIN_8 | GPIO_PIN_9;
    GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull      = GPIO_NOPULL;
    GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_VERY_HIGH;
    GPIO_InitStruct.Alternate = GPIO_AF7_USART3;
    HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);

    /* ---- Bobin GPIO Çıkışları (Push-Pull, başlangıçta LOW) ----
     * Tüm bobin pinleri GPIO_OUTPUT_PP olarak yapılandırılır.
     * Timer AF modu KULLANILMAZ — DDS yazılımsal olarak GPIO sürrer. */
    GPIO_InitStruct.Mode  = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull  = GPIO_NOPULL;
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
    HAL_GPIO_WritePin(GPIOC, GPIO_PIN_6 | GPIO_PIN_7 | GPIO_PIN_8 | GPIO_PIN_9, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_10 | GPIO_PIN_11 | GPIO_PIN_12, GPIO_PIN_RESET);
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
 * ============================================================================ */
void SystemClock_Config(void)
{
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

    __HAL_RCC_PWR_CLK_ENABLE();
    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

    RCC_OscInitStruct.OscillatorType    = RCC_OSCILLATORTYPE_HSE;
    RCC_OscInitStruct.HSEState          = RCC_HSE_BYPASS;
    RCC_OscInitStruct.PLL.PLLState      = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource     = RCC_PLLSOURCE_HSE;
    RCC_OscInitStruct.PLL.PLLM          = 4U;
    RCC_OscInitStruct.PLL.PLLN          = 168U;
    RCC_OscInitStruct.PLL.PLLP          = RCC_PLLP_DIV2;
    RCC_OscInitStruct.PLL.PLLQ          = 7U;
    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) { Error_Handler(); }

    RCC_ClkInitStruct.ClockType         = RCC_CLOCKTYPE_HCLK  | RCC_CLOCKTYPE_SYSCLK
                                        | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource      = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider     = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider    = RCC_HCLK_DIV4;
    RCC_ClkInitStruct.APB2CLKDivider    = RCC_HCLK_DIV2;
    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_5) != HAL_OK)
    {
        Error_Handler();
    }
}

/* ============================================================================
 * HATA İŞLEYİCİ
 * ============================================================================ */
void Error_Handler(void)
{
    __disable_irq();
    /* Hata LED'ini yak (PB0) */
    GPIOB->BSRR = (uint32_t)GPIO_PIN_0;
    while (1) { /* Sonsuz bekle */ }
}

/* ============================================================================
 * IRQ HANDLER'LAR
 * ============================================================================ */

void TIM1_UP_TIM10_IRQHandler(void)
{
    HAL_TIM_IRQHandler(&htim1);
}

void USART3_IRQHandler(void)
{
    HAL_UART_IRQHandler(&huart3);
}

#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line)
{
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