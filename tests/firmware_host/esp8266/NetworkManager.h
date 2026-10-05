/* tests/firmware_host/esp8266 — `NetworkManager` YERİNE GEÇEN taklit (aparat SensorManager.cpp'nin yanına koyar; gerçek
 * NetworkManager.h WiFi/MQTT/portal kütüphanelerini çeker ve SensorManager yalnız `publishEvent`'i kullanır). Olaylar
 * `sensor_kosum.cpp`'de sayılır ("E <tür> <mesaj>"). ⚠️ Gerçek NetworkManager.cpp ve Secrets.h DERLENMEZ. */
#ifndef PEMF_HOST_NETWORK_MANAGER_H
#define PEMF_HOST_NETWORK_MANAGER_H

#include <Arduino.h>

class NetworkManager {
 public:
  void publishEvent(const char *tur, const char *mesaj);
};

#endif /* PEMF_HOST_NETWORK_MANAGER_H */
