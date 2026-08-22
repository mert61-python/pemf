#ifndef COIL_CONTROLLER_H
#define COIL_CONTROLLER_H

#include <Arduino.h>
#include "SharedDefs.h"

// Forward declaration
class TimeManager;

// Start komut parametrelerini taşıyacak struct
struct ControlCommand {
    CommandType type;
    int frequency = 0;
    int dutyCycle = 0;
    // ⚠️ BİRİM DEĞİŞTİ (2026-08-19): backend MQTT sözleşmesi `duration`ı SANİYE gönderir
    // (`servers/api_server.py::_esp_duration_seconds`, ai_router `int(dk*60)`). Eski kod bunu
    // DAKİKA okuyordu → 10 dk'lık seansın süre-bekçisi bobinde 10 SAAT oluyordu (60×).
    int durationSec = 0;
    /* 15. parti (sahip karari 2026-08-20): zamanlanmis-baslangic (start_at/sync_all) makinesi
     * KALDIRILDI (ureticisiz PyQt kalintisi; [4.6] latent kusurlari). timestamp alani struct
     * uyumu icin durur, hicbir yol doldurmaz/okumaz. */
    unsigned long long timestamp = 0;
};

class CoilController {
public:
    CoilController(int pwmPin, int coilId, TimeManager* timeManager);
    void begin();
    void update();  // Loop'ta sürekli çağrılacak

    // PWM kontrolü
    // ÖNEMLİ: PWM sadece stop() komutu veya duration timeout ile durur
    // WiFi/MQTT bağlantı durumu PWM'i ETKİLEMEZ!
    void start(int freq, int duty, int durationSec);
    void stop();

    // Command handler API
    void handleCommand(const ControlCommand& cmd);

    // Durum sorgulama
    PWMStatus getStatus();
    bool isActive();
    int getRemainingTime();  // saniye

    // EEPROM state persistence (restart sonrası devam için)
    void savePWMState();      // PWM durumunu EEPROM'a kaydet
    bool restorePWMState();   // EEPROM'dan PWM durumunu yükle (true = yüklendi)

    // populateStatus pattern için
    void populateStatus(StatusData& data);

private:
    int _pwmPin;
    int _coilId;
    bool _pwmActive;
    int _pwmFrequency;
    int _pwmDutyCycle;
    unsigned long _pwmStartTime;
    unsigned long _pwmDuration;  // ms (0 = suresiz)
    unsigned long _suresizGecenMs;  // süresiz modda önceki boot'lardan devreden geçen ms (kümülatif tavan)
    unsigned long long _pwmStartTimestamp;  // PWM başlangıç zamanı (ms, NTP sync) - TimeManager'dan alınır
    int _pwmDurationSec;      // PWM süresi (SANİYE — backend sözleşmesi, 0 = süresiz)
    // Dürüst raporlama (2026-08-19): %50 donanım tavanı isteneni sessizce kırpıyor ama status
    // İSTENEN değeri yayınlıyordu → backend gerçek çıkışı hiç göremiyordu. populateStatus artık
    // BUNU (efektif duty'yi) yayınlar; getStatus() istenen değeri korur.
    int _effectiveDutyPct = 0;
    TimeManager* _timeManager;  // TimeManager referansı

    // Utility fonksiyonlar
    unsigned long safeMillisDiff(unsigned long current, unsigned long previous);
    void _applyPWM(int freq, int duty);
    void _checkPWMDuration();
};

#endif
