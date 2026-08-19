/* ============================================================================
 * CoilController — ESP32-S3 Full-Bridge Bipolar DDS (YENİDEN YAZIM, 2026-08-19)
 * ============================================================================
 * ⚠️ NEDEN YENİDEN YAZILDI: Orijinal S3 gerçeklemesi KAYIP — masaüstü kopyada bu
 * dosya bir noktada 8266 sürümüyle ezilmiş (iki dosya bayt-bayt aynıydı, mtime
 * aynı gün; makine genelinde ve git geçmişinde S3-imzalı kopya YOK). Bu dosya,
 * hayatta kalan üç sözleşmeye karşı yeniden yazıldı:
 *   · CoilController.h  — sınıf API'si (ctor(SensorManager*), process, getState,
 *     NVS kalıcılık, _updatePWM(freq, duty, phase_deg), self-test olayları)
 *   · SharedDefs.h      — MAX_DUTY_CYCLE 50, DEAD_TIME_TICKS 2, PWMState/ControlCommand,
 *     FIRMWARE_VERSION "Full Bridge Bipolar — HW Phase Sync"
 *   · esps3_pemf_coil.ino — Core-1 çağrı düzeni (begin → process → handleCommand)
 *
 * DALGA BİÇİMİ (sabitlerden geri çıkarılan tasarım — TEZGÂHTA SKOPLA DOĞRULA):
 *   Periyot iki yarıya bölünür; SİMETRİK BİPOLAR sürüş:
 *     [0 ............ duty)                → A=HIGH (pozitif darbe)
 *     [yarım ........ yarım+duty)          → B=HIGH (negatif darbe, aynada)
 *     aralar                               → her iki çıkış LOW
 *   duty her yarımın İÇİNDEN sayılır; MAX_DUTY_CYCLE=50 → darbe kendi yarısını
 *   taşamaz; DEAD_TIME_TICKS kadar boşluk zorlanır → H-köprüde SHOOT-THROUGH
 *   (üst+alt anahtar aynı anda iletimde) imkânsızlaşır. Ortalama DC bileşen 0.
 *
 * FAZ: backend AI Pro bobin 6-7'ye derece cinsinden `phase` gönderir (ölçüldü:
 *   servers/ai_router.py:770 "phase": normalize_phase_deg). Faz, tüm desenin
 *   STM32 senkron darbesine (t=0) göre kaydırılmasıdır: phase_ticks = deg/360·tpp.
 *
 * SENKRON: STM32 PB1 → GPIO7 RISING, her STM periyot başında (firmware/stm32_pemf/Core/Src/main.c
 *   DDS_SYNC_PULSE_TICKS=5×20µs=100µs). ⚠️ TOLERANSLI: darbe yalnız periyot
 *   sınırının ±%2'sindeyken kilitler; frekans uyuşmazlığında (STM ≠ ESP frekansı)
 *   periyot ortasında sıfırlamak düşük frekanslı çıkışı DC'ye yapıştırıyordu —
 *   8266 turunda ölçülen sınıf. Uyuşmazlık sayacı status yoluna rapor edilir.
 *
 * SÜRE BİRİMİ: SANİYE — backend sözleşmesi (servers/api_server.py::
 *   _esp_duration_seconds; ai_router int(dk*60)). 0 = süresiz nöbetçisi.
 * ============================================================================ */

#include "CoilController.h"
#include "SensorManager.h"
#include "SharedDefs.h"
#include "Secrets.h"            /* PREF_KEY_PWM_STATE (NVS anahtar adı) */
#include <sys/time.h>
#include "soc/gpio_struct.h"    /* GPIO.out_w1ts/w1tc — core 3.x'te Arduino.h artık dolaylı getirmiyor */

/* ---- DDS zamanlama sabitleri (8266 ile aynı taban: 50 kHz / 20 µs tick) ---- */
#define DDS_TIMER_FREQ_HZ   50000U
#define DDS_DEFAULT_HZ      100U
#define DDS_MIN_TPP         8U      /* 50k/8 = 6.25 kHz üst sınır — yarım+ölü-zaman sığsın */

/* ---- ISR'ın gördüğü paylaşılan durum ---- */
static volatile uint32_t s_tick        = 0;
static volatile uint32_t s_tpp         = DDS_TIMER_FREQ_HZ / DDS_DEFAULT_HZ;
static volatile uint32_t s_duty_ticks  = 0;      /* yarım-periyot içindeki darbe genişliği */
static volatile uint32_t s_phase_ticks = 0;
static volatile bool     s_active      = false;
static volatile uint8_t  s_pin_a       = PIN_COIL_PWM_A;
static volatile uint8_t  s_pin_b       = PIN_COIL_PWM_B;

/* Senkron tanılama — Network görevi status ile yayınlayabilsin diye sayaçlar. */
static volatile uint32_t s_sync_locked  = 0;
static volatile uint32_t s_sync_ignored = 0;

/* ── DC-YAPIŞMA KORUMASI (donanım-uyum denetimi HG-3, 2026-08-19) ──────────────────────────────
 * STM master frekansı ESP'den çok yüksekse (örn STM 100 Hz, ESP 1 Hz → oran 100×), PB1 darbesi
 * ESP'nin her periyot BAŞINDA gelir ve s_tick'i sürekli sıfırlar → ESP sayacı yarım-periyoda HİÇ
 * ulaşamaz → çıkış tek polaritede DC'ye YAPIŞIR (bobin sürekli tek-yön alan + ısınma; STM'de
 * termal kesme yok). 8266 bu tehlikeyi sync'i tümden kaldırarak çözdü; S3'te KOŞULLU çözüyoruz:
 * ESP doğal periyodunu (natural wrap) tamamlayamadan ardışık MISMATCH_STREAK kez sync kilidi
 * gelirse = frekans uyumsuzluğu → sync DEVRE DIŞI (8266 gibi tek faz). ⚠️ TEZGÂHTA SKOPLA DOĞRULA. */
static volatile bool     s_natural_wrap  = false;  /* ddsTimerISR bir tam periyot tamamladı mı */
static volatile uint32_t s_early_streak  = 0;      /* ardışık "erken kilit" (wrap'sız) sayısı */
static volatile bool     s_sync_disabled = false;  /* uyumsuzluk saptandı → sync artık çıkışı bozmaz */
#define SYNC_MISMATCH_STREAK 8U   /* ~8 periyot başı erken kilit → uyumsuzluk kesin (jitter'ı tolere eder) */

static hw_timer_t*  s_timer = nullptr;
static portMUX_TYPE s_mux   = portMUX_INITIALIZER_UNLOCKED;

/* ============================================================================
 * SYNC ISR — TOLERANSLI faz kilidi (2026-08-19)
 * Darbe periyot sınırına yakınsa (±%2, en az 2 tick) kilitle; değilse SAYIP GEÇ.
 * Eski koşulsuz sıfırlama, frekans uyuşmazlığında duty penceresini sürekli
 * yeniden başlatıp çıkışı DC'ye yapıştırabiliyordu (hasta güvenliği sınıfı).
 * ============================================================================ */
static void IRAM_ATTR syncPulseISR() {
    portENTER_CRITICAL_ISR(&s_mux);
    if (s_sync_disabled) {          /* HG-3: uyumsuzluk saptandı → 8266 gibi tek faz, sync yok */
        portEXIT_CRITICAL_ISR(&s_mux);
        return;
    }
    uint32_t t   = s_tick;
    uint32_t tpp = s_tpp;
    /* tol=tpp/50 (%2) → ÖRTÜK EŞİK: DC-yapışma latch'i ancak STM freq ≳50× ESP freq iken devreye
     * girer (darbe aralığı < tol). Ilımlı uyumsuzluk (2-10×) darbeleri periyot ORTASINA düşürür →
     * ignored dalı → ESP serbest koşar (bipolar, DC yok). tol'ü değiştirirsen bu eşik de kayar. */
    uint32_t tol = tpp / 50U + 2U;

    if (t <= tol) {
        /* Periyot BAŞINDA kilit — sağlıklıysa ESP az önce doğal periyodunu tamamlamış (natural wrap)
         * olmalı. Wrap OLMADAN sürekli buraya düşüyorsak STM bizden hızlı → DC-yapışma riski. */
        if (s_natural_wrap) {
            s_early_streak = 0;
            s_natural_wrap = false;
        } else if (++s_early_streak >= SYNC_MISMATCH_STREAK) {
            s_sync_disabled = true;  /* frekans uyumsuzluğu kesin → sync'i bırak (DC-yapışmayı önle) */
        }
        s_tick = 0;
        s_sync_locked++;
    } else if (t >= (tpp - tol)) {
        /* Periyot SONUNDA kilit — sağlıklı hizalama (sync ESP'yi periyot sonunda sıfırlıyor). */
        s_early_streak = 0;
        s_natural_wrap = false;
        s_tick = 0;
        s_sync_locked++;
    } else {
        s_sync_ignored++;            /* periyot ortasında darbe — yok say (mevcut davranış) */
    }
    portEXIT_CRITICAL_ISR(&s_mux);
}

/* ============================================================================
 * DDS TIMER ISR — 50 kHz. Simetrik bipolar + ölü-zaman + faz ofseti.
 * ============================================================================ */
static void IRAM_ATTR ddsTimerISR() {
    if (!s_active) return;

    portENTER_CRITICAL_ISR(&s_mux);
    uint32_t tick = s_tick + 1U;
    if (tick >= s_tpp) {
        tick = 0U;
        s_natural_wrap = true;  /* HG-3: ESP bir tam periyot tamamladı (sync onu sıfırlamadan) */
    }
    s_tick = tick;
    uint32_t tpp   = s_tpp;
    uint32_t duty  = s_duty_ticks;
    uint32_t faz   = s_phase_ticks;
    portEXIT_CRITICAL_ISR(&s_mux);

    if (duty == 0U) {
        GPIO.out_w1tc = (1UL << s_pin_a) | (1UL << s_pin_b);
        return;
    }

    /* Faz ofsetli göreli konum (0 … tpp-1) */
    uint32_t rel  = (tick >= faz) ? (tick - faz) : (tick + tpp - faz);
    uint32_t yarim = tpp / 2U;

    bool aHigh = (rel < duty);                            /* pozitif darbe   */
    bool bHigh = (rel >= yarim) && (rel < (yarim + duty)); /* negatif (ayna) */

    /* Ölü-zaman garantisi _updatePWM'de duty kırpılarak sağlanır; burada yalnız
     * "ikisi birden asla HIGH olamaz" değişmezi korunur (savunma derinliği). */
    if (aHigh && !bHigh) {
        GPIO.out_w1tc = (1UL << s_pin_b);
        GPIO.out_w1ts = (1UL << s_pin_a);
    } else if (bHigh && !aHigh) {
        GPIO.out_w1tc = (1UL << s_pin_a);
        GPIO.out_w1ts = (1UL << s_pin_b);
    } else {
        GPIO.out_w1tc = (1UL << s_pin_a) | (1UL << s_pin_b);
    }
}

/* ============================================================================ */

CoilController::CoilController(SensorManager* sensors) {
    _sensors = sensors;
    _active = false;
    _frequency = (int)DDS_DEFAULT_HZ;
    _dutyCycle = 25;
    _phase = 0;
    _startTime = 0;
    _duration = 0;
    _endTime = 0;
    _hasDuration = false;
    _durationSec = 0;
    _startTimestamp = 0;
    _syncTargetTime = 0;
    _waitingForSync = false;
    _lastSaveTimeMs = 0;
    _syncFallbackPendingEvent = false;
    _isSelfTesting = false;
    _selfTestStartTime = 0;
    _selfTestPassed = false;
    _selfTestCompletedPendingEvent = false;
    _thermalLock = false;
    _thermalStopPendingEvent = false;
    _effectiveDutyPct = 0;
}

void CoilController::begin() {
    pinMode(PIN_COIL_PWM_A, OUTPUT);
    pinMode(PIN_COIL_PWM_B, OUTPUT);
    digitalWrite(PIN_COIL_PWM_A, LOW);
    digitalWrite(PIN_COIL_PWM_B, LOW);

    /* STM32 senkron girişi — S3'te GPIO7 SERBEST (8266'nın aksine flash hattı değil).
     * INPUT_PULLDOWN: hat takılı değilken yüzen pinin gürültüyle sahte kilit
     * üretmesini engeller (eski kod düz INPUT idi). */
    pinMode(PIN_SYNC_IN, INPUT_PULLDOWN);
    attachInterrupt(digitalPinToInterrupt(PIN_SYNC_IN), syncPulseISR, RISING);
    LOG_PRINTLN("[SYNC] S3: PIN_SYNC_IN hazir (GPIO7 RISING, TOLERANSLI kilit)");

    _setupTimerISR();

    /* Yeniden başlatma sonrası devam (bilinçli tasarım: PWM ağdan bağımsız). */
    loadState();
}

void CoilController::_setupTimerISR() {
    /* ⚠️ Arduino ESP32 core 3.x API'si (2026-08-19, 3.3.11'de derlendi): eski
     * timerBegin(num, prescaler, countUp) imzası KALKTI. Yeni model:
     *   timerBegin(frekans)          → 1 MHz sayaç
     *   timerAlarm(t, 20, true, 0)   → her 20 tick'te (20 µs) sonsuz oto-tekrar = 50 kHz */
    s_timer = timerBegin(1000000);
    if (s_timer == nullptr) {
        LOG_PRINTLN("[DDS][HATA] timerBegin basarisiz — DDS calismayacak!");
        return;
    }
    timerAttachInterrupt(s_timer, &ddsTimerISR);
    timerAlarm(s_timer, 20, true, 0);
    LOG_PRINTLN("[DDS] S3: 50kHz timer basladi (full-bridge bipolar + olu-zaman)");
}

/* ---- Ana döngü (Core 1, 5 Hz) ---- */
void CoilController::process() {
    /* start_at bekleme: backend BUGÜN start_at GÖNDERMİYOR (ölçüldü — servers/
     * altında anahtar hiç yok); alan ileriye dönük. NTP hazırsa hedefe kadar
     * bekle, değilse fallback olayıyla hemen başlat. */
    if (_waitingForSync) {
        struct timeval tv;
        gettimeofday(&tv, NULL);
        unsigned long long simdiMs =
            (unsigned long long)tv.tv_sec * 1000ULL + tv.tv_usec / 1000ULL;
        bool ntpVar = (tv.tv_sec > 1600000000L);  /* ~2020 sonrası = senkron */

        if (!ntpVar) {
            _waitingForSync = false;
            _syncFallbackPendingEvent = true;
            _beginOutput(simdiMs);
        } else if (simdiMs >= _syncTargetTime || (_syncTargetTime - simdiMs) > 10000ULL) {
            /* geçmişte kaldı VEYA >10 sn ileride (şüpheli) → hemen başlat */
            if ((_syncTargetTime > simdiMs) && (_syncTargetTime - simdiMs) > 10000ULL) {
                _syncFallbackPendingEvent = true;
            }
            _waitingForSync = false;
            _beginOutput(simdiMs);
        }
        return;  /* beklerken süre/termal işlemez — çıkış zaten kapalı */
    }

    /* Süre bekçisi (SANİYE sözleşmesi; 0 = süresiz). */
    if (_active && _hasDuration && millis() >= _endTime) {
        LOG_PRINTLN("[PWM] Sure doldu, durduruluyor");
        _stopPWM();
        forceSaveState();
    }
    /* HG-5/6 (2026-08-19, sahip kararı — Plan A-1): SÜRESİZ-MOD MUTLAK TAVANI.
     * duration=0 "süresiz" modda hiçbir cihaz-yerel son-tarih yoktu; broker failover /
     * backend çökmesi / STOP kaybı senaryolarında bobin yalnız termal kesmeye kadar
     * enerjili kalabiliyordu. Artık süresiz mod da SURESIZ_TAVAN_SEC'te (2 saat —
     * backend'in STM _coil_deadline'ı ile aynı) cihazda durur. ⚠️ Bu, "PWM ağ-bağımsız"
     * değişmezini İHLAL ETMEZ: tavan zamana bağlı, ağ durumuna DEĞİL — süreli seanslar
     * ve kısa ağ kesintileri etkilenmez. NVS resume sonrası tavan yeni açılıştan sayar
     * (bilinçli: reboot'ta pencere tazelenir ama sonsuzluk yine imkânsız). */
    else if (_active && !_hasDuration &&
             (millis() - _startTime) >= (unsigned long)SURESIZ_TAVAN_SEC * 1000UL) {
        LOG_PRINTLN("[PWM] SURESIZ-mod mutlak tavani doldu, durduruluyor (guvenlik)");
        _stopPWM();
        forceSaveState();
    }

    /* Self-test penceresi: 1 sn ölçüm, PWM zaten AKTİFKEN. */
    if (_isSelfTesting && (millis() - _selfTestStartTime) >= 1000UL) {
        SensorReadings r = _sensors ? _sensors->readAll() : SensorReadings{};
        _selfTestPassed = r.magSensorOk && (r.magneticField >= 0.10f);
        _isSelfTesting = false;
        _selfTestCompletedPendingEvent = true;
    }

    /* Periyodik NVS yedeği (kalan süre doğru sürsün diye) — 30 sn'de bir. */
    if (_active && (millis() - _lastSaveTimeMs) >= 30000UL) {
        saveState();
    }
}

/* ---- YEREL TERMAL KORUMA (2026-08-19) ----------------------------------------
 * .ino Core-1 döngüsü her 200 ms'de readAll() yapıyor; aynı okumayı buraya geçirir
 * (çift I2C trafiği olmasın). Backend'in 48°C politikası sunucuda KALIR; bu,
 * ağ koptuğunda bobini durduracak tek şey olan cihaz-içi son savunma hattıdır.
 * Sensör arızalıysa kesme YAPILMAZ (sensörsüz kart çalışabilmeli). */
void CoilController::enforceThermalLimit(const SensorReadings& r) {
    if (!r.tempSensorOk) return;

    if (r.tempObject >= TERMAL_KESME_C) {
        if (_active) {
            LOG_PRINTF("[TERMAL] KESME: %.1fC >= %.1fC — PWM durduruluyor\n",
                       r.tempObject, TERMAL_KESME_C);
            _stopPWM();
            forceSaveState();
            _thermalStopPendingEvent = true;
        }
        _thermalLock = true;
    } else if (_thermalLock && r.tempObject <= TERMAL_DONUS_C) {
        _thermalLock = false;   /* histerezis: ancak soğuyunca serbest */
    }
}

bool CoilController::isThermalLocked() { return _thermalLock; }

bool CoilController::consumeThermalStopEvent() {
    if (_thermalStopPendingEvent) { _thermalStopPendingEvent = false; return true; }
    return false;
}

/* ---- Komut işleme (Core 1) ----
 * DÖNÜŞ: false = reddedildi (ACK'ta success=false gitsin — eski .ino her komuta
 * koşulsuz success=true basıyordu). */
bool CoilController::handleCommand(const ControlCommand& cmd) {
    switch (cmd.type) {
        case CMD_START: {
            if (_thermalLock) {
                LOG_PRINTLN("[CMD] start RED: termal kilit aktif (sogumasi bekleniyor)");
                return false;
            }
            /* duty<1 = DURDUR (backend park/reset yolu duty:0.0 gönderir). */
            if (cmd.dutyCycle < 1) {
                _stopPWM();
                forceSaveState();
                return true;
            }
            _frequency = constrain(cmd.frequency, 1, 1000);
            _dutyCycle = constrain(cmd.dutyCycle, 1, MAX_DUTY_CYCLE);
            _phase     = ((cmd.phase % 360) + 360) % 360;
            _durationSec = constrain(cmd.durationSec, 0, 86400);

            if (cmd.timestamp > 0) {
                _syncTargetTime = cmd.timestamp;
                _waitingForSync = true;
                LOG_PRINTLN("[PWM] start_at bekleniyor (process() baslatacak)");
            } else {
                struct timeval tv; gettimeofday(&tv, NULL);
                _beginOutput((unsigned long long)tv.tv_sec * 1000ULL + tv.tv_usec / 1000ULL);
            }
            return true;
        }

        case CMD_STOP:
            _waitingForSync = false;
            _stopPWM();
            forceSaveState();
            return true;

        case CMD_UPDATE_PARAMS: {
            if (_thermalLock) return false;
            if (cmd.frequency > 0) _frequency = constrain(cmd.frequency, 1, 1000);
            if (cmd.dutyCycle > 0) _dutyCycle = constrain(cmd.dutyCycle, 1, MAX_DUTY_CYCLE);
            _phase = ((cmd.phase % 360) + 360) % 360;
            if (cmd.durationSec > 0) {
                _durationSec = constrain(cmd.durationSec, 0, 86400);
                if (_active) {
                    _duration = (unsigned long)_durationSec * 1000UL;
                    _hasDuration = (_duration > 0);
                    _endTime = _startTime + _duration;
                }
            }
            if (_active) {
                _updatePWM(_frequency, _dutyCycle, _phase);
                saveState();
            }
            return true;
        }

        case CMD_SELF_TEST:
            /* ⚠️ GÜVENLİK: self-test bobini KENDİLİĞİNDEN enerjilendirmez — yalnız
             * PWM zaten aktifken alan/akım ölçer. Kapalıyken istek = anında FAIL
             * raporu (olay yine yayınlanır ki istekte bulunan cevapsız kalmasın). */
            if (_active) {
                _isSelfTesting = true;
                _selfTestStartTime = millis();
            } else {
                _selfTestPassed = false;
                _selfTestCompletedPendingEvent = true;
            }
            return true;

        case CMD_CALIBRATE:
            if (_active) {
                LOG_PRINTLN("[CMD] calibrate RED: PWM acikken kalibrasyon yapilmaz");
                return false;
            }
            if (_sensors) _sensors->forceCalibrate();
            return true;

        case CMD_SYNC_TIME:
        case CMD_SYNC_ALL:
        default:
            return true;  /* zaman senkronu Network görevinin işi; sessiz kabul */
    }
}

/* ---- Çıkışı gerçekten başlat ---- */
void CoilController::_beginOutput(unsigned long long epochMs) {
    _updatePWM(_frequency, _dutyCycle, _phase);
    _active = true;
    _startTime = millis();
    _duration = (unsigned long)_durationSec * 1000UL;
    _hasDuration = (_duration > 0);
    _endTime = _startTime + _duration;
    _startTimestamp = epochMs;
    if (_sensors) _sensors->setPWMActive(true);   /* akım okuma AC-RMS moduna geçsin */
    forceSaveState();
    LOG_PRINTF("[PWM] BASLADI: %dHz duty%%%d faz%d sure=%dsn (efektif duty%%%d)\n",
               _frequency, _dutyCycle, _phase, _durationSec, _effectiveDutyPct);
}

void CoilController::_updatePWM(int freq, int duty, int phase_deg) {
    uint32_t tpp = DDS_TIMER_FREQ_HZ / (uint32_t)constrain(freq, 1, 1000);
    if (tpp < DDS_MIN_TPP) tpp = DDS_MIN_TPP;
    uint32_t yarim = tpp / 2U;

    /* duty, yarım-periyodun yüzdesi; ölü-zaman iki geçiş için de kırpılır. */
    uint32_t duty_t = (uint32_t)(((float)constrain(duty, 1, MAX_DUTY_CYCLE) / 100.0f) * (float)tpp);
    uint32_t ust = (yarim > DEAD_TIME_TICKS) ? (yarim - DEAD_TIME_TICKS) : 1U;
    if (duty_t > ust) duty_t = ust;
    if (duty_t < 1U) duty_t = 1U;

    uint32_t faz_t = (uint32_t)(((float)(((phase_deg % 360) + 360) % 360) / 360.0f) * (float)tpp) % tpp;

    portENTER_CRITICAL(&s_mux);
    /* HG-3 (adversaryal review düzeltmesi, 2026-08-19): koruma latch'i YALNIZ gerçek frekans
     * değişiminde sıfırlanır. Eski hâli koşulsuz sıfırlıyordu → aktifken gelen HER set_params /
     * faz-only / keepalive komutu s_early_streak'i 0'a çekip DC-yapışma latch'inin OLUŞMASINI
     * engelleyebilirdi (latch penceresi ~8 STM periyodu; sık re-komut onu sürekli bölerdi).
     * freq değişimi = faz kilidini yeniden dene (uyumluysa tekrar kilitlensin); freq aynıysa
     * latch durumu KORUNUR. Not: STM freq'i değişip ESP'ninki aynı kalırsa devre-dışı sürer —
     * fail-safe yön (tek faz, DC yok), regresyon değil. */
    bool freqChanged = (tpp != s_tpp);  /* eski s_tpp'yi YAZMADAN önce oku */
    s_tpp = tpp;
    s_duty_ticks = duty_t;
    s_phase_ticks = faz_t;
    s_active = true;
    if (freqChanged) {
        s_sync_disabled = false;
        s_early_streak = 0;
        s_natural_wrap = false;
    }
    portEXIT_CRITICAL(&s_mux);

    _effectiveDutyPct = (int)(((float)duty_t * 100.0f) / (float)tpp + 0.5f);
    LOG_PRINTF("[DDS] %dHz duty%%%d faz%d -> tpp=%lu duty_t=%lu faz_t=%lu (efektif %%%d)\n",
               freq, duty, phase_deg, (unsigned long)tpp, (unsigned long)duty_t,
               (unsigned long)faz_t, _effectiveDutyPct);
}

void CoilController::_stopPWM() {
    portENTER_CRITICAL(&s_mux);
    s_active = false;
    s_duty_ticks = 0U;
    portEXIT_CRITICAL(&s_mux);
    digitalWrite(PIN_COIL_PWM_A, LOW);
    digitalWrite(PIN_COIL_PWM_B, LOW);
    _active = false;
    _waitingForSync = false;
    if (_sensors) _sensors->setPWMActive(false);
}

/* ---- Durum raporu (Network görevine) ---- */
PWMState CoilController::getState() {
    PWMState st;
    st.active = _active;
    st.frequency = _frequency;
    /* DÜRÜST RAPOR: efektif duty (ölü-zaman + tick yuvarlaması sonrası gerçek). */
    st.dutyCycle = _active ? _effectiveDutyPct : _dutyCycle;
    st.durationSec = _durationSec;
    st.startTimestamp = _startTimestamp;
    if (_active && _hasDuration) {
        unsigned long simdi = millis();
        st.remainingTimeSec = (_endTime > simdi) ? (_endTime - simdi) / 1000UL : 0UL;
    } else {
        st.remainingTimeSec = 0UL;
    }
    return st;
}

bool CoilController::consumeSyncFallbackEvent() {
    if (_syncFallbackPendingEvent) { _syncFallbackPendingEvent = false; return true; }
    return false;
}

bool CoilController::consumeSelfTestEvent(bool &passed) {
    if (_selfTestCompletedPendingEvent) {
        _selfTestCompletedPendingEvent = false;
        passed = _selfTestPassed;
        return true;
    }
    return false;
}

uint32_t CoilController::syncIgnoredCount() { return s_sync_ignored; }

bool CoilController::syncDisabled() { return s_sync_disabled; }

/* ---- NVS kalıcılık (yeniden başlatmada devam — bilinçli tasarım) ---- */
struct NvsPwmState {
    uint8_t  magic;        /* 0xB3 = S3 v2 (SANİYE birimli) — eski 0xAB kayıtları YOK SAYILIR */
    bool     active;
    int32_t  frequency;
    int32_t  dutyCycle;
    int32_t  phase;
    int32_t  durationSec;
    uint32_t elapsedMs;
    uint8_t  checksum;
};

static uint8_t _nvsChecksum(const NvsPwmState& s) {
    return (uint8_t)(s.magic ^ (uint8_t)s.active ^ (uint8_t)s.frequency
                     ^ (uint8_t)s.dutyCycle ^ (uint8_t)s.phase
                     ^ (uint8_t)s.durationSec ^ (uint8_t)s.elapsedMs);
}

void CoilController::saveState() {
    NvsPwmState s;
    s.magic = 0xB3;
    s.active = _active;
    s.frequency = _frequency;
    s.dutyCycle = _dutyCycle;
    s.phase = _phase;
    s.durationSec = _durationSec;
    s.elapsedMs = (_active && _hasDuration) ? (millis() - _startTime) : 0U;
    s.checksum = _nvsChecksum(s);
    _writeStateToNvs(&s);
    _lastSaveTimeMs = millis();
}

void CoilController::forceSaveState() { saveState(); }

void CoilController::_writeStateToNvs(const void* data) {
    if (_prefs.begin("pemf", false)) {
        _prefs.putBytes(PREF_KEY_PWM_STATE, data, sizeof(NvsPwmState));
        _prefs.end();
    }
}

void CoilController::loadState() {
    NvsPwmState s;
    memset(&s, 0, sizeof(s));
    bool ok = false;
    if (_prefs.begin("pemf", true)) {
        ok = _prefs.getBytes(PREF_KEY_PWM_STATE, &s, sizeof(s)) == sizeof(s);
        _prefs.end();
    }
    if (!ok || s.magic != 0xB3 || s.checksum != _nvsChecksum(s) || !s.active) {
        LOG_PRINTLN("[PWM] NVS'de surdurulecek durum yok");
        return;
    }
    _frequency = constrain((int)s.frequency, 1, 1000);
    _dutyCycle = constrain((int)s.dutyCycle, 1, MAX_DUTY_CYCLE);
    _phase = ((s.phase % 360) + 360) % 360;

    if (s.durationSec > 0) {
        long kalanMs = (long)s.durationSec * 1000L - (long)s.elapsedMs;
        if (kalanMs <= 0) { LOG_PRINTLN("[PWM] NVS: sure zaten dolmus"); return; }
        _durationSec = (int)(kalanMs / 1000L);
        if (_durationSec < 1) _durationSec = 1;
    } else {
        _durationSec = 0;  /* süresizdi — süresiz devam (bilinçli tasarım) */
    }

    struct timeval tv; gettimeofday(&tv, NULL);
    _beginOutput((unsigned long long)tv.tv_sec * 1000ULL + tv.tv_usec / 1000ULL);
    LOG_PRINTF("[PWM] NVS'den devam: %dHz duty%%%d faz%d kalan=%dsn\n",
               _frequency, _dutyCycle, _phase, _durationSec);
}
