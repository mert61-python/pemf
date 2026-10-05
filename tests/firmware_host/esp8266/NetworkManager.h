/* tests/firmware_host/esp8266 — `NetworkManager` YERİNE GEÇEN taklit (aparat gerçek kaynağın yanına koyar; gerçek
 * NetworkManager.h WiFi/MQTT/portal kütüphanelerini çeker). SensorManager yalnız `publishEvent`'i, `processControlCommand`
 * (komut aparatı) ayrıca ACK / WiFi silme / MQTT durumunu kullanır. Tanımlar ilgili koşum dosyasındadır.
 * ⚠️ Gerçek NetworkManager.cpp ve Secrets.h DERLENMEZ. */
#ifndef PEMF_HOST_NETWORK_MANAGER_H
#define PEMF_HOST_NETWORK_MANAGER_H

#include <Arduino.h>

class NetworkManager {
 public:
  void publishEvent(const char *tur, const char *mesaj);
  void sendCommandAck(const char *command_id, bool success);
  void clearAllWiFiCredentials();
  bool isMqttConnected();
};

#endif /* PEMF_HOST_NETWORK_MANAGER_H */
