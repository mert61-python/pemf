/* tests/firmware_host/esp8266/komut_kosum.cpp — 8266 `processControlCommand` (GERÇEK kaynaktan dilim) ana makinede (1-G · Y48).
 *
 * Aparat (`tests/esp8266_komut_aparat.py`) `esp8266_pemf_coil.ino`'dan tekrar önbelleği global'lerini, `isCommandProcessed`,
 * `addCommandToCache` ve `processControlCommand`'ı BAYT BAYT keser → `komut_dilim.inc`; burada derlenir. Gerçek
 * `SharedDefs.h` (CommandRateLimiter, LOG makroları), `SensorManager` (SELFTEST dalı) ve `CoilController.h` bildirimi
 * kullanılır; bobin DAVRANIŞI burada modellenir (`handleCommand`: START → etkin, STOP → durgun).
 * Kullanım: komut_kosum.exe <senaryo.txt> → stdout:
 *   "C <START|STOP> <frekans> <duty> <süre_sn>"  (bobine giden komut)
 *   "A <command_id> <0|1>"                        (sendCommandAck)
 *   "E <tür>"                                      (publishEvent)
 *   "S <etkin 0|1>"                                (DURUM)
 *   "SON"
 * Senaryo: "CMD <komut> <command_id|-> [anahtar=değer ...]" (sayıya benzeyen değer sayı alanı) · "ZAMAN <ms>" · "DURUM". */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <string>

#include "Arduino.h"
#include "ArduinoJson.h"
#include "CoilController.h"
#include "NetworkManager.h"
#include "SensorManager.h"
#include "SharedDefs.h"

HardwareSerial Serial;
EspClass ESP;

static uint64_t g_us = 0;
unsigned long millis() { return (unsigned long)(g_us / 1000u); }
unsigned long micros() { return (unsigned long)g_us; }
void delay(unsigned long ms) { g_us += (uint64_t)ms * 1000u; }
void delayMicroseconds(unsigned int us) { g_us += us; }
void yield() {}
void pinMode(uint8_t, uint8_t) {}
void digitalWrite(uint8_t, uint8_t) {}
int digitalRead(uint8_t) { return HIGH; }
int analogRead(uint8_t) { return 0; }
void pemf_host_gunluk(const char *s) {
  if (getenv("PEMF_KOMUT_GUNLUK")) {
    printf("G %s\n", s);
  }
}

/* ── sensörler takılı değil (SensorManager yalnız SELFTEST dalında okunur) ── */
TwoWire Wire;
uint8_t TwoWire::endTransmission(bool) { return 2; }
bool Adafruit_MLX90614::begin(uint8_t, void *) { return false; }
double Adafruit_MLX90614::readObjectTempC() { return NAN; }
double Adafruit_MLX90614::readAmbientTempC() { return NAN; }
bool Adafruit_MLX90393::begin_I2C(uint8_t, void *) { return false; }
bool Adafruit_MLX90393::readData(float *, float *, float *) { return false; }

/* ── bobin modeli (gerçek CoilController.h bildirimi; davranış burada) ── */
CoilController::CoilController(int pwmPin, int coilId, TimeManager *) : _pwmPin(pwmPin), _coilId(coilId), _pwmActive(false) {}
void CoilController::handleCommand(const ControlCommand &cmd) {
  if (cmd.type == CMD_START) {
    _pwmActive = true;
    printf("C START %d %d %d\n", cmd.frequency, cmd.dutyCycle, cmd.durationSec);
  } else if (cmd.type == CMD_STOP) {
    _pwmActive = false;
    printf("C STOP 0 0 0\n");
  }
}
bool CoilController::isActive() { return _pwmActive; }

/* ── ağ modeli ── */
void NetworkManager::publishEvent(const char *tur, const char *) { printf("E %s\n", tur); }
void NetworkManager::sendCommandAck(const char *command_id, bool success) {
  printf("A %s %d\n", (command_id && command_id[0]) ? command_id : "-", success ? 1 : 0);
}
void NetworkManager::clearAllWiFiCredentials() {}
bool NetworkManager::isMqttConnected() { return true; }

/* ── .ino'nun dilimin kullandığı global'leri (gerçek tanımlarla AYNI tür/ad) ── */
SensorManager sensors(A0);
static NetworkManager g_ag;
NetworkManager *network = &g_ag;
static CoilController g_bobin(5, 8, nullptr);
CoilController *coil = &g_bobin;
CommandRateLimiter commandRateLimiter;
static bool g_thermalLock = false;
void feedWatchdog() {}
void cleanup() {}

#include "komut_dilim.inc"

int main(int argc, char **argv) {
  if (argc < 2) {
    fprintf(stderr, "kullanim: komut_kosum.exe <senaryo.txt>\n");
    return 2;
  }
  FILE *f = fopen(argv[1], "r");
  if (!f) {
    return 2;
  }
  char satir[512];
  while (fgets(satir, sizeof(satir), f)) {
    char k[16] = {0};
    if (sscanf(satir, "%15s", k) != 1) {
      continue;
    }
    if (strcmp(k, "ZAMAN") == 0) {
      double ms = 0;
      sscanf(satir, "%*s %lf", &ms);
      g_us += (uint64_t)(ms * 1000.0);
    } else if (strcmp(k, "DURUM") == 0) {
      printf("S %d\n", coil->isActive() ? 1 : 0);
    } else if (strcmp(k, "CMD") == 0) {
      static StaticJsonDocument<384> doc;
      doc.clear();
      char komut[32] = {0}, kimlik[96] = {0};
      int n = 0;
      sscanf(satir, "%*s %31s %95s %n", komut, kimlik, &n);
      doc.koy("command", komut, false);
      if (strcmp(kimlik, "-") != 0) {
        doc.koy("command_id", kimlik, false);
      }
      const char *p = satir + n;
      char ad[48], deger[96];
      int m = 0;
      while (sscanf(p, " %47[^=]=%95s%n", ad, deger, &m) == 2) {
        char *son = nullptr;
        strtod(deger, &son);
        doc.koy(ad, deger, son && *son == '\0');
        p += m;
      }
      processControlCommand(doc);
    }
  }
  fclose(f);
  printf("SON\n");
  return 0;
}
