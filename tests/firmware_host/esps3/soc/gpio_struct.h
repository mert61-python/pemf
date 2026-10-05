/* tests/firmware_host/esps3 — ESP32-S3 GPIO yazmaç taklidi (1-G · D1.102).
 * `GPIO.out_w1ts = maske` (1 yazılan bitler HIGH) / `GPIO.out_w1tc = maske` (1 yazılan bitler LOW). Her atama aparatın
 * `pemf_gpio_yaz` kancasına SIRAYLA gider → pin seviyesi + kenar günlüğü (`s3_kosum.cpp`). Okuma yok (kaynak okumuyor). */
#ifndef PEMF_HOST_S3_GPIO_STRUCT_H
#define PEMF_HOST_S3_GPIO_STRUCT_H

#include <stdint.h>

void pemf_gpio_yaz(bool ayarla, uint32_t maske);

struct PemfGpioYazmac {
  bool ayarla;
  PemfGpioYazmac &operator=(uint32_t maske) {
    pemf_gpio_yaz(ayarla, maske);
    return *this;
  }
};

struct gpio_dev_t {
  PemfGpioYazmac out_w1ts{true};
  PemfGpioYazmac out_w1tc{false};
};
extern gpio_dev_t GPIO;

#endif /* PEMF_HOST_S3_GPIO_STRUCT_H */
