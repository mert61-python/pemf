/*
 * PEMF Coil Controller - ESP32-S3 Industrial Edition
 * 
 * Mimari: Dual-Core FreeRTOS
 * Core 0: Network Task (WiFi/MQTT/OTA/Logs)
 * Core 1: Control Task (PWM/ADC/Safety)
 * 
 * İletişim: FreeRTOS Queues
 * Depolama: Preferences (NVS)
 */

#include "SharedDefs.h"
#include "NetworkManager.h"
#include "CoilController.h"
#include "SensorManager.h"
#include "TimeManager.h"
#include "StatusLED.h"
#include <esp_task_wdt.h>

// ============================================================================
// GLOBAL HANDLES
// ============================================================================
QueueHandle_t commandQueue;
QueueHandle_t statusQueue;
SemaphoreHandle_t serialMutex; // Global Serial Mutex

TaskHandle_t taskNetworkHandle = NULL;
TaskHandle_t taskControlHandle = NULL;

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

// --- CORE 0: NETWORK TASK ---
void TaskNetwork(void *pvParameters) {
    // Stack Overflow onlemlemek icin Heap'te olusturuyoruz
    PemfNetworkManager* netManager = new PemfNetworkManager();
    netManager->begin();
    
    TimeManager timeManager;
    timeManager.begin(); // NTP Başlat
    
    StatusLED statusLed(PIN_STATUS_LED, false); // false = basit LED, true = RGB LED
    statusLed.begin();
    
    // Status mesajı buffer
    SystemStatusMsg statusMsg;
    // Varsayılan değerler
    memset(&statusMsg, 0, sizeof(SystemStatusMsg));
    statusMsg.pwm.active = false; 
    statusMsg.sensors.allSensorsOk = false;
    
    // Watchdog Kaydı
    esp_task_wdt_add(NULL);

    LOG_PRINTLN("[Sys] Network Task Started on Core 0");
    
    for (;;) {
        // Watchdog Besle
        esp_task_wdt_reset();

        // 1. Network İşlemlerini Yürüt
        netManager->process();
        
        // 2. Control Task'tan Gelen Verileri Kontrol Et
        if (xQueueReceive(statusQueue, &statusMsg, 0) == pdTRUE) {
            // Veriyi MQTT ile gönder (Status ve Sensors ayrı ayrı)
            netManager->publishStatus(statusMsg);
            netManager->publishSensorData(statusMsg.sensors);
        }
        
        // 3. LED Durumu Güncelle (Sistem Durumu Göstergesi)
        bool wifiOk = (WiFi.status() == WL_CONNECTED);
        bool mqttOk = netManager->isMqttConnected();
        bool pwmActive = statusMsg.pwm.active;
        bool portalActive = netManager->isPortalActive();
        
        statusLed.update(wifiOk, mqttOk, pwmActive, portalActive);
        
        // 4. Yield
        vTaskDelay(10 / portTICK_PERIOD_MS); 
    }
}

// --- CORE 1: REAL-TIME CONTROL TASK ---
void TaskControl(void *pvParameters) {
    // Stack Safety: Allocate on Heap
    SensorManager* sensors = new SensorManager();
    CoilController* coil = new CoilController(sensors);
    
    // Başlatma
    sensors->begin();
    coil->begin();
    
    // Watchdog Kaydı
    esp_task_wdt_add(NULL);

    ControlCommand cmd;
    
    LOG_PRINTLN("[Sys] Control Task Started on Core 1");
    
    TickType_t xLastWakeTime;
    const TickType_t xFrequency = (SENSOR_READ_INTERVAL_SEC * 1000) / portTICK_PERIOD_MS; // 3Hz Raporlama Döngüsü (ESP yükünü azaltır)
    
    xLastWakeTime = xTaskGetTickCount();
    
    for (;;) {
        // Watchdog Besle
        esp_task_wdt_reset();

        // 1. PWM Process (Hassas Zamanlama için loop başında)
        coil->process();
        
        // 2. Queue'dan Komut Oku (Non-blocking)
        if (xQueueReceive(commandQueue, &cmd, 0) == pdTRUE) {
            coil->handleCommand(cmd);
        }
        
        // 3. Sensörleri Oku ve Durumu Raporla (1Hz Periyot)
        // Eğer sensör okuması çok uzun sürüyorsa (I2C vb), bu blok optimize edilebilir.
        // xTaskGetTickCount() kullanarak 1 saniyede bir çalışmasını garantiliyoruz.
        if ((xTaskGetTickCount() - xLastWakeTime) >= xFrequency) {
            SensorReadings readings = sensors->readAll();
            PWMState pwmSelect = coil->getState();
            
            // Bellek istatistiklerini hesapla
            uint32_t freeHeap = ESP.getFreeHeap();
            uint32_t maxAllocHeap = ESP.getMaxAllocHeap();
            uint8_t fragmentation = 0;
            
            // Fragmentation hesapla (ESP8266'daki gibi)
            if (freeHeap > 0) {
                fragmentation = 100 - ((maxAllocHeap * 100) / freeHeap);
            } else {
                fragmentation = 100;
            }
            
            SystemStatusMsg status;
            status.sensors = readings;
            status.pwm = pwmSelect;
            status.uptime = millis();
            status.freeHeap = freeHeap;
            status.maxAllocHeap = maxAllocHeap;
            status.fragmentation = fragmentation;
            
            // Core 0'a gönder (Doluysa atla, eski veri kalabilir, sorun değil)
            xQueueSend(statusQueue, &status, 0);
            
            xLastWakeTime = xTaskGetTickCount();
        }
        
        // 4. Kısa Delay (Hızlı Döngü için)
        // PWM process'in sık çalışması gerekiyorsa bu süreyi kısaltabiliriz (1-5ms)
        // Ancak 10ms CoilController süresi için yeterli hassasiyettir (ms bazlı kontrol).
        vTaskDelay(10 / portTICK_PERIOD_MS); 
    }
}

// ============================================================================
// MAIN SETUP
// ============================================================================
void setup() {
    Serial.begin(115200);
    // Mutex i Serial başladıktan hemen sonra oluştur
    serialMutex = xSemaphoreCreateMutex();
    
    // Watchdog Timer Başlat (3 Saniye Timeout, Panic=True -> Reset atar)
    // Core 0 ve Core 1'deki task'lerin hepsi reset atmazsa sistem resetlenir.
    esp_task_wdt_config_t wdt_config = {
        .timeout_ms = WDT_TIMEOUT_SECONDS * 1000,
        .idle_core_mask = (1 << portNUM_PROCESSORS) - 1,    
        .trigger_panic = true
    };
    esp_task_wdt_init(&wdt_config);

    delay(1000);
    LOG_PRINTLN("\n\n=== PEMF COIL CONTROLLER ESP32-S3 STARTING ===");
    
    // 1. Queue Oluşturma
    commandQueue = xQueueCreate(CMD_QUEUE_SIZE, sizeof(ControlCommand));
    statusQueue = xQueueCreate(DATA_QUEUE_SIZE, sizeof(SystemStatusMsg));
    
    if (commandQueue == NULL || statusQueue == NULL) {
        LOG_PRINTLN("[Crit] Queue Creation Failed!");
        while(1);
    }
    
    // 2. Task Oluşturma (Pinned to Cores)
    
    // Network Task -> Core 0
    // SSL (WiFiClientSecure) yoğun stack kullanır, 16KB -> 20KB yaptık.
    xTaskCreatePinnedToCore(
        TaskNetwork,        // Function
        "NetworkTask",      // Name
        20480,              // Stack size (Increased for SSL Stability)
        NULL,               // Params
        PRIORITY_NETWORK,   // Priority
        &taskNetworkHandle, // Handle
        CORE_NETWORK        // Core ID
    );
    
    // Control Task -> Core 1
    // Sensor kütüphaneleri için stack artırıldı (8KB -> 12KB)
    xTaskCreatePinnedToCore(
        TaskControl,        // Function
        "ControlTask",      // Name
        12288,              // Stack size (Increased for Stability)
        NULL,               // Params
        PRIORITY_CONTROL,   // Priority
        &taskControlHandle, // Handle
        CORE_CONTROL        // Core ID
    );
    
    LOG_PRINTLN("[Sys] Setup Complete. System Running.");
}

void loop() {
    // Arduino loop task
    vTaskDelete(NULL); // Task kendini siler, kaynaklar serbest kalır
}
