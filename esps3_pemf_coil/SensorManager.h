#ifndef SENSOR_MANAGER_H
#define SENSOR_MANAGER_H

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_MLX90614.h>
#include <Adafruit_MLX90393.h>
#include "SharedDefs.h"

// ============================================================================
// ENDÜSTRİYEL DÖNÜŞÜM: Gelişmiş ADC ve Hata Yönetimi
// ============================================================================

class SensorManager {
public:
    SensorManager();
    void begin();
    
    // Core 1 loop içinden çağrılır
    SensorReadings readAll();
    
    // PWM durumu bildirimi (max değerleri track için)
    void setPWMActive(bool active);
    
    // I2C Bus Recovery
    void recoverI2CBus(int busNumber);

private:
    Adafruit_MLX90614 _mlxTemp;
    Adafruit_MLX90393 _mlxMag;
    
    float _acsOffset;
    
    // Sensör Durumları
    bool _tempOk;
    bool _magOk;
    
    // PWM Tracking
    bool _pwmActive;
    
    // Max değerler (PWM aktifken)
    float _maxMagneticField;
    float _maxCurrent;
    
    // Hata Sayaçları (Kritik hata bildirimi için)
    int _tempFailCount;
    int _magFailCount;
    int _currentFailCount;
    static const int CRITICAL_FAIL_THRESHOLD = 10;
    static const int I2C_RECOVERY_THRESHOLD = 5;  // Bus recovery eşiği
    
    // Moving Average Filters (Noise reduction)
    float _tempObjectFiltered;
    float _tempAmbientFiltered;
    float _magFieldFiltered;
    float _currentFiltered;
    static constexpr float FILTER_ALPHA = 0.2; // Exponential filter coefficient (0-1, düşük = daha smooth)
    
    // Helpers
    void _initI2C();
    float _readCurrent();
    void _calibrateCurrent();
    float _applyFilter(float newValue, float& filteredValue);
};

#endif
