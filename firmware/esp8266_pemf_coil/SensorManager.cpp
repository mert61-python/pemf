#include "SensorManager.h"
#include "NetworkManager.h"  // publishEvent() iÃ§in gerekli
#include <math.h>
#include <limits.h>  // ULONG_MAX iÃ§in gerekli

const int SENSOR_RETRY_COUNT = 3;
const unsigned long MLX90614_READ_DELAY = 10;  // 10ms bekleme sÃ¼resi
const unsigned long MLX90393_READ_DELAY = 5;   // 5ms bekleme sÃ¼resi
const int MAX_SENSOR_ERRORS = 100;

SensorManager::SensorManager(int currentPin, int sdaPin, int sclPin) {
    _currentPin = currentPin;
    _sdaPin = sdaPin;
    _sclPin = sclPin;
    _acs712Offset = 2.5;  // VarsayÄ±lan offset
    _acs712Calibrated = false;
    _mlx90614Initialized = false;
    _mlx90393Initialized = false;
    _initializedWithoutCalibration = false;

    _mlx90614State = MLX90614_IDLE;
    _mlx90393State = MLX90393_IDLE;
    _mlx90614RequestTime = 0;
    _mlx90393RequestTime = 0;
    _mlx90393RetryCount = 0;
    _lastSensorRead = 0;

    _tempObjectFiltered = 30.0f;
    _tempAmbientFiltered = 25.0f;
    _magFieldFiltered = 0.0f;
    _currentFiltered = 0.0f;

    // Hata sayacÄ± sÄ±fÄ±rla
    for (int i = 0; i < 3; i++) {
        _sensorErrorCount[i] = 0;
    }

    // SensÃ¶r saÄŸlÄ±k durumu takibi sÄ±fÄ±rla
    _tempSensorFailCount = 0;
    _magneticSensorFailCount = 0;
    _currentSensorFailCount = 0;
    _tempSensorCritical = false;
    _magneticSensorCritical = false;
    _currentSensorCritical = false;

    // SensorData sÄ±fÄ±rla
    _data.tempObject = 0.0;
    _data.tempAmbient = 0.0;
    _data.magneticField = 0.0;
    _data.current = 0.0;
    _data.magX = 0.0;
    _data.magY = 0.0;
    _data.magZ = 0.0;
    _data.maxMagneticField = 0.0;
    _data.maxCurrent = 0.0;
    _data.temp_sensor_ok = false;
    _data.magnetic_sensor_ok = false;
    _data.current_sensor_ok = true;
    _data.sensorsOK = false;
    _data.allSensorsOk = false;
}

void SensorManager::begin() {
    beginWithoutCalibration();
    calibrate();
}

void SensorManager::beginWithoutCalibration() {
    if (_initializedWithoutCalibration) return;

    LOG_PRINTLN("==========================================");
    LOG_PRINTLN("GÃœVENLÄ° SENSÃ–R BAÅžLATMA SÄ°STEMÄ° (Adım 1)");
    LOG_PRINTLN("==========================================");

    // 0. I2C bus kontrolÃ¼ ve temizliÄŸi
    LOG_PRINTLN("0. I2C bus durumu kontrol ediliyor...");
    if (_isI2CBusStuck()) {
        _clearI2CBus();
    } else {
        LOG_PRINTLN("âœ“ I2C bus temiz");
    }

    // 1. I2C baÄŸlantÄ±sÄ±nÄ± yeniden baÅŸlat
    LOG_PRINTLN("1. I2C baÄŸlantÄ±sÄ± yeniden baÅŸlatÄ±lÄ±yor...");
    Wire.begin(_sdaPin, _sclPin);  // SDA, SCL
    Wire.setClock(100000L);
    delay(200);
    LOG_PRINTLN("âœ“ I2C baÄŸlantÄ±sÄ± hazÄ±r");

    // 2. MLX90614 SÄ±caklÄ±k SensÃ¶rÃ¼ (Ã–ncelikli)
    LOG_PRINTLN("2. MLX90614 sÄ±caklÄ±k sensÃ¶rÃ¼ baÅŸlatÄ±lÄ±yor...");
    bool mlx90614OK = _initMLX90614Safely();
    _mlx90614Initialized = mlx90614OK;

    // 3. MLX90393 Manyetik Alan SensÃ¶rÃ¼
    LOG_PRINTLN("3. MLX90393 manyetik alan sensÃ¶rÃ¼ baÅŸlatÄ±lÄ±yor...");
    bool mlx90393OK = _initMLX90393Safely();
    _mlx90393Initialized = mlx90393OK;

    // 4. ACS712 AkÄ±m SensÃ¶rÃ¼ (Analog - her zaman hazÄ±r)
    LOG_PRINTLN("4. ACS712 akÄ±m sensÃ¶rÃ¼ hazÄ±rlanÄ±yor...");
    _initACS712Safely();

    _initializedWithoutCalibration = true;
    LOG_PRINTLN("Adım 1: Sensörler başlatıldı (Kalibrasyon Bekliyor)");
}

void SensorManager::calibrate() {
    if (!_initializedWithoutCalibration) {
         beginWithoutCalibration();
    }

    LOG_PRINTLN("5. ACS712 offset kalibrasyonu yapÄ±lÄ±yor...");
    _calibrateACS712();
    _deriveSensitivity();

    // 6. SensÃ¶r durumu Ã¶zeti
    LOG_PRINTLN("==========================================");
    LOG_PRINTLN("SENSÃ–R BAÅžLATMA Ã–ZETÄ°:");
    LOG_PRINTF("MLX90614 (SÄ±caklÄ±k): %s\n", _mlx90614Initialized ? "âœ“ HAZIR" : "âœ— HATA");
    LOG_PRINTF("MLX90393 (Manyetik): %s\n", _mlx90393Initialized ? "âœ“ HAZIR" : "âœ— HATA (AtlandÄ±)");
    LOG_PRINTLN("ACS712 (AkÄ±m): âœ“ HAZIR");

    if (!_mlx90614Initialized && !_mlx90393Initialized) {
        LOG_PRINTLN("==========================================");
        LOG_PRINTLN("âš  SENSÃ–RSÃœZ MOD AKTÄ°F");
        LOG_PRINTLN("   Sistem sadece PWM kontrolÃ¼ yapacak.");
        LOG_PRINTLN("   SensÃ¶r verileri fallback deÄŸerleri kullanacak.");
        LOG_PRINTLN("==========================================");
    } else {
        LOG_PRINTLN("==========================================");
    }
}

void SensorManager::update() {
    // I2C SensÃ¶r Durum Makineleri (Non-blocking)
    _processMLX90614StateMachine();
    _processMLX90393StateMachine();

    // SensÃ¶r okumalarÄ±nÄ± baÅŸlat (1Hz)
    if (safeMillisDiff(millis(), _lastSensorRead) > SENSOR_INTERVAL) {
        _triggerSensorStateMachines();  // Durum makinelerini tetikler

        // AKIM Ã–LÃ‡ÃœMÃœ (10 Ã¶rnek al ve RMS hesapla)
        _readCurrent();

        // SensÃ¶r saÄŸlÄ±k durumu takibi
        _checkSensorHealth();

        _lastSensorRead = millis();
    }
}

SensorData SensorManager::getData() {
    // Kritik durumda fallback deÄŸerleri KULLANMA, NaN dÃ¶n
    if (_tempSensorCritical) {
        _data.tempObject = NAN;
        _data.tempAmbient = NAN;
    } else if (!_data.temp_sensor_ok) {
        // Kritik deÄŸil ama baÅŸarÄ±sÄ±z - fallback kullan (geÃ§ici hata)
        _data.tempObject = _tempObjectFiltered;
        _data.tempAmbient = _tempAmbientFiltered;
        LOG_PRINTLN("[SENSOR] âš ï¸ SÄ±caklÄ±k sensÃ¶rÃ¼ baÅŸarÄ±sÄ±z, fallback deÄŸerler kullanÄ±lÄ±yor");
    }

    if (_magneticSensorCritical) {
        _data.magneticField = NAN;
    } else if (!_data.magnetic_sensor_ok) {
        // Kritik deÄŸil ama baÅŸarÄ±sÄ±z - fallback kullan (geÃ§ici hata)
        _data.magneticField = _magFieldFiltered / 1000.0f;
        LOG_PRINTLN("[SENSOR] âš ï¸ Manyetik sensÃ¶r baÅŸarÄ±sÄ±z, fallback deÄŸerler kullanÄ±lÄ±yor");
    }

    if (_currentSensorCritical) {
        _data.current = NAN;
    } else if (!_data.current_sensor_ok) {
        // Kritik deÄŸil ama baÅŸarÄ±sÄ±z - fallback kullan (geÃ§ici hata)
        _data.current = _currentFiltered;
        LOG_PRINTLN("[SENSOR] âš ï¸ AkÄ±m sensÃ¶rÃ¼ baÅŸarÄ±sÄ±z, fallback deÄŸerler kullanÄ±lÄ±yor");
    }

    return _data;
}

void SensorManager::setPWMActive(bool active) {
    _pwmActive = active;
    if (!active) {
        _data.maxMagneticField = 0;
        _data.maxCurrent = 0;
    }
}

bool SensorManager::isReady() {
    // En az bir sensÃ¶r baÅŸarÄ±lÄ± olmalÄ±
    bool hasValidData = _data.temp_sensor_ok || _data.magnetic_sensor_ok || _data.current_sensor_ok;

    if (!hasValidData) {
        LOG_PRINTLN("[SENSOR] âœ— TÃ¼m sensÃ¶rler baÅŸarÄ±sÄ±z!");
    }

    return hasValidData;
}

void SensorManager::populateStatus(StatusData& data) {
    data.sensors_ok = _data.sensorsOK;
    data.temp_sensor_ok = _data.temp_sensor_ok;
    data.magnetic_sensor_ok = _data.magnetic_sensor_ok;
    data.current_sensor_ok = _data.current_sensor_ok;
}

bool SensorManager::_initMLX90614Safely() {
    LOG_PRINTLN("  MLX90614 sÄ±caklÄ±k sensÃ¶rÃ¼ baÅŸlatÄ±lÄ±yor...");

    for (int attempt = 1; attempt <= SENSOR_RETRY_COUNT; attempt++) {
        LOG_PRINTF("  Deneme %d/%d...\n", attempt, SENSOR_RETRY_COUNT);
                // I2C cihaz kontrolü (exception önleme)
        Wire.beginTransmission(0x5A); // MLX90614 default adres
        uint8_t error = Wire.endTransmission();

        if (error != 0) {
            LOG_PRINTF("  ⚠ I2C adresinde (0x5A) cihaz bulunamadı (hata kodu: %d)\n", error);
            delay(500);
            ESP.wdtFeed();
            continue;
        }

        yield(); // Watchdog besle
                // I2C tarama (debug iÃ§in)
        _scanI2CDevices();

        // MLX90614 baÅŸlat
        if (_mlxTemp.begin()) {
            LOG_PRINTLN("  âœ“ MLX90614 baÄŸlantÄ±sÄ± baÅŸarÄ±lÄ±");

            // SensÃ¶r kalibrasyonu iÃ§in bekle
            delay(1000);

            // Ä°lk okuma testi
            if (_testMLX90614Reading()) {
                LOG_PRINTLN("  âœ“ MLX90614 okuma testi baÅŸarÄ±lÄ±");
                return true;
            } else {
                LOG_PRINTLN("  âš  MLX90614 okuma testi baÅŸarÄ±sÄ±z, yeniden denenecek");
                delay(500);
            }
        } else {
            LOG_PRINTF("  âœ— MLX90614 baÅŸlatma baÅŸarÄ±sÄ±z (deneme %d)\n", attempt);
            delay(1000);
        }

        ESP.wdtFeed();
    }

    LOG_PRINTLN("  âœ— MLX90614 baÅŸlatÄ±lamadÄ±, fallback deÄŸerler kullanÄ±lacak");
    return false;
}

bool SensorManager::_initMLX90393Safely() {
    LOG_PRINTLN("  MLX90393 manyetik alan sensÃ¶rÃ¼ baÅŸlatÄ±lÄ±yor...");

    for (int attempt = 1; attempt <= SENSOR_RETRY_COUNT; attempt++) {
        LOG_PRINTF("  Deneme %d/%d...\n", attempt, SENSOR_RETRY_COUNT);
                // I2C cihaz kontrolü (exception önleme)
        Wire.beginTransmission(0x18);
        uint8_t error = Wire.endTransmission();

        if (error != 0) {
            LOG_PRINTF("  ⚠ I2C adresinde (0x18) cihaz bulunamadı (hata kodu: %d)\n", error);
            delay(500);
            ESP.wdtFeed();
            continue;
        }

        yield(); // Watchdog besle
                if (_mlxMag.begin_I2C(0x18)) {
            LOG_PRINTLN("  âœ“ MLX90393 baÄŸlantÄ±sÄ± baÅŸarÄ±lÄ±");

            // SensÃ¶r ayarlarÄ±
            _mlxMag.setGain(MLX90393_GAIN_1X);
            _mlxMag.setResolution(MLX90393_X, MLX90393_RES_16);
            _mlxMag.setResolution(MLX90393_Y, MLX90393_RES_16);
            _mlxMag.setResolution(MLX90393_Z, MLX90393_RES_16);
            _mlxMag.setFilter(MLX90393_FILTER_1);

            // Kalibrasyon iÃ§in bekle
            delay(1000);

            // Ä°lk okuma testi
            if (_testMLX90393Reading()) {
                LOG_PRINTLN("  âœ“ MLX90393 okuma testi baÅŸarÄ±lÄ±");
                return true;
            } else {
                LOG_PRINTLN("  âš  MLX90393 okuma testi baÅŸarÄ±sÄ±z, yeniden denenecek");
                delay(500);
            }
        } else {
            LOG_PRINTF("  âœ— MLX90393 baÅŸlatma baÅŸarÄ±sÄ±z (deneme %d)\n", attempt);
            delay(1000);
        }

        ESP.wdtFeed();
    }

    LOG_PRINTLN("  âœ— MLX90393 baÅŸlatÄ±lamadÄ±, fallback deÄŸerler kullanÄ±lacak");
    return false;
}

void SensorManager::_initACS712Safely() {
    LOG_PRINTLN("  ACS712 akÄ±m sensÃ¶rÃ¼ hazÄ±rlanÄ±yor...");

    // Analog pin okuma testi
    float totalVoltage = 0;

    for (int i = 0; i < 10; i++) {
        int rawValue = analogRead(_currentPin);
        float voltage = (rawValue / 1023.0) * 3.3;
        totalVoltage += voltage;
        delay(100);
    }

    float avgVoltage = totalVoltage / 10;
    LOG_PRINTF("  âœ“ ACS712 ortalama voltaj: %.3fV (beklenen: ~2.5V)\n", avgVoltage);

    if (avgVoltage > 0.5 && avgVoltage < 3.0) {
        LOG_PRINTLN("  âœ“ ACS712 akÄ±m sensÃ¶rÃ¼ hazÄ±r");
    } else {
        LOG_PRINTLN("  âš  ACS712 voltaj deÄŸeri anormal, kontrol edin");
    }
}

void SensorManager::_calibrateACS712() {
    if (_acs712Calibrated) {
        return;  // Zaten kalibre edilmiÅŸ
    }

    LOG_PRINTLN("[ACS712] Offset kalibrasyonu yapÄ±lÄ±yor (akÄ±m olmadan)...");

    // 100 okuma al ve ortalamasÄ±nÄ± hesapla
    float sumVoltage = 0;
    for (int i = 0; i < 100; i++) {
        int rawValue = analogRead(_currentPin);
        float voltage = (rawValue / 1023.0) * 3.3;
        sumVoltage += voltage;
        delay(10);
        ESP.wdtFeed();
    }

    _acs712Offset = sumVoltage / 100.0;
    _acs712Calibrated = true;

    LOG_PRINTF("[ACS712] Kalibrasyon tamamlandÄ±, offset: %.3fV\n", _acs712Offset);
}

void SensorManager::_processMLX90614StateMachine() {
    unsigned long currentTime = millis();

    switch (_mlx90614State) {
        case MLX90614_IDLE:
            // Durum makinesi tetiklendiÄŸinde REQUESTED'e geÃ§er
            break;

        case MLX90614_REQUESTED:
            // 10ms geÃ§ti mi kontrol et
            if (safeMillisDiff(currentTime, _mlx90614RequestTime) >= MLX90614_READ_DELAY) {
                // OkumayÄ± yap
                float rawObjectTemp = _mlxTemp.readObjectTempC();
                float rawAmbientTemp = _mlxTemp.readAmbientTempC();

                if (!isnan(rawObjectTemp) && !isnan(rawAmbientTemp)) {
                    // GeÃ§erli aralÄ±k kontrolÃ¼
                    if (rawObjectTemp >= -40.0 && rawObjectTemp <= 400.0 &&
                        rawAmbientTemp >= -40.0 && rawAmbientTemp <= 125.0) {
                        _data.tempObject = rawObjectTemp;
                        _data.tempAmbient = rawAmbientTemp;
                        _lastGoodValues[0] = _data.tempObject;
                        _lastGoodValues[1] = _data.tempAmbient;
                        _sensorErrorCount[0] = 0;
                        _data.temp_sensor_ok = true;
                    } else {
                        // GeÃ§ersiz deÄŸer
                        _data.temp_sensor_ok = false;
                    }
                } else {
                    // Okuma baÅŸarÄ±sÄ±z
                    _data.temp_sensor_ok = false;
                }

                _mlx90614State = MLX90614_IDLE;
            }
            break;

        default:
            _mlx90614State = MLX90614_IDLE;
            break;
    }
}

void SensorManager::_processMLX90393StateMachine() {
    unsigned long currentTime = millis();

    switch (_mlx90393State) {
        case MLX90393_IDLE:
            // Durum makinesi tetiklendiÄŸinde REQUESTED'e geÃ§er
            break;

        case MLX90393_REQUESTED:
            // 5ms geÃ§ti mi kontrol et
            if (safeMillisDiff(currentTime, _mlx90393RequestTime) >= MLX90393_READ_DELAY) {
                // OkumayÄ± yap
                _mlx90393State = MLX90393_READING;
                float x, y, z;
                if (_mlxMag.readData(&x, &y, &z)) {
                    float magnitude = sqrt(x*x + y*y + z*z);
                    _data.magneticField = magnitude / 1000.0;  // ÂµT'den mT'ye
                    _lastGoodValues[2] = x;
                    _lastGoodValues[3] = y;
                    _lastGoodValues[4] = z;
                    _sensorErrorCount[1] = 0;
                    _data.magnetic_sensor_ok = true;
                    _mlx90393State = MLX90393_IDLE;
                } else {
                    // Okuma baÅŸarÄ±sÄ±z, retry
                    _mlx90393RetryCount++;
                    if (_mlx90393RetryCount < SENSOR_RETRY_COUNT) {
                        _mlx90393RequestTime = currentTime;  // Yeniden bekle
                        _mlx90393State = MLX90393_REQUESTED;
                    } else {
                        // Maksimum retry sayÄ±sÄ±na ulaÅŸÄ±ldÄ±
                        _sensorErrorCount[1]++;
                        _data.magnetic_sensor_ok = false;
                        _mlx90393State = MLX90393_IDLE;
                    }
                }
            }
            break;

        case MLX90393_READING:
            // Bu durum sadece geÃ§iÅŸ iÃ§in, hemen IDLE'a dÃ¶n
            _mlx90393State = MLX90393_IDLE;
            break;

        default:
            _mlx90393State = MLX90393_IDLE;
            break;
    }
}

void SensorManager::_triggerSensorStateMachines() {
    // MLX90614 okumasÄ±nÄ± baÅŸlat (eÄŸer IDLE durumundaysa ve initialize edilmişse)
    if (_mlx90614Initialized && _mlx90614State == MLX90614_IDLE) {
        _mlx90614RequestTime = millis();
        _mlx90614State = MLX90614_REQUESTED;
    }

    // MLX90393 okumasÄ±nÄ± baÅŸlat (eÄŸer IDLE durumundaysa ve initialize edilmişse)
    if (_mlx90393Initialized && _mlx90393State == MLX90393_IDLE) {
        _mlx90393RequestTime = millis();
        _mlx90393State = MLX90393_REQUESTED;
        _mlx90393RetryCount = 0;
    }

    // Genel durum (geriye dÃ¶nÃ¼k uyumluluk iÃ§in)
    // Eğer sensörler initialize edilmemişse OK sayma
    bool tempOK = _mlx90614Initialized ? _data.temp_sensor_ok : true; // Init edilmediyse, bu kontrolü pass geçmek için true diyemeyiz, ama genel sağlık için sensörsüz modda false olması beklenir mi?
    // Kullanıcı sensörsüz mod istiyor. Eğer init edilmediyse, sensorsOK false mu olmalı true mu?
    // Kullanıcı "sensörsüz de kullanabilmek istiyorum" dedi.
    // Ancak sensorsOK flag'i genellikle sistemin sağlıklı çalışıp çalışmadığını gösterir.
    // Sensörsüz modda bu flag ne ifade etmeli?
    // Mevcut kodda _data.sensorsOK = ... ile hesaplanıyor.

    // Eğer sensör yoksa, "var olan sensörler OK mi?" diye bakmak daha mantıklı.
    // Veya sensör modu aktif değilse false mu dönmeli?
    // Kullanıcı arayüzünde "Sensörler OK" görmek isteyebilir mi?

    // Mevcut mantığı koruyarak sadece init edilmiş olanları kontrol edelim.
    // Init edilmemişse fail kabul etmek yerine, logic'i bozmayalım.

    _data.sensorsOK = (_mlx90614Initialized ? _data.temp_sensor_ok : true) &&
                      (_mlx90393Initialized ? _data.magnetic_sensor_ok : true) &&
                      _data.current_sensor_ok;
}

void SensorManager::_readCurrent() {
    // AKIM Ã–LÃ‡ÃœMÃœ (10 Ã¶rnek al ve RMS hesapla)
    float sumOfSquares = 0.0;
    int sampleCount = 10;

    for (int i = 0; i < sampleCount; i++) {
        int rawValue = analogRead(_currentPin);
        float voltage = (rawValue / 1023.0) * 3.3;  // 3.3V referans (0-1023 ADC)
        // ACS712-30A: 66mV/A, kalibre edilmiÅŸ offset kullan
        float current = (voltage - _acs712Offset) / 0.066;
        sumOfSquares += current * current;
        delayMicroseconds(100); // Ã–rnekler arasÄ±na Ã§ok az bekleme ekle (~100Âµs)
    }

    // RMS (Root Mean Square) hesaplama - PWM sinyali iÃ§in etkin akÄ±m deÄŸeri
    float meanSquare = sumOfSquares / sampleCount;
    _data.current = sqrt(meanSquare);
    _lastGoodValues[5] = _data.current; // Fallback deÄŸerini gÃ¼ncelle
    _data.current_sensor_ok = true;
}

void SensorManager::_deriveSensitivity() {
    float k = _acs712Offset / 2.5f;             // Bölücü oranı
    _acsSensitivity = 0.066f * k;               // [V/A]
}

float SensorManager::_applyFilter(float newValue, float& filteredValue) {
    if (isnan(filteredValue) || filteredValue == 0.0f) {
        filteredValue = newValue;
    } else {
        filteredValue = (FILTER_ALPHA * newValue) + ((1.0f - FILTER_ALPHA) * filteredValue);
    }
    return filteredValue;
}

void SensorManager::recoverI2CBus() {
    _clearI2CBus(); // _clearI2CBus already handles ESP8266 appropriate actions
}

bool SensorManager::_testMLX90614Reading() {
    LOG_PRINTLN("    MLX90614 okuma testi yapÄ±lÄ±yor...");

    for (int test = 0; test < 5; test++) {
        float objectTemp = _mlxTemp.readObjectTempC();
        float ambientTemp = _mlxTemp.readAmbientTempC();

        LOG_PRINTF("    Test %d: Nesne=%.2fÂ°C, Ortam=%.2fÂ°C\n", test+1, objectTemp, ambientTemp);

        // GeÃ§erli sÄ±caklÄ±k aralÄ±ÄŸÄ± kontrolÃ¼
        if (isnan(objectTemp) || isnan(ambientTemp)) {
            LOG_PRINTLN("    âœ— NaN deÄŸer okundu");
            continue;
        }

        if (objectTemp < -40 || objectTemp > 400) {
            LOG_PRINTF("    âœ— Nesne sÄ±caklÄ±ÄŸÄ± anormal: %.2fÂ°C\n", objectTemp);
            continue;
        }

        if (ambientTemp < -40 || ambientTemp > 125) {
            LOG_PRINTF("    âœ— Ortam sÄ±caklÄ±ÄŸÄ± anormal: %.2fÂ°C\n", ambientTemp);
            continue;
        }

        // Ä°lk geÃ§erli okumayÄ± kabul et
        if (test >= 2) {  // En az 3 test yap
            LOG_PRINTLN("    âœ“ MLX90614 okuma testi baÅŸarÄ±lÄ±");
            return true;
        }

        delay(500);
    }

    LOG_PRINTLN("    âœ— MLX90614 okuma testi baÅŸarÄ±sÄ±z");
    return false;
}

bool SensorManager::_testMLX90393Reading() {
    LOG_PRINTLN("    MLX90393 okuma testi yapÄ±lÄ±yor...");

    for (int test = 0; test < 3; test++) {
        float x, y, z;
        if (_mlxMag.readData(&x, &y, &z)) {
            float magnitude = sqrt(x*x + y*y + z*z);
            LOG_PRINTF("    Test %d: X=%.2f, Y=%.2f, Z=%.2f, Mag=%.2f ÂµT\n",
                        test+1, x, y, z, magnitude);

            // GeÃ§erli manyetik alan aralÄ±ÄŸÄ± kontrolÃ¼
            if (magnitude > 0 && magnitude < 100000) {  // 0-100mT aralÄ±ÄŸÄ±
                LOG_PRINTLN("    âœ“ MLX90393 okuma testi baÅŸarÄ±lÄ±");
                return true;
            }
        }

        delay(500);
    }

    LOG_PRINTLN("    âœ— MLX90393 okuma testi baÅŸarÄ±sÄ±z");
    return false;
}

void SensorManager::_scanI2CDevices() {
    LOG_PRINTLN("  I2C cihazlarÄ± taranÄ±yor...");
    int deviceCount = 0;

    for (byte address = 1; address < 127; address++) {
        Wire.beginTransmission(address);
        byte error = Wire.endTransmission();

        if (error == 0) {
            LOG_PRINTF("  I2C cihaz bulundu: 0x%02X\n", address);
            deviceCount++;
        }
    }

    if (deviceCount == 0) {
        LOG_PRINTLN("  âš  HiÃ§ I2C cihaz bulunamadÄ±!");
    } else {
        LOG_PRINTF("  âœ“ %d I2C cihaz bulundu\n", deviceCount);
    }
}

unsigned long SensorManager::safeMillisDiff(unsigned long current, unsigned long previous) {
    // millis() overflow durumunda doÄŸru farkÄ± hesapla
    if (current >= previous) {
        return current - previous;
    } else {
        // Overflow olmuÅŸ
        return (ULONG_MAX - previous) + current + 1;
    }
}

bool SensorManager::_isI2CBusStuck() {
    pinMode(_sdaPin, INPUT_PULLUP);
    pinMode(_sclPin, INPUT_PULLUP);
    delay(1);

    bool sdaLow = (digitalRead(_sdaPin) == LOW);
    bool sclLow = (digitalRead(_sclPin) == LOW);

    if (sdaLow || sclLow) {
        LOG_PRINTF("  [I2C] Bus durumu - SDA: %s, SCL: %s\n",
                   sdaLow ? "LOW(kilitli)" : "HIGH(normal)",
                   sclLow ? "LOW(kilitli)" : "HIGH(normal)");
        return true;
    }
    return false;
}

void SensorManager::_clearI2CBus() {
    LOG_PRINTLN("  [I2C] Bus temizliÄŸi baÅŸlatÄ±lÄ±yor...");

    // 1. Ã–nce soft recovery dene (clock cycle method)
    // Pinleri manuel kontrol iÃ§in yapÄ±landÄ±r (ESP8266'da Wire.end() yok)
    pinMode(_sdaPin, INPUT_PULLUP);
    pinMode(_sclPin, INPUT_PULLUP);
    delay(10);

    // 2. SDA durumunu kontrol et
    pinMode(_sclPin, OUTPUT);
    digitalWrite(_sclPin, LOW);  // SCL'i LOW yap

    bool sdaStuck = (digitalRead(_sdaPin) == LOW);

    if (sdaStuck) {
        LOG_PRINTLN("  [I2C] âš ï¸ SDA hattÄ± LOW'da takÄ±lÄ±, soft recovery deneniyor...");

        // 3. 9 clock cycle gÃ¶nder (I2C spec: maksimum byte uzunluÄŸu)
        for (int i = 0; i < 9; i++) {
            digitalWrite(_sclPin, HIGH);
            delayMicroseconds(5);  // 100kHz iÃ§in 5Î¼s
            digitalWrite(_sclPin, LOW);
            delayMicroseconds(5);

            // Her cycle'da SDA durumunu kontrol et
            if (digitalRead(_sdaPin) == HIGH) {
                LOG_PRINTF("  [I2C] âœ“ SDA soft recovery ile serbest bÄ±rakÄ±ldÄ± (%d. cycle)\n", i + 1);
                sdaStuck = false;
                break;
            }
        }

        // 4. STOP condition oluÅŸtur (SDA: LOWâ†’HIGH while SCL: HIGH)
        if (sdaStuck) {
            pinMode(_sdaPin, OUTPUT);
            digitalWrite(_sdaPin, LOW);
            delayMicroseconds(5);
            digitalWrite(_sclPin, HIGH);
            delayMicroseconds(5);
            digitalWrite(_sdaPin, HIGH);
            delayMicroseconds(10);

            // Son kontrol
            pinMode(_sdaPin, INPUT_PULLUP);
            if (digitalRead(_sdaPin) == HIGH) {
                LOG_PRINTLN("  [I2C] âœ“ Bus soft recovery ile temizlendi");
                sdaStuck = false;
            }
        }

        // 5. Soft recovery baÅŸarÄ±sÄ±zsa hard reset dene
        if (sdaStuck) {
            LOG_PRINTLN("  [I2C] âš ï¸ Soft recovery baÅŸarÄ±sÄ±z, hard reset deneniyor...");
            if (_hardResetI2C()) {
                LOG_PRINTLN("  [I2C] âœ“ Hard reset baÅŸarÄ±lÄ±!");
            } else {
                LOG_PRINTLN("  [I2C] âœ— Hard reset baÅŸarÄ±sÄ±z, donanÄ±m sorunu olabilir!");
            }
        }
    } else {
        LOG_PRINTLN("  [I2C] âœ“ Bus zaten temiz");
    }

    // 6. Wire'Ä± yeniden baÅŸlat
    // ESP8266'da Wire.end() yok, pinleri manuel reset yapÄ±yoruz
    // Pinleri Ã¶nce INPUT_PULLUP yap, sonra Wire.begin() Ã§aÄŸÄ±r
    pinMode(_sdaPin, INPUT_PULLUP);
    pinMode(_sclPin, INPUT_PULLUP);
    delay(10);  // Pinlerin stabilize olmasÄ± iÃ§in bekle

    // Wire instance'Ä± yeniden baÅŸlat (pinleri yeniden ata)
    Wire.begin(_sdaPin, _sclPin);
    Wire.setClock(100000L);  // 100kHz
    delay(100);  // I2C bus'Ä±n stabilize olmasÄ± iÃ§in bekle
}

bool SensorManager::_hardResetI2C() {
    LOG_PRINTLN("  [I2C] Hard reset baÅŸlatÄ±lÄ±yor...");

    // 1. Pinleri GPIO'ya Ã§evir (tam kontrol iÃ§in)
    pinMode(_sdaPin, OUTPUT);
    pinMode(_sclPin, OUTPUT);

    // 2. Her iki hattÄ± LOW yap (bus'Ä± zorla reset et)
    digitalWrite(_sdaPin, LOW);
    digitalWrite(_sclPin, LOW);
    delay(10);  // 10ms bekle (bus'Ä±n tamamen reset olmasÄ± iÃ§in)

    // 3. Her iki hattÄ± HIGH yap (pull-up'larÄ± aktif et)
    digitalWrite(_sdaPin, HIGH);
    digitalWrite(_sclPin, HIGH);
    delay(10);  // 10ms bekle (bus'Ä±n stabilize olmasÄ± iÃ§in)

    // 4. Pinleri INPUT_PULLUP moduna Ã§evir (normal I2C modu)
    pinMode(_sdaPin, INPUT_PULLUP);
    pinMode(_sclPin, INPUT_PULLUP);
    delay(10);  // Pinlerin stabilize olmasÄ± iÃ§in bekle

    // 5. Wire'Ä± tamamen yeniden baÅŸlat
    Wire.begin(_sdaPin, _sclPin);
    Wire.setClock(100000L);  // 100kHz
    delay(100);  // I2C bus'Ä±n stabilize olmasÄ± iÃ§in bekle

    // 6. Bus durumunu kontrol et
    return !_isI2CBusStuck();
}

void SensorManager::_checkSensorHealth() {
    // Eğer sensör initialize edilmemişse (Sensörsüz mod), sağlık kontrolünü atla

    // SÄ±caklÄ±k sensÃ¶rÃ¼ saÄŸlÄ±k kontrolÃ¼
    if (_mlx90614Initialized && !_data.temp_sensor_ok) {
        _tempSensorFailCount++;
        if (_tempSensorFailCount > MAX_CONSECUTIVE_FAILS && !_tempSensorCritical) {
            _tempSensorCritical = true;
            LOG_PRINTLN("[SENSOR] âœ— KRÄ°TÄ°K: SÄ±caklÄ±k sensÃ¶rÃ¼ offline (10 okuma Ã¼st Ã¼ste baÅŸarÄ±sÄ±z)");
            // NetworkManager'a eriÅŸim iÃ§in extern kullan
            extern NetworkManager* network;
            if (network) {
                network->publishEvent("sensor_critical", "Temperature sensor offline - 10 consecutive failures");
            }
            // NaN dÃ¶ndÃ¼r (fallback kullanma)
            _data.tempObject = NAN;
            _data.tempAmbient = NAN;
        }
    } else if (_mlx90614Initialized) {
        // BaÅŸarÄ±lÄ± okuma - fail count'u sÄ±fÄ±rla
        if (_tempSensorFailCount > 0) {
            LOG_PRINTF("[SENSOR] âœ“ SÄ±caklÄ±k sensÃ¶rÃ¼ geri geldi (fail count: %d)\n", _tempSensorFailCount);
            _tempSensorFailCount = 0;
            _tempSensorCritical = false;
        }
    }

    // Manyetik sensÃ¶r saÄŸlÄ±k kontrolÃ¼
    if (_mlx90393Initialized && !_data.magnetic_sensor_ok) {
        _magneticSensorFailCount++;
        if (_magneticSensorFailCount > MAX_CONSECUTIVE_FAILS && !_magneticSensorCritical) {
            _magneticSensorCritical = true;
            LOG_PRINTLN("[SENSOR] âœ— KRÄ°TÄ°K: Manyetik sensÃ¶r offline (10 okuma Ã¼st Ã¼ste baÅŸarÄ±sÄ±z)");
            extern NetworkManager* network;
            if (network) {
                network->publishEvent("sensor_critical", "Magnetic sensor offline - 10 consecutive failures");
            }
            // NaN dÃ¶ndÃ¼r (fallback kullanma)
            _data.magneticField = NAN;
        }
    } else if (_mlx90393Initialized) {
        // BaÅŸarÄ±lÄ± okuma - fail count'u sÄ±fÄ±rla
        if (_magneticSensorFailCount > 0) {
            LOG_PRINTF("[SENSOR] âœ“ Manyetik sensÃ¶r geri geldi (fail count: %d)\n", _magneticSensorFailCount);
            _magneticSensorFailCount = 0;
            _magneticSensorCritical = false;
        }
    }

    // AkÄ±m sensÃ¶rÃ¼ saÄŸlÄ±k kontrolÃ¼ (ACS712 genelde her zaman Ã§alÄ±ÅŸÄ±r, ama kontrol edelim)
    if (!_data.current_sensor_ok) {
        _currentSensorFailCount++;
        if (_currentSensorFailCount > MAX_CONSECUTIVE_FAILS && !_currentSensorCritical) {
            _currentSensorCritical = true;
            LOG_PRINTLN("[SENSOR] âœ— KRÄ°TÄ°K: AkÄ±m sensÃ¶rÃ¼ offline (10 okuma Ã¼st Ã¼ste baÅŸarÄ±sÄ±z)");
            extern NetworkManager* network;
            if (network) {
                network->publishEvent("sensor_critical", "Current sensor offline - 10 consecutive failures");
            }
            // NaN dÃ¶ndÃ¼r (fallback kullanma)
            _data.current = NAN;
        }
    } else {
        // BaÅŸarÄ±lÄ± okuma - fail count'u sÄ±fÄ±rla
        if (_currentSensorFailCount > 0) {
            LOG_PRINTF("[SENSOR] âœ“ AkÄ±m sensÃ¶rÃ¼ geri geldi (fail count: %d)\n", _currentSensorFailCount);
            _currentSensorFailCount = 0;
            _currentSensorCritical = false;
        }
    }
}
