/* tests/firmware_host/esp8266 — Adafruit_MLX90614 taklidi (sıcaklık; değer/arıza `sensor_kosum.cpp` modelinden). */
#ifndef PEMF_HOST_MLX90614_H
#define PEMF_HOST_MLX90614_H

#include <Arduino.h>

class Adafruit_MLX90614 {
 public:
  bool begin(uint8_t adres = 0x5A, void *wire = nullptr);
  double readObjectTempC();
  double readAmbientTempC();
};

#endif /* PEMF_HOST_MLX90614_H */
