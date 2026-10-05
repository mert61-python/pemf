/* tests/firmware_host/esps3/s3_kosum.cpp — ESP32-S3 `CoilController` (GERÇEK kaynak) ana makinede (1-G · D1.102).
 *
 * Aparat (`tests/esps3_coil_aparat.py`) gerçek `CoilController.cpp/.h` + `SharedDefs.h`'yi bayt bayt kopyalar; bu dosya
 * AYRI çeviri birimidir ve kaynağa YALNIZ public API (`begin`, `handleCommand`, `getState`, `syncDisabled`,
 * `syncIgnoredCount`) ve taklit tabloya kaydedilen ISR işaretçileri üzerinden dokunur:
 *   · DDS ISR'ı `timerAttachInterrupt` ile kaydedilen işaretçidir; periyodu `timerBegin`/`timerAlarm` değerlerinden
 *     türetilir ve sanal saatte o aralıkla çağrılır (zamanlayıcı `begin` anında başlar, hep çalışır).
 *   · Senkron ISR'ı `attachInterrupt` ile kaydedilen işaretçidir; GPIO7 giriş SEVİYESİ sürülür, kayıtlı kip RISING ise
 *     yalnız LOW→HIGH kenarında çağrılır. Aynı mikrosaniyede senkron kenarı DDS çağrısından ÖNCE işlenir.
 *   · `GPIO.out_w1ts/out_w1tc` ve `digitalWrite` yazımları pin seviyesine SIRAYLA işlenir; A/B çifti her değiştiğinde
 *     "K <t_us> <A> <B>" basılır (aynı ISR çağrısındaki ara durumlar dahil — aynı t ile).
 * Senaryo satırları:
 *   BASLA <frekans> <duty> <faz> <süre_sn>      → handleCommand(START)          → "C START <0|1>"
 *   GUNCELLE <frekans> <duty> <faz> <süre_sn>   → handleCommand(UPDATE_PARAMS)  (0 = belirtilmedi; faz -1 = belirtilmedi)
 *   DUR                                         → handleCommand(STOP)
 *   SENKRON <ofset_us> <periyot_us> <adet> <genişlik_us>  → şimdiden ofset sonra GPIO7 darbe treni planla
 *   BEKLE <us>                                  → sanal saati ilerlet (DDS + senkron olayları sırayla)
 *   DENEME <kimlik>                             → "T <kimlik>"
 *   DURUM                                       → "S <syncDisabled> <syncIgnored> <aktif> <efektif_duty>"
 * Açılışta: "KURULUM <dds_periyot_us> <senkron_pin> <senkron_kip> <oto_tekrar>"; sonda "SON". */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <algorithm>
#include <vector>

#include "Arduino.h"
#include "CoilController.h"
#include "SensorManager.h"
#include "SharedDefs.h"
#include "soc/gpio_struct.h"
#include <sys/time.h>

HardwareSerial Serial;
gpio_dev_t GPIO;
QueueHandle_t commandQueue = nullptr;
QueueHandle_t statusQueue = nullptr;
SemaphoreHandle_t serialMutex = nullptr; /* NULL → LOG makroları sessiz */

/* ── sanal saat ── */
static uint64_t g_us = 0;
unsigned long millis() { return (unsigned long)(g_us / 1000u); }
unsigned long micros() { return (unsigned long)g_us; }
void delay(unsigned long ms) { g_us += (uint64_t)ms * 1000u; }
int gettimeofday(struct timeval *tv, void *) {
  tv->tv_sec = (long)(g_us / 1000000u);
  tv->tv_usec = (long)(g_us % 1000000u);
  return 0;
}

/* ── pin seviyeleri + kenar günlüğü ── */
static uint8_t g_seviye[64];
static int g_son_a = -1, g_son_b = -1;
static void kenar_bas() {
  const int a = g_seviye[PIN_COIL_PWM_A], b = g_seviye[PIN_COIL_PWM_B];
  if (a != g_son_a || b != g_son_b) {
    printf("K %llu %d %d\n", (unsigned long long)g_us, a, b);
    g_son_a = a;
    g_son_b = b;
  }
}
void pemf_gpio_yaz(bool ayarla, uint32_t maske) {
  for (int p = 0; p < 32; ++p) {
    if (maske & (1UL << p)) {
      g_seviye[p] = ayarla ? 1 : 0;
    }
  }
  kenar_bas();
}
void pinMode(uint8_t, uint8_t) {}
void digitalWrite(uint8_t pin, uint8_t deger) {
  g_seviye[pin] = deger ? 1 : 0;
  kenar_bas();
}
int digitalRead(uint8_t pin) { return g_seviye[pin]; }

/* ── kesme tablosu ── */
static void (*g_senkron_isr)(void) = nullptr;
static int g_senkron_pin = -1, g_senkron_kip = 0;
void attachInterrupt(uint8_t pin, void (*isr)(void), int kip) {
  g_senkron_isr = isr;
  g_senkron_pin = pin;
  g_senkron_kip = kip;
}
static hw_timer_t g_zamanlayici = {1};
static uint32_t g_zaman_frekans = 0;
static uint64_t g_alarm = 0;
static bool g_oto = false;
static void (*g_dds_isr)(void) = nullptr;
hw_timer_t *timerBegin(uint32_t frekans) {
  g_zaman_frekans = frekans;
  return &g_zamanlayici;
}
void timerAttachInterrupt(hw_timer_t *, void (*isr)(void)) { g_dds_isr = isr; }
void timerAlarm(hw_timer_t *, uint64_t deger, bool oto, uint64_t) {
  g_alarm = deger;
  g_oto = oto;
}

/* ── sensör takılı değil ── */
SensorReadings SensorManager::readAll() {
  SensorReadings r;
  memset(&r, 0, sizeof(r));
  return r;
}
void SensorManager::setPWMActive(bool) {}
void SensorManager::forceCalibrate() {}

/* ── olay döngüsü ── */
struct SenkronOlayi {
  uint64_t t;
  int seviye;
};
static std::vector<SenkronOlayi> g_senkron; /* zamana göre sıralı tutulur */
static uint64_t g_dds_periyot_us = 0, g_dds_sonraki = 0;

static void senkron_seviye(int seviye) {
  const int onceki = g_seviye[PIN_SYNC_IN];
  g_seviye[PIN_SYNC_IN] = (uint8_t)seviye;
  if (g_senkron_isr && g_senkron_pin == PIN_SYNC_IN && onceki == 0 && seviye == 1 && g_senkron_kip == RISING) {
    g_senkron_isr();
  }
}

static void bekle(uint64_t sure) {
  const uint64_t son = g_us + sure;
  for (;;) {
    const bool senkron_var = !g_senkron.empty();
    const uint64_t ts = senkron_var ? g_senkron.front().t : UINT64_MAX;
    const uint64_t td = g_dds_isr ? g_dds_sonraki : UINT64_MAX;
    const uint64_t t = std::min(ts, td);
    if (t > son) {
      break;
    }
    g_us = t;
    if (senkron_var && ts <= td) {
      const int seviye = g_senkron.front().seviye;
      g_senkron.erase(g_senkron.begin());
      senkron_seviye(seviye);
    } else {
      g_dds_isr();
      g_dds_sonraki += g_dds_periyot_us;
    }
  }
  g_us = son;
}

int main(int argc, char **argv) {
  if (argc < 2) {
    fprintf(stderr, "kullanim: s3_kosum.exe <senaryo.txt>\n");
    return 2;
  }
  FILE *f = fopen(argv[1], "r");
  if (!f) {
    return 2;
  }
  static SensorManager sensorler;
  static CoilController bobin(&sensorler);
  bobin.begin();
  if (g_zaman_frekans == 0 || g_alarm == 0 || !g_dds_isr) {
    fprintf(stderr, "aparat: DDS zamanlayicisi kurulmadi\n");
    return 3;
  }
  g_dds_periyot_us = (g_alarm * 1000000ull) / g_zaman_frekans;
  g_dds_sonraki = g_us + g_dds_periyot_us;
  printf("KURULUM %llu %d %d %d\n", (unsigned long long)g_dds_periyot_us, g_senkron_pin, g_senkron_kip, g_oto ? 1 : 0);

  char satir[256];
  while (fgets(satir, sizeof(satir), f)) {
    char k[16] = {0};
    if (sscanf(satir, "%15s", k) != 1) {
      continue;
    }
    if (strcmp(k, "BEKLE") == 0) {
      unsigned long long us = 0;
      sscanf(satir, "%*s %llu", &us);
      bekle(us);
    } else if (strcmp(k, "BASLA") == 0 || strcmp(k, "GUNCELLE") == 0) {
      ControlCommand c;
      memset(&c, 0, sizeof(c));
      c.type = (k[0] == 'B') ? CMD_START : CMD_UPDATE_PARAMS;
      sscanf(satir, "%*s %d %d %d %d", &c.frequency, &c.dutyCycle, &c.phase, &c.durationSec);
      const bool ok = bobin.handleCommand(c);
      printf("C %s %d\n", k, ok ? 1 : 0);
    } else if (strcmp(k, "DUR") == 0) {
      ControlCommand c;
      memset(&c, 0, sizeof(c));
      c.type = CMD_STOP;
      const bool ok = bobin.handleCommand(c);
      printf("C DUR %d\n", ok ? 1 : 0);
    } else if (strcmp(k, "SENKRON") == 0) {
      unsigned long long ofset = 0, periyot = 0, adet = 0, genislik = 0;
      sscanf(satir, "%*s %llu %llu %llu %llu", &ofset, &periyot, &adet, &genislik);
      for (unsigned long long i = 0; i < adet; ++i) {
        const uint64_t yuksel = g_us + ofset + i * periyot;
        g_senkron.push_back({yuksel, 1});
        g_senkron.push_back({yuksel + genislik, 0});
      }
      std::stable_sort(g_senkron.begin(), g_senkron.end(),
                       [](const SenkronOlayi &x, const SenkronOlayi &y) { return x.t < y.t; });
    } else if (strcmp(k, "DENEME") == 0) {
      long kimlik = 0;
      sscanf(satir, "%*s %ld", &kimlik);
      printf("T %ld\n", kimlik);
    } else if (strcmp(k, "DURUM") == 0) {
      const PWMState st = bobin.getState();
      printf("S %d %lu %d %d\n", bobin.syncDisabled() ? 1 : 0, (unsigned long)bobin.syncIgnoredCount(),
             st.active ? 1 : 0, st.dutyCycle);
    }
  }
  fclose(f);
  printf("SON\n");
  return 0;
}
