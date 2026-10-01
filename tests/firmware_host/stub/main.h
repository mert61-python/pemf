/* tests/firmware_host — GERÇEK main.h YERİNE geçen HAL taklidi (ana makine ISR koşum takımı, Dalga 1 · 1-B).
 * Kaynak: DENETİM-08 koşum takımının ölçülmüş taklidi (2026-09-25; aynı yüzey). Yalnız main.c'nin kullandığı
 * yüzey; HAL davranış kuralları vendored HAL 1.8.5'ten (stm32f4xx_hal_uart.c).
 * ⚠️ İKİ KANCA (aparat ekler): main.c kopyasındaki her `X->BSRR = v;` yazımı `pemf_host_bsrr(X, v)`, her
 * `__asm volatile("nop");` `pemf_host_nop()` olur → yazım SIRASI ve aradaki NOP sayısı kaydedilir. MSVC ve gcc. */
#ifndef __MAIN_H
#define __MAIN_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

typedef enum { HAL_OK = 0, HAL_ERROR = 1, HAL_BUSY = 2, HAL_TIMEOUT = 3 } HAL_StatusTypeDef;

typedef struct { volatile uint32_t MODER, OTYPER, OSPEEDR, PUPDR, IDR, ODR, BSRR, LCKR, AFR[2]; } GPIO_TypeDef;
extern GPIO_TypeDef g_gpioa, g_gpiob, g_gpioc, g_gpiod, g_gpioe;
#define GPIOA (&g_gpioa)
#define GPIOB (&g_gpiob)
#define GPIOC (&g_gpioc)
#define GPIOD (&g_gpiod)
#define GPIOE (&g_gpioe)

typedef struct { uint32_t Pin, Mode, Pull, Speed, Alternate; } GPIO_InitTypeDef;
#define GPIO_PIN_0 0x0001U
#define GPIO_PIN_1 0x0002U
#define GPIO_PIN_2 0x0004U
#define GPIO_PIN_3 0x0008U
#define GPIO_PIN_4 0x0010U
#define GPIO_PIN_5 0x0020U
#define GPIO_PIN_6 0x0040U
#define GPIO_PIN_7 0x0080U
#define GPIO_PIN_8 0x0100U
#define GPIO_PIN_9 0x0200U
#define GPIO_PIN_10 0x0400U
#define GPIO_PIN_11 0x0800U
#define GPIO_PIN_12 0x1000U
#define GPIO_PIN_13 0x2000U
#define GPIO_PIN_14 0x4000U
#define GPIO_PIN_15 0x8000U
#define GPIO_MODE_OUTPUT_PP 1U
#define GPIO_MODE_AF_PP 2U
#define GPIO_NOPULL 0U
#define GPIO_SPEED_FREQ_HIGH 2U
#define GPIO_SPEED_FREQ_VERY_HIGH 3U
#define GPIO_AF7_USART3 7U
typedef enum { GPIO_PIN_RESET = 0, GPIO_PIN_SET } GPIO_PinState;

typedef struct { int dummy; } TIM_TypeDef;
typedef struct { int dummy; } USART_TypeDef;
extern TIM_TypeDef g_tim1;
extern USART_TypeDef g_usart3;
#define TIM1 (&g_tim1)
#define USART3 (&g_usart3)

typedef struct {
  TIM_TypeDef *Instance;
  struct { uint32_t Prescaler, CounterMode, Period, ClockDivision, RepetitionCounter, AutoReloadPreload; } Init;
} TIM_HandleTypeDef;

#define HAL_UART_STATE_READY 0x20U
#define HAL_UART_STATE_BUSY_TX 0x21U
#define HAL_UART_STATE_BUSY_RX 0x22U
typedef struct {
  USART_TypeDef *Instance;
  struct { uint32_t BaudRate, WordLength, StopBits, Parity, Mode, HwFlowCtl, OverSampling; } Init;
  volatile uint32_t gState;
  volatile uint32_t RxState;
} UART_HandleTypeDef;

#define TIM_COUNTERMODE_UP 0U
#define TIM_CLOCKDIVISION_DIV1 0U
#define TIM_AUTORELOAD_PRELOAD_ENABLE 1U
#define TIM1_UP_TIM10_IRQn 25
#define USART3_IRQn 39
#define UART_WORDLENGTH_8B 0U
#define UART_STOPBITS_1 0U
#define UART_PARITY_NONE 0U
#define UART_MODE_TX_RX 0xCU
#define UART_HWCONTROL_NONE 0U
#define UART_OVERSAMPLING_16 0U

typedef struct { uint32_t OscillatorType, HSEState; struct { uint32_t PLLState, PLLSource, PLLM, PLLN, PLLP, PLLQ; } PLL; } RCC_OscInitTypeDef;
typedef struct { uint32_t ClockType, SYSCLKSource, AHBCLKDivider, APB1CLKDivider, APB2CLKDivider; } RCC_ClkInitTypeDef;
#define RCC_OSCILLATORTYPE_HSE 1U
#define RCC_HSE_BYPASS 5U
#define RCC_PLL_ON 2U
#define RCC_PLLSOURCE_HSE 1U
#define RCC_PLLP_DIV2 2U
#define RCC_CLOCKTYPE_HCLK 2U
#define RCC_CLOCKTYPE_SYSCLK 1U
#define RCC_CLOCKTYPE_PCLK1 4U
#define RCC_CLOCKTYPE_PCLK2 8U
#define RCC_SYSCLKSOURCE_PLLCLK 2U
#define RCC_SYSCLK_DIV1 0U
#define RCC_HCLK_DIV4 5U
#define RCC_HCLK_DIV2 4U
#define FLASH_LATENCY_5 5U
#define PWR_REGULATOR_VOLTAGE_SCALE1 1U

/* pemf_akim.c'nin registre yüzeyi */
typedef struct { volatile uint32_t APB1ENR, APB2ENR; } RCC_TypeDef;
extern RCC_TypeDef g_rcc;
#define RCC (&g_rcc)
#define RCC_APB2ENR_ADC1EN (1U << 8)
typedef struct { volatile uint32_t SR, CR1, CR2, SMPR1, SMPR2, SQR3; volatile uint32_t DR; } ADC_TypeDef;
typedef struct { volatile uint32_t CCR; } ADC_Common_TypeDef;
extern ADC_TypeDef g_adc1;
extern ADC_Common_TypeDef g_adc_common;
#define ADC1 (&g_adc1)
#define ADC (&g_adc_common)
#define ADC_CCR_ADCPRE (3U << 16)
#define ADC_CCR_ADCPRE_0 (1U << 16)
#define ADC_CR2_ADON 1U
#define ADC_CR2_SWSTART (1U << 30)
#define ADC_SR_EOC 2U

#define __HAL_RCC_TIM1_CLK_ENABLE() ((void)0)
#define __HAL_RCC_USART3_CLK_ENABLE() ((void)0)
#define __HAL_RCC_GPIOA_CLK_ENABLE() ((void)0)
#define __HAL_RCC_GPIOB_CLK_ENABLE() ((void)0)
#define __HAL_RCC_GPIOC_CLK_ENABLE() ((void)0)
#define __HAL_RCC_GPIOD_CLK_ENABLE() ((void)0)
#define __HAL_RCC_GPIOE_CLK_ENABLE() ((void)0)
#define __HAL_RCC_PWR_CLK_ENABLE() ((void)0)
#define __HAL_PWR_VOLTAGESCALING_CONFIG(x) ((void)(x))
#define __HAL_UART_CLEAR_OREFLAG(h) ((void)(h))
#define __HAL_UART_CLEAR_NEFLAG(h) ((void)(h))
#define __HAL_UART_CLEAR_FEFLAG(h) ((void)(h))
/* 1-B inceleme (i3): `Error_Handler` davranışla ölçülebilsin diye kancalı — aparat `hata` kipinde buradan
 * longjmp ile çıkar (gerçek kod sonsuz döngüye girer). Diğer kiplerde etkisiz. */
void pemf_host_disable_irq(void);
#define __disable_irq() pemf_host_disable_irq()
#define __enable_irq() ((void)0)

HAL_StatusTypeDef HAL_Init(void);
uint32_t HAL_GetTick(void);
HAL_StatusTypeDef HAL_UART_Init(UART_HandleTypeDef *h);
HAL_StatusTypeDef HAL_UART_Transmit(UART_HandleTypeDef *h, const uint8_t *p, uint16_t n, uint32_t t);
HAL_StatusTypeDef HAL_UART_Transmit_IT(UART_HandleTypeDef *h, const uint8_t *p, uint16_t n);
HAL_StatusTypeDef HAL_UART_Receive_IT(UART_HandleTypeDef *h, uint8_t *p, uint16_t n);
HAL_StatusTypeDef HAL_UART_AbortReceive(UART_HandleTypeDef *h);
void HAL_NVIC_SetPriority(int irq, uint32_t a, uint32_t b);
void HAL_NVIC_EnableIRQ(int irq);
HAL_StatusTypeDef HAL_TIM_Base_Init(TIM_HandleTypeDef *h);
HAL_StatusTypeDef HAL_TIM_Base_Start_IT(TIM_HandleTypeDef *h);
void HAL_TIM_IRQHandler(TIM_HandleTypeDef *h);
void HAL_GPIO_Init(GPIO_TypeDef *p, GPIO_InitTypeDef *i);
void HAL_GPIO_WritePin(GPIO_TypeDef *p, uint16_t pin, GPIO_PinState s);
void HAL_GPIO_TogglePin(GPIO_TypeDef *p, uint16_t pin);
HAL_StatusTypeDef HAL_RCC_OscConfig(RCC_OscInitTypeDef *o);
HAL_StatusTypeDef HAL_RCC_ClockConfig(RCC_ClkInitTypeDef *c, uint32_t l);

void HAL_TIM_MspPostInit(TIM_HandleTypeDef *htim);
/* aparat kancaları */
void pemf_host_bsrr(GPIO_TypeDef *port, uint32_t deger);
void pemf_host_nop(void);
void Error_Handler(void);
#endif
