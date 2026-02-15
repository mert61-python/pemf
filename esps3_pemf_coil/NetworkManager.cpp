#include "NetworkManager.h"
#include <HTTPUpdate.h> // ✅ Add OTA Support

static PemfNetworkManager* instance = nullptr;

// ============================================================================
// BLE CALLBACKS
// ============================================================================

// ✅ Command Callback (For Offline Control)
class BLECommandCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
        String value = pCharacteristic->getValue();
        if (value.length() > 0) {
            String strVal = value;
            LOG_PRINTF("[BLE] Command Rcv: %s\n", strVal.c_str());
            
            // Forward to internal command processor (reusing MQTT logic)
            // Topic is dummy "BLE_CMD"
            if (instance) {
                instance->_processIncomingCommand("BLE_CMD", (byte*)strVal.c_str(), strVal.length());
            }
        }
    }
};

class NetworkConfigCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
        String value = pCharacteristic->getValue();
        if (value.length() > 0) {
            String uuid = pCharacteristic->getUUID().toString().c_str();
            String strVal = value;
            
            if (uuid == BLE_CHAR_WIFI_SSID_UUID) {
                // SSID Buffer Logic for Long Writes (MTU fragmentation)
                static String ssidBuffer = "";
                static unsigned long lastWriteTime = 0;
                
                // If specific time passed, clear buffer (New write)
                if (millis() - lastWriteTime > 2000) { 
                    ssidBuffer = ""; 
                }
                
                ssidBuffer += strVal;
                lastWriteTime = millis();
                
                 LOG_PRINTF("[BLE] SSID Chunk Received: %s (Total: %s)\n", strVal.c_str(), ssidBuffer.c_str());

                 // Save only if it looks complete? No, save update.
                 // Ideally Android sends it in one go with high MTU.
                 // But we save the accumulated buffer.
                 Preferences prefs;
                 prefs.begin("pemf_config", false);
                 prefs.putString(PREF_KEY_WIFI_SSID, ssidBuffer);
                 prefs.end();
            }  
            else if (uuid == BLE_CHAR_WIFI_PASS_UUID) {
                 // Password Buffer Logic (Handles MTU Fragmentation)
                 static String passBuffer = "";
                 static unsigned long lastPassWriteTime = 0;
                 
                 // Reset buffer if too much time passed (new attempt)
                 if (millis() - lastPassWriteTime > 2000) { 
                     passBuffer = ""; 
                 }
                 
                 passBuffer += strVal;
                 lastPassWriteTime = millis();
                 
                 Preferences prefs;
                 prefs.begin("pemf_config", false);
                 prefs.putString(PREF_KEY_WIFI_PASS, passBuffer);
                 prefs.end();
                 
                 LOG_PRINTF("[BLE] Password Chunk Received (Total Len: %d). Restart scheduled...\n", passBuffer.length());
                 
                 // Debounced Restart: Wait 1.5s after LAST chunk to ensure transmission valid
                 if (instance) {
                     instance->triggerRestart(1500);
                 }
            }
        }
    }
};

PemfNetworkManager::PemfNetworkManager() {
    instance = this;
    // Dynamic Allocation (Heap) to prevent Stack Overflow & Corruption
    _netClient = new WiFiClientSecure();
    _mqtt = new PubSubClient();
    _server = new WebServer(80);
}

void PemfNetworkManager::_mqttCallback(char* topic, byte* payload, unsigned int length) {
    if (instance) {
        instance->_processIncomingCommand(topic, payload, length);
    }
}

void PemfNetworkManager::begin() {
    LOG_PRINTLN("[Core 0] NetworkManager başlatılıyor...");
    
    // 1. Config Yükle
    _loadConfig();
    
    // 2. WiFi Başlatma Denemesi
    WiFi.mode(WIFI_STA);
    _connectWiFi();
    
    // Eğer connectWiFi başarısız olduysa ve BLE moduna geçildiyse
    // BLE Service aktif kalir.
    
    // 3. MQTT Ayarla (Sadece STA modundaysak anlamlı ama dursun)
    _netClient->setInsecure(); 
    _mqtt->setClient(*_netClient);
    _mqtt->setServer(_mqttServer.c_str(), _mqttPort);
    _mqtt->setCallback(_mqttCallback);
    // CRITICAL FIX: Buffer boyutu artirildi (Varsayilan 256 yetersiz)
    _mqtt->setBufferSize(2048); 
    
    // 4. Topic Hazırla
    _topicStatus = "pemf/coil/" + String(_coilId) + "/status";
    _topicControl = "pemf/coil/" + String(_coilId) + "/control";
    _topicEvents = "pemf/coil/" + String(_coilId) + "/events";
}

void PemfNetworkManager::_loadConfig() {
    _prefs.begin("pemf_config", true); // Read-only
    _ssid = _prefs.getString(PREF_KEY_WIFI_SSID, DEFAULT_WIFI_SSID);
    _password = _prefs.getString(PREF_KEY_WIFI_PASS, DEFAULT_WIFI_PASS);
    _mqttServer = _prefs.getString(PREF_KEY_MQTT_SERVER, DEFAULT_MQTT_SERVER);
    _mqttPort = _prefs.getInt(PREF_KEY_MQTT_PORT, DEFAULT_MQTT_PORT);
    
    // FIX: Force usage of FACTORY_COIL_ID from Secrets.h
    // This allows changing ID via firmware update (Secrets.h) without needing to wipe NVS.
    _coilId = FACTORY_COIL_ID; 
    // _coilId = _prefs.getInt(PREF_KEY_COIL_ID, FACTORY_COIL_ID); // Disabled NVS Load
    
    _prefs.end();
    
    LOG_PRINTF("[Config] SSID: '%s', Coil ID: %d\n", _ssid.c_str(), _coilId);
}

void PemfNetworkManager::triggerRestart(unsigned long delayMs) {
    _restartPending = true;
    _restartTargetTime = millis() + delayMs;
    LOG_PRINTF("[Sys] Restart scheduled in %lu ms\n", delayMs);
}

void PemfNetworkManager::process() {
    // Check pending restart
    if (_restartPending) {
        if (millis() >= _restartTargetTime) {
            LOG_PRINTLN("[Sys] Performing scheduled restart...");
            delay(100);
            ESP.restart();
        }
    }

    static bool lastWiFiState = false;
    static bool lastPortalState = false;
    
    // AP Modundaysak veya BLE aktifse
    if (_bleActive) {
        // BLE maintain (genelde otomatik ama status guncellemesi burda olabilir)
        return; // MQTT ye gerek yok
    }

    // 1. WiFi Kontrolü (STA Modu)
    bool currentWiFiState = (WiFi.status() == WL_CONNECTED);
    
    // WiFi durumu değişti mi?
    if (currentWiFiState != lastWiFiState) {
        if (currentWiFiState) {
            // WiFi bağlandı
            if (_mqtt && _mqtt->connected()) {
                String msg = "WiFi bağlantısı başarılı: " + WiFi.SSID();
                publishEvent("wifi_connected", msg.c_str());
            }
            LOG_PRINTLN("[WiFi] Bağlandı!");
        } else {
            // WiFi koptu
            if (_mqtt && _mqtt->connected()) {
                publishEvent("wifi_disconnected", "WiFi bağlantısı kesildi");
            }
            LOG_PRINTLN("[WiFi] Bağlantı kesildi!");
        }
        lastWiFiState = currentWiFiState;
    }
    
    if (!currentWiFiState) {
        // WiFi koptuğunda:
        
        // 1. Bir kez reconnect dene
        LOG_PRINTLN("[WiFi] Reconnecting (Single Attempt)...");
        WiFi.disconnect(); 
        WiFi.reconnect();
        
        unsigned long startWait = millis();
        bool reconnected = false;
        while(millis() - startWait < 5000) { // 5 saniye bekle
             if(WiFi.status() == WL_CONNECTED) {
                 reconnected = true;
                 break;
             }
             delay(200);
        }
        
        if(reconnected) {
             LOG_PRINTLN("[WiFi] Reconnected Successfully. Staying Online.");
             _wifiConnected = true;
        } else {
             LOG_PRINTLN("[WiFi] Reconnect Failed. Switching to OFFLINE MODE (BLE).");
             _wifiConnected = false;
             // WiFi'yi kapat (Pil tasarrufu ve kafa karışıklığını önlemek için)
             WiFi.disconnect(true); 
             WiFi.mode(WIFI_OFF);
             
             // BLE Başlat
             _startBLEService();
             
             // Artık bu döngüden çık, BLE modundayız. 
             // Kullanıcı reset atmadan tekrar WiFi denemeyecek.
             return;
        }
    }
    
    // 2. MQTT Kontrolü (Sadece WiFi bağlıysa)
    if (_mqtt && !_mqtt->connected() && WiFi.status() == WL_CONNECTED) {
        _reconnectMQTT();
    }
    
    // 3. MQTT Loop
    if (_mqtt && WiFi.status() == WL_CONNECTED) {
         _mqtt->loop();
    }
}

// See implementation at the bottom of the file
    // I need to change header to PUBLIC or add friend.
    
    // Easier: Add a public method `handleBLECommand` in header.
    // Or simpler: Just Move `_processIncomingCommand` to public section in header.


void PemfNetworkManager::_connectWiFi() {
    // SSID boşsa direkt BLE Provisioning Moduna geç
    if (_ssid == "") {
        LOG_PRINTLN("[WiFi] SSID Ayarlanmamış! BLE Provisioning Moduna geçiliyor...");
        _startBLEService();
        return;
    }

    if (WiFi.status() == WL_CONNECTED) return;
    
    // Eğer BLE açıksa kapatmayı dene (Bağlantı deneyeceğiz)
    // _stopBLEService(); // (İsteğe bağlı: WiFi denerken BLE açık kalabilir mi? Çakışma olabilir)

    LOG_PRINTF("[WiFi] Bağlanılıyor: %s\n", _ssid.c_str());
    WiFi.begin(_ssid.c_str(), _password.c_str());
    
    int attempt = 0;
    while (WiFi.status() != WL_CONNECTED && attempt < 20) { // 10 sn dene
        delay(500);
        LOG_PRINT(".");
        attempt++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        LOG_PRINTLN("\n[WiFi] Bağlandı!");
        LOG_PRINTLN(WiFi.localIP());
        _stopBLEService(); // Başarılıysa BLE'yi kapat
    } else {
        LOG_PRINTLN("\n[WiFi] Bağlantı Başarısız! BLE Moduna geçiliyor...");
        _startBLEService();
    }
}

void PemfNetworkManager::_startBLEService() {
    if (_bleActive) return;

    LOG_PRINTLN("[Network] BLE Provisioning Modu Başlatılıyor...");
    
    // Create Device
    String devName = "PEMF-Coil-" + String(_coilId);
    BLEDevice::init(devName.c_str());
    
    // Create Server
    BLEServer *pServer = BLEDevice::createServer();
    // Callback eklenebilir (Connect/Disconnect)

    // Create Service
    BLEService *pService = pServer->createService(BLE_SERVICE_UUID);

    // Characteristics
    // 1. Command (Read/Write)
    BLECharacteristic *pCommandChar = pService->createCharacteristic(
        BLE_CHAR_COMMAND_UUID,
        BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_WRITE
    );
    pCommandChar->setCallbacks(new BLECommandCallbacks()); // ✅ Attach callback for Offline Control
    
    // 2. Status (Read/Notify)
    _pStatusChar = pService->createCharacteristic(
        BLE_CHAR_STATUS_UUID,
        BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
    );
    _pStatusChar->addDescriptor(new BLE2902()); // Add Client Config Descriptor for Notify
    
    // 3. SSID (Write)
    BLECharacteristic *pSsidChar = pService->createCharacteristic(
        BLE_CHAR_WIFI_SSID_UUID,
        BLECharacteristic::PROPERTY_WRITE
    );
    pSsidChar->setCallbacks(new NetworkConfigCallbacks()); // Define callback
    
    // 4. Pass (Write)
    BLECharacteristic *pPassChar = pService->createCharacteristic(
        BLE_CHAR_WIFI_PASS_UUID,
        BLECharacteristic::PROPERTY_WRITE
    );
    pPassChar->setCallbacks(new NetworkConfigCallbacks()); // Define callback

    // Start Service
    pService->start();

    // Advertise
    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(BLE_SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    // iOS için min/max interval (Opsiyonel)
    pAdvertising->setMinPreferred(0x06);  
    pAdvertising->setMinPreferred(0x12);
    
    BLEDevice::startAdvertising();
    
    _bleActive = true;
    LOG_PRINTLN("[BLE] Waiting for client connection to provision WiFi...");
}

void PemfNetworkManager::_stopBLEService() {
    if (!_bleActive) return;
    LOG_PRINTLN("[BLE] Stopping BLE...");
    BLEDevice::deinit(true); // Stop and release memory
    _bleActive = false;
    _pStatusChar = nullptr; // Clear pointer
}

// Deprecated WebServer Functions (Removed/Placeholder)
// void PemfNetworkManager::_handleWebServer() {}
// void PemfNetworkManager::_handleSaveConfig() {}

void PemfNetworkManager::_reconnectMQTT() {
    if (_bleActive) return; // BLE modunda MQTT bağlanma
    if (WiFi.status() != WL_CONNECTED) return;
    
    static bool lastMqttState = false; // Son MQTT durumu
    
    LOG_PRINTLN("[MQTT] Bağlanılıyor...");
    String clientId = "PEMF-Coil-" + String(_coilId);
    
    if (_mqtt->connect(clientId.c_str(), DEFAULT_MQTT_USER, DEFAULT_MQTT_PASS)) {
        LOG_PRINTLN("[MQTT] Bağlandı!");
        _mqtt->subscribe(_topicControl.c_str());
        
        // MQTT bağlandı eventi
        if (!lastMqttState) {
            publishEvent("mqtt_connected", "MQTT broker'a bağlandı");
            lastMqttState = true;
        }
    } else {
        LOG_PRINTF("[MQTT] Hata, rc=%d. 5sn bekleniyor.\\n", _mqtt->state());
        
        // MQTT bağlantı koptu eventi
        if (lastMqttState) {
            lastMqttState = false;
        }
        
        vTaskDelay(5000 / portTICK_PERIOD_MS); 
    }
}

void PemfNetworkManager::publishStatus(const SystemStatusMsg& msg) {
    // Modify guard: Proceed if MQTT connected OR BLE active
    bool mqttReady = _mqtt && _mqtt->connected();
    if (!mqttReady && !_bleActive) return;
    
    JsonDocument doc; 
    
    // GUI Uyumluluğu için Düz (Flat) JSON Yapısı
    // Python GUI: gui_pyqt_v11.py (on_mqtt_message)
    
    doc["coil_id"] = _coilId;
    doc["fw_version"] = FIRMWARE_VERSION; // ✅ Firmware Info for OTA
    doc["timestamp"] = msg.uptime; // GUI bunu uptime/timestamp olarak kullanıyor
    doc["uptime"] = msg.uptime;
    doc["free_heap"] = msg.freeHeap;
    doc["max_alloc_heap"] = msg.maxAllocHeap;
    doc["fragmentation"] = msg.fragmentation;
    
    // WiFi ve MQTT Durum Bilgileri
    bool wifiConnected = (WiFi.status() == WL_CONNECTED);
    doc["wifi_connected"] = wifiConnected;
    if (wifiConnected) {
        doc["wifi_ssid"] = WiFi.SSID();
        doc["wifi_rssi"] = WiFi.RSSI();
        doc["wifi_ip"] = WiFi.localIP().toString();
    } else {
        doc["wifi_ssid"] = "";
        doc["wifi_rssi"] = 0;
        doc["wifi_ip"] = "";
    }
    
    doc["portal_active"] = _apMode;
    if (_apMode) {
        doc["portal_ip"] = WiFi.softAPIP().toString();
        doc["portal_ssid"] = "PEMF-Coil-" + String(_coilId);
    } else {
        doc["portal_ip"] = "";
        doc["portal_ssid"] = "";
    }
    
    doc["mqtt_connected"] = _mqtt->connected();
    
    // PWM Verileri (Flat)
    doc["pwm_active"] = msg.pwm.active;
    doc["pwm_frequency"] = msg.pwm.frequency;
    doc["pwm_duty"] = msg.pwm.dutyCycle;
    doc["pwm_remaining_time"] = msg.pwm.remainingTimeSec;
    doc["pwm_duration"] = msg.pwm.durationMinutes;
    doc["pwm_start_timestamp"] = (unsigned long long)msg.pwm.startTimestamp;
    
    // Sensör Verileri (Flat ve Key İsimleri GUI ile uyumlu)
    doc["object_temp"] = msg.sensors.tempObject;     // GUI: object_temp
    doc["ambient_temp"] = msg.sensors.tempAmbient;   // GUI: ambient_temp
    doc["current"] = msg.sensors.current;
    doc["magnetic_field"] = msg.sensors.magneticField; // GUI: magnetic_field
    
    // Maksimum değerler (PWM aktifken ölçülen)
    doc["max_magnetic_field"] = msg.sensors.maxMagneticField; // mT
    doc["max_current"] = msg.sensors.maxCurrent;             // A
    
    // Status Flags
    doc["sensors_ok"] = msg.sensors.allSensorsOk;
    doc["temp_sensor_ok"] = msg.sensors.tempSensorOk;
    doc["magnetic_sensor_ok"] = msg.sensors.magSensorOk;
    doc["current_sensor_ok"] = msg.sensors.currentSensorOk;
    
    String output;
    serializeJson(doc, output);
    
    // Asıl status topic'ine gönder
    if (mqttReady && !_mqtt->publish(_topicStatus.c_str(), output.c_str())) {
         LOG_PRINTLN("[MQTT] Status Publish Failed! (Packet too big?)");
    } else {
        // Debug: Sıcaklık verilerinin gönderildiğini logla
        static unsigned long lastTempLog = 0;
        if (millis() - lastTempLog > 10000) {  // 10 saniyede bir
            LOG_PRINTF("[MQTT] Status -> Bobin: %.1f°C, Ortam: %.1f°C\n", 
                       msg.sensors.tempObject, msg.sensors.tempAmbient);
            lastTempLog = millis();
        }
    }
    
    // BLE Notification
    if (_bleActive && _pStatusChar) {
        _pStatusChar->setValue((uint8_t*)output.c_str(), output.length());
        _pStatusChar->notify();
    }
}

bool PemfNetworkManager::isMqttConnected() {
    if(!_mqtt) return false;
    return _mqtt->connected();
}

void PemfNetworkManager::publishSensorData(const SensorReadings& data) {
    // Modify guard: Proceed if MQTT connected OR BLE active
    bool mqttReady = _mqtt && _mqtt->connected();
    if (!mqttReady && !_bleActive) return;
    
    JsonDocument doc;
    doc["coil_id"] = _coilId;
    doc["msg_type"] = "sensor"; // Add discriminator for BLE
    doc["timestamp"] = millis();
    doc["object_temp"] = data.tempObject;
    doc["ambient_temp"] = data.tempAmbient;
    doc["magnetic_field"] = data.magneticField;
    doc["current"] = data.current;
    doc["max_magnetic_field"] = data.maxMagneticField;  // Maksimum manyetik alan
    doc["max_current"] = data.maxCurrent;              // Maksimum akım
    doc["temp_sensor_ok"] = data.tempSensorOk;
    doc["magnetic_sensor_ok"] = data.magSensorOk;
    doc["current_sensor_ok"] = data.currentSensorOk;
    doc["sensors_ok"] = data.allSensorsOk;
    
    String output;
    serializeJson(doc, output);
    
    String topicSensors = "pemf/coil/" + String(_coilId) + "/sensors";
    if (mqttReady && !_mqtt->publish(topicSensors.c_str(), output.c_str())) {
        LOG_PRINTLN("[MQTT] Sensor data publish failed!");
    } else {
        // Debug: Sıcaklık verilerinin gönderildiğini logla
        static unsigned long lastSensorTempLog = 0;
        if (millis() - lastSensorTempLog > 10000) {  // 10 saniyede bir
            LOG_PRINTF("[MQTT] Sensors -> Bobin: %.1f°C, Ortam: %.1f°C\n", 
                       data.tempObject, data.tempAmbient);
            lastSensorTempLog = millis();
        }
    }
    
    // BLE Notification
    if (_bleActive && _pStatusChar) {
        _pStatusChar->setValue((uint8_t*)output.c_str(), output.length());
        _pStatusChar->notify();
    }
}

void PemfNetworkManager::publishEvent(const char* eventType, const char* message) {
    if (_apMode || !_mqtt->connected()) return;
    
    JsonDocument doc;
    doc["coil_id"] = _coilId;
    doc["event_type"] = eventType;
    doc["message"] = message;
    doc["timestamp"] = millis();
    
    String output;
    serializeJson(doc, output);
    
    if (!_mqtt->publish(_topicEvents.c_str(), output.c_str())) {
        LOG_PRINTLN("[MQTT] Event publish failed!");
    }
}

void PemfNetworkManager::sendCommandAck(const char* command_id, bool success) {
    if (_apMode || !_mqtt->connected()) return;
    
    JsonDocument doc;
    doc["coil_id"] = _coilId;
    doc["command_id"] = command_id;
    doc["success"] = success;
    doc["timestamp"] = millis();
    
    String output;
    serializeJson(doc, output);
    
    String topicAck = "pemf/coil/" + String(_coilId) + "/ack";
    if (!_mqtt->publish(topicAck.c_str(), output.c_str(), true)) {
        LOG_PRINTLN("[MQTT] ACK publish failed!");
    }
}

void PemfNetworkManager::publishSystemLog(LogLevel level, const char* message) {
    // Önce seri porta yaz
    const char* levelStr = "";
    if (level == PEMF_LOG_INFO) {
        levelStr = "[INFO]";
    } else if (level == PEMF_LOG_WARN) {
        levelStr = "[WARN]";
    } else if (level == PEMF_LOG_ERROR) {
        levelStr = "[ERROR]";
    }
    
    LOG_PRINTF("%s %s\n", levelStr, message);
    
    // Sadece WARN ve ERROR'ları MQTT'ye gönder
    if ((level == PEMF_LOG_WARN || level == PEMF_LOG_ERROR) && _mqtt && _mqtt->connected() && !_apMode) {
        JsonDocument doc;
        doc["level"] = level;
        doc["msg"] = message;
        doc["heap"] = ESP.getFreeHeap();
        
        String output;
        serializeJson(doc, output);
        
        String topicLog = "pemf/coil/" + String(_coilId) + "/system/log";
        _mqtt->publish(topicLog.c_str(), output.c_str(), false);
    }
}

void PemfNetworkManager::_processIncomingCommand(char* topic, byte* payload, unsigned int length) {
    LOG_PRINTF("[MQTT] Mesaj: %s\n", topic);
    
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, payload, length);
    
    if (error) {
        LOG_PRINTLN("[MQTT] JSON Parse Hatası");
        return;
    }
    
    ControlCommand cmd;
    String cmdStr = doc["command"];
    cmdStr.toUpperCase(); // Case-insensitive compare (GUI sends 'start', we expect 'START')
    
    if (cmdStr == "START") {
        cmd.type = CMD_START;
        cmd.frequency = doc["freq"];
        cmd.dutyCycle = doc["duty"];
        cmd.durationMinutes = doc["duration"];
        if(doc.containsKey("start_at")) {
             cmd.timestamp = doc["start_at"];
        } else {
             cmd.timestamp = 0;
        }
    } 
    else if (cmdStr == "STOP") {
        cmd.type = CMD_STOP;
    }
    else if (cmdStr == "UPDATE") {
        cmd.type = CMD_UPDATE_PARAMS;
        cmd.frequency = doc["freq"];
        cmd.dutyCycle = doc["duty"];
    }
    else if (cmdStr == "UPDATE_FIRMWARE") {
        String url = doc["url"];
        LOG_PRINTF("[OTA] Firmware update requested from: %s\n", url.c_str());
        
        if (url.length() > 0) {
            // Stop PWM before update for safety
            ControlCommand stopCmd;
            stopCmd.type = CMD_STOP;
            xQueueSend(commandQueue, &stopCmd, 0);
            delay(500); // Wait for stop
            
            // Start OTA
            t_httpUpdate_return ret = httpUpdate.update(*_netClient, url);

            switch (ret) {
                case HTTP_UPDATE_FAILED:
                    LOG_PRINTF("[OTA] Update Failed. Error (%d): %s\n", httpUpdate.getLastError(), httpUpdate.getLastErrorString().c_str());
                    break;
                case HTTP_UPDATE_NO_UPDATES:
                    LOG_PRINTLN("[OTA] No updates");
                    break;
                case HTTP_UPDATE_OK:
                    LOG_PRINTLN("[OTA] Update OK! Restarting...");
                    break;
            }
        }
        return; // Don't queue this command
    }
    else {
        LOG_PRINTF("[MQTT] Bilinmeyen Komut: %s\n", cmdStr.c_str());
        return;
    }
    
    if (xQueueSend(commandQueue, &cmd, 0) != pdTRUE) {
        LOG_PRINTLN("[Error] Queue Dolu!");
    }
}
