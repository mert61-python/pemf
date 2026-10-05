/* tests/firmware_host/esp8266 — `IPAddress` taklidi (SharedDefs.h yalnız türü dahil eder). */
#ifndef PEMF_HOST_IPADDRESS_H
#define PEMF_HOST_IPADDRESS_H

#include <Arduino.h>

class IPAddress {
 public:
  IPAddress() {}
  IPAddress(uint8_t, uint8_t, uint8_t, uint8_t) {}
};

#endif /* PEMF_HOST_IPADDRESS_H */
