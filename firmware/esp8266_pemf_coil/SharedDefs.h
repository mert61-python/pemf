#pragma once
#include <Arduino.h>
#include <IPAddress.h>

// ============================================================================
// Core Enums
// ============================================================================
enum CommandType {
    CMD_STOP = 0,
    CMD_START = 1,
    CMD_UPDATE_PARAMS = 2,
    CMD_SYNC_TIME = 3,
    CMD_SYNC_ALL = 5
};

enum BrokerType {
    BROKER_NONE = 0,
    BROKER_LOCAL = 1,
    BROKER_CLOUD = 2
};

// ============================================================================
// PROGMEM String Constants (Flash memory - saves RAM)
// ============================================================================
const char PROGMEM_MQTT_STR[] PROGMEM = "[MQTT]";
const char PROGMEM_MEMORY_STR[] PROGMEM = "[Memory]";
const char PROGMEM_STACK_STR[] PROGMEM = "[Stack]";
const char PROGMEM_ERROR_STR[] PROGMEM = "[ERROR]";
const char PROGMEM_WARN_STR[] PROGMEM = "[WARN]";
const char PROGMEM_INFO_STR[] PROGMEM = "[INFO]";

/*
 * ============================================================================
 * KRİTİK TASARIM KURALI: PWM BAĞIMSIZLIĞI
 * ============================================================================
 *
 * PWM çıkışı, ağ bağlantı durumundan (WiFi/MQTT) TAM BAĞIMSIZDIR!
 *
 * PWM sadece şu durumlarda durur:
 * 1. stop() komutu geldiğinde (MQTT üzerinden)
 * 2. Duration süresi dolduğunda (zamanlı komutlarda)
 *
 * PWM ASLA şu durumlarda durmaz:
 * - WiFi bağlantısı kesildiğinde
 * - MQTT bağlantısı kesildiğinde
 * - Network timeout olduğunda
 * - Portal açıldığında/kapandığında
 *
 * Bu tasarım, tıbbi güvenlik ve tedavi sürekliliği için kritiktir.
 * ============================================================================
 */

/*
 * ============================================================================
 * DONANIM FAZ SENKRONIZASYONU — ⚠️ ESP8266'DA KALDIRILDI (sahip kararı, 2026-08-19)
 * ============================================================================
 * Eski tasarım STM32 PB1 → GPIO7 sync girişi tanımlıyordu. İKİ sebeple kaldırıldı:
 *   1. GPIO7, ESP8266'da FLASH SPI hattıdır (GPIO6-11) — giriş+kesme bağlanamaz;
 *      kart devreye LEHİMLİ olduğundan pin değişimi de mümkün değil.
 *   2. 8266 bobinleri TEK FAZ sürülecek — faz kilidi gerekmiyor. (Üstelik STM
 *      darbesi her STM periyodunda DDS sayacını sıfırladığından, frekans farklıyken
 *      düşük frekanslı çıkış DC'ye yapışıyordu.)
 * PIN_SYNC_IN tanımı BİLEREK YOK — kimse yanlışlıkla flash pinine dokunmasın.
 * Donanım senkronu ESP32-S3 varyantında (esps3_pemf_coil/) yaşamaya devam eder.
 * ============================================================================ */

/* ============================================================================
 * YEREL TERMAL KORUMA EŞİKLERİ (2026-08-19)
 * ============================================================================
 * Kesme eşiği backend güvenlik değişmeziyle BİREBİR (48°C — regresyon yapma listesi);
 * dönüş eşiği histerezisli ki sınırda aç-kapa titremesin. Kullanım: .ino ana döngüsü.
 * ============================================================================ */
#define TERMAL_KESME_C   48.0f  /**< MLX90614 nesne sıcaklığı bu değeri aşarsa PWM DURUR */
#define TERMAL_DONUS_C   45.0f  /**< Kilit ancak bu değerin altında açılır (histerezis)  */

// Memory istatistikleri yapÄ±sÄ±
struct MemoryStats {
    uint32_t freeHeap;          // Toplam boÅŸ heap (bytes)
    uint32_t maxAllocHeap;      // En bÃ¼yÃ¼k allocate edilebilir blok (bytes)
    uint8_t fragmentation;      // % fragmentation (0-100)
};

// Memory istatistikleri al (utility fonksiyon)
inline MemoryStats getMemoryStats() {
    MemoryStats stats;
    stats.freeHeap = ESP.getFreeHeap();
    stats.maxAllocHeap = ESP.getMaxFreeBlockSize();

    // Fragmentation hesapla
    if (stats.freeHeap > 0) {
        // Fragmentation = 100 - (maxAllocHeap * 100 / freeHeap)
        // EÄŸer maxAllocHeap freeHeap'e yakÄ±nsa, fragmentation dÃ¼ÅŸÃ¼k
        // EÄŸer maxAllocHeap Ã§ok kÃ¼Ã§Ã¼kse, fragmentation yÃ¼ksek
        stats.fragmentation = 100 - ((stats.maxAllocHeap * 100) / stats.freeHeap);
    } else {
        stats.fragmentation = 100;  // Heap tamamen dolu
    }

    return stats;
}

// SensÃ¶r veri yapÄ±sÄ±
struct SensorData {
    float tempObject;
    float tempAmbient;
    float magneticField;  // mT
    float current;        // A
    bool temp_sensor_ok;
    bool magnetic_sensor_ok;
    bool current_sensor_ok;
    bool sensorsOK;  // Genel durum

    // ESP32-S3 ile tam hizalama iÃ§in eklenen alanlar
    float magX;
    float magY;
    float magZ;
    float maxMagneticField;
    float maxCurrent;
    bool allSensorsOk; // sensorsOK ile aynÄ±
};

// PWM durum yapÄ±sÄ±
struct PWMStatus {
    bool active;
    int frequency;      // Hz
    int dutyCycle;     // %
    unsigned long remainingTime;  // ms (0 = sÃ¼resiz)
};

// PWM State EEPROM yapısı (restart sonrası kaldığı yerden devam için)
struct PWMStateEEPROM {
    uint8_t magic;           // 0xAB = valid data
    bool active;             // PWM aktif mi?
    int frequency;           // Hz
    int dutyCycle;          // %
    unsigned long duration;  // Orijinal süre (ms, 0=süresiz)
    unsigned long elapsed;   // Geçen süre (ms)
    uint8_t checksum;        // Veri bütünlüğü kontrolü
};

// EEPROM Memory Map
#define EEPROM_PWM_STATE_ADDR     256  // WiFi credentials'tan sonra (0-255 WiFi için)
#define EEPROM_BROKER_STATE_ADDR  300  // Yeni — son aktif broker tipi
#define EEPROM_CONFIG_VER_ADDR    304  // Yeni — CONFIG_VERSION

// Sistem durum yapÄ±sÄ±
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
    unsigned long pwm_remaining_time;
    unsigned long long pwm_start_timestamp;  // PWM başlangıç zamanı (ms, NTP sync)
    int pwm_duration;                         // PWM süresi (SANİYE — backend sözleşmesi, 2026-08-19)

    // SensÃ¶r durumu
    bool sensors_ok;
    bool temp_sensor_ok;
    bool magnetic_sensor_ok;
    bool current_sensor_ok;

    // Sistem durumu
    uint32_t free_heap;
    uint32_t max_alloc_heap;    // En bÃ¼yÃ¼k allocate edilebilir blok
    uint8_t fragmentation;      // % fragmentation (0-100)
    unsigned long uptime;
};

// MQTT mesaj callback tipi
// String yerine const char* kullanarak heap fragmentation'Ä± Ã¶nle
typedef void (*MqttMessageCallback)(const char* topic, const char* payload);

// ============================================================================
// Logging Sistemi (Log Seviyeleri ve Debug MakrolarÄ±)
// ============================================================================

// Log Seviyeleri
enum LogLevel {
    LOG_LEVEL_INFO,    // Sadece Seri Port (Buluta gitmez)
    LOG_LEVEL_WARN,    // Seri Port + Bulut
    LOG_LEVEL_ERROR    // Seri Port + Bulut (Alarm)
};

// Debug Modu AnahtarÄ± (1: AÃ§Ä±k, 0: KapalÄ± - Production)
#define DEBUG_MODE 1

#if DEBUG_MODE
    // EÄŸer DEBUG_MODE 1 ise, bu komutlar Serial komutlarÄ±na dÃ¶nÃ¼ÅŸÃ¼r
    #define LOG_PRINT(...)    Serial.print(__VA_ARGS__)
    #define LOG_PRINTLN(...)  Serial.println(__VA_ARGS__)
    #define LOG_PRINTF(...)   Serial.printf(__VA_ARGS__)
#else
    // EÄŸer DEBUG_MODE 0 ise, bu komutlar "boÅŸluk" olur.
    // Derleyici burayÄ± tamamen siler (zero overhead).
    #define LOG_PRINT(...)
    #define LOG_PRINTLN(...)
    #define LOG_PRINTF(...)
#endif

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
    char errorMessage[64];  // Reduced from 128 to 64 bytes
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
    char payload[128];  // Actual usage: 115 bytes + margin (reduced from 256)
    unsigned long timestamp;
    int priority;  // 0=normal, 1=high, 2=critical
    bool valid;    // Queue item geÃ§erli mi?
};

class CommandQueue {
private:
    static const int MAX_QUEUE_SIZE = 6;  // Reduced from 10 to 6 (memory optimization)
    CommandQueueItem _queue[MAX_QUEUE_SIZE];
    int _size = 0;

    // Priority-based sorting helper
    void _sortByPriority();

public:
    CommandQueue() : _size(0) {
        // Initialize queue items
        for (int i = 0; i < MAX_QUEUE_SIZE; i++) {
            _queue[i].valid = false;
            _queue[i].priority = 0;
            _queue[i].timestamp = 0;
            _queue[i].command[0] = '\0';
            _queue[i].payload[0] = '\0';
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
// Diagnostics System - KALDIRILDI (Dead Code Cleanup)
// ============================================================================
// DiagnosticsManager ve DiagnosticsData tamamen kaldırıldı

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

        // Son 10 saniyedeki aynÄ± komutu say
        int sameCommandCount = 0;
        for (int i = 0; i < _historySize; i++) {
            if (now - _history[i].timestamp < 10000) {  // 10 saniye
                if (strcmp(_history[i].command, command) == 0) {
                    sameCommandCount++;
                }
            }
        }

        // AynÄ± komut 10 saniyede 5 kez (rate limit)
        if (sameCommandCount >= 5) {
            LOG_PRINTF("[CMD] âš ï¸ Rate limit: %s komutu Ã§ok sÄ±k Ã§aÄŸrÄ±ldÄ±!\n", command);
            return false;
        }

        // Komut geÃ§miÅŸine ekle
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
