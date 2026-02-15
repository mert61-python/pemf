#pragma once
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

// ============================================================================
// VERSION INFO
// ============================================================================
#define FIRMWARE_VERSION "1.0.0"

// ============================================================================
// DONANIM VE PIN TANIMLAMALARI (ESP32-S3 DevKit)
// ============================================================================
// Endüstriyel Revizyon: ESP32-S3 Pinout Revizyonu
#define PIN_COIL_PWM    4      // PWM Çıkışı (Coil)
// I2C-0 : Sıcaklık (MLX90614)
#define PIN_I2C_TEMP_SDA 8
#define PIN_I2C_TEMP_SCL 9
// I2C-1 : Manyetik (MLX90393) - Strapping pinlerden kaçınıldı (5/6 yerine 10/11)
#define PIN_I2C_MAG_SDA  10    // GÜNCELLENDI: Strapping pin sorunu giderildi
#define PIN_I2C_MAG_SCL  11    // GÜNCELLENDI: Strapping pin sorunu giderildi
#define PIN_CURRENT_ADC 1      // Akım Sensörü (ADC1_CH0)
#define PIN_STATUS_LED  2      // Durum LED'i (GPIO2 - ESP32-S3 dahili LED)

// ============================================================================
// BLE UUID DEFINITIONS
// ============================================================================
#define BLE_SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define BLE_CHAR_COMMAND_UUID   "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define BLE_CHAR_STATUS_UUID    "885e7834-31e8-467b-a36c-2f92f254923e"
#define BLE_CHAR_WIFI_SSID_UUID "c6f6696d-74d3-469a-8b3d-71b569502928" // Write Only
#define BLE_CHAR_WIFI_PASS_UUID "4466b8d7-06c8-47e9-a76f-22a912c9bf13" // Write Only

// ============================================================================
// SYSTEM CONSTANTS
// ============================================================================
#define PWM_RESOLUTION_BITS 12      // 12-bit PWM çözünürlüğü (0-4095)
#define ADC_RESOLUTION_BITS 12      // 12-bit ADC (0-4095)
#define I2C_FREQ_TEMP       100000  // 100kHz Standard Mode (MLX90614 için optimal)
#define I2C_FREQ_MAG        400000  // 400kHz Fast Mode (MLX90393 destekler, hız artışı)
#define WDT_TIMEOUT_SECONDS 5       // Watchdog Timeout Süresi (Saniye)

// ACS712 Current Sensor Configuration - SABIT 30A MODEL
#define ACS712_SENSITIVITY  0.066   // 66 mV/A (30A modeli)

// Sampling parameters for 100Hz PWM measurement
#define CURRENT_SAMPLES     100     // 100 örnek
#define CURRENT_SAMPLE_US   100     // 100µs aralık = 10ms toplam (1 tam periyot)
#define CURRENT_NUM_CYCLES  5       // 5 periyot ölç = 50ms

// Sensor reading frequency (saniye cinsinden)
#define SENSOR_READ_INTERVAL_SEC  1  // Her saniye okuma (gerçek zamanlı veri)

// ============================================================================
// FreeRTOS CONFIGURATION
// ============================================================================
// Core Definitions
#define CORE_NETWORK 0  // WiFi, MQTT, System Logs
#define CORE_CONTROL 1  // Real-time PWM, Sensors, Safety

// Task Priorities (Higher number = Higher priority)
#define PRIORITY_NETWORK 1
#define PRIORITY_CONTROL 2  // Real-time control needs higher priority

// Queue Sizes
#define CMD_QUEUE_SIZE   10
#define DATA_QUEUE_SIZE  10

// ============================================================================
// DATA STRUCTURES FOR IPC (Inter-Process Communication)
// ============================================================================

// Komut Tipleri
enum CommandType {
    CMD_STOP = 0,
    CMD_START = 1,
    CMD_UPDATE_PARAMS = 2,
    CMD_SYNC_TIME = 3
};

// Queue Mesajı: Network -> Control
struct ControlCommand {
    CommandType type;
    int frequency;          // Hz
    int dutyCycle;         // % (0-100)
    int durationMinutes;    // 0 = sonsuz
    unsigned long long timestamp; // Sync start için
};

// Sensör Verisi
struct SensorReadings {
    float tempObject;
    float tempAmbient;
    float magneticField;    // mT
    float current;          // A
    bool tempSensorOk;
    bool magSensorOk;
    bool currentSensorOk;
    bool allSensorsOk;
    
    // PWM aktifken ölçülen maksimum değerler
    float maxMagneticField; // mT (PWM açık olduğunda)
    float maxCurrent;       // A (PWM açık olduğunda)
};

// PWM Durumu
struct PWMState {
    bool active;
    int frequency;
    int dutyCycle;
    unsigned long remainingTimeSec;
    int durationMinutes;              // Toplam süre (dakika)
    unsigned long long startTimestamp; // Başlangıç zamanı (Unix timestamp ms)
};

// Queue Mesajı: Control -> Network
struct SystemStatusMsg {
    SensorReadings sensors;
    PWMState pwm;
    uint32_t uptime;
    uint32_t freeHeap;
    uint32_t maxAllocHeap;      // En büyük tahsis edilebilir blok
    uint8_t fragmentation;      // Heap parçalanma oranı (0-100)
    int coil_id;
};

// ============================================================================
// LOG LEVELS (ESP8266 Uyumluluğu için)
// ============================================================================
enum LogLevel {
    PEMF_LOG_INFO = 0,
    PEMF_LOG_WARN = 1,
    PEMF_LOG_ERROR = 2
};

// ============================================================================
// GLOBAL QUEUE HANDLES (Defined in main.cpp)
// ============================================================================
extern QueueHandle_t commandQueue;
extern QueueHandle_t statusQueue;

// ============================================================================
// LOGGING MACROS (Thread-Safe Wrapper)
// ============================================================================
#define DEBUG_MODE 1

// Global Mutex for Serial functionality to prevent race conditions & heap corruption
extern SemaphoreHandle_t serialMutex;

#if DEBUG_MODE
    #define LOG_PRINT(...)    do { if(serialMutex){ xSemaphoreTake(serialMutex, portMAX_DELAY); Serial.print(__VA_ARGS__); xSemaphoreGive(serialMutex); } else { Serial.print(__VA_ARGS__); } } while(0)
    #define LOG_PRINTLN(...)  do { if(serialMutex){ xSemaphoreTake(serialMutex, portMAX_DELAY); Serial.println(__VA_ARGS__); xSemaphoreGive(serialMutex); } else { Serial.println(__VA_ARGS__); } } while(0)
    #define LOG_PRINTF(...)   do { if(serialMutex){ xSemaphoreTake(serialMutex, portMAX_DELAY); Serial.printf(__VA_ARGS__); xSemaphoreGive(serialMutex); } else { Serial.printf(__VA_ARGS__); } } while(0)
#else
    #define LOG_PRINT(...)
    #define LOG_PRINTLN(...)
    #define LOG_PRINTF(...)
#endif

