#ifndef STATUS_LED_H
#define STATUS_LED_H

#include <Arduino.h>

class StatusLED {
public:
    StatusLED(int ledPin = LED_BUILTIN);
    void begin();
    void update(bool wifiConnected, bool mqttConnected, bool pwmActive);

private:
    int _ledPin;
    unsigned long _lastBlink;
    bool _ledState;
};

#endif
