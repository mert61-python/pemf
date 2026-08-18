#include "StatusLED.h"

StatusLED::StatusLED(int ledPin) {
    _ledPin = ledPin;
    _lastBlink = 0;
    _ledState = false;
}

void StatusLED::begin() {
    pinMode(_ledPin, OUTPUT);
    digitalWrite(_ledPin, HIGH);  // LED başlangıçta kapalı (HIGH = kapalı ESP8266'da)
}

void StatusLED::update(bool wifiConnected, bool mqttConnected, bool pwmActive) {
    unsigned long currentMillis = millis(); // Tek sefer oku (overflow kontrolü için)

    if (!wifiConnected) {
        // WiFi bağlı değil - hızlı yanıp sönsün (200ms)
        // unsigned long çıkarması overflow'u otomatik yönetir
        if (currentMillis - _lastBlink >= 200) {
            _ledState = !_ledState;
            digitalWrite(_ledPin, _ledState ? LOW : HIGH);
            _lastBlink = currentMillis;
        }
    } else if (!mqttConnected) {
        // MQTT bağlı değil - orta hızda yanıp sönsün (500ms)
        if (currentMillis - _lastBlink >= 500) {
            _ledState = !_ledState;
            digitalWrite(_ledPin, _ledState ? LOW : HIGH);
            _lastBlink = currentMillis;
        }
    } else if (pwmActive) {
        // PWM aktif - LED açık
        digitalWrite(_ledPin, LOW);
        _ledState = true;
    } else {
        // Her şey normal - LED kapalı
        digitalWrite(_ledPin, HIGH);
        _ledState = false;
    }
}
