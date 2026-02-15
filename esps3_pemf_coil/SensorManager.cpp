#include "SensorManager.h"

SensorManager::SensorManager() : _acsOffset(2.5) { 
    _tempOk = false;
    _magOk = false;
    _tempFailCount = 0;
    _magFailCount = 0;
    _currentFailCount = 0;
    
    // Initialize filtered values
    _tempObjectFiltered = 25.0;  // Room temperature default
    _tempAmbientFiltered = 25.0;
    _magFieldFiltered = 0.0;
    _currentFiltered = 0.0;
    
    // PWM tracking ve max değerler
    _pwmActive = false;
    _maxMagneticField = 0.0;
    _maxCurrent = 0.0;
}

void SensorManager::begin() {
    LOG_PRINTLN("[Core 1] SensorManager başlatılıyor...");
    
    // 1. ADC Yapılandırması (ESP32-S3) - PIN BAZLI ATTENUATION ZORÜNLU
    analogReadResolution(ADC_RESOLUTION_BITS); // 12-bit
    
    // ESP32-S3'te pin bazında attenuation ayarlanmalı
    analogSetPinAttenuation(PIN_CURRENT_ADC, ADC_11db); // 0-3.3V referans aralığı
    
    // 2. I2C Başlatma
    _initI2C();
    
    // 3. Akım Sensörü Kalibrasyonu
    _calibrateCurrent();
}

void SensorManager::_initI2C() {
    // 1. I2C Bus 0 (Wire) -> Sıcaklık (MLX90614) - 100 kHz
    // FIX: Adafruit_MLX90614 kütüphanesi begin() içinde Wire.begin() çağırıp pinleri sıfırlayabilir.
    // Bu yüzden önce setPins yapıyoruz.
    Wire.setPins(PIN_I2C_TEMP_SDA, PIN_I2C_TEMP_SCL);
    
    if (!Wire.begin(PIN_I2C_TEMP_SDA, PIN_I2C_TEMP_SCL, I2C_FREQ_TEMP)) {
        LOG_PRINTLN("[Error] I2C-0 (Temp) Başlatılamadı!");
    } else {
        // MLX90614 Varsayılan olarak "Wire" nesnesini kullanır.
        // Kullanıcı isteği üzerine adres 0x5A olarak sabitlendi.
        if (_mlxTemp.begin(0x5A, &Wire)) {
            _tempOk = true;
            LOG_PRINTLN("[Sensors] MLX90614 OK (I2C-0) Address: 0x5A");
        } else {
            // FIX: begin() başarısız olduysa tekrar pinleri ve clock'u zorla
            Wire.begin(PIN_I2C_TEMP_SDA, PIN_I2C_TEMP_SCL, I2C_FREQ_TEMP);
            delay(10);
            
            // Manuel ID kontrolü deneyebiliriz veya kütüphaneye tekrar şans verebiliriz
            LOG_PRINTLN("[Sensors] MLX90614 Bağlanamadı (I2C-0) - İlk deneme başarısız");
        }
    }

    // 2. I2C Bus 1 (Wire1) -> Manyetik (MLX90393) - 400 kHz
    // NOT: ESP32-S3'te 19/20 pinleri USB D-/D+ olduğu için çakışma yapabilir.
    // SharedDefs.h'de 5/6 olarak değiştirdik.
    Wire1.setPins(PIN_I2C_MAG_SDA, PIN_I2C_MAG_SCL);
    Wire1.begin(PIN_I2C_MAG_SDA, PIN_I2C_MAG_SCL, I2C_FREQ_MAG);
    
    // DEBUG: I2C-1 Scanner (Adres tespiti icin)
    LOG_PRINTLN("\n[I2C-1] Scanning I2C Bus for Mag Sensor...");
    int nDevices = 0;
    int foundAddress = 0;
    
    for(byte address = 1; address < 127; address++ ) {
        Wire1.beginTransmission(address);
        if (Wire1.endTransmission() == 0) {
            LOG_PRINTF("[I2C-1] Device found at address: 0x%02X\n", address);
            nDevices++;
            foundAddress = address; // Son bulunan adresi sakla
        }
    }
    
    if (nDevices == 0) {
        LOG_PRINTLN("[I2C-1] No devices found! Skipping Mag Sensor Init.");
        _magOk = false;
        return; // FIX: Cihaz yoksa MLX90393 başlatmayı deneme (Crash önleyici)
    }

    // MLX90393 Bağlantısı
    // Varsayılan Adres: 0x0C. 
    // Scanner 0x18 bulduysa (kullanicinin loglarina gore), onu dene.
    // Heap Corruption onlemi icin Wire1 cagrilari arasinda delay
    delay(50);
    
    // Algoritma: Once scanner ile bulunan adresi dene, yoksa default
    
    bool magFound = false;
    
    // Scanner ile bulunan adresi dene (Eğer mantıklı bir MLX adresi ise)
    if (foundAddress != 0) {
        if (_mlxMag.begin_I2C(foundAddress, &Wire1)) {
            LOG_PRINTF("[Sensors] MLX90393 OK (Address 0x%02X)\n", foundAddress);
            magFound = true;
        }
    }
    
    // Eğer scanner ile bulunan çalışmadıysa veya bulunamadıysa (ki yukarıda return ettik) standartları dene
    if (!magFound) {
        // 1. Deneme: 0x18 (Genelde modullerde jumper ile degisir)
        if (_mlxMag.begin_I2C(0x18, &Wire1)) {
            LOG_PRINTLN("[Sensors] MLX90393 OK (Address 0x18)");
            magFound = true;
        } 
        // 2. Deneme: 0x0C (Adafruit default)
        else if (!magFound && _mlxMag.begin_I2C(0x0C, &Wire1)) {
           LOG_PRINTLN("[Sensors] MLX90393 OK (Address 0x0C)");
           magFound = true;
        }
        // 3. Deneme: 0x19 (Alternatif)
        else if (!magFound && _mlxMag.begin_I2C(0x19, &Wire1)) {
           LOG_PRINTLN("[Sensors] MLX90393 OK (Address 0x19)");
           magFound = true;
        }
    }
    
    if (magFound) {
        _magOk = true;
        _mlxMag.setGain(MLX90393_GAIN_1X);
    } else {
        LOG_PRINTLN("[Sensors] MLX90393 Bağlanamadı (Scanner buldu ama Init başarısız)");
    }
}

void SensorManager::_calibrateCurrent() {
    // 50 örnek alıp ortalama (DC offset) hesapla
    float sum = 0;
    for(int i=0; i<50; i++) {
        sum += analogRead(PIN_CURRENT_ADC);
        delay(2);
    }
    // ADC Değeri üzerinden offset
    float avgAdc = sum / 50.0;
    // Voltaj Karşılığı: (ADC / 4095) * 3.3V
    // Yazılım varsayımı: ACS712 çıkışı ESP32 ADC sınırları içinde.
    _acsOffset = (avgAdc / 4095.0) * 3.3; 
    LOG_PRINTF("[Sensors] Akım Sensörü Offset: %.2f V\n", _acsOffset);
}

float SensorManager::_readCurrent() {
    // GELİŞMİŞ RMS AKİM HESABI - 100Hz PWM için optimize edildi
    // 
    // 100Hz PWM = 10ms periyot
    // 5 periyot ölçeceğiz = 50ms
    // 100 örnek / 50ms = her 500µs'de bir örnek
    // Bu şekilde 5 tam PWM periyodunu kapsarken yeterli örnekleme yapıyoruz
    
    float sumSquares = 0;
    int samples = CURRENT_SAMPLES;  // 100 örnek
    
    for(int i = 0; i < samples; i++) {
        int raw = analogRead(PIN_CURRENT_ADC);
        float voltage = (raw / 4095.0) * 3.3;
        
        // ACS712 hassasiyeti modele göre ayarlanıyor (SharedDefs.h)
        float instantaneousCurrent = (voltage - _acsOffset) / ACS712_SENSITIVITY; 
        sumSquares += instantaneousCurrent * instantaneousCurrent;
        
        delayMicroseconds(CURRENT_SAMPLE_US);  // 100µs bekleme
    }
    
    float rms = sqrt(sumSquares / samples);
    return rms; // Amper
}

SensorReadings SensorManager::readAll() {
    SensorReadings data;
    
    // 1. Sıcaklık
    if (_tempOk) {
        data.tempObject = _mlxTemp.readObjectTempC();
        data.tempAmbient = _mlxTemp.readAmbientTempC();
        data.tempSensorOk = !isnan(data.tempObject);
        
        if (data.tempSensorOk) {
            // Filtreleme kaldırıldı - ham veri kullanılıyor
            _tempFailCount = 0; // Başarılı okuma, sayacı sıfırla
        } else {
            _tempFailCount++;
            if (_tempFailCount == CRITICAL_FAIL_THRESHOLD) {
                LOG_PRINTLN("[CRITICAL] Temperature sensor offline - 10 consecutive failures");
            }
            // I2C Recovery eşiğine ulaştıysa bus recovery dene
            if (_tempFailCount == I2C_RECOVERY_THRESHOLD) {
                LOG_PRINTLN("[Sensors] Attempting I2C-0 bus recovery...");
                recoverI2CBus(0);
            }
        }
    } else {
        data.tempObject = 0;
        data.tempAmbient = 0;
        data.tempSensorOk = false;
    }
    
    // 2. Manyetik Alan
    if (_magOk) {
        float x, y, z;
        if (_mlxMag.readData(&x, &y, &z)) {
            // Magnitude hesabı (uT -> mT)
            float magnitude = sqrt(x*x + y*y + z*z) / 1000.0;
            data.magneticField = _applyFilter(magnitude, _magFieldFiltered);  // Filtering
            data.magSensorOk = true;
            _magFailCount = 0; // Başarılı okuma
        } else {
            data.magneticField = 0;
            data.magSensorOk = false;
            _magFailCount++;
            if (_magFailCount == CRITICAL_FAIL_THRESHOLD) {
                LOG_PRINTLN("[CRITICAL] Magnetic sensor offline - 10 consecutive failures");
            }
            // I2C Recovery eşiğine ulaştıysa bus recovery dene
            if (_magFailCount == I2C_RECOVERY_THRESHOLD) {
                LOG_PRINTLN("[Sensors] Attempting I2C-1 bus recovery...");
                recoverI2CBus(1);
            }
        }
    } else {
        data.magneticField = 0;
        data.magSensorOk = false;
    }
    
    // 3. Akım
    data.current = _readCurrent();
    data.current = _applyFilter(data.current, _currentFiltered);  // Filtering ekle
    data.currentSensorOk = true; // Analog her zaman okur
    
    data.allSensorsOk = data.tempSensorOk && data.magSensorOk && data.currentSensorOk;
    
    // PWM aktifken max değerleri güncelle
    if (_pwmActive) {
        if (data.magneticField > _maxMagneticField) {
            _maxMagneticField = data.magneticField;
        }
        if (data.current > _maxCurrent) {
            _maxCurrent = data.current;
        }
    }
    
    // Max değerleri struct'a kopyala
    data.maxMagneticField = _maxMagneticField;
    data.maxCurrent = _maxCurrent;
    
    // Sensör verilerini logla (her okumada değil, sadece debug için)
    static unsigned long lastLogTime = 0;
    if (millis() - lastLogTime > 10000) {  // 10 saniyede bir logla
        LOG_PRINTF("[Sensors] Bobin: %.1f°C, Ortam: %.1f°C, Mag: %.2f mT, Akım: %.2f A\n",
                   data.tempObject, data.tempAmbient, data.magneticField, data.current);
        if (_pwmActive) {
            LOG_PRINTF("[Sensors] Max -> Mag: %.2f mT, Akım: %.2f A\n", 
                       _maxMagneticField, _maxCurrent);
        }
        lastLogTime = millis();
    }
    
    return data;
}

// PWM durum bildirimi
void SensorManager::setPWMActive(bool active) {
    // PWM başladığında max değerleri sıfırla
    if (active && !_pwmActive) {
        _maxMagneticField = 0.0;
        _maxCurrent = 0.0;
        LOG_PRINTLN("[Sensors] PWM başladı - Max değerler sıfırlandı");
    }
    // PWM durduğunda max değerleri logla
    else if (!active && _pwmActive) {
        LOG_PRINTF("[Sensors] PWM durdu - Max Manyetik Alan: %.2f mT, Max Akım: %.2f A\n", 
                   _maxMagneticField, _maxCurrent);
    }
    _pwmActive = active;
}

// Exponential Moving Average Filter
float SensorManager::_applyFilter(float newValue, float& filteredValue) {
    filteredValue = (FILTER_ALPHA * newValue) + ((1.0 - FILTER_ALPHA) * filteredValue);
    return filteredValue;
}

// I2C Bus Recovery - Stuck bus durumunda reset
void SensorManager::recoverI2CBus(int busNumber) {
    LOG_PRINTF("[Sensors] I2C-%d Bus Recovery başlatılıyor...\n", busNumber);
    
    if (busNumber == 0) {
        Wire.end();
        delay(100);
        Wire.begin(PIN_I2C_TEMP_SDA, PIN_I2C_TEMP_SCL, I2C_FREQ_TEMP);
        delay(100);
        
        // Sensörü tekrar başlat
        if (_mlxTemp.begin(0x5A, &Wire)) {
            _tempOk = true;
            _tempFailCount = 0;
            LOG_PRINTLN("[Sensors] MLX90614 Re-initialized after bus recovery");
        }
    } else if (busNumber == 1) {
        Wire1.end();
        delay(100);
        Wire1.begin(PIN_I2C_MAG_SDA, PIN_I2C_MAG_SCL, I2C_FREQ_MAG);
        delay(100);
        
        // Standart adresleri tekrar dene
        const byte addresses[] = {0x0C, 0x18, 0x19};
        for (int i = 0; i < 3; i++) {
            if (_mlxMag.begin_I2C(addresses[i], &Wire1)) {
                _magOk = true;
                _magFailCount = 0;
                _mlxMag.setGain(MLX90393_GAIN_5X);
                _mlxMag.setOversampling(MLX90393_OSR_2);
                _mlxMag.setFilter(MLX90393_FILTER_7);
                LOG_PRINTF("[Sensors] MLX90393 Re-initialized (0x%02X) after bus recovery\n", addresses[i]);
                break;
            }
        }
    }
}
