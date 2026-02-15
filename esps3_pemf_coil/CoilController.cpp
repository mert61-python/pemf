#include "CoilController.h"
#include "SensorManager.h"
#include "driver/mcpwm.h"
#include "soc/mcpwm_reg.h"
#include "soc/mcpwm_struct.h"

// ESP32-S3 Endüstriyel MCPWM Kullanımı
// Motor Control PWM (MCPWM) donanımı kullanılarak yüksek hassasiyetli ve korumalı PWM üretimi.

CoilController::CoilController(SensorManager* sensors) : _sensors(sensors) {
    _active = false;
    _frequency = 100;
    _dutyCycle = 50;
    _hasDuration = false;
    _waitingForSync = false;
    _syncTargetTime = 0;
    _durationMinutes = 0;
    _startTimestamp = 0;
}

void CoilController::begin() {
    LOG_PRINTLN("[Core 1] CoilController başlatılıyor...");
    
    // NVS Load
    loadState();
    
    // Hardware Init
    _setupMCPWM();
    
    // Eğer state restore edildi ve aktifse, PWM'i tekrar başlat
    if (_active) {
        LOG_PRINTF("[Core 1] Önceki durum geri yüklendi: %d Hz, %d%%\n", _frequency, _dutyCycle);
        _updatePWM(_frequency, _dutyCycle);
    }
}

void CoilController::process() {
    // 1. Sync Wait Kontrolü (Eğer senkron başlangıç bekleniyorsa)
    if (_waitingForSync) {
        // NTP Senkronizasyonunu kontrol et
        struct timeval tv;
        gettimeofday(&tv, NULL);
        unsigned long long currentMs = (unsigned long long)tv.tv_sec * 1000ULL + (unsigned long long)tv.tv_usec / 1000ULL;
        
        // Eger NTP henuz set olmadıysa (yil 1970 ise), 
        // manuel olarak millis bazli fallback yap ya da bekle.
        // GUI su anda 'hedef zaman' olarak sistem saatini gonderiyor.
        // HATA DUZELTME: ESP internete bagli degilse veya NTP almadıysa 1970'te kalir ve asla baslamaz.
        // Bu yuzden eger timeSynced degilse, hemen baslatmak daha guvenli (kullanici deneyimi acisindan).
        bool timeSynced = (tv.tv_sec > 1600000000); // 2020+
        
        // Eger zaman durustse ve vakit geldiyse, YA DA zaman yanlissa (internet yoksa) bekleme yapma baslat
        if ((timeSynced && currentMs >= _syncTargetTime) || !timeSynced) {
            LOG_PRINTLN("[Core 1] SYNC TIME REACHED. Starting PWM.");
            _waitingForSync = false;
            _active = true;
            _startTime = millis();
            
            // Başlangıç timestamp'ini kaydet
            struct timeval tv;
            gettimeofday(&tv, NULL);
            _startTimestamp = (unsigned long long)tv.tv_sec * 1000ULL + (unsigned long long)tv.tv_usec / 1000ULL;
            
            // CRITICAL FIX: _endTime hesaplamasi burada yapilmali
            if (_hasDuration) {
                _endTime = _startTime + _duration;
            }
            
            _updatePWM(_frequency, _dutyCycle);
            saveState();
        }
    }

    // 2. Süre Kontrolü
    if (_active && _hasDuration) {
        if (millis() >= _endTime) {
            LOG_PRINTLN("[Core 1] Süre doldu, PWM durduruluyor.");
            _stopPWM();
            saveState();
        }
    }
}

void CoilController::handleCommand(const ControlCommand& cmd) {
    if (cmd.type == CMD_STOP) {
        _stopPWM();
        saveState();
        LOG_PRINTLN("[Core 1] Komut: STOP");
    }
    else if (cmd.type == CMD_START) {
        _frequency = cmd.frequency;
        _dutyCycle = cmd.dutyCycle;
        _durationMinutes = cmd.durationMinutes; // Dakika cinsinden kaydet
        
        if (cmd.durationMinutes > 0) {
            _hasDuration = true;
            _duration = cmd.durationMinutes * 60 * 1000UL;
            _endTime = millis() + _duration;
        } else {
            _hasDuration = false;
        }
        
        if (cmd.timestamp > 0) {
             // Sync start logic
             _syncTargetTime = cmd.timestamp; // Hedef sure
             _waitingForSync = true; 
             // sure tanimini kaydet ama baslangic zamani (startTime/endTime) 
             // sync gerceklestiginde (process() icinde) ayarlanacak.
             LOG_PRINTLN("[Core 1] Komut: SYNC START (Bekleniyor)");
        } else {
            _active = true;
            _startTime = millis();
            
            // Başlangıç timestamp'ini kaydet (Unix time ms)
            struct timeval tv;
            gettimeofday(&tv, NULL);
            _startTimestamp = (unsigned long long)tv.tv_sec * 1000ULL + (unsigned long long)tv.tv_usec / 1000ULL;
            
            if (_hasDuration) {
                 _endTime = _startTime + _duration;
            }
            _updatePWM(_frequency, _dutyCycle);
            saveState();
            LOG_PRINTF("[Core 1] Komut: START (%d Hz, %d%%)\n", _frequency, _dutyCycle);
        }
    }
    else if (cmd.type == CMD_UPDATE_PARAMS) {
        // Canlı parametre güncelleme
        _frequency = cmd.frequency;
        _dutyCycle = cmd.dutyCycle;
        if (_active) {
            _updatePWM(_frequency, _dutyCycle);
            saveState(); // Update state in NVS
            LOG_PRINTF("[Core 1] Parametre Güncellendi: %d Hz, %d%%\n", _frequency, _dutyCycle);
        }
    }
}

PWMState CoilController::getState() {
    PWMState state;
    state.active = _active;
    state.frequency = _frequency;
    state.dutyCycle = _dutyCycle;
    state.durationMinutes = _durationMinutes;
    state.startTimestamp = _startTimestamp;
    
    // Eger sync start bekliyorsak, aktif gibi gosterip surenin henuz saymadigini belli etmeliyiz
    // Veya 0 sure gondermeliyiz.
    
    if (_active && _hasDuration) {
        unsigned long now = millis();
        // Baslamis ve suresi isleyen islem
        if (_startTime > 0 && now < _endTime) {
            state.remainingTimeSec = (_endTime - now) / 1000;
        } else {
            // Suresi dolmus veya baslamamis
             state.remainingTimeSec = 0;
        }
    }
    // Bekleyen islem (Henuz pwm baslamadi ama sure ayarli)
    else if (_waitingForSync && _hasDuration) {
         // Henuz sayac baslamadi, tum sureyi dondur
         state.remainingTimeSec = _duration / 1000;
    }
    else {
        state.remainingTimeSec = 0;
    }
    
    return state;
}

void CoilController::_setupMCPWM() {
    LOG_PRINTLN("[Core 1] Configuring MCPWM...");

    // 1. GPIO Haritalama
    // MCPWM Unit 0, Pin A, Coil PWM Pini
    mcpwm_gpio_init(MCPWM_UNIT_0, MCPWM0A, PIN_COIL_PWM);

    // 2. Config Yapılandırması
    mcpwm_config_t pwm_config;
    pwm_config.frequency = _frequency;    // Frekans
    pwm_config.cmpr_a = 0;                // Başlangıç duty cycle = 0
    pwm_config.cmpr_b = 0;
    pwm_config.counter_mode = MCPWM_UP_COUNTER;
    pwm_config.duty_mode = MCPWM_DUTY_MODE_0; // Active High

    // 3. MCPWM Başlat
    mcpwm_init(MCPWM_UNIT_0, MCPWM_TIMER_0, &pwm_config);

    // 4. (Opsiyonel) Fault Handler - Endüstriyel Koruma
    // Örnek: GPIO 12 Low olduğunda PWM'i kes (Şuan aktif değil, rezerve)
    // mcpwm_fault_init(MCPWM_UNIT_0, MCPWM_HIGH_LEVEL_TGR, ...);

    // Timer'ı başlat (Gerekirse) - init zaten başlatır genellikle ama garanti olsun
    mcpwm_start(MCPWM_UNIT_0, MCPWM_TIMER_0);

    // Başlangıçta kapalı tut
    _stopPWM();
    
    LOG_PRINTLN("[Core 1] MCPWM Configured Successfully");
}

void CoilController::_updatePWM(int freq, int duty) {
    if (freq <= 0) freq = 1;
    if (duty > 100) duty = 100;
    if (duty < 0) duty = 0;

    // Frekansı güncelle
    mcpwm_set_frequency(MCPWM_UNIT_0, MCPWM_TIMER_0, freq);

    // Duty Cycle güncelle (% olarak)
    mcpwm_set_duty(MCPWM_UNIT_0, MCPWM_TIMER_0, MCPWM_OPR_A, (float)duty);
    
    // Duty tipini tekrar onayla (Gerekli olmayabilir ama güvenli)
    mcpwm_set_duty_type(MCPWM_UNIT_0, MCPWM_TIMER_0, MCPWM_OPR_A, MCPWM_DUTY_MODE_0);
    
    // PWM aktif durumunu sensörlere bildir
    if (_sensors) {
        _sensors->setPWMActive(true);
    }
}

void CoilController::_stopPWM() {
    _active = false;
    _waitingForSync = false;
    _startTimestamp = 0;
    _durationMinutes = 0;
    
    // PWM sinyalini 0'a çek veya durdur
    mcpwm_set_signal_low(MCPWM_UNIT_0, MCPWM_TIMER_0, MCPWM_OPR_A);
    
    // PWM durduğunu sensörlere bildir
    if (_sensors) {
        _sensors->setPWMActive(false);
    }
}

void CoilController::loadState() {
    _prefs.begin("pemf_state", true); // Read-only false
    _active = _prefs.getBool("active", false);
    _frequency = _prefs.getInt("freq", 100);
    _dutyCycle = _prefs.getInt("duty", 50);
    // Restart durumunda duration recovery
    bool wasDurable = _prefs.getBool("has_dur", false);
    if (wasDurable) {
        _active = false; // Süreli işlemler restartta iptal edilir (Güvenlik)
        LOG_PRINTLN("[NVS] Önceki işlem süreliydi, güvenlik için durduruldu.");
    }
    _prefs.end();
}

void CoilController::saveState() {
    _prefs.begin("pemf_state", false); // Read-write
    _prefs.putBool("active", _active);
    _prefs.putInt("freq", _frequency);
    _prefs.putInt("duty", _dutyCycle);
    _prefs.putBool("has_dur", _hasDuration);
    _prefs.end();
}
