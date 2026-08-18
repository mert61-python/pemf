// ============================================================================
// SensorManager.cpp — Düzeltilmiş Akım Sensörü Mantığı
//
// Değişiklikler (v1.1.0 → v1.2.0):
//
//  [FIX-1] NVS-öncelikli kalibrasyon:
//    Her boot'ta "taze ölçüm" yapan yaklaşım KALDIRILDI.
//    NVS'de geçerli sürüm + geçerli aralıkta offset varsa → direkt kullan.
//    Yalnızca NVS boşsa, sürüm uyumsuzsa veya forceCalibrate() çağrıldıysa ölç.
//    → Switching EMI altında kötü kalibrasyon → 60A sorunu giderildi.
//
//  [FIX-2] analogRead() geri dönüşü:
//    ESP32-S3 GPIO1 üzerinde analogReadMilliVolts() bug'lı çalıştığı için
//    (27mV hatası) klasik analogRead() + (raw * 3.3 / 4095) dönüşümüne
//    geri dönüldü.
//
//  [FIX-3] PWM durumuna göre okuma stratejisi:
//    PWM KAPALI → basit DC ortalama + deadband (gürültüyü bastırır)
//    PWM AÇIK   → AC RMS (bipolar full-bridge için doğru)
//    Her iki modda CURRENT_NOISE_FLOOR altındaki değerler 0 döndürülür.
//
//  [FIX-4] forceCalibrate() public metodu:
//    MQTT'den "cmd_calibrate" komutu ile veya butonla tetiklenebilir.
//    Timer açıkken kalibrasyon yapılacaksa: coil DURDURULMUŞ olmalı.
// ============================================================================

#include "SensorManager.h"

SensorManager::SensorManager() : _acsOffset(ACS712_OFFSET_EXPECTED) {
    _tempOk              = false;
    _magOk               = false;
    _tempFailCount       = 0;
    _magFailCount        = 0;
    _currentFailCount    = 0;
    _calibrated          = false;

    _tempObjectFiltered  = 25.0f;
    _tempAmbientFiltered = 25.0f;
    _magFieldFiltered    = 0.0f;
    _currentFiltered     = 0.0f;

    _pwmActive             = false;
    _magMeasurementPending = false;
    _maxMagneticField      = 0.0f;
    _maxCurrent            = 0.0f;

    // Varsayılan hassasiyet: ilk kalibrasyon öncesi güvenli fallback
    _acsSensitivity = ACS712_BASE_SENSITIVITY *
                      (ACS712_OFFSET_EXPECTED / ACS712_VCC_HALF);
}

// ============================================================================
// begin() — Geriye dönük uyumluluk wrapper
// ============================================================================
void SensorManager::begin() {
    beginWithoutCalibration();
    _calibrateCurrent(false); // force=false → NVS öncelikli
    LOG_PRINTLN("[Init] ✓ SensorManager tamamen başlatıldı! (legacy begin)");
}

// ============================================================================
// beginWithoutCalibration() — Adım 1
// ADC ve I2C sensörlerini başlatır; kalibrasyon yapmaz.
// CoilController::begin() (timer) öncesi çağrılmalıdır.
// ============================================================================
void SensorManager::beginWithoutCalibration() {
    LOG_PRINTLN("[Core 1] SensorManager başlatılıyor (kalibrasyon hariç)...");

    delay(500); // Güç stabilizasyonu

    // ADC Yapılandırması
    analogReadResolution(ADC_RESOLUTION_BITS);
    pinMode(PIN_CURRENT_ADC, INPUT);
    analogRead(PIN_CURRENT_ADC);              // ADC kanalını aktive et
    delay(10);
    analogSetPinAttenuation(PIN_CURRENT_ADC, ADC_11db); // 0–3.3V

    // Isınma okumalarını at (ADC başlangıç gürültüsü)
    for (int i = 0; i < 20; i++) {
        analogRead(PIN_CURRENT_ADC);
        delayMicroseconds(200);
    }

    LOG_PRINTLN("[Init] ADC konfigürasyonu tamamlandı");
    delay(100);

    LOG_PRINTLN("[Init] I2C başlatma işlemi başlıyor...");
    _initI2C();
    LOG_PRINTLN("[Init] ADC + I2C hazır. Kalibrasyon timer başladıktan sonra yapılacak.");
}

// ============================================================================
// calibrate() — Adım 3
// CoilController::begin() ÇAĞRILDIKTAN SONRA çağrılır.
// NVS'de geçerli offset varsa ölçüm YAPILMAZ, NVS'den yüklenir.
// ============================================================================
void SensorManager::calibrate() {
    LOG_PRINTLN("[Init] Akım sensörü kalibrasyon başlatılıyor...");
    _calibrateCurrent(false); // force=false → NVS öncelikli
    LOG_PRINTLN("[Init] ✓ SensorManager tamamen başlatıldı!");
}

// ============================================================================
// forceCalibrate() — Dış tetikleyici (MQTT / Buton)
//
// ÖNEMLİ: Bu metot çağrılmadan önce PWM DURDURULMUŞ olmalıdır.
// Bobin akımı sıfır değilken yapılan kalibrasyon yanlış offset üretir.
// ============================================================================
void SensorManager::forceCalibrate() {
    LOG_PRINTLN("[Kalibrasyon] ⚡ Force kalibrasyon tetiklendi (NVS sıfırlanıyor)...");

    // NVS'deki kaydı sil → _calibrateCurrent taze ölçüm yapar
    _prefs.begin("pemf_calib", false);
    _prefs.remove("acs_offset");
    _prefs.end();
    _calibrated = false;

    _calibrateCurrent(true); // force=true
}

// ============================================================================
// _calibrateCurrent() — NVS-Öncelikli Kalibrasyon
// ============================================================================
void SensorManager::_calibrateCurrent(bool force) {
    _prefs.begin("pemf_calib", false);

    // --- Sürüm kontrolü ---
    int savedCalibVer = _prefs.getInt("calib_ver", 0);
    if (savedCalibVer < ACS712_CALIB_VERSION) {
        _prefs.remove("acs_offset");
        _prefs.putInt("calib_ver", ACS712_CALIB_VERSION);
        LOG_PRINTF("[Kalibrasyon] ⚠ NVS temizlendi (v%d → v%d)\n",
                   savedCalibVer, ACS712_CALIB_VERSION);
    }

    float minValid = ACS712_OFFSET_EXPECTED - ACS712_OFFSET_TOLERANCE;
    float maxValid = ACS712_OFFSET_EXPECTED + ACS712_OFFSET_TOLERANCE;

    // --- [FIX-1] NVS öncelikli: geçerli offset varsa ÖLÇÜM YAPMA ---
    if (!force) {
        float savedOffset = _prefs.getFloat("acs_offset", -1.0f);
        if (savedOffset >= minValid && savedOffset <= maxValid) {
            _acsOffset  = savedOffset;
            _calibrated = true;
            _deriveSensitivity();
            _prefs.end();
            LOG_PRINTF("[Kalibrasyon] ✓ NVS'den yüklendi: %.4fV (ölçüm atlandı)\n",
                       _acsOffset);
            return;
        }
        LOG_PRINTF("[Kalibrasyon] NVS offset geçersiz (%.4fV), taze ölçüm yapılıyor...\n",
                   _prefs.getFloat("acs_offset", -1.0f));
    } else {
        LOG_PRINTLN("[Kalibrasyon] Force mod: NVS bypass, taze ölçüm yapılıyor...");
    }

    // --- Taze ölçüm ---
    LOG_PRINTLN("[Kalibrasyon] ⚠ PWM KAPALI ve bobin akımsız olduğundan emin olun!");
    LOG_PRINTLN("[Kalibrasyon] Stabilizasyon bekleniyor (500ms)...");
    delay(500);

    // [FIX-2] analogRead — ESP32-S3 GPIO1 bug'ı nedeniyle klasik yönteme dönüş
    // İlk 10 okuma ısınma için atılır
    for (int i = 0; i < 10; i++) {
        analogRead(PIN_CURRENT_ADC);
        delayMicroseconds(200);
    }

    // 500 örnek → daha güvenilir ortalama
    double sumRaw = 0.0;
    for (int i = 0; i < 500; i++) {
        sumRaw += analogRead(PIN_CURRENT_ADC);
        delayMicroseconds(400); // 500 × 400µs = 200ms toplam
    }

    float avgRaw = (float)(sumRaw / 500.0);
    _acsOffset = avgRaw * (3.3f / 4095.0f);  // Raw → Voltaj
    float measuredMv = _acsOffset * 1000.0f; // Sadece log için

    LOG_PRINTF("[Kalibrasyon] Ölçülen ortalama: %.2f mV → %.4f V\n", measuredMv, _acsOffset);

    // --- Geçerlilik kontrolü + fallback ---
    if (_acsOffset < minValid || _acsOffset > maxValid) {
        LOG_PRINTF("[Kalibrasyon] ⚠ UYARI: %.4fV beklenen [%.3f–%.3f]V dışında!\n",
                   _acsOffset, minValid, maxValid);
        LOG_PRINTF("[Kalibrasyon] → Fallback: ACS712_OFFSET_EXPECTED = %.4fV kullanılıyor\n",
                   ACS712_OFFSET_EXPECTED);
        _acsOffset = ACS712_OFFSET_EXPECTED;
        // Fallback değeri NVS'e kaydetme → bir sonraki boot yeniden ölçer
        _calibrated = false;
        _deriveSensitivity();
        _prefs.end();
        return;
    }

    _deriveSensitivity();
    _calibrated = true;
    _prefs.putFloat("acs_offset", _acsOffset);
    _prefs.end();

    LOG_PRINTF("[Kalibrasyon] ✓ Offset NVS'e kaydedildi: %.4fV\n", _acsOffset);
}

// ============================================================================
// _deriveSensitivity() — Offset'ten hassasiyet türetimi
// ============================================================================
void SensorManager::_deriveSensitivity() {
    float k = _acsOffset / ACS712_VCC_HALF;
    _acsSensitivity = ACS712_BASE_SENSITIVITY * k;

    LOG_PRINTF("[Kalibrasyon] ── Hassasiyet Türetimi ─────────────────────\n");
    LOG_PRINTF("[Kalibrasyon]   0A ADC offset      : %.4f V\n",     _acsOffset);
    LOG_PRINTF("[Kalibrasyon]   ACS712 Vcc/2 ref   : %.4f V\n",     ACS712_VCC_HALF);
    LOG_PRINTF("[Kalibrasyon]   Bölücü oranı k     : %.4f\n",       k);
    LOG_PRINTF("[Kalibrasyon]   Efektif hassasiyet : %.2f mV/A\n",  _acsSensitivity * 1000.0f);
    LOG_PRINTF("[Kalibrasyon] ────────────────────────────────────────────\n");
}

// ============================================================================
// _readCurrent() — PWM Durumuna Göre Okuma Stratejisi
// ============================================================================
float SensorManager::_readCurrent() {

    // ---- MOD A: PWM KAPALI → DC Ortalama + Deadband ----
    if (!_pwmActive) {
        double sumRaw = 0.0;
        for (int i = 0; i < CURRENT_DC_SAMPLES; i++) {
            sumRaw += analogRead(PIN_CURRENT_ADC);
            delayMicroseconds(500);
        }

        float avgRaw = (float)(sumRaw / CURRENT_DC_SAMPLES);
        float voltage = avgRaw * (3.3f / 4095.0f);
        float current = (voltage - _acsOffset) / _acsSensitivity;

        // Deadband: CURRENT_NOISE_FLOOR altındaki değerleri sıfırla
        if (fabsf(current) < CURRENT_NOISE_FLOOR) {
            return 0.0f;
        }
        return current;
    }

    // ---- MOD B: PWM AÇIK → AC RMS ----
    float sumSquares  = 0.0f;
    int   validSamples = 0;
    int   clipCount    = 0;

    for (int i = 0; i < CURRENT_SAMPLES; i++) {
        uint32_t raw = analogRead(PIN_CURRENT_ADC);
        uint32_t mv = (raw * 3300) / 4095; // Klip tespiti için yaklaşık mV hesabı

        // Klip tespiti: mV cinsinden eşik
        if (mv >= ADC_CLIP_MV) {
            clipCount++;
            delayMicroseconds(CURRENT_SAMPLE_US);
            if ((i & 0x0F) == 0x0F) taskYIELD();
            continue;
        }

        float voltage        = raw * (3.3f / 4095.0f);
        float instantCurrent = (voltage - _acsOffset) / _acsSensitivity;
        sumSquares  += instantCurrent * instantCurrent;
        validSamples++;

        delayMicroseconds(CURRENT_SAMPLE_US);
        if ((i & 0x0F) == 0x0F) taskYIELD();
    }

    // Klip uyarısı (5 saniyede bir)
    if (clipCount > 10) {
        static unsigned long lastClipWarn = 0;
        if (millis() - lastClipWarn > 5000) {
            LOG_PRINTF("[Sensör] ⚠ ADC klip: %d/%d örnek doyumda!\n",
                       clipCount, CURRENT_SAMPLES);
            lastClipWarn = millis();
        }
    }

    if (validSamples < 10) {
        return 0.0f;
    }

    float rms = sqrtf(sumSquares / validSamples);
    // Noise floor: PEMF akımı için <CURRENT_NOISE_FLOOR A gürültü kabul edilir
    return (rms < CURRENT_NOISE_FLOOR) ? 0.0f : rms;
}

// ============================================================================
// readAll() — Tüm Sensörleri Oku
// ============================================================================
SensorReadings SensorManager::readAll() {
    SensorReadings data;

    // 1. Sıcaklık
    if (_tempOk) {
        data.tempObject  = _mlxTemp.readObjectTempC();
        data.tempAmbient = _mlxTemp.readAmbientTempC();
        data.tempSensorOk = !isnan(data.tempObject) && !isnan(data.tempAmbient);

        if (data.tempSensorOk) {
            _tempFailCount = 0;
        } else {
            _tempFailCount++;
            if (_tempFailCount == I2C_RECOVERY_THRESHOLD) {
                LOG_PRINTLN("[Sensör] I2C-0 bus recovery deneniyor...");
                recoverI2CBus(0);
            }
            if (_tempFailCount == CRITICAL_FAIL_THRESHOLD) {
                LOG_PRINTLN("[CRITICAL] Sıcaklık sensörü offline — 10 ardışık hata");
            }
        }
    } else {
        data.tempObject   = 0.0f;
        data.tempAmbient  = 0.0f;
        data.tempSensorOk = false;
    }

    // 2. Manyetik Alan — pipelined single-shot
    if (_magOk) {
        float x = 0.0f, y = 0.0f, z = 0.0f;
        bool readOk = false;

        if (_magMeasurementPending) {
            readOk = _mlxMag.readMeasurement(&x, &y, &z);
            _magMeasurementPending = false;
        }

        if (_mlxMag.startSingleMeasurement()) {
            _magMeasurementPending = true;
        }

        if (readOk) {
            x /= 1000.0f; // µT → mT
            y /= 1000.0f;
            z /= 1000.0f;

            float magnitude    = sqrtf(x*x + y*y + z*z);
            data.magneticField = magnitude;
            data.magX          = x;
            data.magY          = y;
            data.magZ          = z;
            data.magSensorOk   = true;
            _magFailCount      = 0;
        } else {
            data.magneticField = 0.0f;
            data.magX = data.magY = data.magZ = 0.0f;
            data.magSensorOk = false;
            _magFailCount++;
            if (_magFailCount == I2C_RECOVERY_THRESHOLD) {
                LOG_PRINTLN("[Sensör] I2C-1 bus recovery deneniyor...");
                recoverI2CBus(1);
            }
            if (_magFailCount == CRITICAL_FAIL_THRESHOLD) {
                LOG_PRINTLN("[CRITICAL] Manyetik sensör offline — 10 ardışık hata");
            }
        }
    } else {
        data.magneticField = 0.0f;
        data.magX = data.magY = data.magZ = 0.0f;
        data.magSensorOk = false;
    }

    // 3. Akım — [FIX-3] PWM durumuna göre strateji
    data.current         = _readCurrent();
    data.currentSensorOk = _calibrated; // Kalibrasyon yapılmamışsa güvenilmez işaretle

    data.allSensorsOk = data.tempSensorOk && data.magSensorOk && data.currentSensorOk;

    // PWM aktifken max değerleri güncelle
    if (_pwmActive) {
        if (data.magneticField > _maxMagneticField) _maxMagneticField = data.magneticField;
        if (data.current        > _maxCurrent)       _maxCurrent       = data.current;
    }

    data.maxMagneticField = _maxMagneticField;
    data.maxCurrent       = _maxCurrent;

    // Periyodik log (10 saniyede bir)
    static unsigned long lastLogTime = 0;
    if (millis() - lastLogTime > 10000) {
        LOG_PRINTF("[Sensör] Bobin: %.1f°C, Ortam: %.1f°C, Mag: %.2f mT, Akım: %.2fA\n",
                   data.tempObject, data.tempAmbient, data.magneticField, data.current);
        if (data.magSensorOk) {
            LOG_PRINTF("[Sensör] Mag Eksenler → X:%.2f Y:%.2f Z:%.2f mT\n",
                       data.magX, data.magY, data.magZ);
        }
        if (_pwmActive) {
            LOG_PRINTF("[Sensör] Max → Mag:%.2f mT, Akım:%.2f A\n",
                       _maxMagneticField, _maxCurrent);
        }
        LOG_PRINTF("[Sensör] Kalib → offset:%.4fV, sens:%.2f mV/A, %s\n",
                   _acsOffset, _acsSensitivity * 1000.0f,
                   _calibrated ? "✓ NVS" : "⚠ FALLBACK");
        lastLogTime = millis();
    }

    return data;
}

// ============================================================================
// setPWMActive() — PWM Durum Bildirimi
// ============================================================================
void SensorManager::setPWMActive(bool active) {
    if (active != _pwmActive) {
        if (!active && _pwmActive) {
            LOG_PRINTF("[Sensör] PWM durdu — Max Mag:%.2f mT, Max Akım:%.2f A\n",
                       _maxMagneticField, _maxCurrent);
        }
        _maxMagneticField = 0.0f;
        _maxCurrent       = 0.0f;

        if (active) {
            LOG_PRINTLN("[Sensör] PWM başladı — Max değerler sıfırlandı");
        }
    }
    _pwmActive = active;
}

// ============================================================================
// _initI2C() — Sadeleştirilmiş I2C Başlatma
// ============================================================================
void SensorManager::_initI2C() {
    LOG_PRINTLN("\n========================================");
    LOG_PRINTLN("[I2C] Sensör Başlatma");
    LOG_PRINTLN("========================================\n");

    // I2C-0: MLX90614 Sıcaklık
    LOG_PRINTLN("[I2C-0] MLX90614 başlatılıyor (GPIO8/9)...");
    Wire.end();
    delay(50);

    if (!Wire.begin(PIN_I2C_TEMP_SDA, PIN_I2C_TEMP_SCL, I2C_FREQ_TEMP)) {
        LOG_PRINTLN("[I2C-0] ✗ Bus başlatılamadı!");
        _tempOk = false;
    } else {
        delay(500);
        _tempOk = _mlxTemp.begin(0x5A, &Wire);
        LOG_PRINTF("[I2C-0] %s MLX90614\n", _tempOk ? "✓" : "✗");
    }

    delay(500);

    // I2C-1: MLX90393 Manyetik
    LOG_PRINTLN("[I2C-1] MLX90393 başlatılıyor (GPIO10/11, 0x18)...");
    Wire1.end();
    delay(50);

    if (!Wire1.begin(PIN_I2C_MAG_SDA, PIN_I2C_MAG_SCL, I2C_FREQ_MAG)) {
        LOG_PRINTLN("[I2C-1] ✗ Bus başlatılamadı!");
        _magOk = false;
    } else {
        delay(500);
        _magOk = false;
        if (_mlxMag.begin_I2C(0x18, &Wire1)) {
            _magOk = true;
            delay(100);
            _mlxMag.setGain(MLX90393_GAIN_2_5X);
            delay(50);
            _mlxMag.setOversampling(MLX90393_OSR_1);
            delay(50);
            _mlxMag.setFilter(MLX90393_FILTER_3);
            delay(50);
            _magMeasurementPending = _mlxMag.startSingleMeasurement();
            LOG_PRINTLN("[I2C-1] ✓ MLX90393, Gain 2.5X, OSR 1, Filter 3");
        } else {
            LOG_PRINTLN("[I2C-1] ✗ MLX90393 başlatılamadı (0x18)");
        }
    }

    LOG_PRINTLN("\n========================================");
    LOG_PRINTF("[I2C] MLX90614: %s\n", _tempOk ? "✓ OK" : "✗ OFFLINE");
    LOG_PRINTF("[I2C] MLX90393: %s\n", _magOk  ? "✓ OK" : "✗ OFFLINE");
    LOG_PRINTLN("========================================\n");
}

// ============================================================================
// _applyFilter() — Üstel Hareketli Ortalama
// ============================================================================
float SensorManager::_applyFilter(float newValue, float& filteredValue) {
    filteredValue = (FILTER_ALPHA * newValue) + ((1.0f - FILTER_ALPHA) * filteredValue);
    return filteredValue;
}

// ============================================================================
// recoverI2CBus() — Takılı Bus Kurtarma
// ============================================================================
void SensorManager::recoverI2CBus(int busNumber) {
    LOG_PRINTF("[Sensör] I2C-%d Bus Recovery başlatılıyor...\n", busNumber);

    int sdaPin = (busNumber == 0) ? PIN_I2C_TEMP_SDA : PIN_I2C_MAG_SDA;
    int sclPin = (busNumber == 0) ? PIN_I2C_TEMP_SCL : PIN_I2C_MAG_SCL;

    if (busNumber == 0) Wire.end();
    else                Wire1.end();

    vTaskDelay(pdMS_TO_TICKS(50));

    // Manuel Bus Clear (9 clock pulse)
    pinMode(sdaPin, INPUT_PULLUP);
    pinMode(sclPin, OUTPUT);
    digitalWrite(sclPin, HIGH);
    delayMicroseconds(10);
    for (int i = 0; i < 9; i++) {
        digitalWrite(sclPin, LOW);  delayMicroseconds(10);
        digitalWrite(sclPin, HIGH); delayMicroseconds(10);
        if (digitalRead(sdaPin) == HIGH) break;
    }
    // STOP koşulu
    pinMode(sdaPin, OUTPUT);
    digitalWrite(sdaPin, LOW);  delayMicroseconds(10);
    digitalWrite(sdaPin, HIGH); delayMicroseconds(10);

    if (busNumber == 0) {
        Wire.begin(sdaPin, sclPin, I2C_FREQ_TEMP);
        vTaskDelay(pdMS_TO_TICKS(100));
        if (_mlxTemp.begin(0x5A, &Wire)) {
            _tempOk        = true;
            _tempFailCount = 0;
            LOG_PRINTLN("[Sensör] ✓ MLX90614 recovery başarılı");
        }
    } else {
        Wire1.begin(sdaPin, sclPin, I2C_FREQ_MAG);
        vTaskDelay(pdMS_TO_TICKS(100));
        for (int retry = 0; retry < 3; retry++) {
            if (_mlxMag.begin_I2C(0x18, &Wire1)) {
                _magOk       = true;
                _magFailCount = 0;
                _mlxMag.setGain(MLX90393_GAIN_2_5X);
                _mlxMag.setOversampling(MLX90393_OSR_1);
                _mlxMag.setFilter(MLX90393_FILTER_3);
                _magMeasurementPending = _mlxMag.startSingleMeasurement();
                LOG_PRINTLN("[Sensör] ✓ MLX90393 recovery başarılı");
                return;
            }
            vTaskDelay(pdMS_TO_TICKS(200));
        }
        _magOk = false;
        LOG_PRINTLN("[Sensör] ⚠ MLX90393 recovery başarısız — sistem devam ediyor");
    }
}
