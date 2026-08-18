#pragma once
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

// ============================================================================
// VERSION INFO
// ============================================================================
#define FIRMWARE_VERSION "1.3.0"  // Full Bridge Bipolar — toleransli HW sync + SANIYE sozlesmesi + yerel termal (2026-08-19)

// ============================================================================
// DONANIM VE PIN TANIMLAMALARI (ESP32-S3 DevKit)
// ============================================================================
#define PIN_COIL_PWM_A  4
#define PIN_COIL_PWM_B  5
#define PIN_I2C_TEMP_SDA 8
#define PIN_I2C_TEMP_SCL 9
#define PIN_I2C_MAG_SDA  10
#define PIN_I2C_MAG_SCL  11
#define PIN_CURRENT_ADC 1       // Akım Sensörü (ADC1_CH0)
#define PIN_STATUS_LED  2
#define PIN_BLE_TRIGGER 0

/*
 * ============================================================================
 * DONANIM FAZ SENKRONIZASYONU — ESP32-S3 Slave Pin Tanımları
 * ============================================================================
 *
 * STM32 Master → ESP32-S3 Slave bağlantısı:
 *   STM32 PB1  ───── sinyal kablosu ──────► ESP32-S3 GPIO7 (PIN_SYNC_IN)
 *   STM32 GND  ───── toprak kablosu ──────► ESP32-S3 GND
 *
 * ⚠️  İki kartın GND'leri mutlaka bağlanmalıdır!
 *
 * Sinyal: Her 100Hz PWM döngüsünün başında STM32 tarafından 100µs genişliğinde
 *         RISING pulse üretilir (PB1 → HIGH, 5 tick × 20µs sonra LOW).
 *
 * ISR:    syncPulseISR() → TOLERANSLI kilit (2026-08-19): darbe yalnız periyot
 *         sınırının ±%2'sindeyken sayacı sıfırlar; frekans uyuşmazlığında yok
 *         sayılır ve sayılır (syncIgnoredCount) — koşulsuz sıfırlama, STM ile
 *         frekans farklıyken çıkışı DC'ye yapıştırabiliyordu.
 *
 * Sonuç:  Tüm STM32 (Bobin 1-5) ve ESP32-S3 (Bobin 6-8) bobinleri
 *         mikrosaniye hassasiyetinde faz kilitli çalışır.
 *         Yazılımsal UART/UDP sync'e gerek kalmaz.
 * ============================================================================ */
#define PIN_SYNC_IN     7   /**< STM32 PB1'den gelen sync sinyali (GPIO7, RISING EXTI) */

// BLE Provisioning Timeout
#define BLE_ADV_TIMEOUT_SEC   120
#define WIFI_CONNECT_TIMEOUT_SEC 10

// ============================================================================
// BLE UUID DEFINITIONS
// ============================================================================
#define BLE_SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define BLE_CHAR_COMMAND_UUID   "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define BLE_CHAR_STATUS_UUID    "885e7834-31e8-467b-a36c-2f92f254923e"
#define BLE_CHAR_WIFI_SSID_UUID "c6f6696d-74d3-469a-8b3d-71b569502928"
#define BLE_CHAR_WIFI_PASS_UUID "4466b8d7-06c8-47e9-a76f-22a912c9bf13"
#define BLE_CHAR_MQTT_CFG_UUID  "d3a2f8e1-94b7-4c6e-b0d5-7e8f1a2b3c4d"

// ============================================================================
// SYSTEM CONSTANTS
// ============================================================================
#define PWM_RESOLUTION_BITS 12
#define ADC_RESOLUTION_BITS 12

#define I2C_FREQ_TEMP       100000
#define I2C_FREQ_MAG        100000

#define I2C_POWER_UP_DELAY_MS       500
#define I2C_BUS_STABILIZATION_MS    300
#define I2C_INTER_BUS_DELAY_MS      1000
#define I2C_SENSOR_INIT_DELAY_MS    300
#define I2C_RETRY_DELAY_MS          500
#define I2C_TIMEOUT_MS      1000
#define I2C_RETRY_COUNT     3

#define WDT_TIMEOUT_SECONDS 10

// ============================================================================
// ACS712 AKIM SENSÖRÜ — DİNAMİK KALİBRASYON
// ============================================================================
#define ACS712_VCC_HALF          2.5f    // [V]   ACS712 0A çıkış gerilimi (Vcc/2)
#define ACS712_BASE_SENSITIVITY  0.066f  // [V/A] 66mV/A — ACS712-30A @ 5V besleme

#define ACS712_OFFSET_EXPECTED   1.789f  // [V] 0A'da beklenen ADC gerilimi
#define ACS712_OFFSET_TOLERANCE  0.45f   // [V] ±tolerans → geçerli: [1.339, 2.239]V

// NVS versiyonu — artır → eski kalibrasyon silinir
#define ACS712_CALIB_VERSION     5

// ============================================================================
// ADC CLIP EŞİĞİ — mV Cinsinden
// ============================================================================
#define ADC_CLIP_MV              3200    // [mV] Klip eşiği (analogReadMilliVolts için)

// ============================================================================
// AKIM OKUMA PARAMETRELERİ
// ============================================================================
#define CURRENT_SAMPLES          100
#define CURRENT_SAMPLE_US        200
#define CURRENT_DC_SAMPLES       32
#define CURRENT_NOISE_FLOOR      0.3f    // [A]
#define SENSOR_READ_INTERVAL_MS  200     // 5 Hz

// ============================================================================
// FreeRTOS CONFIGURATION
// ============================================================================
#define CORE_NETWORK 0
#define CORE_CONTROL 1

#define PRIORITY_NETWORK 1
#define PRIORITY_CONTROL 2

#define CMD_QUEUE_SIZE   10
#define DATA_QUEUE_SIZE  10

// ============================================================================
// GÜVENLİK SINIRLARI
// ============================================================================
#define MAX_DUTY_CYCLE 50

#define DEAD_TIME_TICKS    2

/* YEREL TERMAL KORUMA (2026-08-19) — backend 48°C değişmeziyle birebir; ağ
 * koptuğunda bobini durduracak tek şey cihazın kendisi. Histerezisli. */
#define TERMAL_KESME_C   48.0f
#define TERMAL_DONUS_C   45.0f

// ============================================================================
// KOMUT TİPLERİ
// ============================================================================
enum CommandType {
    CMD_STOP = 0,
    CMD_START = 1,
    CMD_UPDATE_PARAMS = 2,
    CMD_SYNC_TIME = 3,
    CMD_SELF_TEST = 4,
    CMD_SYNC_ALL = 5,
    CMD_CALIBRATE = 6
};

// Queue Mesajı: Network -> Control
struct ControlCommand {
    CommandType type;
    char command_id[36];
    int frequency;
    int dutyCycle;
    int phase;              // 0-359 derece; varsayılan 0
    // ⚠️ BİRİM: SANİYE (2026-08-19) — backend sözleşmesi (_esp_duration_seconds).
    // Eski ad durationMinutes idi; dakika okumak süre-bekçisini 60× uzatıyordu.
    int durationSec;
    unsigned long long timestamp;
};

// Sensör Verisi
struct SensorReadings {
    float tempObject;
    float tempAmbient;
    float magneticField;
    float magX;
    float magY;
    float magZ;
    float current;
    bool tempSensorOk;
    bool magSensorOk;
    bool currentSensorOk;
    bool allSensorsOk;
    float maxMagneticField;
    float maxCurrent;
};

// PWM Durumu
struct PWMState {
    bool active;
    int frequency;
    int dutyCycle;               // EFEKTİF duty (aktifken) — dürüst rapor, 2026-08-19
    unsigned long remainingTimeSec;
    int durationSec;             // SANİYE (backend sözleşmesi)
    unsigned long long startTimestamp;
};

// Queue Mesajı: Control -> Network
struct SystemStatusMsg {
    SensorReadings sensors;
    PWMState pwm;
    uint32_t uptime;
    uint32_t freeHeap;
    uint32_t maxAllocHeap;
    uint8_t fragmentation;
    int coil_id;
    bool syncFallbackEvent;
    bool selfTestCompleted;
    bool selfTestPassed;
    bool has_cmd_ack;
    bool cmd_ack_success;
    char ack_cmd_id[36];
    // Yerel termal koruma + senkron tanılaması (2026-08-19)
    bool thermalLock;            // start'lar reddediliyor (soğuma bekleniyor)
    bool thermalStopEvent;       // bu turda termal kesme oldu (Network olay yayınlar)
    uint32_t syncIgnored;        // frekans uyuşmazlığında yok sayılan sync darbesi
};

// ============================================================================
// LOG LEVELS
// ============================================================================
enum LogLevel {
    PEMF_LOG_INFO = 0,
    PEMF_LOG_WARN = 1,
    PEMF_LOG_ERROR = 2
};

// ============================================================================
// GLOBAL QUEUE HANDLES
// ============================================================================
extern QueueHandle_t commandQueue;
extern QueueHandle_t statusQueue;

// ============================================================================
// LOGGING MACROS (Thread-Safe)
// ============================================================================
#define DEBUG_MODE 1

extern SemaphoreHandle_t serialMutex;

#if DEBUG_MODE
    #define LOG_PRINT(...)    do { if(serialMutex && xSemaphoreTake(serialMutex, pdMS_TO_TICKS(100)) == pdTRUE){ Serial.print(__VA_ARGS__); xSemaphoreGive(serialMutex); } } while(0)
    #define LOG_PRINTLN(...)  do { if(serialMutex && xSemaphoreTake(serialMutex, pdMS_TO_TICKS(100)) == pdTRUE){ Serial.println(__VA_ARGS__); xSemaphoreGive(serialMutex); } } while(0)
    #define LOG_PRINTF(...)   do { if(serialMutex && xSemaphoreTake(serialMutex, pdMS_TO_TICKS(100)) == pdTRUE){ Serial.printf(__VA_ARGS__); xSemaphoreGive(serialMutex); } } while(0)
#else
    #define LOG_PRINT(...)
    #define LOG_PRINTLN(...)
    #define LOG_PRINTF(...)
#endif
