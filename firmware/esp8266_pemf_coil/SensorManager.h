#ifndef SENSOR_MANAGER_H
#define SENSOR_MANAGER_H

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_MLX90614.h>
#include <Adafruit_MLX90393.h>
#include "SharedDefs.h"

// I2C SensÃ¶r Durum Makinesi (Non-blocking okuma iÃ§in)
enum MLX90614State {
    MLX90614_IDLE,
    MLX90614_REQUESTED
};

enum MLX90393State {
    MLX90393_IDLE,
    MLX90393_REQUESTED,
    MLX90393_READING
};

class SensorManager {
public:
    SensorManager(int currentPin, int sdaPin = D2, int sclPin = D1);
    void begin();                   // Legacy — backward compat
    void beginWithoutCalibration(); // Adım 1: ADC + I2C init, kalibrasyon YOK
    void calibrate();               // Adım 3: Timer açıkken offset ölç
    void update();  // Loop'ta sÃ¼rekli Ã§aÄŸrÄ±lacak
    SensorData getData();
    bool isReady();  // TÃ¼m sensÃ¶rler hazÄ±r mÄ±?
    void setPWMActive(bool active); // PWM aktifken maxMagneticField/maxCurrent takibi

    // populateStatus pattern iÃ§in
    void populateStatus(StatusData& data);

private:
    int _currentPin;
    int _sdaPin;
    int _sclPin;

    // SensÃ¶r nesneleri
    Adafruit_MLX90614 _mlxTemp;
    Adafruit_MLX90393 _mlxMag;
    SensorData _data;
    bool _pwmActive = false;

    // ACS712 kalibrasyon
    float _acs712Offset;
    float _acsSensitivity;   // [V/A] — runtime'da türetilir
    bool _acs712Calibrated;

    // Sensör başlatma durumu
    bool _mlx90614Initialized;
    bool _mlx90393Initialized;
    bool _initializedWithoutCalibration = false;

    // State machine deÄŸiÅŸkenleri
    MLX90614State _mlx90614State;
    MLX90393State _mlx90393State;
    unsigned long _mlx90614RequestTime;
    unsigned long _mlx90393RequestTime;
    int _mlx90393RetryCount;

    // Filtered vars insted of array
    float _tempObjectFiltered;
    float _tempAmbientFiltered;
    float _magFieldFiltered;
    float _currentFiltered;
    static constexpr float FILTER_ALPHA = 0.2f;

    int _sensorErrorCount[3];  // MLX90614, MLX90393, ACS712
    unsigned long _lastSensorUpdateTime;  // Son baÅŸarÄ±lÄ± sensor okuma zamanÄ±
    const unsigned long SENSOR_TIMEOUT = 10000;  // 10 saniye - bu sÃ¼re geÃ§erse uyarÄ± ver

    // SensÃ¶r saÄŸlÄ±k durumu takibi (consecutive fail sayÄ±sÄ±)
    int _tempSensorFailCount;      // SÄ±caklÄ±k sensÃ¶rÃ¼ Ã¼st Ã¼ste baÅŸarÄ±sÄ±z okuma sayÄ±sÄ±
    int _magneticSensorFailCount;  // Manyetik sensÃ¶r Ã¼st Ã¼ste baÅŸarÄ±sÄ±z okuma sayÄ±sÄ±
    int _currentSensorFailCount;   // AkÄ±m sensÃ¶rÃ¼ Ã¼st Ã¼ste baÅŸarÄ±sÄ±z okuma sayÄ±sÄ±
    bool _tempSensorCritical;      // SÄ±caklÄ±k sensÃ¶rÃ¼ kritik durumda mÄ±?
    bool _magneticSensorCritical;  // Manyetik sensÃ¶r kritik durumda mÄ±?
    bool _currentSensorCritical;    // AkÄ±m sensÃ¶rÃ¼ kritik durumda mÄ±?
    const int MAX_CONSECUTIVE_FAILS = 10;  // 10 okuma Ã¼st Ã¼ste baÅŸarÄ±sÄ±z olursa kritik

    // SensÃ¶r okuma zamanlayÄ±cÄ±larÄ±
    unsigned long _lastSensorRead;
    const unsigned long SENSOR_INTERVAL = 1000;  // 1000ms = 1Hz

    // YardÄ±mcÄ± fonksiyonlar
    bool _initMLX90614Safely();
    bool _initMLX90393Safely();
    void _initACS712Safely();
    void _calibrateACS712();
    void _processMLX90614StateMachine();
    void _processMLX90393StateMachine();
    void _triggerSensorStateMachines();
    void _readCurrent();
    bool _testMLX90614Reading();
    bool _testMLX90393Reading();
    void _scanI2CDevices();

    // I2C Bus Recovery
    void _clearI2CBus();
    bool _isI2CBusStuck();
    bool _hardResetI2C();  // DonanÄ±m seviyesi hard reset

    // SensÃ¶r saÄŸlÄ±k durumu kontrolÃ¼
    void _checkSensorHealth();

    // I2C recovery
    void recoverI2CBus();
    void _deriveSensitivity();
    float _applyFilter(float newValue, float& filteredValue);

    // Utility
    unsigned long safeMillisDiff(unsigned long current, unsigned long previous);
};

#endif
