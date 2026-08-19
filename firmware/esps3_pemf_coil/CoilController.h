#ifndef COIL_CONTROLLER_H
#define COIL_CONTROLLER_H

#include <Arduino.h>
#include "SharedDefs.h"
#include <Preferences.h>

// Forward declaration
class SensorManager;

/* ⚠️ 2026-08-19: .cpp KAYIPTI (8266 kopyasıyla ezilmişti) ve bu başlığa karşı
 * YENİDEN YAZILDI — ayrıntı CoilController.cpp baş yorumunda. Bu turda eklenenler:
 *   · handleCommand artık bool döner (RED = ACK'ta success=false; eski .ino her
 *     komuta koşulsuz success basıyordu)
 *   · yerel termal koruma API'si (enforceThermalLimit/isThermalLocked/…)
 *   · süre birimi SANİYE (backend sözleşmesi), alan adları buna göre
 *   · senkron tanılaması (syncIgnoredCount — frekans uyuşmazlığı görünür olsun) */
class CoilController {
public:
    CoilController(SensorManager* sensors);
    void begin();

    // Core 1 Task Loop içinde çağrılır
    void process();

    // Komut işleme — false = reddedildi (termal kilit / geçersiz durum)
    bool handleCommand(const ControlCommand& cmd);

    // Yerel termal koruma (Core 1 döngüsü readAll sonucunu geçirir; çift I2C olmasın)
    void enforceThermalLimit(const SensorReadings& r);
    bool isThermalLocked();
    bool consumeThermalStopEvent();

    // Durum getirme
    PWMState getState();

    // NVS Persistence
    void loadState();
    void saveState();
    void forceSaveState();

    // One-shot event flag for Network task
    bool consumeSyncFallbackEvent();
    bool consumeSelfTestEvent(bool &passed);

    // Senkron tanılama: periyot sınırı dışında gelip YOK SAYILAN darbe sayısı.
    // Büyüyorsa STM ile frekans uyuşmazlığı var demektir (status ile yayınlanır).
    uint32_t syncIgnoredCount();

    // HG-3 (2026-08-19): DC-yapışma koruması tetiklendi mi — STM freq ESP'den çok yüksek olunca
    // sync DEVRE DIŞI bırakıldı (8266 gibi tek faz). true = faz senkronu frekans uyumsuzluğu
    // yüzünden kapalı; operatöre "faz kilidi yok" bildirilmeli (status ile yayınlanır).
    bool syncDisabled();

private:
    SensorManager* _sensors;

    // PWM Parametreleri
    bool _active;
    int _frequency;
    int _dutyCycle;              // İSTENEN duty (%1..MAX_DUTY_CYCLE)
    int _phase;                  // 0-359 derece (STM senkron t=0'ına göre)
    unsigned long _startTime;    // millis
    unsigned long _duration;     // ms (0 = süresiz)
    unsigned long _suresizGecenMs; // süresiz modda önceki boot'lardan devreden geçen ms (kümülatif tavan)
    bool _hasDuration;
    int _durationSec;            // SANİYE — backend sözleşmesi (0 = süresiz)
    unsigned long long _startTimestamp;  // epoch ms (NTP)
    int _effectiveDutyPct;       // ölü-zaman + tick yuvarlaması sonrası GERÇEK çıkış

    // Sync Başlangıç (backend bugün start_at göndermiyor — ileriye dönük)
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

    // Yerel termal koruma
    bool _thermalLock;
    bool _thermalStopPendingEvent;

    // Hardware Functions
    void _setupTimerISR();
    void _updatePWM(int freq, int duty, int phase_deg = 0);
    void _stopPWM();
    void _beginOutput(unsigned long long epochMs);
    void _writeStateToNvs(const void* data);
};

#endif
