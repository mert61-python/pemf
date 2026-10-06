/* tests/firmware_host/isr_kosum.c — ANA MAKİNE ISR KOŞUM TAKIMI (Dalga 1 · 1-B: D1.21, D1.25–D1.28).
 *
 * GERÇEK firmware/stm32_pemf/Core/Src/main.c bu çeviri birimine #include edilir (aparat yalnız iki satır
 * biçimini değiştirir: `X->BSRR = v;` → pemf_host_bsrr(X, v) ve `__asm volatile("nop");` → pemf_host_nop();
 * anlam aynı, yazım SIRASI kaydedilir). TIM1 ISR'ı (HAL_TIM_PeriodElapsedCallback) doğrudan, tick tick çağrılır.
 * Donanıma DOKUNMAZ. MSVC (`cl /std:c11`) ve gcc (`-std=c11`) ile derlenir; KAYNAK makrosu dönüştürülmüş
 * main.c'nin yoludur.
 *
 * Kipler (stdout satırları ayrıştırıcı içindir):
 *   harita                → "H <i> <portA> <pinA> <portB> <pinB>" (main.c'nin coil_gpio tablosu) + "K <i> <unipolar>"
 *   ofset                 → "O <alan> <offsetof>" (BinaryCmdPacket_t) + "Z <sizeof>" + "R <UART_RX_BUF_SZ>"
 *   isr N bobin_maske f d p [t2 f2 d2 p2 [ref_ms]]
 *                         → (ref_ms: ikinci set HW_SYNC hizalamasını da taşır — 1-G İG-8.28)
 *                           "B <tick> <port> <bsrr_hex> <onceki_nop>" her BSRR yazımı;
 *                           "S <tick> <i> <tpp> <duty_ticks> <hedef>" parametre uygulandıktan sonraki ilk tick'te
 *                           ve t2'den hemen önce. Bobin maskesindeki bobinler (f, d, p) ile sürülür, diğerleri duty 0.
 *                           İsteğe bağlı ortam (1-G inceleme): ISR_GUNLUK_BAS (günlük başlangıcı), ISR_KIP_BAS ve
 *                           ISR_KIP_TICK + ISR_KIP_MASKE (çalışırken kip değişimi) — bkz. isr dalı.
 *   zorla|hata N bobin_maske f d p
 *                         → N tick sürülür, "BASLA", sonra zorla: PEMF_ForceAllCoilOutputsLow() · hata: Error_Handler()
 *                           (BSRR günlüklü); "P <i> <g_prev_state>"; hata kipinde "IRQ" (kesmeler kapatılmaya varıldı).
 *   etkin f d u [f d u ...] → "E <f> <d> <u> <binde>" — firmware'in ACK `E=` rapor işlevi (Coil_EtkinDutyBinde;
 *                           Y69). Yalnız main.c metni PEMF_HOST_ETKIN_SONDASI tanımıyla biterse derlenir. ISR koşmaz;
 *                           ölçülen oranla kıyas çağıranda (tests/test_firmware_ETKIN_duty_ACK_Y69.py).
 */
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "main.h"

GPIO_TypeDef g_gpioa, g_gpiob, g_gpioc, g_gpiod, g_gpioe;
TIM_TypeDef g_tim1;
USART_TypeDef g_usart3;
RCC_TypeDef g_rcc;
ADC_TypeDef g_adc1;
ADC_Common_TypeDef g_adc_common;

static unsigned long long g_tick = 0;
static unsigned g_nop = 0;
static int g_gunluk = 0;

static const char *port_adi(GPIO_TypeDef *p) {
  if (p == &g_gpioa) return "A";
  if (p == &g_gpiob) return "B";
  if (p == &g_gpioc) return "C";
  if (p == &g_gpiod) return "D";
  if (p == &g_gpioe) return "E";
  return "?";
}

void pemf_host_bsrr(GPIO_TypeDef *port, uint32_t deger) {
  if (g_gunluk) printf("B %llu %s %08x %u\n", g_tick, port_adi(port), (unsigned)deger, g_nop);
  g_nop = 0;
}
void pemf_host_nop(void) { g_nop++; }

/* `hata` kipi: Error_Handler `__disable_irq()`'a varınca buradan dönülür (sonsuz döngüye girilmez). */
static jmp_buf g_hata_jmp;
static int g_hata_bekle = 0;
void pemf_host_disable_irq(void) {
  if (g_hata_bekle) {
    g_hata_bekle = 0;
    longjmp(g_hata_jmp, 1);
  }
}

/* ---- HAL taklidi (davranış: stub/main.h başlığı) ---- */
HAL_StatusTypeDef HAL_Init(void) { return HAL_OK; }
uint32_t HAL_GetTick(void) { return (uint32_t)(g_tick / 50ULL); } /* 50 kHz tick → ms */
HAL_StatusTypeDef HAL_UART_Init(UART_HandleTypeDef *h) { h->gState = HAL_UART_STATE_READY; h->RxState = HAL_UART_STATE_READY; return HAL_OK; }
HAL_StatusTypeDef HAL_UART_Transmit(UART_HandleTypeDef *h, const uint8_t *p, uint16_t n, uint32_t t) { (void)h; (void)p; (void)n; (void)t; return HAL_OK; }
HAL_StatusTypeDef HAL_UART_Transmit_IT(UART_HandleTypeDef *h, const uint8_t *p, uint16_t n) { (void)h; (void)p; (void)n; return HAL_OK; }
HAL_StatusTypeDef HAL_UART_Receive_IT(UART_HandleTypeDef *h, uint8_t *p, uint16_t n) { (void)h; (void)p; (void)n; return HAL_OK; }
HAL_StatusTypeDef HAL_UART_AbortReceive(UART_HandleTypeDef *h) { (void)h; return HAL_OK; }
void HAL_NVIC_SetPriority(int irq, uint32_t a, uint32_t b) { (void)irq; (void)a; (void)b; }
void HAL_NVIC_EnableIRQ(int irq) { (void)irq; }
HAL_StatusTypeDef HAL_TIM_Base_Init(TIM_HandleTypeDef *h) { (void)h; return HAL_OK; }
HAL_StatusTypeDef HAL_TIM_Base_Start_IT(TIM_HandleTypeDef *h) { (void)h; return HAL_OK; }
void HAL_TIM_IRQHandler(TIM_HandleTypeDef *h) { (void)h; }
void HAL_GPIO_Init(GPIO_TypeDef *p, GPIO_InitTypeDef *i) { (void)p; (void)i; }
void HAL_GPIO_WritePin(GPIO_TypeDef *p, uint16_t pin, GPIO_PinState s) { (void)p; (void)pin; (void)s; }
void HAL_GPIO_TogglePin(GPIO_TypeDef *p, uint16_t pin) { (void)p; (void)pin; }
HAL_StatusTypeDef HAL_RCC_OscConfig(RCC_OscInitTypeDef *o) { (void)o; return HAL_OK; }
HAL_StatusTypeDef HAL_RCC_ClockConfig(RCC_ClkInitTypeDef *c, uint32_t l) { (void)c; (void)l; return HAL_OK; }

/* ---- sensör/akım modülleri: ISR'a ilgisiz, boş gövde (prototipler Core/Inc başlıklarından) ---- */
#include "pemf_akim.h"
#include "pemf_sensor.h"
void PEMF_Akim_Init(void) {}
bool PEMF_Akim_Poll(void) { return false; }
void PEMF_Akim_Oku(uint32_t sira, PEMF_AkimVerisi_t *hedef) { (void)sira; memset(hedef, 0, sizeof(*hedef)); }
uint32_t PEMF_Sensor_BobinId(uint32_t sira) { return sira + 6U; }
void PEMF_Sensor_Init(void) {}
bool PEMF_Sensor_Poll(uint32_t simdi_ms) { (void)simdi_ms; return false; }
void PEMF_Sensor_Oku(uint32_t sira, PEMF_SensorVerisi_t *hedef) { (void)sira; memset(hedef, 0, sizeof(*hedef)); }
void PEMF_Sensor_Rapor(uint32_t sira, uint8_t *sicaklik_adres, uint8_t *alan_adres) { (void)sira; (void)sicaklik_adres; (void)alan_adres; }
int _printf_float(void) { return 0; }

#define main fw_main
#include KAYNAK
#undef main

static void parametre(unsigned maske, float f, float d, float p) {
  for (uint32_t i = 0U; i < NUM_COILS; i++) {
    int sec = (int)((maske >> i) & 1U);
    g_shadow.coil[i].freq = sec ? f : 100.0f;
    g_shadow.coil[i].duty = sec ? d : 0.0f;
    g_shadow.coil[i].phase = sec ? p : 0.0f;
    g_shadow.coil[i].dur_min = sec ? 60U : 0U;
  }
  g_shadow.ref_ms_valid = 0U;
  g_shadow.pending = 1U;
}

static void durum_bas(void) {
  for (uint32_t i = 0U; i < NUM_COILS; i++)
    printf("S %llu %u %u %d %d\n", g_tick, (unsigned)i, (unsigned)g_tpp[i], (int)g_duty_ticks[i], (int)g_target_duty_ticks[i]);
}

int main(int argc, char **argv) {
  if (argc < 2) return 2;
  Coil_StateInit();
  if (strcmp(argv[1], "harita") == 0) {
    for (uint32_t i = 0U; i < NUM_COILS; i++) {
      printf("H %u %s %u %s %u\n", (unsigned)i, port_adi(coil_gpio[i].portA), (unsigned)coil_gpio[i].pinA,
             port_adi(coil_gpio[i].portB), (unsigned)coil_gpio[i].pinB);
      printf("K %u %u\n", (unsigned)i, (unsigned)g_unipolar[i]);
    }
    return 0;
  }
  if (strcmp(argv[1], "ofset") == 0) {
    printf("O header %u\n", (unsigned)offsetof(BinaryCmdPacket_t, header));
    printf("O duty %u\n", (unsigned)offsetof(BinaryCmdPacket_t, duty));
    printf("O phase %u\n", (unsigned)offsetof(BinaryCmdPacket_t, phase));
    printf("O freq %u\n", (unsigned)offsetof(BinaryCmdPacket_t, freq));
    printf("O duration %u\n", (unsigned)offsetof(BinaryCmdPacket_t, duration));
    printf("O ref_ms %u\n", (unsigned)offsetof(BinaryCmdPacket_t, ref_ms));
    printf("O unipolar_maskesi %u\n", (unsigned)offsetof(BinaryCmdPacket_t, unipolar_maskesi));
    printf("O crc32 %u\n", (unsigned)offsetof(BinaryCmdPacket_t, crc32));
    printf("Z %u\n", (unsigned)sizeof(BinaryCmdPacket_t));
    printf("R %u\n", (unsigned)UART_RX_BUF_SZ);
    printf("N %u\n", (unsigned)NUM_COILS);
    return 0;
  }
#ifdef PEMF_HOST_ETKIN_SONDASI
  /* Y69: makroyu YALNIZ tests/test_firmware_ETKIN_duty_ACK_Y69.py main.c metninin SONUNA ekler (rapor işlevi olmayan
   * eski firmware ile ve diğer kapılarda takım bu dal olmadan derlenir). */
  if (strcmp(argv[1], "etkin") == 0 && argc >= 5 && ((argc - 2) % 3) == 0) {
    for (int a = 2; a + 2 < argc; a += 3) {
      const uint8_t u = (uint8_t)atoi(argv[a + 2]);
      printf("E %s %s %u %ld\n", argv[a], argv[a + 1], (unsigned)u,
             Coil_EtkinDutyBinde((float)atof(argv[a + 1]), (float)atof(argv[a]), u));
    }
    return 0;
  }
#endif
  if (strcmp(argv[1], "isr") == 0 && (argc == 7 || argc == 11 || argc == 12)) {
    unsigned long long n = strtoull(argv[2], NULL, 10);
    unsigned maske = (unsigned)strtoul(argv[3], NULL, 0);
    unsigned long long t2 = (argc >= 11) ? strtoull(argv[7], NULL, 10) : 0ULL;
    htim1.Instance = TIM1;
    g_pwm_started = 1U;
    parametre(maske, (float)atof(argv[4]), (float)atof(argv[5]), (float)atof(argv[6]));
    /* 1-G inceleme G-5.1: ISR_GUNLUK_BAS=<tick> verilirse "B" satırları o tick'ten itibaren basılır (ISR baştan AYNEN
     * koşar; yalnız günlük kısalır). Verilmezse davranış değişmez. Kullanan, önceki seviyeler bilinmediği için
     * analizi en az bir tam periyot sonra başlatır (her sürülen bacak bir periyotta bir kez düşer → seviye eşitlenir). */
    const char *gunluk_bas_s = getenv("ISR_GUNLUK_BAS");
    const unsigned long long gunluk_bas = gunluk_bas_s ? strtoull(gunluk_bas_s, NULL, 10) : 0ULL;
    g_gunluk = (gunluk_bas == 0ULL);
    /* 1-G inceleme G-5.2: ÇALIŞIRKEN KİP DEĞİŞİMİ. Ürün `Coil_KipUygula(pkt.unipolar_maskesi)`'yı ANA DÖNGÜDEN, gölgesiz
     * çağırır (backend bobin çalışırken kipi HEMEN gönderir — `surus_kipi_ayarla`) → ISR yeni `g_unipolar`'ı bir sonraki
     * tick'te görür. ISR_KIP_BAS=<maske>: döngüden önce · ISR_KIP_TICK=<tick> + ISR_KIP_MASKE=<maske>: o tick'te ISR'dan
     * ÖNCE (t2'yle aynı tick'se parametre setinden de önce — paket işleme sırası). Verilmezse davranış değişmez. */
    const char *kip_bas_s = getenv("ISR_KIP_BAS");
    const char *kip_tick_s = getenv("ISR_KIP_TICK");
    const char *kip_maske_s = getenv("ISR_KIP_MASKE");
    const unsigned long long kip_tick = (kip_tick_s && kip_maske_s) ? strtoull(kip_tick_s, NULL, 10) : 0ULL;
    if (kip_bas_s) Coil_KipUygula((uint8_t)strtoul(kip_bas_s, NULL, 0));
    for (g_tick = 0ULL; g_tick < n; g_tick++) {
      if (!g_gunluk && g_tick >= gunluk_bas) g_gunluk = 1;
      if (kip_tick && g_tick == kip_tick) Coil_KipUygula((uint8_t)strtoul(kip_maske_s, NULL, 0));
      if (t2 && g_tick == t2) {
        durum_bas();
        parametre(maske, (float)atof(argv[8]), (float)atof(argv[9]), (float)atof(argv[10]));
        if (argc == 12) {
          /* 1-G İG-8.28: ikinci parametre seti HW_SYNC `ref_ms` hizalamasını da taşır (paket ayrıştırıcının yaptığı gibi
           * gölgeye) → ISR `g_dds_tick`i periyot ORTASINDA yeniden konumlandırır (ikinci süreksizlik kaynağı). */
          g_shadow.ref_ms = (uint32_t)strtoul(argv[11], NULL, 10);
          g_shadow.ref_ms_valid = 1U;
        }
      }
      HAL_TIM_PeriodElapsedCallback(&htim1);
      if (g_tick == 0ULL || (t2 && g_tick == t2)) durum_bas();
    }
    return 0;
  }
  /* zorla|hata N bobin_maske f d p → N tick sürülür (günlüklü), sonra "BASLA" ve
   * zorla: PEMF_ForceAllCoilOutputsLow() · hata: Error_Handler() (`__disable_irq` kancasından dönülür);
   * ardından "P <i> <g_prev_state>" ve hata kipinde "IRQ" (kesmeler kapatılmaya varıldı). */
  if ((strcmp(argv[1], "zorla") == 0 || strcmp(argv[1], "hata") == 0) && argc == 7) {
    unsigned long long n = strtoull(argv[2], NULL, 10);
    unsigned maske = (unsigned)strtoul(argv[3], NULL, 0);
    htim1.Instance = TIM1;
    g_pwm_started = 1U;
    parametre(maske, (float)atof(argv[4]), (float)atof(argv[5]), (float)atof(argv[6]));
    g_gunluk = 1; /* sürüş de günlüklü: çağrı anında bobinlerin GERÇEKTEN sürüldüğü görülsün */
    for (g_tick = 0ULL; g_tick < n; g_tick++) HAL_TIM_PeriodElapsedCallback(&htim1);
    printf("BASLA\n");
    if (strcmp(argv[1], "zorla") == 0) {
      PEMF_ForceAllCoilOutputsLow();
    } else {
      g_hata_bekle = 1;
      if (setjmp(g_hata_jmp) == 0) {
        Error_Handler();
        printf("DONDU\n"); /* Error_Handler kesmeleri kapatmadan döndü */
      } else {
        printf("IRQ\n");
      }
    }
    for (uint32_t i = 0U; i < NUM_COILS; i++) printf("P %u %u\n", (unsigned)i, (unsigned)g_prev_state[i]);
    return 0;
  }
  return 2;
}
