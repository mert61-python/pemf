#ifndef SENSOR_MANAGER_H
#define SENSOR_MANAGER_H

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_MLX90614.h>
#include <Adafruit_MLX90393.h>
#include <Preferences.h>
#include "SharedDefs.h"

// ============================================================================
// SensorManager v1.2.0
//
// ACS712 Kalibrasyon Stratejisi (güncellenmiş):
//   - NVS'de geçerli offset varsa → yükle, boot'ta ölçüm YOK
//   - NVS boşsa / sürüm uyumsuzsa → taze ölçüm, kaydet
//   - forceCalibrate() → MQTT/buton ile zorla; PWM kapalıyken çağır
//
// Akım Okuma Stratejisi:
//   - PWM KAPALI → DC ortalama (32 örnek) + deadband
//   - PWM AÇIK   → AC RMS (100 örnek, 2 periyot)
//   - Her iki modda: |current| < CURRENT_NOISE_FLOOR → 0.0A
//
// ADC:
//   - analogReadMilliVolts() — ESP32-S3 dahili kalibrasyon eğrisi
// ============================================================================

class SensorManager {
public:
    SensorManager();

    // İki adımlı başlatma (önerilen):
    //   1. beginWithoutCalibration() → ADC + I2C
    //   2. coilController.begin()   → timer
    //   3. calibrate()              → NVS öncelikli kalibrasyon
    void beginWithoutCalibration();
    void calibrate();

    // Legacy wrapper (tek adım, eski uyumluluk)
    void begin();

    // Dış tetikleyici — MQTT veya buton
    // ⚠ Çağrılmadan önce PWM durdurulmuş olmalıdır!
    void forceCalibrate();

    // Core 1 loop içinden çağrılır
    SensorReadings readAll();

    // PWM durumu bildirimi
    void setPWMActive(bool active);

    // I2C Bus Recovery
    void recoverI2CBus(int busNumber);

    // Kalibrasyon durumu sorgulama
    bool isCalibrated() const { return _calibrated; }
    float getAcsOffset() const { return _acsOffset; }
    float getAcsSensitivity() const { return _acsSensitivity; }

private:
    Adafruit_MLX90614 _mlxTemp;
    Adafruit_MLX90393 _mlxMag;
    Preferences       _prefs;

    // Sensör durumu
    bool _tempOk;
    bool _magOk;

    // PWM takibi
    bool _pwmActive;

    // Kalibrasyon durumu
    bool  _calibrated;      // true = NVS'den yüklendi veya başarıyla ölçüldü
    float _acsOffset;       // [V]   0A'da ölçülen ADC gerilimi
    float _acsSensitivity;  // [V/A] = ACS712_BASE_SENSITIVITY × (_acsOffset / ACS712_VCC_HALF)

    // Pipelined manyetik okuma
    bool _magMeasurementPending;

    // PWM aktifken max değerler
    float _maxMagneticField;
    float _maxCurrent;

    // Hata sayaçları
    int _tempFailCount;
    int _magFailCount;
    int _currentFailCount;
    static const int CRITICAL_FAIL_THRESHOLD = 10;
    static const int I2C_RECOVERY_THRESHOLD  = 5;

    // Moving average (şu an kullanılmıyor; ileride aktifleştirilebilir)
    float _tempObjectFiltered;
    float _tempAmbientFiltered;
    float _magFieldFiltered;
    float _currentFiltered;
    static constexpr float FILTER_ALPHA = 0.2f;

    // Dahili yardımcılar
    void  _initI2C();
    void  _calibrateCurrent(bool force);
    void  _deriveSensitivity();
    float _readCurrent();
    float _applyFilter(float newValue, float& filteredValue);
};

#endif // SENSOR_MANAGER_H
