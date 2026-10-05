/* tests/firmware_host/dongu/dongu_kosum.c — STM ANA DÖNGÜ KOŞUM TAKIMI (Dalga 1 · 1-G · D1.106). Yalnız Windows x64.
 *
 * GERÇEK firmware (`main.c`, `pemf_sensor.c`, `pemf_akim.c`, `stm32f4xx_it.c`, `stm32f4xx_hal_msp.c`,
 * `system_stm32f4xx.c`) ve GERÇEK vendored HAL 1.8.5 MSVC'de derlenir; çevre birimi yazmaçları GERÇEK adreslerinde
 * (0x40000000…, 0xE0000000…) ayrılan bellektedir. Model gereken sayfalar (USART2-4, I2C1-3, ADC, CRC/RCC/FLASH,
 * SCS, DWT) PAGE_NOACCESS: her erişim VEH'e düşer → model değeri hazırlar → sayfa açılır + tek adım (TF) → komut
 * koşar → tek adım istisnasında yazılan değer modele verilir → sayfa yeniden kilitlenir. GPIO/TIM/PWR gibi
 * davranışı gerekmeyen sayfalar düz bellektir. Kaynak metni DEĞİŞMEZ; aparatın iki biçim dönüşümü:
 * `__asm volatile("nop");` → `pemf_host_nop();` ve HAL `__weak` tanımları → `/alternatename`.
 *
 * SANAL ZAMAN (ns): model erişimi ERISIM_NS (50), HAL_GetTick GETTICK_NS (1000: ana döngü turunun CPU payı — firmware
 * turda iki kez çağırır; ISR'da 0), NOP 6 (1 çevrim @168 MHz) ilerletir; AYNI yazmacın
 * DEĞİŞMEYEN değerle üst üste okunması (bayrak bekleme döngüsü) o yazmacın bir sonraki DEĞİŞİM anına atlar (kesme
 * olayları arada sırayla teslim edilir). Kesmeler — SysTick (LOAD/HCLK), TIM1 güncellemesi (PSC/ARR, TIM1 saati),
 * USART3 (TXE/TC/RXNE/ORE, CR1/CR3 + NVIC) — her erişimden sonra, HAL_GetTick'te ve `__enable_irq`'da, PRIMASK
 * kapalı ve ISR dışındayken ZAMAN SIRASIYLA teslim edilir (iç içe kesme yok). USART3 bayt süresi BRR'DEN:
 * 10 bit × BRR / PCLK1 (PCLK1 = SystemCoreClock >> APBPrescTable[PPRE1]); 115200 / 42 MHz → BRR 0x16D → 86,9 µs.
 * ADC: (SMP çevrimi + 12) / ADCCLK (PCLK2 / ADCPRE). I2C: CCR'den SCL (100 kHz → bayt+ACK 90 µs).
 *
 * ⚠️ MODEL SINIRI (uydurma ölçüm YOK): CPU'nun kendi komut süresi yok sayılır (snprintf/CRC "anlık"); I2C çevre
 * biriminin ACK/POS inceliği sürücünün beklediği bayrak sırasına indirgenmiştir; sensör değerleri senaryodan sabittir.
 * Gerçek UART zamanlaması, gerçek ACS712/I2C hattı ve MAGCHK TEZGÂHTA ölçülür (Oturum 13).
 *
 * Kullanım: dongu_kosum.exe <senaryo.txt>  → stdout: "L <başlangıç_us> <bitiş_us> <satır>" (UART'tan ÇIKAN her satır),
 * sonda "SON …". Senaryo: SURE_US n · ERISIM_NS n · ACS <adc_kanalı> <mV> · I2C <hat> <MLX90614|MLX90393> <adres hex>
 * · SICAKLIK <hat> <ortam_C> <nesne_C> · ALAN <hat> <x> <y> <z> (ham LSB) · PAKET <t_us> <hex>. */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "main.h"
#include "stm32f4xx_it.h"

/* ⚠️ Bu çeviri birimi windows.h İÇERMEZ: STM32 başlıklarının kısa makroları (CRC, RCC, ADC, ERROR…) Windows
 * başlıklarıyla çakışır. VEH, bellek ayırma/koruma, iş parçacığı ve bekçi `dongu_win.c`'dedir (yalnız düz C türleri). */
void dw_bitir(int kod);                            /* stdout boşaltılır, süreç `kod` ile sonlanır */
int dw_bellek_kur(void);                           /* 0x40000000 + 0xE0000000 bölgeleri ve VEH; 0 = başarısız */
void dw_sayfa_kilitle(uintptr_t taban, int kilit); /* 1 = PAGE_NOACCESS · 0 = PAGE_READWRITE */

extern int pemf_fw_main(void);
extern void TIM1_UP_TIM10_IRQHandler(void);
extern uint32_t pemf_host_aktif_maske(void); /* aparatın main.c sonuna eklediği salt-okur sonda */

/* main.c newlib-nano'nun float printf'ini `&_printf_float` ile bağlatır (ARM'de -u yerine); MSVC CRT'de float zaten
 * var → sembol yalnız bağlayıcıyı doyurur (ISR koşum takımıyla aynı). */
int _printf_float(void) { return 0; }

/* ── sanal zaman ve genel durum ─────────────────────────────────────────────────────────────────────── */
static volatile uint64_t g_vt;       /* ns */
static uint64_t g_bitis = 30000000000ULL;
static uint64_t g_erisim_ns = 50U;
static uint64_t g_gettick_ns = 1000U; /* ana döngü turunun CPU payı (HAL_GetTick başına; ISR'da 0) */
static int g_isr, g_primask;
static uint64_t g_erisim, g_isr_sayisi, g_tx_bayt, g_rx_ore, g_rx_kayip, g_tdr_ezildi;

static void senaryo_bitir(int kod);
static void zamani_ilerlet(uint64_t hedef);
static void kesmeleri_teslim_et(void);

static __declspec(noreturn) void olumcul(const char *neden) {
  printf("!!! OLUMCUL vt_us=%llu %s\n", (unsigned long long)(g_vt / 1000U), neden);
  dw_bitir(7);
  for (;;) {
  }
}

/* ── sayfalar ───────────────────────────────────────────────────────────────────────────────────────── */
#define SAYFA 0x1000U
enum { M_USART = 1, M_I2C, M_ADC, M_RCC, M_SCS, M_DWT, M_BB };
typedef struct {
  uintptr_t taban;
  int tur;
  uint32_t golge[SAYFA / 4U];
} Sayfa;
static Sayfa g_sayfa[] = {
    {0x40004000U, M_USART, {0}}, {0x40005000U, M_I2C, {0}}, {0x40012000U, M_ADC, {0}},
    {0x40023000U, M_RCC, {0}},   {0xE000E000U, M_SCS, {0}}, {0xE0001000U, M_DWT, {0}},
    /* bit-band takma adları (HAL F4: `__HAL_RCC_PLL_ENABLE()` = *RCC_CR_PLLON_BB = 1 …) → hedef yazmacın biti */
    {0x42470000U, M_BB, {0}},    {0x42471000U, M_BB, {0}},
};
#define SAYFA_N (sizeof(g_sayfa) / sizeof(g_sayfa[0]))
static Sayfa *const S_USART = &g_sayfa[0];
static Sayfa *const S_I2C = &g_sayfa[1];
static Sayfa *const S_ADC = &g_sayfa[2];
static Sayfa *const S_RCC = &g_sayfa[3];
static Sayfa *const S_SCS = &g_sayfa[4];
static Sayfa *const S_DWT = &g_sayfa[5];
#define G(s, ofs) ((s)->golge[(ofs) / 4U])
static uint64_t g_sayac[SAYFA_N][SAYFA / 4U]; /* tanı: yazmaç başına erişim sayısı */

static Sayfa *sayfa_bul(uintptr_t adr) {
  for (size_t i = 0; i < SAYFA_N; i++) {
    if (adr >= g_sayfa[i].taban && adr < g_sayfa[i].taban + SAYFA) {
      return &g_sayfa[i];
    }
  }
  return NULL;
}

/* ── saatler (RCC gölgesinden; HAL'in kendi hesabıyla aynı tablolar) ─────────────────────────────────── */
static uint32_t pclk1(void) { return SystemCoreClock >> APBPrescTable[(G(S_RCC, 0x808U) >> 10) & 7U]; }
static uint32_t pclk2(void) { return SystemCoreClock >> APBPrescTable[(G(S_RCC, 0x808U) >> 13) & 7U]; }
static int nvic_etkin(int irq) { return (G(S_SCS, 0x100U + 4U * (uint32_t)(irq / 32)) >> (irq % 32)) & 1U; }

/* ── USART3 (sayfa ofseti 0x800) ────────────────────────────────────────────────────────────────────── */
#define U_SR 0x800U
#define U_DR 0x804U
#define U_BRR 0x808U
#define U_CR1 0x80CU
#define U_CR3 0x814U
#define SR_PE 0x001U
#define SR_FE 0x002U
#define SR_NE 0x004U
#define SR_ORE 0x008U
#define SR_IDLE 0x010U
#define SR_RXNE 0x020U
#define SR_TC 0x040U
#define SR_TXE 0x080U
typedef struct {
  uint64_t t;
  uint8_t b;
} RxBayt;
static RxBayt *g_rx;
static size_t g_rx_n, g_rx_kap;
static struct {
  uint32_t sr;
  uint8_t rdr, tdr, kayan;
  int tdr_dolu, kaydirma, sr_okundu;
  uint64_t bitis;
  size_t rx_i;
} U = {SR_TC};
static char g_satir[8192];
static size_t g_satir_n;
static uint64_t g_satir_bas;

static uint64_t u_bayt_ns(void) {
  const uint32_t brr = G(S_USART, U_BRR);
  const uint32_t pc = pclk1();
  if ((brr == 0U) || (pc == 0U)) {
    return 86806U;
  }
  return (uint64_t)10U * (uint64_t)brr * 1000000000ULL / (uint64_t)pc; /* 10 bit (8N1) × BRR / PCLK1 */
}

static void u_bayt_cikti(uint8_t b, uint64_t t) {
  g_tx_bayt++;
  if (g_satir_n == 0U) {
    g_satir_bas = t - u_bayt_ns();
  }
  if (b == '\n') {
    size_t n = g_satir_n;
    while ((n > 0U) && (g_satir[n - 1U] == '\r')) {
      n--;
    }
    printf("L %llu %llu %.*s\n", (unsigned long long)(g_satir_bas / 1000U), (unsigned long long)(t / 1000U), (int)n,
           g_satir);
    g_satir_n = 0U;
  } else if (b == '\r') {
    if (g_satir_n < sizeof(g_satir) - 1U) {
      g_satir[g_satir_n++] = '\r'; /* satır sonunda kırpılır */
    }
  } else if (g_satir_n < sizeof(g_satir) - 1U) {
    g_satir[g_satir_n++] = (char)(((b >= 32U) && (b < 127U)) ? b : '?');
  }
}

static void u_guncelle(void) {
  while (U.kaydirma && (U.bitis <= g_vt)) {
    u_bayt_cikti(U.kayan, U.bitis);
    if (U.tdr_dolu) {
      U.kayan = U.tdr;
      U.tdr_dolu = 0;
      U.bitis += u_bayt_ns();
    } else {
      U.kaydirma = 0;
      U.sr |= SR_TC;
    }
  }
  while ((U.rx_i < g_rx_n) && (g_rx[U.rx_i].t <= g_vt)) {
    const uint32_t cr1 = G(S_USART, U_CR1);
    if ((cr1 & USART_CR1_UE) && (cr1 & USART_CR1_RE)) {
      if (U.sr & SR_RXNE) {
        U.sr |= SR_ORE; /* önceki bayt okunmadı → bu bayt KAYBOLUR (gerçek donanım) */
        g_rx_ore++;
      } else {
        U.rdr = g_rx[U.rx_i].b;
        U.sr |= SR_RXNE;
      }
    } else {
      g_rx_kayip++;
    }
    U.rx_i++;
  }
}

static uint32_t u_sr(void) {
  u_guncelle();
  return (U.sr & ~SR_TXE) | (U.tdr_dolu ? 0U : SR_TXE);
}

static uint64_t u_sonraki(void) {
  uint64_t t = UINT64_MAX;
  if (U.kaydirma) {
    t = U.bitis;
  }
  if ((U.rx_i < g_rx_n) && (g_rx[U.rx_i].t < t)) {
    t = g_rx[U.rx_i].t;
  }
  return t;
}

static int u_kesme(void) {
  const uint32_t sr = u_sr(), cr1 = G(S_USART, U_CR1), cr3 = G(S_USART, U_CR3);
  if (!nvic_etkin(USART3_IRQn)) {
    return 0;
  }
  return ((cr1 & USART_CR1_TXEIE) && (sr & SR_TXE)) || ((cr1 & USART_CR1_TCIE) && (sr & SR_TC)) ||
         ((cr1 & USART_CR1_RXNEIE) && (sr & (SR_RXNE | SR_ORE))) || ((cr1 & USART_CR1_PEIE) && (sr & SR_PE)) ||
         ((cr3 & USART_CR3_EIE) && (sr & (SR_FE | SR_NE | SR_ORE)));
}

static uint32_t usart_oku(uint32_t ofs) {
  if (ofs == U_SR) {
    return u_sr();
  }
  if (ofs == U_DR) {
    u_guncelle();
    return U.rdr;
  }
  return G(S_USART, ofs);
}

static void usart_okundu(uint32_t ofs) {
  if (ofs == U_SR) {
    U.sr_okundu = 1;
  } else if (ofs == U_DR) {
    U.sr &= ~SR_RXNE;
    if (U.sr_okundu) {
      U.sr &= ~(SR_PE | SR_FE | SR_NE | SR_ORE | SR_IDLE); /* SR okuması + DR okuması dizisi */
    }
    U.sr_okundu = 0;
  }
}

static void usart_yaz(uint32_t ofs, uint32_t v) {
  if (ofs == U_SR) {
    U.sr &= (v | ~0x0360U); /* rc_w0: CTS, LBD, TC, RXNE */
    return;
  }
  if (ofs == U_DR) {
    u_guncelle();
    if (U.sr_okundu) {
      U.sr &= ~SR_TC; /* SR okuması + DR yazması dizisi TC'yi temizler */
    }
    U.sr_okundu = 0;
    if (!(G(S_USART, U_CR1) & USART_CR1_TE)) {
      return;
    }
    if (!U.kaydirma) {
      U.kayan = (uint8_t)v;
      U.kaydirma = 1;
      U.bitis = g_vt + u_bayt_ns();
    } else if (!U.tdr_dolu) {
      U.tdr = (uint8_t)v;
      U.tdr_dolu = 1;
    } else {
      U.tdr = (uint8_t)v; /* TXE beklenmeden yazıldı: önceki bayt ezildi */
      g_tdr_ezildi++;
    }
    return;
  }
  G(S_USART, ofs) = v;
}

/* ── ADC1 (sayfa ofseti 0x000) + ortak (0x300) ─────────────────────────────────────────────────────── */
#define A_SR 0x000U
#define A_CR2 0x008U
#define A_SMPR1 0x00CU
#define A_SMPR2 0x010U
#define A_SQR3 0x034U
#define A_DR 0x04CU
#define A_CCR 0x304U
static int g_acs_mv[19];
static uint32_t g_gurultu = 12345U;
static struct {
  uint32_t sr, dr, kanal;
  int donusum;
  uint64_t bitis;
} A;

static void a_guncelle(void) {
  if (A.donusum && (A.bitis <= g_vt)) {
    A.donusum = 0;
    int ham = 0;
    const int mv = g_acs_mv[A.kanal];
    if (mv > 0) {
      g_gurultu = g_gurultu * 1103515245U + 12345U;
      ham = (int)((int64_t)mv * 4095 / 3300) + (int)((g_gurultu >> 16) % 5U) - 2;
      ham = (ham < 0) ? 0 : ((ham > 4095) ? 4095 : ham);
    }
    A.dr = (uint32_t)ham;
    A.sr |= ADC_SR_EOC;
  }
}

static uint32_t adc_oku(uint32_t ofs) {
  if (ofs == A_SR) {
    a_guncelle();
    return A.sr;
  }
  if (ofs == A_DR) {
    a_guncelle();
    return A.dr;
  }
  return G(S_ADC, ofs);
}

static void adc_okundu(uint32_t ofs) {
  if (ofs == A_DR) {
    A.sr &= ~ADC_SR_EOC;
  }
}

static void adc_yaz(uint32_t ofs, uint32_t v) {
  if (ofs == A_SR) {
    A.sr &= (v | ~0x3FU);
    return;
  }
  if (ofs == A_DR) {
    return;
  }
  if (ofs == A_CR2) {
    G(S_ADC, ofs) = v & ~ADC_CR2_SWSTART; /* SWSTART dönüşüm başlayınca donanımca iner */
    if ((v & ADC_CR2_SWSTART) && (v & ADC_CR2_ADON)) {
      static const uint32_t smp_cevrim[8] = {3U, 15U, 28U, 56U, 84U, 112U, 144U, 480U};
      const uint32_t ch = G(S_ADC, A_SQR3) & 0x1FU;
      const uint32_t smp = (ch < 10U) ? ((G(S_ADC, A_SMPR2) >> (3U * ch)) & 7U)
                                      : ((G(S_ADC, A_SMPR1) >> (3U * (ch - 10U))) & 7U);
      const uint32_t bolen = 2U * (((G(S_ADC, A_CCR) >> 16) & 3U) + 1U);
      const uint64_t adcclk = (uint64_t)pclk2() / bolen;
      A.kanal = (ch < 19U) ? ch : 0U;
      A.donusum = 1;
      A.bitis = g_vt + ((uint64_t)(smp_cevrim[smp] + 12U) * 1000000000ULL) / (adcclk ? adcclk : 1U);
      A.sr |= ADC_SR_STRT;
    }
    return;
  }
  G(S_ADC, ofs) = v;
}

/* ── I2C1 (0x400) / I2C2 (0x800) + cihazlar ─────────────────────────────────────────────────────────── */
enum { H_BOS, H_START, H_SB, H_ADRES, H_ADDR, H_AF, H_TX, H_RX, H_STOP };
typedef struct {
  uint8_t adres;
  int tur; /* 1 = MLX90614, 2 = MLX90393 */
  uint8_t komut[8], yanit[8];
  int komut_n, yanit_n, yanit_i, yazma_aktif;
  uint16_t kayit[16];
  float ortam_c, nesne_c;
  int16_t x, y, z;
} Cihaz;
typedef struct {
  uint32_t ofs;
  uint32_t sr1, sr2;
  uint8_t dr, adres_bayt, tx_kayan, tdr, rx_kayan;
  int d, okuma, sr1_okundu, tx_kaydirma, tdr_dolu, rx_tutulan, rx_ack, stop_istek, start_istek;
  uint64_t t;
  Cihaz *aktif;
  Cihaz cihaz[4];
  int n;
} Hat;
static Hat g_hat[2] = {{0x400U}, {0x800U}};
#define I_CR1 0x00U
#define I_DR 0x10U
#define I_SR1 0x14U
#define I_SR2 0x18U
#define I_CCR 0x1CU

static Hat *hat_bul(uint32_t ofs) {
  if ((ofs >= 0x400U) && (ofs < 0x428U)) {
    return &g_hat[0];
  }
  if ((ofs >= 0x800U) && (ofs < 0x828U)) {
    return &g_hat[1];
  }
  return NULL;
}
static uint64_t h_yarim(Hat *h) { /* SCL yarım periyodu: standart kip T_high = CCR × T_PCLK1 */
  const uint32_t ccr = G(S_I2C, h->ofs + I_CCR) & 0xFFFU;
  const uint32_t pc = pclk1();
  return (ccr && pc) ? ((uint64_t)ccr * 1000000000ULL / pc) : 5000U;
}
static uint64_t h_bayt(Hat *h) { return 18U * h_yarim(h); } /* 8 veri + ACK = 9 SCL periyodu */

static void cihaz_isle(Cihaz *c) {
  if (c->tur == 1) { /* MLX90614 SMBus "read word": [komut] → LSB, MSB, PEC */
    const float t = (c->komut[0] == 0x06U) ? c->ortam_c : c->nesne_c;
    const uint16_t ham = (uint16_t)((t + 273.15f) / 0.02f + 0.5f);
    c->yanit[0] = (uint8_t)(ham & 0xFFU);
    c->yanit[1] = (uint8_t)(ham >> 8);
    c->yanit[2] = 0U;
    c->yanit_n = 3;
    return;
  }
  const uint8_t k = c->komut[0]; /* MLX90393: her komuttan sonra durum baytı (+ veri) okunur */
  memset(c->yanit, 0, sizeof(c->yanit));
  if (k == 0x50U) { /* RR: [0x50][kayıt<<2] → durum, MSB, LSB */
    const uint16_t v = c->kayit[(c->komut[1] >> 2) & 15U];
    c->yanit[1] = (uint8_t)(v >> 8);
    c->yanit[2] = (uint8_t)(v & 0xFFU);
    c->yanit_n = 3;
  } else if (k == 0x60U) { /* WR: [0x60][MSB][LSB][kayıt<<2] → durum */
    c->kayit[(c->komut[3] >> 2) & 15U] = (uint16_t)((c->komut[1] << 8) | c->komut[2]);
    c->yanit_n = 1;
  } else if ((k & 0xF0U) == 0x40U) { /* RM xyz → durum + X, Y, Z (büyük uçlu int16) */
    const int16_t e[3] = {c->x, c->y, c->z};
    for (int i = 0; i < 3; i++) {
      c->yanit[1 + 2 * i] = (uint8_t)((uint16_t)e[i] >> 8);
      c->yanit[2 + 2 * i] = (uint8_t)((uint16_t)e[i] & 0xFFU);
    }
    c->yanit_n = 7;
  } else { /* EX / RT / SM → durum */
    c->yanit_n = 1;
  }
}
static void cihaz_baslat(Cihaz *c, int okuma) {
  if (!okuma) {
    c->komut_n = 0;
    c->yazma_aktif = 1;
  } else {
    c->yanit_i = 0;
  }
}
static void cihaz_bitir(Cihaz *c) {
  if (c->yazma_aktif) {
    c->yazma_aktif = 0;
    cihaz_isle(c);
  }
}

static void h_dur_kur(Hat *h, uint64_t t0) {
  h->d = H_STOP;
  h->t = t0 + h_yarim(h);
}

static void h_guncelle(Hat *h) {
  while ((h->t != UINT64_MAX) && (h->t <= g_vt)) {
    const uint64_t t0 = h->t;
    h->t = UINT64_MAX;
    switch (h->d) {
    case H_START:
      if (h->aktif) { /* tekrarlı START önceki işlemi bitirir */
        cihaz_bitir(h->aktif);
        h->aktif = NULL;
      }
      h->sr1 &= ~I2C_SR1_BTF; /* START üretimi BTF'yi indirir (önceki yazmanın BTF'si tekrarlı START'ta kalmaz) */
      h->tx_kaydirma = h->tdr_dolu = h->rx_tutulan = 0;
      h->sr1 |= I2C_SR1_SB;
      h->sr2 |= I2C_SR2_MSL | I2C_SR2_BUSY;
      G(S_I2C, h->ofs + I_CR1) &= ~I2C_CR1_START;
      h->d = H_SB;
      break;
    case H_ADRES: {
      Cihaz *c = NULL;
      for (int i = 0; i < h->n; i++) {
        if (h->cihaz[i].adres == (uint8_t)(h->adres_bayt >> 1)) {
          c = &h->cihaz[i];
        }
      }
      if (c) {
        h->aktif = c;
        h->okuma = h->adres_bayt & 1U;
        cihaz_baslat(c, h->okuma);
        h->sr1 |= I2C_SR1_ADDR;
        if (h->okuma) {
          h->sr2 &= ~I2C_SR2_TRA;
        } else {
          h->sr2 |= I2C_SR2_TRA;
        }
        h->d = H_ADDR;
      } else {
        h->sr1 |= I2C_SR1_AF; /* NACK: o adreste cihaz yok — ADDR HİÇ gelmez */
        h->d = H_AF;
      }
      break;
    }
    case H_TX:
      if (h->aktif && h->aktif->komut_n < 8) {
        h->aktif->komut[h->aktif->komut_n++] = h->tx_kayan;
      }
      if (h->tdr_dolu) {
        h->tx_kayan = h->tdr;
        h->tdr_dolu = 0;
        h->t = t0 + h_bayt(h);
      } else {
        h->tx_kaydirma = 0;
        h->sr1 |= I2C_SR1_BTF;
        if (h->stop_istek) {
          h->stop_istek = 0;
          h_dur_kur(h, t0);
        } else if (h->start_istek) {
          h->start_istek = 0;
          h->d = H_START;
          h->t = t0 + h_yarim(h);
        }
      }
      break;
    case H_RX: {
      const uint8_t b = (h->aktif && h->aktif->yanit_i < h->aktif->yanit_n) ? h->aktif->yanit[h->aktif->yanit_i++] : 0xFFU;
      const int ack = (G(S_I2C, h->ofs + I_CR1) & I2C_CR1_ACK) != 0U;
      if (!(h->sr1 & I2C_SR1_RXNE)) {
        h->dr = b;
        h->sr1 |= I2C_SR1_RXNE;
        if (h->stop_istek) {
          h->stop_istek = 0;
          h_dur_kur(h, t0);
        } else if (ack) {
          h->t = t0 + h_bayt(h);
        }
      } else {
        h->rx_kayan = b; /* DR dolu → bayt kaydırmada bekler (BTF), saat uzatılır */
        h->rx_tutulan = 1;
        h->rx_ack = ack;
        h->sr1 |= I2C_SR1_BTF;
      }
      break;
    }
    case H_STOP:
      h->sr2 &= ~(I2C_SR2_MSL | I2C_SR2_BUSY | I2C_SR2_TRA);
      h->sr1 &= ~(I2C_SR1_BTF | I2C_SR1_SB | I2C_SR1_ADDR);
      G(S_I2C, h->ofs + I_CR1) &= ~(I2C_CR1_STOP | I2C_CR1_START);
      if (h->aktif) {
        cihaz_bitir(h->aktif);
        h->aktif = NULL;
      }
      h->d = H_BOS;
      h->tx_kaydirma = h->tdr_dolu = 0;
      if (h->start_istek) { /* STOP sürerken istenen START: hat boşalınca üretilir */
        h->start_istek = 0;
        h->d = H_START;
        h->t = t0 + h_yarim(h);
      }
      break;
    default:
      break;
    }
  }
}

static uint32_t h_sr1(Hat *h) {
  h_guncelle(h);
  return (h->sr1 & ~I2C_SR1_TXE) | (((h->d == H_TX) && !h->tdr_dolu) ? I2C_SR1_TXE : 0U);
}

static void h_sifirla(Hat *h) {
  h->sr1 = h->sr2 = 0U;
  h->d = H_BOS;
  h->t = UINT64_MAX;
  h->aktif = NULL;
  h->sr1_okundu = h->tx_kaydirma = h->tdr_dolu = h->rx_tutulan = h->stop_istek = h->start_istek = 0;
}

static uint32_t i2c_oku(uint32_t ofs) {
  Hat *h = hat_bul(ofs);
  if (!h) {
    return G(S_I2C, ofs);
  }
  const uint32_t r = ofs - h->ofs;
  if (r == I_SR1) {
    return h_sr1(h);
  }
  if (r == I_SR2) {
    h_guncelle(h);
    return h->sr2;
  }
  if (r == I_DR) {
    h_guncelle(h);
    return h->dr;
  }
  h_guncelle(h); /* CR1'in START/STOP bitleri olayla (donanımca) iner: bayat bit oku-değiştir-yaz ile GERİ yazılmasın */
  return G(S_I2C, ofs);
}

static void i2c_okundu(uint32_t ofs) {
  Hat *h = hat_bul(ofs);
  if (!h) {
    return;
  }
  const uint32_t r = ofs - h->ofs;
  if (r == I_SR1) {
    h->sr1_okundu = 1;
  } else if (r == I_SR2) {
    if (h->sr1_okundu && (h->sr1 & I2C_SR1_ADDR)) { /* SR1 + SR2 okuma dizisi ADDR'yi temizler */
      h->sr1 &= ~I2C_SR1_ADDR;
      if (h->okuma) {
        h->d = H_RX;
        h->t = g_vt + h_bayt(h);
      } else {
        h->d = H_TX;
      }
    }
    h->sr1_okundu = 0;
  } else if (r == I_DR) {
    h->sr1 &= ~I2C_SR1_RXNE;
    if (h->rx_tutulan) {
      h->dr = h->rx_kayan;
      h->rx_tutulan = 0;
      h->sr1 |= I2C_SR1_RXNE;
      h->sr1 &= ~I2C_SR1_BTF;
      if (h->stop_istek) {
        h->stop_istek = 0;
        h_dur_kur(h, g_vt);
      } else if (h->rx_ack) {
        h->t = g_vt + h_bayt(h);
      }
    }
    h->sr1_okundu = 0;
  }
}

static void i2c_yaz(uint32_t ofs, uint32_t v, uint32_t onceki) {
  Hat *h = hat_bul(ofs);
  if (!h) {
    G(S_I2C, ofs) = v;
    return;
  }
  const uint32_t r = ofs - h->ofs;
  h_guncelle(h);
  if (r == I_SR1) {
    h->sr1 &= (v | ~0xDF00U); /* rc_w0 hata bayrakları */
    return;
  }
  if (r == I_SR2) {
    return;
  }
  if (r == I_DR) {
    if (h->d == H_SB) {
      h->adres_bayt = (uint8_t)v;
      h->sr1 &= ~I2C_SR1_SB;
      h->d = H_ADRES;
      h->t = g_vt + h_bayt(h);
    } else if (h->d == H_TX) {
      h->sr1 &= ~I2C_SR1_BTF;
      if (!h->tx_kaydirma) {
        h->tx_kayan = (uint8_t)v;
        h->tx_kaydirma = 1;
        h->t = g_vt + h_bayt(h);
      } else {
        h->tdr = (uint8_t)v;
        h->tdr_dolu = 1;
      }
    }
    h->sr1_okundu = 0;
    return;
  }
  G(S_I2C, ofs) = v;
  if (r != I_CR1) {
    return;
  }
  if (v & I2C_CR1_SWRST) { /* SWRST: çevre birimi sıfırlamada — yazmaçlar sıfırlanır (CR1'de yalnız SWRST kalır) */
    h_sifirla(h);
    for (uint32_t o = 0U; o < 0x28U; o += 4U) {
      G(S_I2C, h->ofs + o) = 0U;
    }
    G(S_I2C, ofs) = I2C_CR1_SWRST;
    return;
  }
  if (!(v & I2C_CR1_PE)) {
    return;
  }
  /* START/STOP "yazılımca kurulur, donanımca iner": oku-değiştir-yaz (`CR1 |= ACK`) bekleyen biti YENİDEN yazar →
   * istek yalnız 0→1 KENARINDA (komutun okuduğu değere göre). */
  const uint32_t yeni_bit = v & ~onceki;
  if (yeni_bit & I2C_CR1_START) {
    if (h->d == H_BOS || h->d == H_AF || ((h->d == H_TX) && !h->tx_kaydirma)) {
      if (h->d == H_AF) {
        h->sr2 &= ~(I2C_SR2_MSL | I2C_SR2_BUSY);
      }
      h->d = H_START;
      h->t = g_vt + h_yarim(h);
    } else if ((h->d != H_START) && (h->d != H_SB)) {
      h->start_istek = 1;
    }
  }
  if (yeni_bit & I2C_CR1_STOP) {
    if (h->d == H_TX && h->tx_kaydirma) {
      h->stop_istek = 1;
    } else if (h->d == H_RX) {
      if (!h->rx_tutulan && (h->t == UINT64_MAX)) {
        h_dur_kur(h, g_vt); /* alım durmuştu (NACK) → hemen STOP */
      } else {
        h->stop_istek = 1;
      }
    } else if ((h->d == H_TX) || (h->d == H_AF) || (h->d == H_SB) || (h->d == H_ADDR)) {
      h_dur_kur(h, g_vt);
    } else if (h->d == H_BOS) {
      G(S_I2C, ofs) &= ~I2C_CR1_STOP;
    } else {
      h->stop_istek = 1;
    }
  }
}

static uint64_t i2c_degisim(uint32_t ofs) {
  Hat *h = hat_bul(ofs);
  if (!h) {
    return UINT64_MAX;
  }
  h_guncelle(h);
  return h->t;
}

/* ── RCC/FLASH (0x40023000), SCS (0xE000E000), DWT (0xE0001000) ─────────────────────────────────────── */
static uint32_t rcc_oku(uint32_t ofs) {
  uint32_t v = G(S_RCC, ofs);
  if (ofs == 0x800U) { /* CR: hazır bitleri açma bitlerinden — osilatör/PLL anında kilitlenir */
    v &= ~((1U << 1) | (1U << 17) | (1U << 25) | (1U << 27) | (1U << 29));
    v |= ((v >> 0) & 1U) << 1;
    v |= ((v >> 16) & 1U) << 17;
    v |= ((v >> 24) & 1U) << 25;
    v |= ((v >> 26) & 1U) << 27;
    v |= ((v >> 28) & 1U) << 29;
  } else if (ofs == 0x808U) { /* CFGR: SWS = SW */
    v = (v & ~0xCU) | ((v & 3U) << 2);
  } else if ((ofs == 0x870U) || (ofs == 0x874U)) { /* BDCR LSERDY / CSR LSIRDY */
    v = (v & ~2U) | ((v & 1U) << 1);
  } else if (ofs == 0xC0CU) { /* FLASH SR: meşgul değil */
    v = 0U;
  }
  return v;
}

static uint64_t g_systick_t, g_tim1_t;
static int g_systick_acik, g_tim1_acik;
static uint32_t g_cyc_taban;
static uint64_t g_cyc_t;

static uint64_t systick_periyot(void) {
  const uint64_t load = (G(S_SCS, 0x014U) & 0xFFFFFFU) + 1U;
  return load * 1000000000ULL / (SystemCoreClock ? SystemCoreClock : 16000000U);
}
static int systick_etkin(void) { return (G(S_SCS, 0x010U) & 3U) == 3U; }

static uint32_t scs_oku(uint32_t ofs) {
  if (ofs == 0xD00U) {
    return 0x410FC241U; /* CPUID: Cortex-M4 r0p1 */
  }
  if (ofs == 0xD0CU) {
    return 0xFA050000U | (G(S_SCS, ofs) & 0xFFFFU);
  }
  if ((ofs >= 0x180U) && (ofs < 0x1A0U)) {
    return G(S_SCS, ofs - 0x80U); /* ICER okuması = etkin bitler */
  }
  if ((ofs >= 0x280U) && (ofs < 0x2A0U)) {
    return G(S_SCS, ofs - 0x80U);
  }
  return G(S_SCS, ofs);
}
static void scs_yaz(uint32_t ofs, uint32_t v) {
  if ((ofs >= 0x100U) && (ofs < 0x120U)) {
    G(S_SCS, ofs) |= v; /* ISER: 1 yazılan biti etkinleştirir */
  } else if ((ofs >= 0x180U) && (ofs < 0x1A0U)) {
    G(S_SCS, ofs - 0x80U) &= ~v; /* ICER */
  } else if ((ofs >= 0x200U) && (ofs < 0x220U)) {
    G(S_SCS, ofs) |= v;
  } else if ((ofs >= 0x280U) && (ofs < 0x2A0U)) {
    G(S_SCS, ofs - 0x80U) &= ~v;
  } else if (ofs == 0xD0CU) {
    if ((v >> 16) == 0x05FAU) {
      G(S_SCS, ofs) = v & 0xFFFFU;
    }
  } else if (ofs == 0x018U) {
    G(S_SCS, ofs) = 0U; /* SysTick VAL: her yazım sıfırlar */
  } else {
    const int once = systick_etkin();
    G(S_SCS, ofs) = v;
    if ((ofs == 0x010U) && !once && systick_etkin()) {
      g_systick_t = g_vt + systick_periyot();
      g_systick_acik = 1;
    }
  }
}

static uint32_t dwt_oku(uint32_t ofs) {
  if (ofs == 0x004U) {
    if (G(S_DWT, 0x000U) & 1U) {
      return g_cyc_taban + (uint32_t)((g_vt - g_cyc_t) * (uint64_t)SystemCoreClock / 1000000000ULL);
    }
    return g_cyc_taban;
  }
  return G(S_DWT, ofs);
}
static void dwt_yaz(uint32_t ofs, uint32_t v) {
  if (ofs == 0x004U) {
    g_cyc_taban = v;
    g_cyc_t = g_vt;
    return;
  }
  if ((ofs == 0x000U) && !(G(S_DWT, 0x000U) & 1U) && (v & 1U)) {
    g_cyc_t = g_vt;
  }
  G(S_DWT, ofs) = v;
}

/* ── model dağıtımı ─────────────────────────────────────────────────────────────────────────────────── */
static uint32_t model_oku(Sayfa *s, uint32_t ofs);
static void model_yaz(Sayfa *s, uint32_t ofs, uint32_t v, uint32_t onceki);

/* bit-band: takma ad 0x42000000 + bayt×32 + bit×4 ↔ 0x40000000 + bayt'ın biti */
static int bb_hedef(Sayfa *s, uint32_t ofs, Sayfa **hs, uint32_t *hofs, uint32_t *bit) {
  const uintptr_t takma = s->taban + ofs;
  const uintptr_t bayt = 0x40000000U + (takma - 0x42000000U) / 32U;
  *bit = (uint32_t)(((takma - 0x42000000U) % 32U) / 4U) + 8U * (uint32_t)(bayt & 3U);
  *hs = sayfa_bul(bayt & ~(uintptr_t)3U);
  if (!*hs) {
    return 0;
  }
  *hofs = (uint32_t)((bayt & ~(uintptr_t)3U) - (*hs)->taban);
  return 1;
}
static uint32_t bb_oku(Sayfa *s, uint32_t ofs) {
  Sayfa *hs;
  uint32_t hofs, bit;
  if (!bb_hedef(s, ofs, &hs, &hofs, &bit)) {
    olumcul("bit-band hedefi modellenmemis bir sayfada");
  }
  return (model_oku(hs, hofs) >> bit) & 1U;
}
static void bb_yaz(Sayfa *s, uint32_t ofs, uint32_t v) {
  Sayfa *hs;
  uint32_t hofs, bit;
  if (!bb_hedef(s, ofs, &hs, &hofs, &bit)) {
    olumcul("bit-band hedefi modellenmemis bir sayfada");
  }
  const uint32_t simdi = model_oku(hs, hofs);
  model_yaz(hs, hofs, (v & 1U) ? (simdi | (1U << bit)) : (simdi & ~(1U << bit)), simdi);
}

static uint32_t model_oku(Sayfa *s, uint32_t ofs) {
  switch (s->tur) {
  case M_BB:
    return bb_oku(s, ofs);
  case M_USART:
    return usart_oku(ofs);
  case M_I2C:
    return i2c_oku(ofs);
  case M_ADC:
    return adc_oku(ofs);
  case M_RCC:
    return rcc_oku(ofs);
  case M_SCS:
    return scs_oku(ofs);
  case M_DWT:
    return dwt_oku(ofs);
  default:
    return G(s, ofs);
  }
}
static void model_okundu(Sayfa *s, uint32_t ofs) {
  if (s->tur == M_USART) {
    usart_okundu(ofs);
  } else if (s->tur == M_I2C) {
    i2c_okundu(ofs);
  } else if (s->tur == M_ADC) {
    adc_okundu(ofs);
  }
}
static void model_yaz(Sayfa *s, uint32_t ofs, uint32_t v, uint32_t onceki) {
  switch (s->tur) {
  case M_BB:
    bb_yaz(s, ofs, v);
    break;
  case M_USART:
    usart_yaz(ofs, v);
    break;
  case M_I2C:
    i2c_yaz(ofs, v, onceki);
    break;
  case M_ADC:
    adc_yaz(ofs, v);
    break;
  case M_SCS:
    scs_yaz(ofs, v);
    break;
  case M_DWT:
    dwt_yaz(ofs, v);
    break;
  default:
    G(s, ofs) = v;
    break;
  }
}
static uint64_t model_degisim(Sayfa *s, uint32_t ofs) { /* okunan değerin bir sonraki değişebileceği an */
  if (s->tur == M_USART && ofs == U_SR) {
    return u_sonraki();
  }
  if (s->tur == M_ADC && ofs == A_SR) {
    return A.donusum ? A.bitis : UINT64_MAX;
  }
  if (s->tur == M_I2C) {
    return i2c_degisim(ofs);
  }
  return UINT64_MAX;
}

/* ── kesmeler ───────────────────────────────────────────────────────────────────────────────────────── */
static uint32_t tim1_saati(void) {
  const uint32_t ppre2 = (G(S_RCC, 0x808U) >> 13) & 7U;
  return pclk2() * ((ppre2 < 4U) ? 1U : 2U); /* APB2 bölücü ≠ 1 → zamanlayıcı saati 2 × PCLK2 */
}
static uint64_t tim1_periyot(void) {
  const uint64_t n = ((uint64_t)TIM1->PSC + 1U) * ((uint64_t)TIM1->ARR + 1U);
  const uint32_t clk = tim1_saati();
  return clk ? (n * 1000000000ULL / clk) : 20000U;
}
static int tim1_etkin(void) {
  const int e = (TIM1->CR1 & TIM_CR1_CEN) && (TIM1->DIER & TIM_DIER_UIE) && nvic_etkin(TIM1_UP_TIM10_IRQn);
  if (e && !g_tim1_acik) {
    g_tim1_acik = 1;
    g_tim1_t = g_vt + tim1_periyot();
  } else if (!e) {
    g_tim1_acik = 0;
  }
  return e;
}

static uint64_t kesme_sonraki(void) { /* GELECEKTEKİ ilk kesme olayı (vadesi gelmiş ama teslim edilemeyen bekler) */
  uint64_t t = UINT64_MAX;
  if (systick_etkin() && (g_systick_t > g_vt) && (g_systick_t < t)) {
    t = g_systick_t;
  }
  if (tim1_etkin() && (g_tim1_t > g_vt) && (g_tim1_t < t)) {
    t = g_tim1_t;
  }
  u_guncelle();
  const uint64_t u = u_sonraki();
  if ((u > g_vt) && (u < t)) {
    t = u;
  }
  return t;
}

static void isr_kos(void (*f)(void)) {
  g_isr = 1;
  g_isr_sayisi++;
  f();
  g_isr = 0;
}

static void kesmeleri_teslim_et(void) {
  if (g_isr || g_primask) {
    return;
  }
  for (int koruma = 0; koruma < 1000000; koruma++) {
    const uint64_t ts = systick_etkin() ? g_systick_t : UINT64_MAX;
    const uint64_t tt = tim1_etkin() ? g_tim1_t : UINT64_MAX;
    if ((ts <= g_vt) && (ts <= tt)) {
      g_systick_t += systick_periyot();
      isr_kos(SysTick_Handler);
      continue;
    }
    if (tt <= g_vt) {
      g_tim1_t += tim1_periyot();
      TIM1->SR |= TIM_SR_UIF;
      isr_kos(TIM1_UP_TIM10_IRQHandler);
      static uint32_t onceki_maske = 0U; /* sonda: etkin bobin maskesi her TIM1 tick'inde (20 µs) — değiştiyse yaz */
      const uint32_t maske = pemf_host_aktif_maske();
      if (maske != onceki_maske) {
        printf("A %llu %u\n", (unsigned long long)(g_vt / 1000U), (unsigned)maske);
        onceki_maske = maske;
      }
      continue;
    }
    if (u_kesme()) {
      isr_kos(USART3_IRQHandler);
      continue;
    }
    return;
  }
  olumcul("kesme teslimi bitmedi (kosul temizlenmiyor)");
}

static void zamani_ilerlet(uint64_t hedef) {
  for (;;) {
    if (!g_isr && !g_primask) {
      kesmeleri_teslim_et();
    }
    if (g_vt >= hedef) {
      break;
    }
    uint64_t t = kesme_sonraki();
    if (t > hedef) {
      t = hedef;
    }
    if (t <= g_vt) {
      t = g_vt + 1U;
    }
    g_vt = t;
    if (g_vt >= g_bitis) {
      senaryo_bitir(0);
    }
  }
}

/* ── VEH: erişim → model ────────────────────────────────────────────────────────────────────────────── */
typedef struct {
  Sayfa *s;
  uintptr_t kelime;
  uint32_t ofs, hazir;
  int yazma;
} Bekleyen;
static Bekleyen g_bek[32];
static int g_bek_n;
/* Bayrak bekleme döngüsü algılama: bağlam (ana / ISR) başına son 4 erişim. Yalnız OKUMALARDAN oluşan 1- ya da
 * 2-periyotlu tekrar (HAL'in TXE beklemesi SR + CR1'i dönüşümlü okur) = döngü → okunan yazmaçların en erken DEĞİŞİM
 * anına atlanır (aradaki kesmeler sırayla teslim edilir). Değer değişmezse ve olay yoksa (ör. NACK'te ADDR) atlama YOK:
 * döngü kendi bütçesini erişim başına ERISIM_NS ile tüketir (gerçek donanımdaki gibi). */
typedef struct {
  Sayfa *s;
  uint32_t ofs, deger;
  int okuma;
} Erisim;
static Erisim g_gecmis[2][4];
static uint64_t g_iz_bas = UINT64_MAX, g_iz_adet;

static int ayni(const Erisim *a, const Erisim *b) {
  return a->okuma && b->okuma && (a->s == b->s) && (a->ofs == b->ofs) && (a->deger == b->deger);
}

static void erisim_sonrasi(Sayfa *s, uint32_t ofs, int degisti, uint32_t deger) {
  g_erisim++;
  g_sayac[s - g_sayfa][ofs / 4U]++;
  if ((g_erisim >= g_iz_bas) && (g_erisim < g_iz_bas + g_iz_adet)) {
    printf("IZ %llu vt=%llu %s 0x%08llX=0x%08X isr=%d\n", (unsigned long long)g_erisim, (unsigned long long)g_vt,
           degisti ? "Y" : "O", (unsigned long long)(s->taban + ofs), deger, g_isr);
  }
  Erisim *h = g_gecmis[g_isr ? 1 : 0];
  memmove(&h[1], &h[0], 3U * sizeof(Erisim));
  h[0].s = s;
  h[0].ofs = ofs;
  h[0].deger = deger;
  h[0].okuma = !degisti;
  uint64_t hedef = g_vt + g_erisim_ns;
  uint64_t t = UINT64_MAX;
  /* ⚠️ Atlama yalnız okunan yazmaç(lar)ın ŞU ANKİ model değeri son okunanla AYNIYSA: değişim son okumadan sonra
   * zaten olduysa (ör. TC kurulmuş) döngü onu bir sonraki okumada görmeli — eskiden bir sonraki RX olayına atlanıyordu. */
  if (ayni(&h[0], &h[1]) && ayni(&h[1], &h[2])) { /* 1-periyot: aynı yazmaç, aynı değer, 3 kez */
    if (model_oku(s, ofs) == deger) {
      t = model_degisim(s, ofs);
    }
  } else if (ayni(&h[0], &h[2]) && ayni(&h[1], &h[3]) && !ayni(&h[0], &h[1])) { /* 2-periyot */
    if ((model_oku(h[0].s, h[0].ofs) == h[0].deger) && (model_oku(h[1].s, h[1].ofs) == h[1].deger)) {
      const uint64_t t0 = model_degisim(h[0].s, h[0].ofs), t1 = model_degisim(h[1].s, h[1].ofs);
      t = (t0 < t1) ? t0 : t1;
    }
  }
  if ((t != UINT64_MAX) && (t > hedef)) {
    hedef = t;
  }
  zamani_ilerlet(hedef);
}

/* VEH (dongu_win.c) bu üç işlevi çağırır. Erişim ihlali: değer hazırlanır, sayfa açılır → çağıran TF kurar.
 * Tek adım: yazılan değer okunur, sayfa kilitlenir, model işler, zaman ilerler (kesmeler burada teslim edilir). */
int dk_erisim_basla(uintptr_t adr, int yazma) {
  Sayfa *s = sayfa_bul(adr);
  if (!s) {
    return 0;
  }
  if (g_bek_n >= 32) {
    olumcul("ic ice erisim derinligi");
  }
  Bekleyen *b = &g_bek[g_bek_n++];
  b->s = s;
  b->kelime = adr & ~(uintptr_t)3U;
  b->ofs = (uint32_t)(b->kelime - s->taban);
  b->yazma = yazma;
  b->hazir = model_oku(s, b->ofs);
  dw_sayfa_kilitle(s->taban, 0);
  *(volatile uint32_t *)b->kelime = b->hazir;
  return 1;
}

int dk_bekleyen_var(void) { return g_bek_n > 0; }

void dk_erisim_bitir(void) {
  const Bekleyen b = g_bek[--g_bek_n];
  const uint32_t yeni = *(volatile uint32_t *)b.kelime;
  dw_sayfa_kilitle(b.s->taban, 1);
  const int degisti = b.yazma || (yeni != b.hazir);
  if (degisti) {
    model_yaz(b.s, b.ofs, yeni, b.hazir);
  } else {
    model_okundu(b.s, b.ofs);
  }
  erisim_sonrasi(b.s, b.ofs, degisti, b.hazir);
}

/* ── firmware kancaları ─────────────────────────────────────────────────────────────────────────────── */
uint32_t HAL_GetTick(void) { /* güçlü tanım: HAL'in zayıf HAL_GetTick'i `/alternatename` ile geri çekilir */
  if (!g_isr) {
    zamani_ilerlet(g_vt + g_gettick_ns);
  }
  return uwTick;
}
void pemf_host_nop(void) {
  g_vt += 6U;
  if (g_vt >= g_bitis) {
    senaryo_bitir(0);
  }
}
void pemf_host_irq_kapat(void) { g_primask = 1; }
void pemf_host_irq_ac(void) {
  g_primask = 0;
  if (!g_isr) {
    kesmeleri_teslim_et();
  }
}
uint32_t pemf_host_primask_al(void) { return (uint32_t)g_primask; }
void pemf_host_primask_yaz(uint32_t deger) {
  if (deger & 1U) {
    pemf_host_irq_kapat();
  } else {
    pemf_host_irq_ac();
  }
}

/* ── senaryo, kurulum, bitiş ────────────────────────────────────────────────────────────────────────── */
static void senaryo_bitir(int kod) {
  if (g_satir_n) {
    printf("P %llu %.*s\n", (unsigned long long)(g_satir_bas / 1000U), (int)g_satir_n, g_satir);
  }
  for (int k = 0; k < 12; k++) { /* tanı: en sık erişilen yazmaçlar */
    uint64_t eniyi = 0U;
    size_t si = 0U, oi = 0U;
    for (size_t i = 0; i < SAYFA_N; i++) {
      for (size_t o = 0; o < SAYFA / 4U; o++) {
        if (g_sayac[i][o] > eniyi) {
          eniyi = g_sayac[i][o];
          si = i;
          oi = o;
        }
      }
    }
    if (!eniyi) {
      break;
    }
    printf("SAYAC 0x%08llX %llu\n", (unsigned long long)(g_sayfa[si].taban + 4U * oi), (unsigned long long)eniyi);
    g_sayac[si][oi] = 0U;
  }
  printf("SON vt_us=%llu erisim=%llu isr=%llu tx_bayt=%llu rx_bayt=%llu rx_ore=%llu rx_kayip=%llu tdr_ezildi=%llu "
         "brr=0x%X pclk1=%lu\n",
         (unsigned long long)(g_vt / 1000U), (unsigned long long)g_erisim, (unsigned long long)g_isr_sayisi,
         (unsigned long long)g_tx_bayt, (unsigned long long)U.rx_i, (unsigned long long)g_rx_ore,
         (unsigned long long)g_rx_kayip, (unsigned long long)g_tdr_ezildi, (unsigned)G(S_USART, U_BRR),
         (unsigned long)pclk1());
  fflush(stdout);
  dw_bitir(kod);
}

static void rx_ekle(uint64_t t, uint8_t b) {
  if (g_rx_n == g_rx_kap) {
    g_rx_kap = g_rx_kap ? 2U * g_rx_kap : 4096U;
    g_rx = (RxBayt *)realloc(g_rx, g_rx_kap * sizeof(RxBayt));
    if (!g_rx) {
      olumcul("bellek");
    }
  }
  g_rx[g_rx_n].t = t;
  g_rx[g_rx_n].b = b;
  g_rx_n++;
}

static Hat *senaryo_hat(int no) { return (no == 2) ? &g_hat[1] : &g_hat[0]; }
static Cihaz *senaryo_cihaz(int hat, int tur) {
  Hat *h = senaryo_hat(hat);
  for (int i = 0; i < h->n; i++) {
    if (h->cihaz[i].tur == tur) {
      return &h->cihaz[i];
    }
  }
  return NULL;
}

static void senaryo_oku(const char *yol) {
  FILE *f = fopen(yol, "r");
  if (!f) {
    olumcul("senaryo acilamadi");
  }
  static char satir[8192];
  uint64_t son_t = 0U;
  while (fgets(satir, sizeof(satir), f)) {
    char ad[32] = {0};
    if (sscanf(satir, "%31s", ad) != 1 || ad[0] == '#') {
      continue;
    }
    if (!strcmp(ad, "SURE_US")) {
      unsigned long long v;
      sscanf(satir + 7, "%llu", &v);
      g_bitis = v * 1000ULL;
    } else if (!strcmp(ad, "IZ")) {
      unsigned long long b, n;
      if (sscanf(satir + 2, "%llu %llu", &b, &n) == 2) {
        g_iz_bas = b;
        g_iz_adet = n;
      }
    } else if (!strcmp(ad, "GETTICK_NS")) {
      unsigned long long v;
      if (sscanf(satir + 10, "%llu", &v) == 1) {
        g_gettick_ns = v;
      }
    } else if (!strcmp(ad, "ERISIM_NS")) {
      unsigned long long v;
      sscanf(satir + 9, "%llu", &v);
      g_erisim_ns = v;
    } else if (!strcmp(ad, "ACS")) {
      int ch, mv;
      if (sscanf(satir + 3, "%d %d", &ch, &mv) == 2 && ch >= 0 && ch < 19) {
        g_acs_mv[ch] = mv;
      }
    } else if (!strcmp(ad, "I2C")) {
      int hat;
      char tur[16];
      unsigned adres;
      if (sscanf(satir + 3, "%d %15s %x", &hat, tur, &adres) == 3) {
        Hat *h = senaryo_hat(hat);
        Cihaz *c = &h->cihaz[h->n++];
        memset(c, 0, sizeof(*c));
        c->adres = (uint8_t)adres;
        c->tur = !strcmp(tur, "MLX90614") ? 1 : 2;
        c->ortam_c = 25.0f;
        c->nesne_c = 30.0f;
        c->x = 36;
        c->z = 31;
      }
    } else if (!strcmp(ad, "SICAKLIK")) {
      int hat;
      float o, n;
      if (sscanf(satir + 8, "%d %f %f", &hat, &o, &n) == 3) {
        Cihaz *c = senaryo_cihaz(hat, 1);
        if (c) {
          c->ortam_c = o;
          c->nesne_c = n;
        }
      }
    } else if (!strcmp(ad, "ALAN")) {
      int hat, x, y, z;
      if (sscanf(satir + 4, "%d %d %d %d", &hat, &x, &y, &z) == 4) {
        Cihaz *c = senaryo_cihaz(hat, 2);
        if (c) {
          c->x = (int16_t)x;
          c->y = (int16_t)y;
          c->z = (int16_t)z;
        }
      }
    } else if (!strcmp(ad, "PAKET")) {
      unsigned long long t_us;
      int ofs = 0;
      if (sscanf(satir + 5, "%llu %n", &t_us, &ofs) >= 1) {
        const char *p = satir + 5 + ofs;
        uint64_t t = t_us * 1000ULL;
        if (t < son_t) {
          t = son_t; /* paketler üst üste binmez: hat sırayla taşır */
        }
        while (p[0] && p[1] && p[0] != '\n' && p[0] != '\r') {
          unsigned b;
          if (sscanf(p, "%2x", &b) != 1) {
            break;
          }
          rx_ekle(t, (uint8_t)b);
          t += 86806U; /* bilgisayar tarafı 115200 baud: 10 bit / 115200 */
          p += 2;
        }
        son_t = t;
      }
    }
  }
  fclose(f);
}

/* Windows katmanının çağırdığı kurulum / koşu / bekçi işlevleri. */
int dk_hazirla(const char *senaryo) {
  senaryo_oku(senaryo);
  if (!dw_bellek_kur()) {
    return 0;
  }
  G(S_RCC, 0x800U) = 0x00000083U; /* RCC_CR: HSION + HSIRDY + HSITRIM */
  G(S_RCC, 0x804U) = 0x24003010U; /* RCC_PLLCFGR sıfırlama değeri */
  G(S_RCC, 0x874U) = 0x0E000000U; /* RCC_CSR */
  for (int i = 0; i < 2; i++) {
    h_sifirla(&g_hat[i]);
  }
  for (size_t i = 0; i < SAYFA_N; i++) {
    dw_sayfa_kilitle(g_sayfa[i].taban, 1);
  }
  return 1;
}

void dk_firmware(void) {
  pemf_fw_main();
  printf("!!! FIRMWARE main() DONDU vt_us=%llu\n", (unsigned long long)(g_vt / 1000U));
  fflush(stdout);
  dw_bitir(5);
}

uint64_t dk_vt(void) { return g_vt; }
uint64_t dk_erisim(void) { return g_erisim; }
