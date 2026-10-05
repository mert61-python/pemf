/* tests/firmware_host/esp8266 — ESP8266 Arduino çekirdeğinin ana makine taklidi (1-G · D1.62 SensorManager aparatı).
 *
 * Yalnız `firmware/esp8266_pemf_coil/SensorManager.cpp`'nin kullandığı yüzey: sanal zaman (`millis`/`delay`), A0 ADC
 * modeli (`analogRead`), I2C pin seviyeleri (bus kurtarma), `Serial` günlüğü (sayılır, basılmaz), `ESP.wdtFeed`.
 * Model `sensor_kosum.cpp`'dedir; firmware kaynağı DEĞİŞMEDEN (bayt bayt kopya, sha256 aparatta doğrulanır) derlenir. */
#ifndef PEMF_HOST_ARDUINO_H
#define PEMF_HOST_ARDUINO_H

#include <math.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t byte;

#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define OUTPUT_OPEN_DRAIN 3
#define A0 17
#define D1 5
#define D2 4
#define F(x) (x)
#define PSTR(x) (x)
#define snprintf_P snprintf
#define IRAM_ATTR
#define ICACHE_RAM_ATTR
#define PROGMEM

static inline size_t strlcpy(char *hedef, const char *kaynak, size_t boy) {
  const size_t n = strlen(kaynak);
  if (boy > 0) {
    const size_t k = (n < boy - 1) ? n : boy - 1;
    memcpy(hedef, kaynak, k);
    hedef[k] = '\0';
  }
  return n;
}

unsigned long millis();
unsigned long micros();
void delay(unsigned long ms);
void delayMicroseconds(unsigned int us);
int analogRead(uint8_t pin);
void pinMode(uint8_t pin, uint8_t mode);
void digitalWrite(uint8_t pin, uint8_t val);
int digitalRead(uint8_t pin);
void yield();

void pemf_host_gunluk(const char *metin);

class HardwareSerial {
 public:
  template <typename T> size_t print(const T &) { return 0; }
  template <typename T> size_t print(const T &, int) { return 0; }
  size_t println() { return 0; }
  size_t println(const char *s) {
    pemf_host_gunluk(s);
    return 0;
  }
  template <typename T> size_t println(const T &) { return 0; }
  template <typename T> size_t println(const T &, int) { return 0; }
  size_t printf(const char *fmt, ...) {
    char tampon[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(tampon, sizeof(tampon), fmt, ap);
    va_end(ap);
    pemf_host_gunluk(tampon);
    return 0;
  }
};
extern HardwareSerial Serial;

class EspClass {
 public:
  void wdtFeed() {}
  uint32_t getFreeHeap() { return 40000u; }
  uint32_t getMaxFreeBlockSize() { return 30000u; }
  void restart() { printf("R RESTART\n"); }
};
extern EspClass ESP;

#endif /* PEMF_HOST_ARDUINO_H */
