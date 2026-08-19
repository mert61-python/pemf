#include "CoilController.h"
#include "TimeManager.h"
#include "SharedDefs.h"
#include <limits.h>
#include <EEPROM.h>

/* ============================================================================
 * DONANIM SYNC — Yazılımsal DDS Sabitleri
 * ============================================================================
 * STM32 Master'dan gelen 100µs RISING pulse (PB1 → GPIO 7) her PWM döngüsünün
 * başını işaret eder. Slave ISR bu anı yakalar ve s_tick_counter'ı sıfırlayarak
 * faz kilidi oluşturur.
 * ============================================================================ */
#define DDS_TIMER_FREQ_HZ     50000U                         /**< Timer kesme frekansı    */
#define DDS_PWM_DEFAULT_HZ    100U                           /**< Varsayılan PWM frekansı */
#define DDS_TICKS_PER_PERIOD  (DDS_TIMER_FREQ_HZ / DDS_PWM_DEFAULT_HZ)  /**< 500 tick   */

/* ---- ISR'dan erişilen DDS global durumu (IRAM'de tutulur) ---- */
static volatile uint32_t IRAM_ATTR s_tick_counter    = 0;
static volatile uint32_t IRAM_ATTR s_ticks_per_period = DDS_TICKS_PER_PERIOD;
static volatile uint32_t IRAM_ATTR s_duty_ticks       = 0;
static volatile bool     IRAM_ATTR s_dds_active       = false;
static volatile uint8_t  IRAM_ATTR s_pin_a            = 0;  /**< IN_A (veya tek pin)  */

#ifdef ESP32
/* ESP32-S3: Full-bridge — iki çıkış pini */
static volatile uint8_t  IRAM_ATTR s_pin_b            = 0;  /**< IN_B (negatif yön)   */
static hw_timer_t*                  s_dds_timer        = nullptr;
static portMUX_TYPE                 s_timer_mux        = portMUX_INITIALIZER_UNLOCKED;
#endif

/* ============================================================================
 * SYNC PULSE ISR — ⚠️ ESP8266'DA KULLANIM DIŞI (sahip kararı, 2026-08-19)
 * ============================================================================
 * İKİ SEBEP:
 *   1. DONANIM: Tanımlı pin GPIO7 idi — ESP8266'da GPIO6-11 FLASH SPI hattıdır; giriş+kesme
 *      bağlamak flash erişimiyle çakışıp cihazı kararsızlaştırır. Kart devreye LEHİMLİ,
 *      pin değişimi mümkün değil.
 *   2. KARAR: 8266 bobinleri TEK FAZ sürülecek — faz kilidi gereksiz. Ayrıca STM32 darbesi
 *      her STM periyodunda DDS sayacını sıfırladığından, ESP frekansı STM'den farklıyken
 *      periyot hiç tamamlanamıyor ve düşük frekansta çıkış sürekli HIGH'a (DC) yapışıyordu.
 * ESP32-S3 varyantında (ayrı klasör) donanım senkronu DURUYOR — S3'te GPIO7 serbesttir.
 * ============================================================================ */
#ifdef ESP32
static void IRAM_ATTR syncPulseISR() {
    s_tick_counter = 0;   /* DDS fazını STM32 ile hizala — mikrosaniye hassasiyetinde */
}
#endif

/* ============================================================================
 * DDS TIMER ISR — 50kHz (her 20µs bir çağrılır)
 * ============================================================================
 * Her kesmede:
 *   1. Tick sayacını artır (0 … ticks_per_period-1)
 *   2. Mevcut tick'in duty penceresi içinde olup olmadığına bak
 *   3. GPIO çıkışını güncelle (ESP32: bipolar full-bridge, ESP8266: yarım köprü)
 * ============================================================================ */
#ifdef ESP32
static void IRAM_ATTR ddsTimerISR() {
    if (!s_dds_active) return;

    portENTER_CRITICAL_ISR(&s_timer_mux);
    uint32_t tick = s_tick_counter + 1U;
    if (tick >= s_ticks_per_period) tick = 0U;
    s_tick_counter = tick;
    uint32_t duty  = s_duty_ticks;
    portEXIT_CRITICAL_ISR(&s_timer_mux);

    if (duty == 0U) {
        /* Kapalı — her iki çıkışı da LOW yap */
        GPIO.out_w1tc = (1UL << s_pin_a) | (1UL << s_pin_b);
    } else {
        bool high = (tick < duty);
        if (high) {
            /* Pozitif yarı periyot: A=HIGH, B=LOW */
            GPIO.out_w1tc = (1UL << s_pin_b);
            GPIO.out_w1ts = (1UL << s_pin_a);
        } else {
            /* Negatif yarı periyot: A=LOW, B=HIGH */
            GPIO.out_w1tc = (1UL << s_pin_a);
            GPIO.out_w1ts = (1UL << s_pin_b);
        }
    }
}
#else
/* ---- ESP8266: timer1 tabanlı DDS ISR ---- */
static void ICACHE_RAM_ATTR ddsTimerISR() {
    if (!s_dds_active) return;

    uint32_t tick = s_tick_counter + 1U;
    if (tick >= s_ticks_per_period) tick = 0U;
    s_tick_counter = tick;

    if (s_duty_ticks == 0U) {
        GPOC = (1UL << s_pin_a);  /* GPIO clear (düşük seviye) */
    } else {
        bool high = (tick < s_duty_ticks);
        if (high) {
            GPOS = (1UL << s_pin_a);  /* GPIO set */
        } else {
            GPOC = (1UL << s_pin_a);  /* GPIO clear */
        }
    }
    /* timer1 TIM_LOOP modunda otomatik tekrar eder — write gerekmez */
}
#endif

CoilController::CoilController(int pwmPin, int coilId, TimeManager* timeManager) {
    _pwmPin = pwmPin;
    _coilId = coilId;
    _pwmActive = false;
    _pwmFrequency = 1000;
    _pwmDutyCycle = 50;
    _pwmStartTime = millis();
    _pwmStartTimestamp = 0;
    _pwmDurationSec = 0;
    _effectiveDutyPct = 0;
    _timeManager = timeManager;
    _startState = PWM_START_IDLE;
    _targetTimestampMs = 0;
}

void CoilController::begin() {
#ifdef ESP32
    /* ---- ESP32-S3: Bipolar Full-Bridge (iki pin) ---- */
    s_pin_a = (uint8_t)PIN_COIL_PWM_A;
    s_pin_b = (uint8_t)PIN_COIL_PWM_B;
    pinMode(PIN_COIL_PWM_A, OUTPUT);
    pinMode(PIN_COIL_PWM_B, OUTPUT);
    digitalWrite(PIN_COIL_PWM_A, LOW);
    digitalWrite(PIN_COIL_PWM_B, LOW);

    /* Sync giriş pini — RISING kenar STM32 periyot başını işaret eder */
    pinMode(PIN_SYNC_IN, INPUT);
    attachInterrupt(digitalPinToInterrupt(PIN_SYNC_IN), syncPulseISR, RISING);
    LOG_PRINTLN(F("[SYNC] ESP32-S3 Slave: PIN_SYNC_IN hazir (GPIO7, RISING)"));

    /* DDS Timer kurulumu — 50kHz (1MHz saat / alarm=20) */
    /* Timer 0, prescaler=80 → 80MHz/80=1MHz, up-counting              */
    s_dds_timer = timerBegin(0, 80, true);
    timerAttachInterrupt(s_dds_timer, &ddsTimerISR, true);
    timerAlarmWrite(s_dds_timer, 20, true);  /* 1MHz / 20 = 50kHz, oto-tekrar */
    timerAlarmEnable(s_dds_timer);
    LOG_PRINTLN(F("[DDS] ESP32-S3: 50kHz timer baslatildi (full-bridge)"));

#else
    /* ---- ESP8266: Yarım-köprü (tek pin) ---- */
    s_pin_a = (uint8_t)_pwmPin;
    pinMode(_pwmPin, OUTPUT);
    digitalWrite(_pwmPin, LOW);

    /* ⚠️ SYNC GİRİŞİ BİLEREK YOK (2026-08-19): eski kod burada GPIO7'ye (FLASH SPI hattı!)
     * pinMode+attachInterrupt bağlıyordu. 8266 tek faz sürülecek; gerekçe dosya başındaki
     * SYNC PULSE ISR blok yorumunda. Donanımda sync hattı bağlıysa bile bu pine DOKUNULMAZ. */
    LOG_PRINTLN(F("[SYNC] ESP8266: donanim senkronu KULLANILMIYOR (tek faz karari)"));

    /* timer1 kurulumu — TIM_DIV16: 80MHz/16=5MHz, 5MHz/100ticks=50kHz */
    timer1_enable(TIM_DIV16, TIM_EDGE, TIM_LOOP);
    timer1_attachInterrupt(ddsTimerISR);
    timer1_write(100);  /* 5MHz / 50000Hz = 100 tick = 20µs periyot */
    LOG_PRINTLN(F("[DDS] ESP8266: 50kHz timer1 baslatildi (half-bridge)"));
#endif
}

void CoilController::update() {
    // Not: Sync wait kontrolu Main.ino'dan checkSyncWait() ile yapiliyor
    // Burada sadece PWM sure kontrolu yapiliyor

    _checkPWMDuration();

    // Periyodik EEPROM guncellemesi (her 30 saniyede bir)
    // Restart olursa kalan süreyi doğru yükleyebilmek için
    if (_pwmActive) {
        static unsigned long lastEEPROMSave = 0;
        if (safeMillisDiff(millis(), lastEEPROMSave) >= 30000) {  // 30 saniye
            savePWMState();
            lastEEPROMSave = millis();
        }
    }
}

void CoilController::handleCommand(const ControlCommand& cmd) {
    switch (cmd.type) {
        case CMD_START:
            start(cmd.frequency, cmd.dutyCycle, cmd.durationSec, cmd.timestamp);
            break;
        case CMD_STOP:
            stop();
            break;
        case CMD_UPDATE_PARAMS:
            setParams(cmd.frequency, cmd.dutyCycle, cmd.durationSec);
            break;
        case CMD_SYNC_ALL:
            if (_pwmActive) {
                stop();
                start(_pwmFrequency, _pwmDutyCycle, _pwmDurationSec, cmd.timestamp);
            } else {
                _syncFallbackEvent = true;
            }
            break;
        default:
            break;
    }
}

bool CoilController::consumeSyncFallbackEvent() {
    if (_syncFallbackEvent) {
        _syncFallbackEvent = false;
        return true;
    }
    return false;
}

void CoilController::start(int freq, int duty, int durationSec, unsigned long long targetTimestampMs) {
    _pwmFrequency = constrain(freq, 1, 1000);  // 1Hz - 1kHz
    _pwmDutyCycle = constrain(duty, 1, 99);     // 1% - 99% (tutarlilik icin setParams() ile ayni)
    /* SANIYE -> ms (backend sozlesmesi: _esp_duration_seconds; 0 = suresiz nobetcisi) */
    _pwmDuration = (unsigned long)durationSec * 1000UL;
    _pwmDurationSec = durationSec;

    // EÄŸer targetTimestampMs verilmiÅŸse, non-blocking bekleme state'ine geÃ§
    if (targetTimestampMs > 0) {
        _targetTimestampMs = targetTimestampMs;
        _startState = PWM_START_WAITING;
        LOG_PRINT(F("[PWM] start_at bekleniyor: "));
        LOG_PRINTLN((unsigned long)(targetTimestampMs / 1000));
        // âœ… Ã–NEMLÄ°: _pwmStartTime burada set edilmez!
        // PWM henÃ¼z baÅŸlamadÄ±, duration hesaplamasÄ± iÃ§in gerÃ§ek baÅŸlangÄ±Ã§ zamanÄ± gerekli.
        // _pwmStartTime sadece PWM gerÃ§ekten baÅŸladÄ±ÄŸÄ±nda (checkSyncWait() iÃ§inde) set edilecek.
        return;  // PWM henÃ¼z baÅŸlatÄ±lmadÄ±, checkSyncWait() iÃ§inde baÅŸlatÄ±lacak
    }

    // Hemen baÅŸlat (targetTimestampMs yok)
    _startState = PWM_START_IDLE;
    _applyPWM(_pwmFrequency, _pwmDutyCycle);
    _pwmActive = true;
    // - Sadece PWM gercekten basladiginda _pwmStartTime set edilir
    _pwmStartTime = millis();

    // TimeManager'dan şu anki timestamp'i al
    if (_timeManager) {
        _pwmStartTimestamp = _timeManager->getCurrentTimeMs();
    } else {
        _pwmStartTimestamp = 0;
    }

    // PWM başlatıldı, EEPROM'a kaydet
    savePWMState();
}

void CoilController::stop() {
    /* DDS çıkışını kapat — ISR hâlâ çalışıyor ama duty=0 → LOW çıkış */
#ifdef ESP32
    portENTER_CRITICAL(&s_timer_mux);
    s_dds_active = false;
    s_duty_ticks = 0U;
    portEXIT_CRITICAL(&s_timer_mux);
    /* GPIO'yu güvenli LOW konumuna al */
    digitalWrite(PIN_COIL_PWM_A, LOW);
    digitalWrite(PIN_COIL_PWM_B, LOW);
#else
    noInterrupts();
    s_dds_active = false;
    s_duty_ticks = 0U;
    interrupts();
    digitalWrite(_pwmPin, LOW);
#endif

    _pwmActive = false;
    _startState = PWM_START_IDLE;
    _targetTimestampMs = 0;

    /* PWM durduruldu, EEPROM'u temizle */
    savePWMState();
}

void CoilController::setParams(int freq, int duty, int durationSec) {
    _pwmFrequency = constrain(freq, 1, 1000);
    _pwmDutyCycle = constrain(duty, 1, 99);
    _pwmDuration = (unsigned long)durationSec * 1000UL;  /* SANIYE (backend sozlesmesi) */
    _pwmDurationSec = durationSec;

    // EÄŸer PWM aktifse, yeni parametrelerle gÃ¼ncelle
    if (_pwmActive) {
        _applyPWM(_pwmFrequency, _pwmDutyCycle);
    }
}

PWMStatus CoilController::getStatus() {
    PWMStatus status;
    status.active = _pwmActive;
    status.frequency = _pwmFrequency;
    status.dutyCycle = _pwmDutyCycle;

    if (_pwmActive && _pwmDuration > 0) {
        unsigned long elapsed = safeMillisDiff(millis(), _pwmStartTime);
        status.remainingTime = (_pwmDuration > elapsed) ? (_pwmDuration - elapsed) : 0;
    } else {
        status.remainingTime = 0;
    }

    return status;
}

bool CoilController::isActive() {
    return _pwmActive;
}

bool CoilController::isWaiting() {
    return _startState == PWM_START_WAITING;
}

int CoilController::getRemainingTime() {
    if (_pwmActive && _pwmDuration > 0) {
        unsigned long elapsed = safeMillisDiff(millis(), _pwmStartTime);
        unsigned long remaining = (_pwmDuration > elapsed) ? (_pwmDuration - elapsed) : 0;
        return remaining / 1000;  // saniye cinsinden
    }
    return 0;
}

void CoilController::populateStatus(StatusData& data) {
    data.pwm_active = _pwmActive;
    data.pwm_frequency = _pwmFrequency;
    /* DURUST RAPOR (2026-08-19): %50 donanim tavani isteneni kirpar; backend'e GERCEK cikis
     * gitsin. Istenen deger getStatus()'ta durur (set_params'in temeli). */
    data.pwm_duty_cycle = _pwmActive ? _effectiveDutyPct : _pwmDutyCycle;
    data.pwm_start_timestamp = _pwmStartTimestamp;
    data.pwm_duration = _pwmDurationSec;  /* SANIYE (backend sozlesmesi) */

    if (_pwmActive && _pwmDuration > 0) {
        unsigned long elapsed = safeMillisDiff(millis(), _pwmStartTime);
        data.pwm_remaining_time = (_pwmDuration > elapsed) ? (_pwmDuration - elapsed) : 0;
    } else {
        data.pwm_remaining_time = 0;
    }
}

unsigned long CoilController::safeMillisDiff(unsigned long current, unsigned long previous) {
    // millis() overflow durumunda doÄŸru farkÄ± hesapla
    if (current >= previous) {
        return current - previous;
    } else {
        // Overflow olmuÅŸ
        return (ULONG_MAX - previous) + current + 1;
    }
}

void CoilController::_applyPWM(int freq, int duty) {
    /* Frekans → ticks_per_period dönüşümü
     * DDS timer sabit 50kHz çalışır; PWM frekansı değişince sadece
     * periyot uzunluğu (tick sayısı) değişir.                        */
    int clampedFreq = constrain(freq, 1, 1000);
    uint32_t tpp = (uint32_t)(DDS_TIMER_FREQ_HZ / (uint32_t)clampedFreq);
    if (tpp < 4U) tpp = 4U;

    /* Duty → tick dönüşümü (%50 üzeri kısıtlanır — güvenlik limiti) */
    uint32_t duty_t = (uint32_t)(((float)duty / 100.0f) * (float)tpp);
    if (duty_t >= (tpp / 2U)) duty_t = (tpp / 2U) - 1U;  /* Maks %50 */

    /* ⚠️ EFEKTİF DUTY (2026-08-19 düzeltme): %50 tavanı + tick yuvarlaması sonrası GERÇEK
     * çıkış oranı. Bu satır ÖNCE S3'e eklenmiş, 8266'ya EKLENMEMİŞTİ (regresyon) —
     * populateStatus aktifken _effectiveDutyPct'i raporluyor, hiç güncellenmeyince duty=0
     * gidiyor ve backend gerçek çıkışı sıfır sanıyordu (donanım-uyum analizi D-2 yakaladı). */
    _effectiveDutyPct = (int)(((float)duty_t * 100.0f) / (float)tpp + 0.5f);

    /* ISR ile çakışmayı önlemek için atomik güncelleme */
#ifdef ESP32
    portENTER_CRITICAL(&s_timer_mux);
    s_ticks_per_period = tpp;
    s_duty_ticks       = duty_t;
    s_dds_active       = true;
    portEXIT_CRITICAL(&s_timer_mux);
#else
    noInterrupts();
    s_ticks_per_period = tpp;
    s_duty_ticks       = duty_t;
    s_dds_active       = true;
    interrupts();
#endif

    LOG_PRINTF("[DDS] _applyPWM: %dHz, %d%% → tpp=%lu, duty_ticks=%lu\n",
               clampedFreq, duty, (unsigned long)tpp, (unsigned long)duty_t);
}

void CoilController::_checkPWMDuration() {
    // PWM sadece sure doldugunda veya stop() komutu geldiginde durdurulur
    // Baglanti durumu (WiFi/MQTT) PWM'i ASLA ETKİLEMEZ!
    if (_pwmActive && _pwmDuration > 0) {
        if (safeMillisDiff(millis(), _pwmStartTime) >= _pwmDuration) {
            LOG_PRINTLN(F("[PWM] Sure doldu, PWM durduruldu"));
            stop();  // stop() içinde EEPROM'a kaydedilir
        }
    }
    /* HG-5/6 (2026-08-19, Plan A-1): SÜRESİZ-MOD (duration=0) MUTLAK TAVANI — S3 ile aynı.
     * Zamana bağlı, ağa DEĞİL → "PWM ağ-bağımsız" değişmezini ihlal etmez; süreli seanslar
     * etkilenmez. STOP kaybı/failover senaryosunda sonsuz çalışmayı keser (2 saat). */
    else if (_pwmActive && _pwmDuration == 0 &&
             safeMillisDiff(millis(), _pwmStartTime) >= (SURESIZ_TAVAN_SEC * 1000UL)) {
        LOG_PRINTLN(F("[PWM] SURESIZ-mod mutlak tavani doldu, PWM durduruldu (guvenlik)"));
        stop();
    }
}

void CoilController::checkSyncWait(unsigned long long currentTimeMs) {
    if (_startState != PWM_START_WAITING) {
        return;  // Bekleme state'inde deÄŸil
    }

    if (currentTimeMs == 0) {
        return;  // Zaman senkronize edilmemiÅŸ
    }

    long waitMs = (long)(_targetTimestampMs - currentTimeMs);

    if (waitMs <= 0) {
        // Bekleme sÃ¼resi doldu veya geÃ§miÅŸte kaldÄ±, PWM'i baÅŸlat
        if (waitMs < -1000) {  // 1 saniyeden fazla geÃ§miÅŸte
            LOG_PRINTLN(F("[PWM][SYNC] HATA: Hedef zaman gecmiste kaldi! Hemen baslatiliyor."));
        } else {
            LOG_PRINTLN(F("[PWM][SYNC] Bekleme tamamlandi, PWM baslatiliyor"));
        }

        _startState = PWM_START_IDLE;  // âœ… State'i IDLE'a dÃ¶ndÃ¼r (READY yerine)
        _applyPWM(_pwmFrequency, _pwmDutyCycle);
        _pwmActive = true;
        // - ONEMLI: _pwmStartTime sadece burada set edilir (PWM gercekten basladiginda)
        // Bu sayede duration hesaplamalari dogru calisir.
        _pwmStartTime = millis();
        _pwmStartTimestamp = currentTimeMs;  // Timestamp'i kaydet
        _targetTimestampMs = 0;  // Temizle

        // PWM başlatıldı, EEPROM'a kaydet
        savePWMState();
    } else if (waitMs > 10000) {
        // Bekleme sÃ¼resi Ã§ok uzun (>10s), hemen baÅŸlat
        LOG_PRINTLN(F("[PWM][SYNC] UYARI: Bekleme suresi cok uzun (>10s), hemen baslatiliyor."));

        // ✅ PWM zaten aktifse başlatma
        if (!_pwmActive) {
            _startState = PWM_START_IDLE;  // ✅ State'i IDLE'a döndür
            _applyPWM(_pwmFrequency, _pwmDutyCycle);
            _pwmActive = true;
            // - ONEMLI: _pwmStartTime sadece burada set edilir (PWM gercekten basladiginda)
            _pwmStartTime = millis();
            _pwmStartTimestamp = currentTimeMs;  // Timestamp'i kaydet
            _targetTimestampMs = 0;

            // PWM başlatıldı, EEPROM'a kaydet
            savePWMState();
        } else {
            // PWM zaten aktif, sadece state'i temizle
            _startState = PWM_START_IDLE;
            _targetTimestampMs = 0;
        };
    } else {
        // Hala bekleniyor, her ÅŸey normal
        // LOG_PRINT(F("[PWM][SYNC] Bekleniyor: "));
        // LOG_PRINT(waitMs);
        // LOG_PRINTLN(F(" ms kaldÄ±"));
    }
}

// ============================================================================
// EEPROM State Persistence (Restart sonrası PWM devam için)
// ============================================================================

void CoilController::savePWMState() {
    PWMStateEEPROM state;

    state.magic = 0xAB;  // Valid data marker
    state.active = _pwmActive;
    state.frequency = _pwmFrequency;
    state.dutyCycle = _pwmDutyCycle;
    state.duration = _pwmDuration;

    // Geçen süreyi hesapla
    if (_pwmActive && _pwmDuration > 0) {
        state.elapsed = safeMillisDiff(millis(), _pwmStartTime);
    } else {
        state.elapsed = 0;
    }

    // Checksum hesapla (basit XOR)
    state.checksum = state.magic ^ state.active ^ state.frequency ^
                     state.dutyCycle ^ (state.duration & 0xFF) ^
                     (state.elapsed & 0xFF);

    // EEPROM'a yaz
    EEPROM.put(EEPROM_PWM_STATE_ADDR, state);
    EEPROM.commit();

    LOG_PRINTLN(F("[PWM] Durum EEPROM'a kaydedildi"));
}

bool CoilController::restorePWMState() {
    PWMStateEEPROM state;

    // EEPROM'dan oku
    EEPROM.get(EEPROM_PWM_STATE_ADDR, state);

    // Magic number kontrolü
    if (state.magic != 0xAB) {
        LOG_PRINTLN(F("[PWM] EEPROM'da kayitli durum bulunamadi"));
        return false;
    }

    // Checksum kontrolü
    uint8_t calculated_checksum = state.magic ^ state.active ^ state.frequency ^
                                   state.dutyCycle ^ (state.duration & 0xFF) ^
                                   (state.elapsed & 0xFF);

    if (calculated_checksum != state.checksum) {
        LOG_PRINTLN(F("[PWM] EEPROM checksum hatasi, durum yuklenmedi"));
        return false;
    }

    // PWM aktif değilse yükleme yapma
    if (!state.active) {
        LOG_PRINTLN(F("[PWM] EEPROM'da PWM aktif degil"));
        return false;
    }

    // Kalan süreyi hesapla
    unsigned long remaining = 0;
    if (state.duration > 0) {
        if (state.elapsed < state.duration) {
            remaining = state.duration - state.elapsed;
        } else {
            // Süre dolmuş
            LOG_PRINTLN(F("[PWM] EEPROM'daki PWM suresi dolmus"));
            return false;
        }
    }

    // PWM'i geri yükle
    _pwmFrequency = state.frequency;
    _pwmDutyCycle = state.dutyCycle;
    _pwmDuration = remaining;  // Kalan süreyi kullan

    // PWM'i başlat
    _applyPWM(_pwmFrequency, _pwmDutyCycle);
    _pwmActive = true;
    _pwmStartTime = millis();  // Yeni başlangıç zamanı

    if (remaining > 0) {
        LOG_PRINTF("[PWM] EEPROM'dan yuklendi ve kaldigi yerden devam ediyor: %dHz, %d%%, %lums kaldi\n",
                   _pwmFrequency, _pwmDutyCycle, remaining);
    } else {
        LOG_PRINTF("[PWM] EEPROM'dan yuklendi ve suresiz devam ediyor: %dHz, %d%%\n",
                   _pwmFrequency, _pwmDutyCycle);
    }

    return true;
}
