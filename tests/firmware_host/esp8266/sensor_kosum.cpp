/* tests/firmware_host/esp8266/sensor_kosum.cpp — GERÇEK 8266 `SensorManager.cpp`'yi ana makinede koşturan model (1-G · D1.62).
 *
 * Kullanım: sensor_kosum.exe <senaryo.txt> → stdout:
 *   "D <t_ms> <temp_ok> <nesne> <ortam> <mag_ok> <mag_mT> <x> <y> <z> <cur_ok> <akım_A> <sensors_ok>"  (OKU → getData())
 *   "E <tür>"   (NetworkManager::publishEvent)
 *   "SON gunluk=<satır sayısı>"
 * Senaryo (satır satır):
 *   A0 <toprak|yuzen|3v3|acs> [k]   A0 modeli. acs: V = k·(2,5 + 0,066·I) ± 5 mV gürültü (bölücü oranı k; S3 kartının
 *                                   ölçülen ofseti 1,789 V → k = 0,716). yuzen: 1,7 V ± 0,28 V düzgün gürültü (DENETIM-08-2
 *                                   ölçümüyle aynı mertebe: RMS sapma ~0,16 V → "2,455 A"). toprak 0 V, 3v3 3,3 V.
 *   AKIM <A>                        ACS712'den geçen DC akım
 *   MLX614 <0|1> · SICAKLIK <nesne> <ortam> · SICAKLIK_HATA <0|1>
 *   MLX393 <0|1> · MAG <x> <y> <z> (µT) · MAG_HATA <0|1>
 *   BASLAT                          sm.beginWithoutCalibration(); sm.calibrate();  (.ino setup sırası)
 *   GUNCELLE <ms>                   ms boyunca 1 ms adımla sm.update()
 *   OKU                             getData() satırı
 * Gürültü belirlenimci (sabit tohumlu LCG). Sanal zaman: delay/delayMicroseconds ilerletir. */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "Adafruit_MLX90393.h"
#include "Adafruit_MLX90614.h"
#include "Arduino.h"
#include "NetworkManager.h"
#include "SensorManager.h"
#include "Wire.h"

HardwareSerial Serial;
EspClass ESP;
TwoWire Wire;

static uint64_t g_us = 0;
static unsigned long g_gunluk = 0;
static uint32_t g_tohum = 0x1234567u;

static enum { A0_TOPRAK, A0_YUZEN, A0_3V3, A0_ACS } g_a0 = A0_TOPRAK;
static double g_k = 1.0, g_akim = 0.0;
static int g_mlx614 = 0, g_sicaklik_hata = 0, g_mlx393 = 0, g_mag_hata = 0;
static double g_nesne = 36.5, g_ortam = 25.0, g_mx = 0.0, g_my = 0.0, g_mz = 0.0;

static double rastgele(void) { /* [0, 1) */
  g_tohum = g_tohum * 1664525u + 1013904223u;
  return (double)(g_tohum >> 8) / 16777216.0;
}

unsigned long millis() { return (unsigned long)(g_us / 1000u); }
unsigned long micros() { return (unsigned long)g_us; }
void delay(unsigned long ms) { g_us += (uint64_t)ms * 1000u; }
void delayMicroseconds(unsigned int us) { g_us += us; }
void yield() {}
void pinMode(uint8_t, uint8_t) {}
void digitalWrite(uint8_t, uint8_t) {}
int digitalRead(uint8_t) { return HIGH; } /* I2C hatları pull-up: veri yolu takılı değil */
void pemf_host_gunluk(const char *) { g_gunluk++; }

int analogRead(uint8_t pin) {
  g_us += 100u; /* 8266 ADC dönüşümü ~100 µs */
  if (pin != A0) {
    return 0;
  }
  double v = 0.0;
  switch (g_a0) {
    case A0_TOPRAK: v = 0.0; break;
    case A0_3V3: v = 3.3; break;
    case A0_YUZEN: v = 1.7 + (rastgele() - 0.5) * 0.56; break;
    case A0_ACS: v = g_k * (2.5 + 0.066 * g_akim) + (rastgele() - 0.5) * 0.010; break;
  }
  long ham = lround(v / 3.3 * 1023.0);
  return (int)(ham < 0 ? 0 : (ham > 1023 ? 1023 : ham));
}

uint8_t TwoWire::endTransmission(bool) {
  if ((_adres == 0x5A && g_mlx614) || (_adres == 0x18 && g_mlx393)) {
    return 0;
  }
  return 2; /* NACK (adres) */
}

bool Adafruit_MLX90614::begin(uint8_t, void *) { return g_mlx614 != 0; }
double Adafruit_MLX90614::readObjectTempC() { return (g_mlx614 && !g_sicaklik_hata) ? g_nesne : NAN; }
double Adafruit_MLX90614::readAmbientTempC() { return (g_mlx614 && !g_sicaklik_hata) ? g_ortam : NAN; }

bool Adafruit_MLX90393::begin_I2C(uint8_t, void *) { return g_mlx393 != 0; }
bool Adafruit_MLX90393::readData(float *x, float *y, float *z) {
  if (!g_mlx393 || g_mag_hata) {
    return false;
  }
  *x = (float)g_mx;
  *y = (float)g_my;
  *z = (float)g_mz;
  return true;
}

void NetworkManager::publishEvent(const char *tur, const char *) { printf("E %s\n", tur); }
static NetworkManager g_ag;
NetworkManager *network = &g_ag;

static void sayi(double v) {
  if (isnan(v)) {
    printf(" nan");
  } else {
    printf(" %.6f", v);
  }
}

int main(int argc, char **argv) {
  if (argc < 2) {
    fprintf(stderr, "kullanim: sensor_kosum.exe <senaryo.txt>\n");
    return 2;
  }
  FILE *f = fopen(argv[1], "r");
  if (!f) {
    fprintf(stderr, "senaryo acilamadi\n");
    return 2;
  }
  static SensorManager sm(A0, D2, D1);
  char satir[256];
  while (fgets(satir, sizeof(satir), f)) {
    char k[32] = {0}, a[32] = {0};
    double p1 = 0, p2 = 0, p3 = 0;
    if (sscanf(satir, "%31s", k) != 1) {
      continue;
    }
    if (strcmp(k, "A0") == 0) {
      sscanf(satir, "%*s %31s %lf", a, &p1);
      g_a0 = strcmp(a, "yuzen") == 0 ? A0_YUZEN : (strcmp(a, "3v3") == 0 ? A0_3V3 : (strcmp(a, "acs") == 0 ? A0_ACS : A0_TOPRAK));
      if (g_a0 == A0_ACS) {
        g_k = p1;
      }
    } else if (strcmp(k, "AKIM") == 0) {
      sscanf(satir, "%*s %lf", &g_akim);
    } else if (strcmp(k, "MLX614") == 0) {
      sscanf(satir, "%*s %d", &g_mlx614);
    } else if (strcmp(k, "SICAKLIK") == 0) {
      sscanf(satir, "%*s %lf %lf", &g_nesne, &g_ortam);
    } else if (strcmp(k, "SICAKLIK_HATA") == 0) {
      sscanf(satir, "%*s %d", &g_sicaklik_hata);
    } else if (strcmp(k, "MLX393") == 0) {
      sscanf(satir, "%*s %d", &g_mlx393);
    } else if (strcmp(k, "MAG") == 0) {
      sscanf(satir, "%*s %lf %lf %lf", &p1, &p2, &p3);
      g_mx = p1;
      g_my = p2;
      g_mz = p3;
    } else if (strcmp(k, "MAG_HATA") == 0) {
      sscanf(satir, "%*s %d", &g_mag_hata);
    } else if (strcmp(k, "BASLAT") == 0) {
      sm.beginWithoutCalibration();
      sm.calibrate();
    } else if (strcmp(k, "GUNCELLE") == 0) {
      sscanf(satir, "%*s %lf", &p1);
      const uint64_t bitis = g_us + (uint64_t)(p1 * 1000.0);
      while (g_us < bitis) {
        sm.update();
        g_us += 1000u;
      }
    } else if (strcmp(k, "OKU") == 0) {
      SensorData d = sm.getData();
      printf("D %lu %d", millis(), (int)d.temp_sensor_ok);
      sayi(d.tempObject);
      sayi(d.tempAmbient);
      printf(" %d", (int)d.magnetic_sensor_ok);
      sayi(d.magneticField);
      sayi(d.magX);
      sayi(d.magY);
      sayi(d.magZ);
      printf(" %d", (int)d.current_sensor_ok);
      sayi(d.current);
      printf(" %d\n", (int)d.sensorsOK);
    }
  }
  fclose(f);
  printf("SON gunluk=%lu\n", g_gunluk);
  return 0;
}
