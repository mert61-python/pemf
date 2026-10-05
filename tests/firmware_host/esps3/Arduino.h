/* tests/firmware_host/esps3 — Arduino-ESP32 (core 3.x) taklidi (1-G · D1.102 S3 CoilController aparatı).
 * Yalnız `firmware/esps3_pemf_coil/CoilController.cpp`'nin kullandığı yüzey: sanal zaman, pin/kesme kaydı, donanım
 * zamanlayıcısı (ISR işaretçisi kaydedilir; aparat elle çağırır), portMUX (tek iş parçacığı → boş), Serial (sessiz). */
#ifndef PEMF_HOST_S3_ARDUINO_H
#define PEMF_HOST_S3_ARDUINO_H

#include <math.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define HIGH 1
#define LOW 0
#define INPUT 0x01
#define OUTPUT 0x03
#define INPUT_PULLUP 0x05
#define INPUT_PULLDOWN 0x09
#define RISING 0x01
#define FALLING 0x02
#define IRAM_ATTR
#define digitalPinToInterrupt(p) (p)
#define constrain(x, lo, hi) ((x) < (lo) ? (lo) : ((x) > (hi) ? (hi) : (x)))

typedef struct {
  int kilit;
} portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED {0}
#define portENTER_CRITICAL(m) ((void)(m))
#define portEXIT_CRITICAL(m) ((void)(m))
#define portENTER_CRITICAL_ISR(m) ((void)(m))
#define portEXIT_CRITICAL_ISR(m) ((void)(m))

typedef struct hw_timer_s {
  int kimlik;
} hw_timer_t;

unsigned long millis();
unsigned long micros();
void delay(unsigned long ms);
void pinMode(uint8_t pin, uint8_t mode);
void digitalWrite(uint8_t pin, uint8_t val);
int digitalRead(uint8_t pin);
void attachInterrupt(uint8_t pin, void (*isr)(void), int mod);
hw_timer_t *timerBegin(uint32_t frekans);
void timerAttachInterrupt(hw_timer_t *t, void (*isr)(void));
void timerAlarm(hw_timer_t *t, uint64_t deger, bool otomatik, uint64_t tekrar);

class HardwareSerial {
 public:
  template <typename T> size_t print(const T &) { return 0; }
  size_t println() { return 0; }
  template <typename T> size_t println(const T &) { return 0; }
  size_t printf(const char *, ...) { return 0; }
};
extern HardwareSerial Serial;

#endif /* PEMF_HOST_S3_ARDUINO_H */
