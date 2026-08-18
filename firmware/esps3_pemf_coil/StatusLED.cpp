#include "StatusLED.h"
#include "SharedDefs.h"

StatusLED::StatusLED(int ledPin, bool isRGB, int numPixels) {
    _ledPin = ledPin;
    _isRGB = isRGB;
    _numPixels = numPixels;
    _currentState = LED_IDLE;
    _previousState = LED_OFF;
    _lastBlinkTime = 0;
    _blinkState = false;
    _blinkCount = 0;
}

void StatusLED::begin() {
    if (_isRGB) {
        // RGB LED için konfigürasyon (WS2812/Neopixel)
        // ESP32-S3'te RMT veya SPI kullanılabilir
        // Burada basit PWM kullanacağız (3 pin - R, G, B)
        // Gerçek RGB LED için Adafruit_NeoPixel kütüphanesi gerekir
        LOG_PRINTLN("[StatusLED] RGB LED mode - Using simple LED fallback");
        pinMode(_ledPin, OUTPUT);
        digitalWrite(_ledPin, LOW);
    } else {
        // Basit LED konfigürasyonu
        pinMode(_ledPin, OUTPUT);
        digitalWrite(_ledPin, LOW);
        LOG_PRINTLN("[StatusLED] Simple LED mode initialized");
    }

    // Başlangıç animasyonu - 3 kez yanıp sön
    for (int i = 0; i < 3; i++) {
        _setSimpleLED(true);
        delay(100);
        _setSimpleLED(false);
        delay(100);
    }
}

void StatusLED::update(bool wifiConnected, bool mqttConnected, bool pwmActive, bool portalActive) {
    // Öncelik sırasına göre durum belirleme
    LEDState newState;

    if (portalActive) {
        // Portal modu en yüksek öncelik
        newState = LED_PORTAL_MODE;
    }
    else if (pwmActive) {
        // PWM aktifse göster
        newState = LED_PWM_ACTIVE;
    }
    else if (mqttConnected) {
        // MQTT bağlı - her şey normal
        newState = LED_MQTT_CONNECTED;
    }
    else if (wifiConnected) {
        // WiFi bağlı ama MQTT bağlanamıyor
        newState = LED_MQTT_CONNECTING;
    }
    else {
        // WiFi bağlı değil
        newState = LED_WIFI_CONNECTING;
    }

    // Durum değişti mi?
    if (newState != _currentState) {
        _currentState = newState;
        _lastBlinkTime = millis();
        _blinkState = false;
        _blinkCount = 0;

        // Durum değişikliğini logla (spam önlemek için sadece değişim anında)
        if (_previousState != _currentState) {
            LOG_PRINTF("[StatusLED] State changed to: %d\n", _currentState);
            _previousState = _currentState;
        }
    }

    // Yanıp sönme işlemini yap
    _processBlinking();
}

void StatusLED::setState(LEDState state) {
    _currentState = state;
    _lastBlinkTime = millis();
    _blinkState = false;
    _blinkCount = 0;
}

void StatusLED::off() {
    _currentState = LED_OFF;
    _setSimpleLED(false);
}

StatusLED::Color StatusLED::_getColorForState(LEDState state) {
    Color color;

    switch (state) {
        case LED_IDLE:
            color = {0, 0, 50};  // Mavi (düşük)
            break;
        case LED_WIFI_CONNECTING:
            color = {0, 0, 100}; // Mavi
            break;
        case LED_WIFI_CONNECTED:
            color = {0, 100, 0}; // Yeşil
            break;
        case LED_PORTAL_MODE:
            color = {100, 50, 0}; // Turuncu
            break;
        case LED_MQTT_CONNECTING:
            color = {50, 0, 100}; // Mor
            break;
        case LED_MQTT_CONNECTED:
            color = {0, 150, 0}; // Yeşil parlak
            break;
        case LED_PWM_ACTIVE:
            color = {100, 0, 0}; // Kırmızı
            break;
        case LED_ERROR:
            color = {200, 0, 0}; // Kırmızı parlak
            break;
        case LED_BLUETOOTH_MODE:
            color = {0, 0, 200}; // Mavi parlak
            break;
        default:
            color = {0, 0, 0};   // Kapalı
            break;
    }

    return color;
}

bool StatusLED::_shouldBlink(LEDState state) {
    // Hangi durumlar yanıp sönmeli?
    switch (state) {
        case LED_IDLE:
        case LED_WIFI_CONNECTING:
        case LED_PORTAL_MODE:
        case LED_MQTT_CONNECTING:
        case LED_PWM_ACTIVE:
        case LED_ERROR:
            return true;
        default:
            return false;
    }
}

int StatusLED::_getBlinkInterval(LEDState state) {
    // Her durum için yanıp sönme hızı (ms)
    switch (state) {
        case LED_IDLE:
            return 2000; // Yavaş (2 saniye)
        case LED_WIFI_CONNECTING:
            return 500;  // Orta hız
        case LED_PORTAL_MODE:
            return 750;  // Orta-yavaş
        case LED_MQTT_CONNECTING:
            return 600;  // Orta hız
        case LED_PWM_ACTIVE:
            return 1000; // Yavaş yanıp sönme (PWM aktif)
        case LED_ERROR:
            return 200;  // Hızlı yanıp sönme (hata)
        default:
            return 1000;
    }
}

void StatusLED::_setColor(Color color) {
    // RGB LED kontrolü (gelecekte Adafruit_NeoPixel ile genişletilebilir)
    // Şimdilik basit LED'i kullan
    bool shouldBeOn = (color.r > 0 || color.g > 0 || color.b > 0);
    _setSimpleLED(shouldBeOn);
}

void StatusLED::_setSimpleLED(bool on) {
    digitalWrite(_ledPin, on ? HIGH : LOW);
}

void StatusLED::_processBlinking() {
    unsigned long currentTime = millis();

    if (_shouldBlink(_currentState)) {
        int interval = _getBlinkInterval(_currentState);

        // Yanıp sönme zamanı geldi mi?
        if (currentTime - _lastBlinkTime >= interval) {
            _blinkState = !_blinkState;
            _lastBlinkTime = currentTime;
            _blinkCount++;

            if (_blinkState) {
                Color color = _getColorForState(_currentState);
                _setColor(color);
            } else {
                _setSimpleLED(false);
            }
        }
    } else {
        // Sabit ışık - yanıp sönme yok
        Color color = _getColorForState(_currentState);
        _setColor(color);
    }
}
