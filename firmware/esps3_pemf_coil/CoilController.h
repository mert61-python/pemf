#ifndef COIL_CONTROLLER_H
#define COIL_CONTROLLER_H

#include <Arduino.h>
#include "SharedDefs.h"
#include <Preferences.h>

// Forward declaration
class SensorManager;

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
    void forceSaveState();

    // One-shot event flag for Network task
    bool consumeSyncFallbackEvent();
    bool consumeSelfTestEvent(bool &passed);

private:
    SensorManager* _sensors;

    // PWM Parametreleri
    bool _active;
    int _frequency;
    int _dutyCycle;
    int _phase;              // [YENİ — Sorun 3/4] 0-359 derece
    unsigned long _startTime;
    unsigned long _duration;
    unsigned long _endTime;
    bool _hasDuration;
    int _durationMinutes;
    unsigned long long _startTimestamp;

    // Sync Başlangıç
    unsigned long long _syncTargetTime;
    bool _waitingForSync;

    // Preferences (NVS)
    Preferences _prefs;
    unsigned long _lastSaveTimeMs;

    bool _syncFallbackPendingEvent;

    // Self-test
    bool _isSelfTesting;
    unsigned long _selfTestStartTime;
    bool _selfTestPassed;
    bool _selfTestCompletedPendingEvent;

    // Hardware Functions
    void _setupTimerISR();

    // [Sorun 4 FIX] phase_deg parametresi eklendi (varsayılan 0)
    // _updatePWM çağrıldığında target_phase_ticks de güncellenir.
    void _updatePWM(int freq, int duty, int phase_deg = 0);

    void _stopPWM();
    void _writeStateToNvs();
};

#endif
