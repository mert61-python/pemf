#ifndef COIL_CONTROLLER_H
#define COIL_CONTROLLER_H

#include <Arduino.h>
#include "SharedDefs.h"
#include <Preferences.h>

// Forward declaration
class SensorManager;

// ============================================================================
// ENDÜSTRİYEL DÖNÜŞÜM: Dual-Core ve ledc API
// ============================================================================
// Bu sınıf Core 1 üzerinde çalışacak Task tarafından kullanılır.
// PWM üretimi için ESP32'nin donanımsal LEDC (PWM) çevre birimini kullanır.
// ============================================================================

class CoilController {
public:
    CoilController(SensorManager* sensors);
    void begin();
    
    // Core 1 Task Loop içinde çağrılır
    void process();

    // Command Queue işleme
    void handleCommand(const ControlCommand& cmd);

    // Durum getirme
    PWMState getState();

    // NVS Persistence
    void loadState();
    void saveState();

private:
    // SensorManager referansı (PWM durum bildirimi için)
    SensorManager* _sensors;
    
    // PWM Parametreleri
    bool _active;
    int _frequency;
    int _dutyCycle;
    unsigned long _startTime;
    unsigned long _duration;     // ms
    unsigned long _endTime;      // Bitiş zamanı (millis)
    bool _hasDuration;           // Süreli mi?
    int _durationMinutes;        // Toplam süre (dakika)
    unsigned long long _startTimestamp; // Başlangıç zamanı (Unix timestamp ms)

    // Sync Başlangıç
    unsigned long long _syncTargetTime;
    bool _waitingForSync;

    // Preferences (NVS)
    Preferences _prefs;

    // Hardware Functions
    void _setupMCPWM();
    void _updatePWM(int freq, int duty);
    void _stopPWM();
};

#endif

