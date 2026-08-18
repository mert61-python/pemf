#ifndef STATUS_LED_H
#define STATUS_LED_H

#include <Arduino.h>

// ============================================================================
// ESP32-S3 Status LED System (RGB LED Support)
// ============================================================================
// Durum göstergesi için RGB LED veya basit LED kullanır
// RGB LED varsa renk kodlu durumlar, yoksa yanıp sönme kalıpları
// ============================================================================

// LED Durumları
enum LEDState {
    LED_IDLE,              // Sistem başlatılıyor (Mavi yavaş yanıp sönen)
    LED_WIFI_CONNECTING,   // WiFi'ye bağlanıyor (Mavi hızlı yanıp sönen)
    LED_WIFI_CONNECTED,    // WiFi bağlı (Yeşil sabit)
    LED_PORTAL_MODE,       // Portal modu (Turuncu yanıp sönen)
    LED_MQTT_CONNECTING,   // MQTT bağlanıyor (Mor yanıp sönen)
    LED_MQTT_CONNECTED,    // MQTT bağlı (Yeşil parlak)
    LED_PWM_ACTIVE,        // PWM aktif (Kırmızı yanıp sönen)
    LED_ERROR,             // Hata durumu (Kırmızı hızlı yanıp sönen)
    LED_BLUETOOTH_MODE,    // Bluetooth modu (Mavi sabit)
    LED_OFF                // LED kapalı
};

class StatusLED {
public:
    StatusLED(int ledPin, bool isRGB = false, int numPixels = 1);
    void begin();

    // Ana güncelleme fonksiyonu
    void update(bool wifiConnected, bool mqttConnected, bool pwmActive, bool portalActive = false);

    // Manuel durum ayarlama
    void setState(LEDState state);

    // LED'i kapat
    void off();

private:
    int _ledPin;
    bool _isRGB;
    int _numPixels;
    LEDState _currentState;
    LEDState _previousState;
    unsigned long _lastBlinkTime;
    bool _blinkState;
    int _blinkCount;

    // RGB LED için renk tanımları
    struct Color {
        uint8_t r, g, b;
    };

    // Durum renkleri
    Color _getColorForState(LEDState state);

    // Yanıp sönme kontrolü
    bool _shouldBlink(LEDState state);
    int _getBlinkInterval(LEDState state);

    // LED kontrol fonksiyonları
    void _setColor(Color color);
    void _setSimpleLED(bool on);
    void _processBlinking();
};

#endif
