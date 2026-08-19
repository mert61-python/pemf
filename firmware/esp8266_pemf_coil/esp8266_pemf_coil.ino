/*
 * PEMF IoT Sistemi - ESP8266 Coil Controller
 * * Modüler OOP Yapısı - Separation of Concerns Prensibi
 * * Bu kod 8 farklı ESP8266 cihazında kullanılabilir.
 * Sadece COIL_ID değerini değiştirerek farklı coil'ler için kullanın.
 * * Modüller:
 * - SensorManager: Tüm sensör işlemleri (MLX90614, MLX90393, ACS712)
 * - NetworkManager: WiFi, MQTT, EEPROM credential yönetimi
 * - CoilController: PWM kontrolü, güvenlik limitleri, zamanlayıcılar
 * - TimeManager: NTP zaman senkronizasyonu
 * - StatusLED: Durum LED yönetimi
 * * Gerekli Kütüphaneler:
 * - WiFiManager by tzapu
 * - PubSubClient by Nick O'Leary
 * - Adafruit MLX90614 Library
 * - Adafruit MLX90393 Library
 * - ArduinoJson
 */

#include "SharedDefs.h"
#include "SensorManager.h"
#include "NetworkManager.h"
#include "CoilController.h"
#include "TimeManager.h"
#include "StatusLED.h"
#include "Secrets.h"
#include <ArduinoJson.h>

extern "C" {
    #include "user_interface.h"
}

// ============================================================================
// COIL ID - Secrets.h'dan alinir
// ============================================================================
int COIL_ID = COIL_ID_CONST;

// ============================================================================
// Pin Tanımlamaları
// ============================================================================
const int PWM_PIN = D5;        // PWM çıkış pini (coil sürücü)
const int CURRENT_PIN = A0;    // ACS712 akım sensörü analog pini
const int LED_PIN = LED_BUILTIN; // Durum LED'i

// ============================================================================
// Modül Nesneleri
// ============================================================================
SensorManager sensors(CURRENT_PIN);
NetworkManager* network = nullptr;
CoilController* coil = nullptr;

TimeManager timeManager;
StatusLED statusLED(LED_PIN);
CommandRateLimiter commandRateLimiter;

// ── YEREL TERMAL KORUMA (2026-08-19) ─────────────────────────────────────────
// Backend'in 48°C politikası SUNUCUDA koşar; PWM ise bilerek ağdan bağımsızdır —
// yani ağ koptuğunda ısınan bobini durduracak HİÇBİR şey yoktu. Bu kilit cihazın
// kendi son savunma hattıdır: eşik backend güvenlik değişmeziyle birebir (48.0),
// dönüş histerezisli (45.0) ki sınırda aç-kapa titremesin. Sensör ARIZALIYSA kesme
// YAPILMAZ (sensörsüz kart çalışabilmeli) — arıza zaten status'ta görünür.
static bool g_thermalLock = false;


// ============================================================================
// Utility Fonksiyonlar
// ============================================================================
void feedWatchdog() {
    // Software watchdog feed
    ESP.wdtFeed();
}

void cleanup() {
    LOG_PRINTLN("[CLEANUP] Moduller temizleniyor...");
    if (coil) {
        coil->stop();
        delete coil;
        coil = nullptr;
        LOG_PRINTLN("[CLEANUP] CoilController silindi");
    }

    if (network) {
        delete network;
        network = nullptr;
        LOG_PRINTLN("[CLEANUP] NetworkManager silindi");
    }

    LOG_PRINTLN("[CLEANUP] Temizleme tamamlandi");
    delay(500);
}

void checkMemoryHealth() {
    static unsigned long lastMemoryCheck = 0;
    const unsigned long MEMORY_CHECK_INTERVAL = 60000; // 1 dakika
    const int LOW_MEMORY_THRESHOLD = 8192; // 8KB
    const float HIGH_FRAGMENTATION_THRESHOLD = 40.0;
    const int LOW_STACK_THRESHOLD = 1024;

    unsigned long currentTime = millis();
    if (currentTime - lastMemoryCheck < MEMORY_CHECK_INTERVAL) {
        return;
    }
    lastMemoryCheck = currentTime;

    // Memory istatistiklerini al
    MemoryStats memStats = getMemoryStats();
    uint32_t freeStack = ESP.getFreeContStack();

    LOG_PRINT(F("[Memory] Free Heap: "));
    LOG_PRINT(memStats.freeHeap);
    LOG_PRINT(F(" bytes, Max Free Block: "));
    LOG_PRINT(memStats.maxAllocHeap);
    LOG_PRINT(F(" bytes, Fragmentation: "));
    LOG_PRINT(memStats.fragmentation);
    LOG_PRINT(F("%, Free Stack: "));
    LOG_PRINT(freeStack);
    LOG_PRINTLN(F(" bytes"));

    // Stack overflow kontrolü (kritik!)
    if (freeStack < LOW_STACK_THRESHOLD) {
        if (network) {
            static char stackMsg[96];
            snprintf(stackMsg, sizeof(stackMsg), "⚠️ Düşük stack: %u bytes", freeStack);
            network->publishSystemLog(LOG_LEVEL_ERROR, stackMsg);
        }
        if (freeStack < 512) {
            ESP.restart();
        }
    }

    static uint32_t lastFreeStack = 0;
    if (lastFreeStack > 0 && freeStack < lastFreeStack - 200) {
        LOG_PRINTF("[Stack] Stack kullanimi ani artis (dusus: %u bytes)\n", lastFreeStack - freeStack);
    }
    lastFreeStack = freeStack;

    // Fragmentation kontrolü
    if (memStats.fragmentation > HIGH_FRAGMENTATION_THRESHOLD) {
        if (network) {
            static char fragMsg[96];
            snprintf(fragMsg, sizeof(fragMsg), "Yüksek bellek fragmentasyonu: %u%% (free: %u)",
                    memStats.fragmentation, memStats.freeHeap);
            network->publishSystemLog(LOG_LEVEL_WARN, fragMsg);
        }
        if (memStats.fragmentation > 70) {
            ESP.restart();
        }
    }

    // Free heap kontrolü
    if (memStats.freeHeap < LOW_MEMORY_THRESHOLD) {
        if (memStats.freeHeap < 4096) {
            ESP.restart();
        }
    }
}

// ============================================================================
// Setup Fonksiyonu
// ============================================================================
void setup() {
    Serial.begin(115200);

    // -------------------------------------------------------------
    // TİCARİ GARANTİ: CPU HIZINI 160 MHZ'E ZORLA
    // -------------------------------------------------------------
    if (ESP.getCpuFreqMHz() != 160) {
        system_update_cpu_freq(160);
    }
    // -------------------------------------------------------------

    LOG_PRINTLN();
    LOG_PRINTLN("=================================");
    LOG_PRINTLN("PEMF IoT Coil Controller v3.0");
    LOG_PRINT("CPU Frekansi: ");
    LOG_PRINT(ESP.getCpuFreqMHz());
    LOG_PRINTLN(" MHz (Boost Modu Aktif)");

    LOG_PRINTLN("Moduller OOP Yapisi + Secrets.h");
    LOG_PRINTLN("=================================");

    feedWatchdog();

    LOG_PRINTF("Coil ID: %d\n", COIL_ID);
    LOG_PRINTLN("=================================");

    feedWatchdog();

    // 1. EEPROM Başlat & CONFIG_VERSION Kontrolü
    EEPROM.begin(EEPROM_SIZE);
    uint8_t storedVersion = EEPROM.read(EEPROM_CONFIG_VER_ADDR);
    if (storedVersion != CONFIG_VERSION) {
        LOG_PRINTLN("[SETUP] Config version değişti, EEPROM sıfırlanıyor...");
        for (int i = 0; i < 256; i++) EEPROM.write(i, 0); // WiFi ayarlarını sil
        EEPROM.write(EEPROM_CONFIG_VER_ADDR, CONFIG_VERSION);
        EEPROM.commit();
    }

    // 2. Modülleri COIL_ID ile oluştur
    network = new NetworkManager(COIL_ID);
    coil = new CoilController(PWM_PIN, COIL_ID, &timeManager);

    feedWatchdog();

    // 3. Sensörlerin İki Adımlı Başlatılması (I2C/ADC init -> PWM Init -> Calibration)
    sensors.beginWithoutCalibration();
    feedWatchdog();

    coil->begin();

    sensors.calibrate();
    feedWatchdog();

    // NetworkManager'i Secrets.h ile baslat
    network->begin(
        WIFI_SSID_CONST,
        WIFI_PASS_CONST,
        DEFAULT_CLOUD_MQTT_HOST, // Varsayılanı ver, NetworkManager içten kendi Local/Cloud dener
        DEFAULT_CLOUD_MQTT_PORT,
        DEFAULT_CLOUD_MQTT_USER,
        DEFAULT_CLOUD_MQTT_PASS
    );
    feedWatchdog();

    // TimeManager başlat
    timeManager.begin();
    feedWatchdog();

    // RESTART SONRASI PWM DURUMUNU GERİ YÜKLE
    if (coil->restorePWMState()) {
        LOG_PRINTLN("[SETUP] PWM durumu EEPROM'dan yuklendi, kaldigi yerden devam ediyor!");
    } else {
        LOG_PRINTLN("[SETUP] EEPROM'da kayitli PWM durumu yok veya gecersiz");
    }
    feedWatchdog();

    statusLED.begin();
    feedWatchdog();

    // Callback'leri ayarla
    network->setMqttCallback(handleMqttMessage);

    LOG_PRINTLN("==========================================");
    LOG_PRINTLN("SETUP TAMAMLANDI!");
    LOG_PRINTLN("==========================================");

    // Memory ve Stack durumu
    MemoryStats memStats = getMemoryStats();
    uint32_t freeStack = ESP.getFreeContStack();
    LOG_PRINTF("Free Heap: %u bytes\n", memStats.freeHeap);
    LOG_PRINTF("Max Free Block: %u bytes\n", memStats.maxAllocHeap);
    LOG_PRINTF("Fragmentation: %u%%\n", memStats.fragmentation);
    LOG_PRINTF("Free Stack: %u bytes ", freeStack);

    if (freeStack > 2000) {
        LOG_PRINTLN("✓ (EXCELLENT)");
    } else if (freeStack > 1500) {
        LOG_PRINTLN("✓ (GOOD)");
    } else if (freeStack > 1024) {
        LOG_PRINTLN("⚠ (WARNING)");
    } else {
        LOG_PRINTLN("✗ (CRITICAL)");
    }

    LOG_PRINTLN("==========================================");
}

// ============================================================================
// Ana Loop
// ============================================================================
void loop() {
    feedWatchdog();

    // Pointer kontrolü
    if (!network || !network->isMqttConnected()) {
        if (!coil) return; // Coil varsa update etmeliyiz
    }

    // Modulleri guncelle
    sensors.update();
    network->update();

    if (coil && network) {
        if (coil->consumeSyncFallbackEvent()) {
             network->publishEvent("fallback_log", "NTP yok, sync_all atlaniyor");
        }
    }

    // CoilController sync wait kontrolü
    if (coil->isWaiting() && timeManager.isSynced()) {
        unsigned long long currentTime = timeManager.getCurrentTimeMs();
        coil->checkSyncWait(currentTime);
    }

    coil->update();
    timeManager.update();

    // PWM KORUMA MEKANİZMASI
    static bool lastPwmState = false;
    bool currentPwmState = coil->isActive();

    if (currentPwmState != lastPwmState) {
        if (currentPwmState) {
            LOG_PRINTLN(F("[PWM] PWM AKTIF - Baglanti durumu PWM'i ASLA ETKILEMEZ!"));
        } else {
            LOG_PRINTLN(F("[PWM] ⏹️ PWM DURDU - Sadece stop komutu veya süre dolması ile durur"));
        }
        lastPwmState = currentPwmState;
    }

    static unsigned long lastPublish = 0;
    static unsigned long lastStatusPublish = 0;

    if (millis() - lastPublish > 1000) {
        if (network->isMqttConnected()) {
            SensorData sensorData = sensors.getData();
            network->publishSensorData(sensorData);
        }
        lastPublish = millis();
    }

    if (millis() - lastStatusPublish > 3000) {
        if (network->isMqttConnected()) {
            StatusData status;
            status.coil_id = COIL_ID;
            status.timestamp = millis();
            status.uptime = millis();

            MemoryStats memStats = getMemoryStats();
            status.free_heap = memStats.freeHeap;
            status.max_alloc_heap = memStats.maxAllocHeap;
            status.fragmentation = memStats.fragmentation;

            if (memStats.fragmentation > 50) {
                LOG_PRINTF("[MEM] ⚠️ High fragmentation detected: %u%% (free: %u, max: %u)\n",
                          memStats.fragmentation, memStats.freeHeap, memStats.maxAllocHeap);
            }

            sensors.populateStatus(status);
            network->populateStatus(status);
            coil->populateStatus(status);

            network->publishStatus(status);
        }
        lastStatusPublish = millis();
    }

    // Termal kesme: 500 ms'de bir yerel denetim (ağdan TAMAMEN bağımsız).
    static unsigned long lastThermalCheck = 0;
    if (millis() - lastThermalCheck >= 500) {
        lastThermalCheck = millis();
        SensorData td = sensors.getData();
        if (td.temp_sensor_ok) {
            if (td.tempObject >= TERMAL_KESME_C) {
                if (coil->isActive()) {
                    coil->stop();
                    if (network && network->isMqttConnected()) {
                        static char tmsg[72];
                        snprintf(tmsg, sizeof(tmsg), "Yerel termal kesme: %.1fC >= %.1fC",
                                 (double)td.tempObject, (double)TERMAL_KESME_C);
                        network->publishEvent("thermal_stop", tmsg);
                    }
                }
                g_thermalLock = true;
            } else if (g_thermalLock && td.tempObject <= TERMAL_DONUS_C) {
                g_thermalLock = false;
                if (network && network->isMqttConnected()) {
                    network->publishEvent("thermal_unlock", "Sicaklik dustu, start yeniden serbest");
                }
            }
        }
    }

    statusLED.update(network->isWiFiConnected(),
                     network->isMqttConnected(),
                     coil->isActive());

    checkMemoryHealth();
    yield();
}

// ============================================================================
// Command Deduplication Cache (MQTT duplicate message önleme)
// ============================================================================
const int CMD_CACHE_SIZE = 8;
static char commandIdCache[CMD_CACHE_SIZE][48];
static int cacheIndex = 0;

bool isCommandProcessed(const char* command_id) {
    if (strlen(command_id) == 0) {
        return false;
    }
    for (int i = 0; i < CMD_CACHE_SIZE; i++) {
        if (strcmp(commandIdCache[i], command_id) == 0) {
            return true;
        }
    }
    return false;
}

void addCommandToCache(const char* command_id) {
    if (strlen(command_id) == 0) return;
    strlcpy(commandIdCache[cacheIndex], command_id, sizeof(commandIdCache[0]));
    cacheIndex = (cacheIndex + 1) % CMD_CACHE_SIZE;
}

// ============================================================================
void handleMqttMessage(const char* topic, const char* payload) {
    LOG_PRINT(F("[MQTT] Mesaj alindi - Topic: "));
    LOG_PRINTLN(topic);

    // Stack optimizasyonu: Statik JSON buffer
    static StaticJsonDocument<384> jsonDoc;
    jsonDoc.clear();

    DeserializationError error = deserializeJson(jsonDoc, payload);
    if (error) {
        LOG_PRINT(F("[MQTT] JSON parse hatasi: "));
        LOG_PRINTLN(error.c_str());
        return;
    }

    feedWatchdog();
    processControlCommand(jsonDoc);
}

// ============================================================================
// Kontrol Komutunu İşle
// ============================================================================
void processControlCommand(JsonDocument& doc) {
    // Stack optimizasyonu: Statik bufferlar
    static char command[16];
    static char command_id[64];

    const char* cmdStr = doc["command"] | "";
    strlcpy(command, cmdStr, sizeof(command));

    const char* cmdIdStr = doc["command_id"] | "";
    strlcpy(command_id, cmdIdStr, sizeof(command_id));

    const bool isStop = (strcmp(command, "stop") == 0);

    // DUPLICATE COMMAND CHECK
    // ⚠️ STOP İSTİSNASI (2026-08-19): aynı command_id'li STOP tekrarı eskiden SESSİZCE
    // yutuluyordu (ACK yenilenmeden) — backend teslimden emin olamazdı. STOP idempotent:
    // tekrarında ACK yeniden gönderilir.
    if (isCommandProcessed(command_id)) {
        LOG_PRINTF("[CMD] Duplicate command: %s\n", command_id);
        if (isStop && network && strlen(command_id) > 0) {
            network->sendCommandAck(command_id, true);
        }
        return;
    }

    addCommandToCache(command_id);
    bool success = false;

    feedWatchdog();

    // RATE LIMIT CHECK — ⚠️ STOP MUAF (2026-08-19): aynı komut 10 sn'de 5+ kez gelince
    // düşürülüyordu ve STOP da kapsamdaydı. Panik anında arka arkaya STOP tam bu deseni
    // üretir; 6. STOP'un düşmesi HASTA GÜVENLİĞİ ihlalidir. STOP hiçbir koşulda sınırlanmaz.
    if (!isStop && !commandRateLimiter.allowCommand(command)) {
        LOG_PRINTF("[CMD] ✗ Rate limit exceeded: %s\n", command);
        if (strlen(command_id) > 0 && network) {
            network->sendCommandAck(command_id, false);
            network->publishEvent("command_error", "Rate limit exceeded");
        }
        return;
    }

    if (strcmp(command, "start") == 0) {
        // ── BACKEND UYUM YAMASI (2026-08-19) — dort kirigin kapanisi ──────────────
        // 1. `duty < 1` = DURDUR: backend'in park/reset yolu `duty: 0.0` gonderir; eski
        //    dogrulama bunu reddediyordu. Niyet acikca "kapat"tir.
        float dutyOn = doc.containsKey("duty") ? doc["duty"].as<float>() : -1.0f;
        if (doc.containsKey("duty") && dutyOn < 1.0f) {
            if (coil) {
                ControlCommand cmdKapat;
                cmdKapat.type = CMD_STOP;
                coil->handleCommand(cmdKapat);
            }
            if (strlen(command_id) > 0 && network) network->sendCommandAck(command_id, true);
            LOG_PRINTLN(F("[CMD] duty<1 -> STOP olarak islendi (backend park yolu)"));
            return;
        }

        // 2. TERMAL KILIT: yerel kesme tetiklendiyse sicaklik dusene kadar start reddedilir.
        if (g_thermalLock) {
            LOG_PRINTLN(F("[CMD] start reddedildi: TERMAL KILIT aktif"));
            if (strlen(command_id) > 0 && network) {
                network->sendCommandAck(command_id, false);
                network->publishEvent("thermal_lock", "Start reddedildi: bobin sicak (>48C), sogumasi bekleniyor");
            }
            return;
        }

        bool isValid = true;
        static char errorMsg[96];
        errorMsg[0] = '\0';

        if (!doc.containsKey("freq") || !doc.containsKey("duty") || !doc.containsKey("duration")) {
            isValid = false;
            strlcpy(errorMsg, "Missing required param(s)", sizeof(errorMsg));
        } else if (!doc["freq"].is<float>() && !doc["freq"].is<int>()) {
            // 3. FREQ SAYISAL: backend float gonderir (round(x,1) → "1.0"); eski `is<int>`
            //    denetimi TUM AI start'larini "freq must be integer" ile reddediyordu.
            isValid = false;
            strlcpy(errorMsg, "freq must be numeric", sizeof(errorMsg));
        } else {
            float fRaw = doc["freq"].as<float>();
            if (fRaw < 1.0f || fRaw > 1000.0f) { isValid = false; strlcpy(errorMsg, "freq out of range", sizeof(errorMsg)); }

            float d = dutyOn;
            if (d < 1.0 || d > 99.0) { isValid = false; strlcpy(errorMsg, "duty out of range", sizeof(errorMsg)); }

            // 4. DURATION = SANIYE (backend sozlesmesi `_esp_duration_seconds`; 0 = suresiz
            //    nobetcisi — backend kendi kapaklarini uygulayip gonderir). Kendi akil-sagligi
            //    tavani: 24 saat.
            long dur = doc["duration"].as<long>();
            if (dur < 0 || dur > 86400) { isValid = false; strlcpy(errorMsg, "duration out of range (sec)", sizeof(errorMsg)); }
        }

        // NOT (2026-08-19): "PWM already active, stop first" reddi KALDIRILDI. Backend canli
        // ayarlamayi tekrar `start` ile yapar (set_params hic kullanmaz); red, AI'nin dongu
        // ici duty guncellemelerini sessizce bosa cikariyor ve bobini ilk parametrede
        // donduruyordu. Aktifken gelen start = parametre guncelle + sureyi yeni komuta gore
        // yeniden baslat (CoilController::start zaten boyle davranir).

        if (!isValid) {
            LOG_PRINTF("[CMD] ✗ Validation failed: %s\n", errorMsg);
            if (strlen(command_id) > 0 && network) {
                network->sendCommandAck(command_id, false);
                static char errorEvent[128];
                snprintf(errorEvent, sizeof(errorEvent), "Command validation failed: %s", errorMsg);
                network->publishEvent("command_error", errorEvent);
            }
            return;
        }

        int freq = (int)round(doc["freq"].as<float>());   // float kabul, DDS icin tam sayiya yuvarla
        int duty = (int)round(dutyOn);
        int duration = (int)doc["duration"].as<long>();   // SANIYE

        unsigned long long target_timestamp = 0;
        if (doc.containsKey("start_at")) {
            if (doc["start_at"].is<unsigned long long>()) {
                target_timestamp = doc["start_at"].as<unsigned long long>();
            } else {
                const char* str = doc["start_at"];
                target_timestamp = strtoull(str, nullptr, 10);
            }

            if (target_timestamp > 0) {
                if (timeManager.isSynced()) {
                    unsigned long long currentTime = timeManager.getCurrentTimeMs();
                    long waitMs = (long)(target_timestamp - currentTime);

                    if (waitMs > 0 && waitMs < 10000) {
                        LOG_PRINTF("[SYNC] Beklenecek Sure: %ld ms (Non-blocking)\n", waitMs);
                    } else if (waitMs < 0) {
                        LOG_PRINTLN("[SYNC] HATA: Hedef zaman gecmiste kaldi! Hemen baslatiliyor.");
                        target_timestamp = 0;
                    } else {
                        LOG_PRINTLN("[SYNC] UYARI: Bekleme süresi çok uzun (>10s), hemen başlatılıyor.");
                        target_timestamp = 0;
                    }
                } else {
                    LOG_PRINTLN("[SYNC] UYARI: Zaman senkronize edilmemiş, hemen başlatılıyor.");
                    target_timestamp = 0;
                }
            }
        }

        if (coil) {
            ControlCommand cmd;
            cmd.type = CMD_START;
            cmd.frequency = freq;
            cmd.dutyCycle = duty;
            cmd.durationSec = duration;
            cmd.timestamp = target_timestamp;
            coil->handleCommand(cmd);
            success = coil->isActive() || coil->isWaiting();

            if (success) {
                LOG_PRINTF("[CMD] ✓ PWM başlatıldı: %dHz, %d%%, %dsn\n", freq, duty, duration);
            }
        }

    } else if (strcmp(command, "stop") == 0) {
        if (coil) {
            ControlCommand cmd;
            cmd.type = CMD_STOP;
            coil->handleCommand(cmd);
            success = !coil->isActive();
            LOG_PRINTLN("[CMD] ✓ PWM durduruldu");
        }

    } else if (strcmp(command, "set_params") == 0) {
        // [INLINED VALIDATION FOR SET_PARAMS]
        bool isValid = true;
        static char errorMsg[96];
        errorMsg[0] = '\0';

        if (!doc.containsKey("freq") && !doc.containsKey("duty") && !doc.containsKey("duration")) {
            isValid = false;
            strlcpy(errorMsg, "At least one parameter required (freq/duty/duration)", sizeof(errorMsg));
        } else {
            if (doc.containsKey("freq")) {
                if (!doc["freq"].is<float>() && !doc["freq"].is<int>()) {
                    isValid = false;
                    strlcpy(errorMsg, "freq must be numeric", sizeof(errorMsg));
                } else {
                    float f = doc["freq"].as<float>();   // start ile ayni: float kabul
                    if (f < 1.0f || f > 1000.0f) { isValid = false; strlcpy(errorMsg, "freq out of range", sizeof(errorMsg)); }
                }
            }
            if (isValid && doc.containsKey("duty")) {
                float d = doc["duty"].as<float>();
                if (d < 1.0 || d > 99.0) { isValid = false; strlcpy(errorMsg, "duty out of range", sizeof(errorMsg)); }
            }
            if (isValid && doc.containsKey("duration")) {
                if (!doc["duration"].is<int>()) {
                    isValid = false;
                    strlcpy(errorMsg, "duration must be integer", sizeof(errorMsg));
                } else {
                    // SANIYE (backend sozlesmesi) — start ile ayni tavan (24 saat).
                    long dur = doc["duration"].as<long>();
                    if (dur < 0 || dur > 86400) { isValid = false; strlcpy(errorMsg, "duration out of range (sec)", sizeof(errorMsg)); }
                }
            }
        }

        if (!isValid) {
            LOG_PRINTF("[CMD] ✗ Validation failed: %s\n", errorMsg);
            if (strlen(command_id) > 0 && network) {
                network->sendCommandAck(command_id, false);
                static char errorEvent[128];
                snprintf(errorEvent, sizeof(errorEvent), "Command validation failed: %s", errorMsg);
                network->publishEvent("command_error", errorEvent);
            }
            return;
        }

        // Mevcut değerleri al veya yenileriyle güncelle
        int freq = doc["freq"] | (coil ? coil->getStatus().frequency : 1000);
        float dutyFloat = doc["duty"] | (coil ? coil->getStatus().dutyCycle : 50.0);
        int duty = (int)round(dutyFloat);
        // SANIYE: kalan sure ms -> sn (eski kod /60000 ile dakikaya ceviriyordu).
        int duration = doc["duration"] | (coil ? (int)(coil->getStatus().remainingTime / 1000) : 0);

        if (coil) {
            ControlCommand cmd;
            cmd.type = CMD_UPDATE_PARAMS;
            cmd.frequency = freq;
            cmd.dutyCycle = duty;
            cmd.durationSec = duration;
            coil->handleCommand(cmd);
            success = true;
            LOG_PRINTF("[CMD] ✓ Parametreler güncellendi: %dHz, %d%%, %dsn\n", freq, duty, duration);
        }

    } else if (strcmp(command, "sync_all") == 0) {
        unsigned long long target_timestamp = doc["start_at"] | 0ULL;
        if (coil && coil->isActive()) {
            ControlCommand cmd;
            cmd.type = CMD_SYNC_ALL;
            cmd.timestamp = target_timestamp;
            coil->handleCommand(cmd);
            success = true;
        }

    } else if (strcmp(command, "SELFTEST") == 0) {
        /* D-1 tamamlayıcısı (2026-08-19): backend artık selftest'i doğru topiğe yayınlıyor
         * ama 8266'da işleyici yoktu → "Unknown command" + success=false dönüyordu (arızalı
         * cihaz ile işleyicisiz cihaz ayırt edilemiyordu). S3 İLE AYNI GÜVENLİK SEMANTİĞİ:
         * self-test ASLA kendi kendini enerjilendirmez — yalnız PWM ZATEN AKTİFKEN alan ölçer
         * (mag ≥ 0.10 mT = geçti). Pasifken "ölçüm yapılamadı" olayı döner, bobin başlatılmaz. */
        SensorData st = sensors.getData();
        static char stMsg[96];
        if (coil && coil->isActive()) {
            bool gecti = st.magnetic_sensor_ok && (st.magneticField >= 0.10f);
            snprintf(stMsg, sizeof(stMsg), "coil8 self-test: mag=%.3fmT sensor_ok=%d",
                     (double)st.magneticField, st.magnetic_sensor_ok ? 1 : 0);
            if (network) network->publishEvent(gecti ? "selftest_ok" : "selftest_fail", stMsg);
            success = gecti;
        } else {
            /* Pasif: guvenli-red — S3 de pasifken olcum yapmaz (kendini enerjilendirmek yasak) */
            snprintf(stMsg, sizeof(stMsg), "coil8 self-test atlandi: PWM pasif (guvenlik)");
            if (network) network->publishEvent("selftest_skipped", stMsg);
            success = true; /* islendi (arizali degil); sonuc event'te */
        }

    } else if (strcmp(command, "status") == 0) {
        success = true; // Status düzenli gidiyor

    } else if (strcmp(command, "clear_wifi") == 0) {
        LOG_PRINTLN("[CMD] Clear WiFi komutu alındı!");
        if (network) {
            network->clearAllWiFiCredentials();
            network->sendCommandAck(command_id, true);
            network->publishEvent("clear_wifi", "Tüm WiFi bilgileri temizlendi, ESP yeniden başlatılıyor");
            delay(1000);
            cleanup();
            ESP.restart();
        }
        success = true;
    } else {
        LOG_PRINTF("[CMD] ✗ Bilinmeyen komut: %s\n", command);
        if (strlen(command_id) > 0 && network) {
            network->sendCommandAck(command_id, false);
            static char errorMsg[96];
            snprintf(errorMsg, sizeof(errorMsg), "Unknown command: %s", command);
            network->publishEvent("command_error", errorMsg);
        }
        return;
    }

    // Command ACK gönder
    if (strlen(command_id) > 0 && network) {
        network->sendCommandAck(command_id, success);
        LOG_PRINTF("[CMD] ACK gönderildi: %s -> %s\n", command_id, success ? "SUCCESS" : "FAILED");
    }

    feedWatchdog();
}
