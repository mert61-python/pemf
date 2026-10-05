/* tests/firmware_host/esp8266 — `Wire` (I2C) taklidi: yalnız adres yoklaması (`beginTransmission`/`endTransmission`).
 * Cihaz varlığı `sensor_kosum.cpp`'deki modelden okunur (MLX90614 0x5A, MLX90393 0x18). */
#ifndef PEMF_HOST_WIRE_H
#define PEMF_HOST_WIRE_H

#include <Arduino.h>

class TwoWire {
 public:
  void begin() {}
  void begin(int, int) {}
  void end() {}
  void setClock(uint32_t) {}
  void beginTransmission(uint8_t adres) { _adres = adres; }
  uint8_t endTransmission(bool = true);

 private:
  uint8_t _adres = 0;
};
extern TwoWire Wire;

#endif /* PEMF_HOST_WIRE_H */
