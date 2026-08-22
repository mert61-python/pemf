/*
 * PEMF Coil Controller - ESP32-S3 Industrial Edition
 * '
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
// GLOBAL HANDLES & STATIC OBJECTS
// ============================================================================
QueueHandle_t commandQueue;
QueueHandle_t statusQueue;
SemaphoreHandle_t serialMutex; // Global Serial Mutex

TaskHandle_t taskNetworkHandle = NULL;
TaskHandle_t taskControlHandle = NULL;

// Statik nesneler (Dinamik bellek / heap fragmentasyonunu önlemek için)
static PemfNetworkManager sysNetManager;
static TimeManager sysTimeManager;
static StatusLED sysStatusLed(PIN_STATUS_LED, false);
static SensorManager sysSensors;
static CoilController sysCoil(&sysSensors);

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

// --- CORE 0: NETWORK TASK ---
void TaskNetwork(void *pvParameters) {
    // Stack Overflow onlemlemek icin Statik nesneleri baslat
    sysNetManager.begin();

    sysTimeManager.begin(); // NTP Başlat
    sysStatusLed.begin();

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
        sysNetManager.process();

        // 2. Control Task'tan Gelen Verileri Kontrol Et
        if (xQueueReceive(statusQueue, &statusMsg, 0) == pdTRUE) {
            // Komut ACK mesajı ise
            if (statusMsg.has_cmd_ack) {
                sysNetManager.sendCommandAck(statusMsg.ack_cmd_id, statusMsg.cmd_ack_success);
                continue; // Bu boş yapıyı sensör/durum olarak publish etme
            }

            if (statusMsg.thermalStopEvent) {
                sysNetManager.publishEvent("thermal_stop",
                    "Yerel termal kesme: bobin 48C esigini asti, PWM durduruldu (45C altinda kilit acilir)");
            }
            // UYUMSUZ-6: publishSensorData kaldırıldı - tüm sensör verisi /status içinde mevcut.
            // Çift yayın GUI'de çift deque append'e yol açıyordu.
            sysNetManager.publishStatus(statusMsg);

            // Self-Test Event Yakalama
            if (statusMsg.selfTestCompleted) {
                char selfTestMsg[160];
                if (statusMsg.selfTestPassed) {
                    snprintf(
                        selfTestMsg,
                        sizeof(selfTestMsg),
                        "Self-Test Basarili: Mag=%.2f mT, Curr=%.2f A",
                        statusMsg.sensors.magneticField,
                        statusMsg.sensors.current
                    );
                    sysNetManager.publishEvent("selftest_ok", selfTestMsg);
                } else {
                    snprintf(
                        selfTestMsg,
                        sizeof(selfTestMsg),
                        "Self-Test Basarisiz: Mag=%.2f mT (<0.10 mT esik), Curr=%.2f A",
                        statusMsg.sensors.magneticField,
                        statusMsg.sensors.current
                    );
                    sysNetManager.publishEvent("selftest_fail", selfTestMsg);
                }
            }
        }

        // 3. LED Durumu Güncelle (Sistem Durumu Göstergesi)
        bool wifiOk = (WiFi.status() == WL_CONNECTED);
        bool mqttOk = sysNetManager.isMqttConnected();
        bool pwmActive = statusMsg.pwm.active;
        bool portalActive = sysNetManager.isPortalActive();
        bool bleActive = sysNetManager.isBLEActive();

        // BLE aktifse özel LED modu göster
        if (bleActive) {
            sysStatusLed.setState(LED_BLUETOOTH_MODE);
        } else {
            sysStatusLed.update(wifiOk, mqttOk, pwmActive, portalActive);
        }

        // 4. Yield
        vTaskDelay(10 / portTICK_PERIOD_MS);
    }
}

// --- CORE 1: REAL-TIME CONTROL TASK ---
void TaskControl(void *pvParameters) {
    // -----------------------------------------------------------------------
    // BAŞLATMA SIRASI — KRİTİK
    //
    // 1. beginWithoutCalibration(): ADC + I2C başlatılır, akım kalibrasyonu YOK.
    // 2. sysCoil.begin()           : 50 kHz DDS timer başlar.
    // 3. sysSensors.calibrate()    : Timer AÇIKKEN offset ölçülür.
    //    → Timer gürültüsü offset'e bake-in edilir.
    //    → _readCurrent() içinde (voltage - _acsOffset) bu gürültüyü iptal eder.
    //    → NVS'de geçerli offset varsa yeniden ölçüm atlanır (yalnızca türetme yapılır).
    // -----------------------------------------------------------------------
    sysSensors.beginWithoutCalibration();
    sysCoil.begin();
    sysSensors.calibrate();

    // Watchdog Kaydı
    esp_task_wdt_add(NULL);

    ControlCommand cmd;

    LOG_PRINTLN("[Sys] Control Task Started on Core 1");

    TickType_t xLastWakeTime;
    const TickType_t xFrequency = pdMS_TO_TICKS(SENSOR_READ_INTERVAL_MS);

    xLastWakeTime = xTaskGetTickCount();

    for (;;) {
        // HATA-4 DUZELTME: vTaskDelayUntil ile sabit periyot - timing drift onlendi
        vTaskDelayUntil(&xLastWakeTime, xFrequency);

        // Watchdog Besle
        esp_task_wdt_reset();

        // 1. PWM Process (Sure ve senkronizasyon kontrolu)
        sysCoil.process();

        // 2. Queue'dan Tum Bekleyen Komutlari Oku (Non-blocking)
        while (xQueueReceive(commandQueue, &cmd, 0) == pdTRUE) {
            // 2026-08-19: handleCommand artik bool doner — RED (ornegin termal kilit)
            // ACK'ta success=false olarak gitsin. Eski kod KOSULSUZ true basiyordu;
            // backend reddedilen komutu basarili saniyordu.
            bool kabulEdildi = sysCoil.handleCommand(cmd);

            if (strlen(cmd.command_id) > 0) {
                SystemStatusMsg ackMsg;
                memset(&ackMsg, 0, sizeof(ackMsg));
                ackMsg.has_cmd_ack = true;
                ackMsg.cmd_ack_success = kabulEdildi;
                strncpy(ackMsg.ack_cmd_id, cmd.command_id, 35);
                /* [5.12] (sahip onayi 2026-08-20): eski 0-timeout, kuyruk dolu penceresinde
                 * (mdns 2000 ms blogu) E-stop ACK'ini DUSURUYORDU → backend sahte "onay gelmedi"
                 * alarmi. SINIRLI bekleme: kontrol dongusu 200 ms periyotlu, 50 ms blok guvenli;
                 * tuketici 10 ms'de bir bosalttigindan yer acilir. (Eski yorumdaki "overwrite
                 * deneriz" vaadi hic gerceklenmemisti.) */
                if(xQueueSend(statusQueue, &ackMsg, pdMS_TO_TICKS(50)) != pdTRUE) {
                    LOG_PRINTLN("[Warn] statusQueue dolu! ACK mesaji gonderilemedi.");
                }
            }
        }

        // 3. Sensorleri Oku ve Durumu Raporla
        SensorReadings readings = sysSensors.readAll();
        // 2026-08-19: YEREL TERMAL KORUMA — ag koptugunda bobini durduracak tek sey
        // cihazin kendisi (48C kesme / 45C histerezis; sensor arizaliysa dokunmaz).
        sysCoil.enforceThermalLimit(readings);
        PWMState pwmSelect = sysCoil.getState();

        // Bellek istatistiklerini hesapla
        uint32_t freeHeap = ESP.getFreeHeap();
        uint32_t maxAllocHeap = ESP.getMaxAllocHeap();
        uint8_t fragmentation = 0;

        // HATA-8 FIX: Güvenli fragmentation hesabı (integer overflow önlendi)
        // maxAllocHeap <= freeHeap her zaman geçerli; 100UL ile overflow engellendi
        if (freeHeap > 0 && maxAllocHeap <= freeHeap) {
            fragmentation = (uint8_t)(100 - ((uint32_t)(maxAllocHeap * 100UL) / freeHeap));
        } else if (freeHeap == 0) {
            fragmentation = 100;
        } else {
            fragmentation = 0;
        }

        SystemStatusMsg status;
        // HATA-9 FIX: C++ Stack Garbage temizliği.
        // Aksi takdirde bir üst scope'daki ackMsg'nin 'has_cmd_ack=true' değeri kalıyor ve
        // NetworkManager tüm sonrakileri ACK sanıp sonsuza dek atlıyordu.
        memset(&status, 0, sizeof(SystemStatusMsg));
        status.sensors = readings;
        status.pwm = pwmSelect;
        status.uptime = millis();
        status.freeHeap = freeHeap;
        status.maxAllocHeap = maxAllocHeap;
        status.fragmentation = fragmentation;
        status.coil_id = FACTORY_COIL_ID; // HATA-5 DUZELTME: coil_id eksik set ediliyordu
        status.syncFallbackEvent = false;  /* 15. parti: zamanlanmis-baslangic kalkti — alan tel-uyumu icin durur */
        status.thermalLock = sysCoil.isThermalLocked();
        status.thermalStopEvent = sysCoil.consumeThermalStopEvent();
        status.syncIgnored = sysCoil.syncIgnoredCount();
        status.syncDisabled = sysCoil.syncDisabled();

        bool stPassed = false;
        if (sysCoil.consumeSelfTestEvent(stPassed)) {
            status.selfTestCompleted = true;
            status.selfTestPassed = stPassed;
        } else {
            status.selfTestCompleted = false;
            status.selfTestPassed = false;
        }

        static unsigned long lastStackLogMs = 0;
        if (millis() - lastStackLogMs > 10000) {
            UBaseType_t minFreeWords = uxTaskGetStackHighWaterMark(NULL);
            unsigned long minFreeBytes = (unsigned long)minFreeWords * sizeof(StackType_t);
            LOG_PRINTF("[Stack] ControlTask min free stack: %lu bytes\n", minFreeBytes);
            if (minFreeBytes < 512) {
                LOG_PRINTLN("[Stack][WARN] ControlTask stack low (<512 bytes). Stack boyutunu artirin.");
            }
            lastStackLogMs = millis();
        }

        // Core 0'a gonder. Periyodik durum atlanabilir (200 ms sonra yenisi gelir) ama
        // [5.12] (sahip onayi 2026-08-20): icindeki TEK-ATIMLIK olaylar atlanamaz — tuketilmis
        // olay bir daha uretilmez; termal-kesme olayi operatore HIC ulasmayabilirdi. Gonderim
        // duserse olaylari geri kur, sonraki tur yeniden dener.
        if (xQueueSend(statusQueue, &status, 0) != pdTRUE) {
            LOG_PRINTLN("[Warn] statusQueue dolu! Guncel durum datasi atlandi.");
            if (status.thermalStopEvent) sysCoil.restoreThermalStopEvent();
            if (status.selfTestCompleted) sysCoil.restoreSelfTestEvent(status.selfTestPassed);
        }
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
    // HATA-1 FIX: Arduino framework zaten TWDT başlatıyor; deinit yapıp yeniden init et.
    esp_task_wdt_deinit();
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
    // HATA-12 FIX: Sensor kütüphaneleri + Wire + Adafruit_MLX90393 için 12KB → 16KB
    xTaskCreatePinnedToCore(
        TaskControl,        // Function
        "ControlTask",      // Name
        16384,              // Stack size (Increased: Sensor libs need headroom)
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
