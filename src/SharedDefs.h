#pragma once
#include <Arduino.h>
#include <IPAddress.h>

// ============================================================================
// ESP32-S3 ONLY - ESP8266 Support Removed
// ============================================================================
#ifndef ESP32
    #error "ESP32-S3 required! ESP8266 is no longer supported."
#endif

// Memory istatistikleri yapısı
struct MemoryStats {
    uint32_t freeHeap;          // Toplam boş heap (bytes)
    uint32_t maxAllocHeap;      // En büyük allocate edilebilir blok (bytes)
    uint8_t fragmentation;      // % fragmentation (0-100)
};

// Memory istatistikleri al (utility fonksiyon)
inline MemoryStats getMemoryStats() {
    MemoryStats stats;
    stats.freeHeap = ESP.getFreeHeap();
    stats.maxAllocHeap = ESP.getMaxAllocHeap();
    
    // Fragmentation hesapla
    if (stats.freeHeap > 0) {
        // Fragmentation = 100 - (maxAllocHeap * 100 / freeHeap)
        // Eğer maxAllocHeap freeHeap'e yakınsa, fragmentation düşük
        // Eğer maxAllocHeap çok küçükse, fragmentation yüksek
        stats.fragmentation = 100 - ((stats.maxAllocHeap * 100) / stats.freeHeap);
    } else {
        stats.fragmentation = 100;  // Heap tamamen dolu
    }
    
    return stats;
}

// Sensör veri yapısı
struct SensorData {
    float tempObject;
    float tempAmbient;
    float magneticField;  // mT
    float current;        // A
    bool temp_sensor_ok;
    bool magnetic_sensor_ok;
    bool current_sensor_ok;
    bool sensorsOK;  // Genel durum
};

// PWM durum yapısı
struct PWMStatus {
    bool active;
    int frequency;      // Hz
    int dutyCycle;     // %
    unsigned long remainingTime;  // ms (0 = süresiz)
};

// Sistem durum yapısı
struct StatusData {
    int coil_id;
    unsigned long timestamp;
    
    // WiFi durumu
    bool wifi_connected;
    char wifi_ssid[33];    // String yerine char array (max 32 karakter + null terminator)
    int wifi_rssi;
    char wifi_ip[16];      // String yerine char array (IPv4: "xxx.xxx.xxx.xxx" + null)
    bool portal_active;
    char portal_ip[16];    // String yerine char array
    char portal_ssid[33];  // String yerine char array
    
    // MQTT durumu
    bool mqtt_connected;
    
    // PWM durumu
    bool pwm_active;
    int pwm_frequency;
    int pwm_duty_cycle;
    int pwm_duration;  // dakika cinsinden (0 = süresiz)
    unsigned long long pwm_start_timestamp;  // Epoch milliseconds (0 = inactive)
    
    // Sensör durumu
    bool sensors_ok;
    bool temp_sensor_ok;
    bool magnetic_sensor_ok;
    bool current_sensor_ok;
    
    // Sistem durumu
    uint32_t free_heap;
    uint32_t max_alloc_heap;    // En büyük allocate edilebilir blok
    uint8_t fragmentation;      // % fragmentation (0-100)
    unsigned long uptime;
    bool cooling_down;
    bool safety_violation;
};

// MQTT mesaj callback tipi
// String yerine const char* kullanarak heap fragmentation'ı önle
typedef void (*MqttMessageCallback)(const char* topic, const char* payload);

// ============================================================================
// Logging Sistemi (Log Seviyeleri ve Debug Makroları)
// ============================================================================

// Log Seviyeleri
enum LogLevel {
    LOG_LEVEL_INFO,    // Sadece Seri Port (Buluta gitmez)
    LOG_LEVEL_WARN,    // Seri Port + Bulut
    LOG_LEVEL_ERROR    // Seri Port + Bulut (Alarm)
};

// Debug Modu Anahtarı (1: Açık, 0: Kapalı - Production)
#define DEBUG_MODE 1

#if DEBUG_MODE
    // Eğer DEBUG_MODE 1 ise, bu komutlar Serial komutlarına dönüşür
    #define LOG_PRINT(...)    Serial.print(__VA_ARGS__)
    #define LOG_PRINTLN(...)  Serial.println(__VA_ARGS__)
    #define LOG_PRINTF(...)   Serial.printf(__VA_ARGS__)
#else
    // Eğer DEBUG_MODE 0 ise, bu komutlar "boşluk" olur.
    // Derleyici burayı tamamen siler (zero overhead).
    #define LOG_PRINT(...)
    #define LOG_PRINTLN(...)
    #define LOG_PRINTF(...)
#endif

// ============================================================================
// Sensor Configuration Constants (Magic Numbers Eliminated)
// ============================================================================

namespace SensorConfig {
    // Sensor Recovery Thresholds
    constexpr int SOFT_RECOVERY_THRESHOLD = 5;        // Fail count for soft recovery
    constexpr int HARD_RECOVERY_THRESHOLD = 10;       // Fail count for hard recovery (critical)
    
    // I2C Timing
    constexpr int I2C_INIT_DELAY_MS = 100;           // Delay after I2C bus initialization
    constexpr int I2C_FAST_TIMEOUT_MS = 1500;        // Fast I2C timeout (400kHz)
    constexpr int I2C_SLOW_TIMEOUT_MS = 3000;        // Slow I2C timeout (100kHz)
    constexpr int I2C_BUS_CLEAR_DELAY_MS = 10;       // Delay during bus clearing
    constexpr int I2C_BUS_PROBE_DELAY_MS = 1;        // Delay for bus stuck detection
    
    // Sensor Calibration
    constexpr int SENSOR_CALIBRATION_DELAY_MS = 1000;  // Sensor warm-up time
    constexpr int SENSOR_TEST_DELAY_MS = 100;          // Delay between test readings
    constexpr int ACS712_CALIBRATION_SAMPLES = 100;    // Samples for offset calibration
    constexpr int ACS712_CALIBRATION_DELAY_MS = 10;    // Delay between calibration samples
    
    // Health Check
    constexpr unsigned long SENSOR_HEALTH_CHECK_INTERVAL_MS = 100;  // Health check throttle
    constexpr unsigned long SENSOR_TIMEOUT_MS = 10000;              // 10 seconds timeout
}

// ============================================================================
// Command Validation System
// ============================================================================

// Command validation error types
enum CommandError {
    CMD_OK = 0,
    CMD_ERROR_MISSING_PARAM,
    CMD_ERROR_INVALID_TYPE,
    CMD_ERROR_OUT_OF_RANGE,
    CMD_ERROR_LOGIC_ERROR
};

// Command validation result structure
struct CommandValidationResult {
    bool valid;
    CommandError error;
    char errorMessage[128];
};

// Validation helper macros
#define VALIDATE_REQUIRED(doc, key, result) \
    if (!doc.containsKey(key)) { \
        snprintf(result.errorMessage, sizeof(result.errorMessage), "Missing required field: %s", key); \
        result.error = CMD_ERROR_MISSING_PARAM; \
        result.valid = false; \
        return result; \
    }

#define VALIDATE_RANGE(value, min, max, name, result) \
    if ((value) < (min) || (value) > (max)) { \
        snprintf(result.errorMessage, sizeof(result.errorMessage), \
                 "%s out of range: %d (expected %d-%d)", name, value, min, max); \
        result.error = CMD_ERROR_OUT_OF_RANGE; \
        result.valid = false; \
        return result; \
    }

// ============================================================================
// Command Queue System (Asynchronous Command Processing)
// ============================================================================

struct CommandQueueItem {
    char command[16];
    char payload[256];
    unsigned long timestamp;
    int priority;  // 0=normal, 1=high, 2=critical
    bool valid;    // Queue item geçerli mi?
};

class CommandQueue {
private:
    static const int MAX_QUEUE_SIZE = 10;
    CommandQueueItem _queue[MAX_QUEUE_SIZE];
    int _size = 0;
    
    // ✅ Thread-safety: FreeRTOS mutex
    SemaphoreHandle_t _mutex;
    
    // Priority-based sorting helper
    void _sortByPriority();
    
public:
    CommandQueue() : _size(0) {
        // ✅ Create mutex for thread-safe access
        _mutex = xSemaphoreCreateMutex();
        
        // Initialize queue items
        for (int i = 0; i < MAX_QUEUE_SIZE; i++) {
            _queue[i].valid = false;
            _queue[i].priority = 0;
            _queue[i].timestamp = 0;
            _queue[i].command[0] = '\0';
            _queue[i].payload[0] = '\0';
        }
    }
    
    ~CommandQueue() {
        // ✅ Cleanup mutex
        if (_mutex) {
            vSemaphoreDelete(_mutex);
            _mutex = nullptr;
        }
    }
    
    // Enqueue a command (priority: 0=normal, 1=high, 2=critical)
    bool enqueue(const char* cmd, const char* payload, int priority = 0);
    
    // Dequeue highest priority command
    bool dequeue(CommandQueueItem& item);
    
    // Check if queue is empty
    bool isEmpty() const { return _size == 0; }
    
    // Get current queue size
    int size() const { return _size; }
    
    // Clear all items
    void clear();
};

// ============================================================================
// Telemetry/Diagnostics System
// ============================================================================

struct DiagnosticsData {
    unsigned long uptimeSeconds;      // Sistem çalışma süresi (saniye)
    uint32_t totalResets;             // Toplam reset sayısı
    uint32_t wifiDisconnects;         // WiFi bağlantı kesilme sayısı
    uint32_t mqttDisconnects;         // MQTT bağlantı kesilme sayısı
    uint32_t sensorErrors;             // Sensör hata sayısı
    float avgLoopTime;                 // Ortalama loop süresi (ms)
    uint32_t maxLoopTime;              // Maksimum loop süresi (ms)
    uint32_t commandCount;             // İşlenen komut sayısı
    uint32_t commandQueueOverflows;    // Command queue taşma sayısı
    uint32_t memoryLowEvents;          // Düşük bellek uyarı sayısı
    uint32_t stackLowEvents;           // Düşük stack uyarı sayısı
};

class DiagnosticsManager {
private:
    DiagnosticsData _data;
    unsigned long _lastLoopTime;
    unsigned long _loopTimeSum;
    uint32_t _loopCount;
    unsigned long _lastDiagnosticsPublish;
    const unsigned long DIAGNOSTICS_PUBLISH_INTERVAL = 600000;  // 10 dakika
    
public:
    DiagnosticsManager() {
        memset(&_data, 0, sizeof(DiagnosticsData));
        _lastLoopTime = millis();
        _loopTimeSum = 0;
        _loopCount = 0;
        _lastDiagnosticsPublish = 0;
    }
    
    // Loop başında çağrılmalı
    void startLoop();
    
    // Loop sonunda çağrılmalı
    void endLoop();
    
    // Event tracking
    void recordReset();
    void recordWifiDisconnect();
    void recordMqttDisconnect();
    void recordSensorError();
    void recordCommand();
    void recordQueueOverflow();
    void recordMemoryLow();
    void recordStackLow();
    
    // Get diagnostics data
    const DiagnosticsData& getData() const { return _data; }
    
    // Update uptime
    void updateUptime() {
        _data.uptimeSeconds = millis() / 1000;
    }
    
    // Check if diagnostics should be published
    bool shouldPublish() {
        unsigned long now = millis();
        if (now - _lastDiagnosticsPublish > DIAGNOSTICS_PUBLISH_INTERVAL) {
            _lastDiagnosticsPublish = now;
            return true;
        }
        return false;
    }
};

// ============================================================================
// Command Rate Limiter
// ============================================================================

class CommandRateLimiter {
private:
    struct CommandLog {
        unsigned long timestamp;
        char command[16];
    };
    
    static const int MAX_COMMAND_HISTORY = 20;
    CommandLog _history[MAX_COMMAND_HISTORY];
    int _historySize = 0;
    
public:
    bool allowCommand(const char* command) {
        unsigned long now = millis();
        
        // Son 10 saniyedeki aynı komutu say
        int sameCommandCount = 0;
        for (int i = 0; i < _historySize; i++) {
            if (now - _history[i].timestamp < 10000) {  // 10 saniye
                if (strcmp(_history[i].command, command) == 0) {
                    sameCommandCount++;
                }
            }
        }
        
        // Aynı komut 10 saniyede 5 kez (rate limit)
        if (sameCommandCount >= 5) {
            LOG_PRINTF("[CMD] ⚠️ Rate limit: %s komutu çok sık çağrıldı!\n", command);
            return false;
        }
        
        // Komut geçmişine ekle
        if (_historySize >= MAX_COMMAND_HISTORY) {
            // En eski komutu sil (FIFO)
            for (int i = 0; i < MAX_COMMAND_HISTORY - 1; i++) {
                _history[i] = _history[i + 1];
            }
            _historySize--;
        }
        
        _history[_historySize].timestamp = now;
        strlcpy(_history[_historySize].command, command, sizeof(_history[0].command));
        _historySize++;
        
        return true;
    }
    
    void clearHistory() {
        _historySize = 0;
    }
};

