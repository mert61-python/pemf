#include "NetworkManager.h"
#include "Secrets.h"  // 2026-08-19: DEFAULT_LOCAL_MQTT_* + MQTT_LOCAL_MAX_RETRIES burada tanimli - include eksikti, dosya derlenmiyordu
#include <limits.h>  // ULONG_MAX iÃ§in gerekli

// Diagnostics sistemi kaldırıldı

// Static instance pointer for MQTT callback
NetworkManager* NetworkManager::_instance = nullptr;

// Callback lock for thread-safety
volatile unsigned long NetworkManager::_callbackLock = 0;

NetworkManager::NetworkManager(int coilId) {
    _coilId = coilId;
    // MQTT broker bilgileri artık begin() içinde config'den alınacak
    _mqttBrokerHost[0] = '\0';
    _mqttBrokerPort = 8883;
    _globalControlTopic = "pemf/control/all";
    _msgCallback = nullptr;
    _portalActive = false;
    _portalStartTime = 0;
    _pendingWifiConnect = false;
    _pendingWifiConnectTime = 0;
    _pendingSSID[0] = '\0';
    _pendingPass[0] = '\0';
    _lastWiFiCheck = 0;
    _lastMqttReconnect = 0;
    _wifiRetryCount = 0;
    _mqttRetryCount = 0;
    _lastWiFiState = false;
    _lastPortalState = false;
    _wifiConnectState = WIFI_IDLE;
    _wifiConnectStartTime = 0;
    _currentWiFiCredentialIndex = 0;
    _eepromInitialized = false;

    // Heap buffer'ları allocate et (stack overflow önlemi)
    _mqttPayloadBuffer = (char*)malloc(MQTT_PAYLOAD_SIZE);
    _mqttTopicBuffer = (char*)malloc(MQTT_TOPIC_SIZE);

    if (!_mqttPayloadBuffer || !_mqttTopicBuffer) {
        LOG_PRINTLN("[CRITICAL] Heap allocation failed!");
    }

    // MQTT client setup - later decided based on broker
    // _mqttClient.setClient(_espClient);

    // Instance pointer for static callback
    _instance = this;
}

void NetworkManager::begin(const char* wifiSsid, const char* wifiPass, const char* mqttServer, int mqttPort, const char* mqttUser, const char* mqttPass) {
    // begin() sadece baslatma komutunu verir, blocking yapmaz
    strlcpy(_wifiSsid, wifiSsid, sizeof(_wifiSsid));
    strlcpy(_wifiPass, wifiPass, sizeof(_wifiPass));

    // Cloud config defaults
    strlcpy(_mqttBrokerHost, mqttServer, sizeof(_mqttBrokerHost));
    _mqttBrokerPort = mqttPort;
    strlcpy(_mqttUser, mqttUser, sizeof(_mqttUser));
    strlcpy(_mqttPass, mqttPass, sizeof(_mqttPass));

    _cloudMqttHost = mqttServer;
    _cloudMqttPort = mqttPort;
    _localMqttHost = DEFAULT_LOCAL_MQTT_HOST;
    _localMqttPort = DEFAULT_LOCAL_MQTT_PORT;

    // EEPROM baÅŸlat (sadece bir kez)
    if (!_eepromInitialized) {
        EEPROM.begin(EEPROM_SIZE);
        _loadWiFiCredentials();
        _eepromInitialized = true;
        // EEPROM.end() Ã§aÄŸrÄ±lmaz, destructor'da Ã§aÄŸrÄ±lÄ±r veya sistem kapanana kadar aÃ§Ä±k kalÄ±r
    }

    // Topic'leri baÅŸlat
    _initTopics();

    // WiFi baÅŸlat (blocking yapmaz)
    _setupWiFi();

    // SSL/TLS yapÄ±landÄ±rmasÄ± - Bellek optimizasyonu
    _netClientSecure.setInsecure();
    _netClientSecure.setBufferSizes(384, 384);  // MFLN probe kaldırıldı - sabit değer

    // MQTT baÅŸlat (blocking yapmaz)
    _setupMQTT();

    // Ä°lk durum bilgilerini ayarla
    _lastWiFiState = (WiFi.status() == WL_CONNECTED);
    _lastPortalState = _portalActive;
    if (_lastWiFiState) {
        strlcpy(_lastWiFiSSID, WiFi.SSID().c_str(), sizeof(_lastWiFiSSID));
    }
}

void NetworkManager::update() {
    // ✅ ESP32 MANTIK: Pending WiFi connection kontrolü (1 saniye gecikme)
    if (_pendingWifiConnect && safeMillisDiff(millis(), _pendingWifiConnectTime) >= 1000) {
        _pendingWifiConnect = false;

        LOG_PRINTF("[WiFi] Gecikme tamamlandi, baglaniyor: %s\n", _pendingSSID);

        // Portal'ı kapat
        if (_portalActive) {
            _portalActive = false;
            _portalStatusServer.stop();
            WiFi.softAPdisconnect(true);  // âœ… SoftAP'yi tamamen kapat
            LOG_PRINTLN("[WiFi] Portal kapatıldı (SoftAP + WebServer durduruldu)");
        }

        // ✅ STA moduna geç (portal kapatıldı)
        WiFi.mode(WIFI_STA);

        // ✅ Network stack temizliği için kısa bekleme
        delay(100);

        LOG_PRINTLN("[WiFi] STA moduna gecildi");

        // WiFi'ye bağlan
        WiFi.begin(_pendingSSID, _pendingPass);
        LOG_PRINTLN("[WiFi] WiFi.begin() cagrildi, baglanti bekleniyor...");

        // State machine'e geç
        _wifiConnectState = WIFI_CONNECTING;
        _wifiConnectStartTime = millis();
    }

    // WiFi bağlantısını kontrol et
    _checkWiFiConnection();

    // Portal aktifse portal'Ä± iÅŸle
    if (_portalActive) {
        // WiFiManager artık kullanılmıyor - sadece kendi HTTP sunucumuz
        _portalStatusServer.handleClient();

        // âœ… Portal timeout KALDIRILDI - Portal sadece WiFi baÄŸlantÄ±sÄ± kurulduÄŸunda kapanacak
        // Kullanıcı WiFi yapılandırması yapana kadar portal açık kalacak
    }

    // MQTT bağlantı durumu kontrolü
    static bool lastMqttState = false;
    bool currentMqttState = _mqttClient.connected();

    lastMqttState = currentMqttState;

    // MQTT baÄŸlantÄ±sÄ± yoksa baÄŸlanmayÄ± dene
    if (!_mqttClient.connected()) {
        if (WiFi.status() == WL_CONNECTED) {
            if (safeMillisDiff(millis(), _lastMqttReconnect) > MQTT_RETRY_DELAY) {
                _reconnectMQTT();
                _lastMqttReconnect = millis();
            }
        }
        return;  // MQTT baÄŸlantÄ±sÄ± yok, diÄŸer iÅŸlemleri yapma
    }

    // MQTT mesajlarini isle
    _mqttClient.loop();
}

void NetworkManager::setMqttCallback(MqttMessageCallback cb) {
    _msgCallback = cb;
}

void NetworkManager::publishSensorData(const SensorData& data) {
    if (!_mqttClient.connected()) {
        return;
    }

    // Stack optimizasyonu: StaticJsonDocument yerine snprintf kullanimi
    // 384 byte'lik buffer, eski yontemde 256 (Doc) + 256 (Buf) = 512+ kullaniyordu.
    char jsonBuffer[384];

    int jsonLen = snprintf_P(jsonBuffer, sizeof(jsonBuffer),
        PSTR("{\"coil_id\":%d,\"timestamp\":%lu,\"object_temp\":%.2f,\"ambient_temp\":%.2f,"
             "\"magnetic_field\":%.3f,\"current\":%.2f,\"temp_sensor_ok\":%s,\"magnetic_sensor_ok\":%s,"
             "\"current_sensor_ok\":%s,\"sensors_ok\":%s}"),
        _coilId, millis(),
        data.tempObject, data.tempAmbient,
        data.magneticField, data.current,
        data.temp_sensor_ok ? "true" : "false",
        data.magnetic_sensor_ok ? "true" : "false",
        data.current_sensor_ok ? "true" : "false",
        data.sensorsOK ? "true" : "false"
    );

    // Mesaj boyutu kontrolü
    if (jsonLen < 0 || jsonLen >= (int)sizeof(jsonBuffer)) {
        LOG_PRINTF("[MQTT] Sensor mesaji buffer'a sigmadi: %d bytes\n", jsonLen);
        return;
    }

    // QoS 0: Sensor data kaybolabilir (1Hz geldiği için tolere edilebilir)
    bool success = _mqttClient.publish(_sensorTopic, jsonBuffer, false);

    if (!success) {
        LOG_PRINTLN("[MQTT] Sensor data gonderilemedi (QoS 0)");
    }
}

void NetworkManager::publishStatus(const StatusData& status) {
    if (!_mqttClient.connected()) {
        return;
    }

    // Stack optimizasyonu: BSS segmentinde allocation
    static char jsonBuffer[480];

    int jsonLen = snprintf_P(jsonBuffer, sizeof(jsonBuffer),
        PSTR("{\"coil_id\":%d,\"timestamp\":%lu,\"wifi_connected\":%s,\"wifi_ssid\":\"%s\",\"wifi_rssi\":%d,"
             "\"wifi_ip\":\"%s\",\"portal_active\":%s,\"portal_ip\":\"%s\",\"portal_ssid\":\"%s\","
             "\"mqtt_connected\":%s,\"pwm_active\":%s,\"pwm_frequency\":%d,\"pwm_duty_cycle\":%d,"
             "\"pwm_remaining_time\":%lu,\"pwm_start_timestamp\":%llu,\"pwm_duration\":%d,"
             "\"sensors_ok\":%s,\"temp_sensor_ok\":%s,"
             "\"magnetic_sensor_ok\":%s,\"current_sensor_ok\":%s,"
             "\"free_heap\":%u,\"max_alloc_heap\":%u,\"fragmentation\":%u,\"uptime\":%lu}"),
        status.coil_id, status.timestamp,
        status.wifi_connected ? "true" : "false", status.wifi_ssid, status.wifi_rssi,
        status.wifi_ip, status.portal_active ? "true" : "false", status.portal_ip, status.portal_ssid,
        status.mqtt_connected ? "true" : "false", status.pwm_active ? "true" : "false", status.pwm_frequency, status.pwm_duty_cycle,
        status.pwm_remaining_time, status.pwm_start_timestamp, status.pwm_duration,
        status.sensors_ok ? "true" : "false", status.temp_sensor_ok ? "true" : "false",
        status.magnetic_sensor_ok ? "true" : "false", status.current_sensor_ok ? "true" : "false",
        status.free_heap, status.max_alloc_heap, status.fragmentation, status.uptime
    );

    // Mesaj boyutu kontrolü
    if (jsonLen < 0 || jsonLen >= (int)sizeof(jsonBuffer)) {
         LOG_PRINTF("[MQTT] Status mesaji sigmadi! Req: %d\n", jsonLen);
         return;
    }

    // âš ï¸ Ã–NEMLÄ°: QoS 0 (Retained = true)
    bool success = _mqttClient.publish(_statusTopic, jsonBuffer, true);

    if (!success) {
        LOG_PRINTF("[MQTT] Status gonderilemedi (state: %d)\n", _mqttClient.state());
    }
}

void NetworkManager::publishEvent(const char* eventType, const char* message) {
    if (!_mqttClient.connected()) {
        return;
    }

    // Stack optimizasyonu: Statik bufferlar (heap yerine)
    static char safeMessage[512];  // Mesaj boyutu sınırla
    static char jsonBuffer[768];   // JSON için buffer (512 mesaj + 256 overhead)
    static char topic[64];

    // Mesajı güvenli boyuta kısalt
    size_t msgLen = strlen(message);
    if (msgLen > 480) {  // 512 - "..." için yer bırak
        strncpy(safeMessage, message, 477);
        safeMessage[477] = '.';
        safeMessage[478] = '.';
        safeMessage[479] = '.';
        safeMessage[480] = '\0';
    } else {
        strlcpy(safeMessage, message, sizeof(safeMessage));
    }

    // JSON oluştur
    int jsonLen = snprintf_P(jsonBuffer, sizeof(jsonBuffer),
        PSTR("{\"coil_id\":%d,\"event_type\":\"%s\",\"message\":\"%s\",\"timestamp\":%lu}"),
        _coilId, eventType, safeMessage, millis()
    );

    // Mesaj boyutu kontrolü
    if (jsonLen < 0 || jsonLen >= (int)sizeof(jsonBuffer)) {
        LOG_PRINTF("[MQTT] Event buffer tasti: %d bytes\n", jsonLen);
        return;
    }

    // Topic oluştur
    snprintf(topic, sizeof(topic), "pemf/coil/%d/events", _coilId);

    // Publish (QoS 0)
    _mqttClient.publish(topic, jsonBuffer, false);
}

bool NetworkManager::isWiFiConnected() {
    return WiFi.status() == WL_CONNECTED;
}

bool NetworkManager::isMqttConnected() {
    return _mqttClient.connected();
}

const char* NetworkManager::getWiFiSSID() {
    // WiFi.SSID() String dÃ¶ner, ama c_str() ile direkt pointer dÃ¶ndÃ¼r
    // Not: Bu pointer geÃ§icidir, hemen kullanÄ±lmalÄ±dÄ±r
    return WiFi.SSID().c_str();
}

int NetworkManager::getWiFiRSSI() {
    return WiFi.RSSI();
}

IPAddress NetworkManager::getWiFiIP() {
    return WiFi.localIP();
}

bool NetworkManager::isPortalActive() {
    return _portalActive;
}

void NetworkManager::populateStatus(StatusData& data) {
    bool wifiConnected = WiFi.status() == WL_CONNECTED;
    data.wifi_connected = wifiConnected;

    if (wifiConnected) {
        // String'den char array'e gÃ¼venli kopyalama
        strlcpy(data.wifi_ssid, WiFi.SSID().c_str(), sizeof(data.wifi_ssid));
        data.wifi_rssi = WiFi.RSSI();
        IPAddress ip = WiFi.localIP();
        snprintf(data.wifi_ip, sizeof(data.wifi_ip), "%d.%d.%d.%d", ip[0], ip[1], ip[2], ip[3]);
    } else {
        data.wifi_ssid[0] = '\0'; // BoÅŸ string
        data.wifi_rssi = 0;
        data.wifi_ip[0] = '\0';
    }

    data.portal_active = _portalActive;
    if (_portalActive) {
        IPAddress portalIp = WiFi.softAPIP();
        snprintf(data.portal_ip, sizeof(data.portal_ip), "%d.%d.%d.%d", portalIp[0], portalIp[1], portalIp[2], portalIp[3]);
        snprintf(data.portal_ssid, sizeof(data.portal_ssid), "PEMF-Coil-%d", _coilId);
    } else {
        data.portal_ip[0] = '\0';
        data.portal_ssid[0] = '\0';
    }

    data.mqtt_connected = _mqttClient.connected();
}

void NetworkManager::_initTopics() {
    snprintf_P(_sensorTopic, sizeof(_sensorTopic), PSTR("pemf/coil/%d/sensors"), _coilId);
    snprintf_P(_controlTopic, sizeof(_controlTopic), PSTR("pemf/coil/%d/control"), _coilId);
    snprintf_P(_statusTopic, sizeof(_statusTopic), PSTR("pemf/coil/%d/status"), _coilId);
    snprintf_P(_eventTopic, sizeof(_eventTopic), PSTR("pemf/coil/%d/events"), _coilId);
}

void NetworkManager::_setupWiFi() {
    // begin() sadece baslatma komutunu verir, blocking yapmaz
    LOG_PRINTLN("WiFi baglantisi kuruluyor...");

    // Secrets.h'den gelen WiFi credential'lari (eger doluysa)
    if (strlen(_wifiSsid) > 0) {
        LOG_PRINTF("[WiFi] Secrets.h WiFi ayarlarina baglaniliyor: %s\n", _wifiSsid);
        WiFi.mode(WIFI_STA);
        WiFi.begin(_wifiSsid, _wifiPass);
    } else {
        LOG_PRINTLN("[WiFi] Secrets.h WiFi ayarlari bos, kayitli aglar denenecek...");
    }

    // Kayitli WiFi var mi kontrol et
    bool hasSavedWiFi = false;
    for (int i = 0; i < MAX_WIFI_CREDENTIALS; i++) {
        if (_savedWiFiList[i].valid && strlen(_savedWiFiList[i].ssid) > 0) {
            hasSavedWiFi = true;
            break;
        }
    }

    if (!hasSavedWiFi) {
        // KayÄ±tlÄ± WiFi yok, portal aÃ§Ä±lacak (update() iÃ§inde)
        LOG_PRINTLN("[WiFi] Kayitli WiFi bulunamadi, portal acilacak");
        return;
    }

    // KayÄ±tlÄ± WiFi var, mevcut aÄŸlarÄ± tara (non-blocking, update() iÃ§inde yapÄ±lacak)
    LOG_PRINTLN("[WiFi] Kayitli WiFi'ler var, baglanti denemesi yapilacak");
    // GerÃ§ek baÄŸlantÄ± kontrolÃ¼ update() iÃ§inde yapÄ±lacak
}

void NetworkManager::_checkWiFiConnection() {
    unsigned long currentTime = millis();

    // WiFi kontrolÃ¼ sadece belirli aralÄ±klarla yapÄ±lsÄ±n
    if (safeMillisDiff(currentTime, _lastWiFiCheck) < WIFI_CHECK_INTERVAL) {
        return;
    }

    _lastWiFiCheck = currentTime;

    // Reconnection loop koruma: Maksimum 3 saniyede bir deneme (5s aralÄ±ÄŸÄ± ile throttle)
    static unsigned long lastReconnectAttempt = 0;
    const unsigned long RECONNECT_THROTTLE = 5000;  // 5 saniye minimum aralÄ±k
    unsigned long timeSinceLastAttempt = safeMillisDiff(currentTime, lastReconnectAttempt);
    bool canAttemptReconnect = (timeSinceLastAttempt > RECONNECT_THROTTLE || lastReconnectAttempt == 0);

    // WiFi baÄŸlantÄ±sÄ±nÄ± kontrol et
    bool currentWiFiState = (WiFi.status() == WL_CONNECTED);

    // Ä°lk baÄŸlantÄ± denemesi (setup'tan sonra)
    static bool firstConnectionAttempt = true;
    if (firstConnectionAttempt && !currentWiFiState) {
        firstConnectionAttempt = false;
        // KayÄ±tlÄ± WiFi'leri dene (async, state machine ile)
        _tryConnectToSavedWiFi();
        // BaÄŸlantÄ± durumu update() iÃ§inde kontrol edilecek
        if (WiFi.status() == WL_CONNECTED) {
            currentWiFiState = true;
            _saveCurrentWiFi();
        } else if (_wifiConnectState == WIFI_IDLE) {
            // TÃ¼m credential'ler denendi, portal aÃ§
            _startWiFiPortal();
        }
    }

    // WiFi durumu deÄŸiÅŸti mi kontrol et
    if (currentWiFiState != _lastWiFiState) {
        if (currentWiFiState) {
            strlcpy(_lastWiFiSSID, WiFi.SSID().c_str(), sizeof(_lastWiFiSSID));
            if (_mqttClient.connected()) {
                char eventMsg[128];
                snprintf(eventMsg, sizeof(eventMsg), "WiFi baÄŸlantÄ±sÄ± baÅŸarÄ±lÄ±: %s", _lastWiFiSSID);
                publishEvent("wifi_connected", eventMsg);
            }
            LOG_PRINTF("[WiFi] Baglanti geri geldi: %s\n", _lastWiFiSSID);
        } else {
            // WiFi disconnect

            if (_mqttClient.connected()) {
                publishEvent("wifi_disconnected", "WiFi baÄŸlantÄ±sÄ± kesildi");
            }
            LOG_PRINTLN("[WiFi] Baglanti kesildi! Yeniden baglaniyor...");
        }
        _lastWiFiState = currentWiFiState;
    }

    // Portal durumu deÄŸiÅŸti mi kontrol et
    if (_portalActive != _lastPortalState) {
        if (_portalActive) {
            if (_mqttClient.connected()) {
                publishEvent("portal_opened", "WiFi Portal aÃ§Ä±ldÄ±");
            }
            LOG_PRINTLN("[WiFi] Portal acildi");
        } else {
            // Portal kapatÄ±ldÄ± - WebServer'Ä± durdur, SoftAP kapat, bellek temizle
            _portalStatusServer.stop();
            WiFi.softAPdisconnect(true);  // âœ… SoftAP'yi tamamen kapat
            WiFi.mode(WIFI_STA);          // âœ… Sadece Station mode

            // âœ… Network stack temizliÄŸi için kısa bekleme
            delay(100);

            LOG_PRINTLN("[WiFi] Portal kapatildi, WebServer durduruldu");
            if (_mqttClient.connected()) {
                publishEvent("portal_closed", "WiFi Portal kapatÄ±ldÄ±");
            }
        }
        _lastPortalState = _portalActive;
    }

    // WiFi bağlantısını kontrol et (throttle ile)
    // ✅ Portal açıkken otomatik reconnect denemesi YAPMA
    // Kullanıcı Android'den WiFi yapılandırması yapana kadar bekle
    if (!currentWiFiState && !_portalActive) {
        if (canAttemptReconnect) {
            _reconnectWiFi();
            lastReconnectAttempt = currentTime;  // Throttle counter'ı güncelle
        }
    } else if (currentWiFiState) {
        if (_wifiRetryCount > 0) {
            _wifiRetryCount = 0;
        }
    }
    // Portal açıkken: WiFi bağlantısı yok ama reconnect denemesi yapılmıyor
    // Kullanıcı Android uygulamasından WiFi yapılandırması yapacak
}

void NetworkManager::_reconnectWiFi() {
    // State machine ile async reconnect
    if (_wifiConnectState == WIFI_IDLE) {
        _wifiRetryCount++;
        LOG_PRINTF("[WiFi] Reconnect denemesi #%d\n", _wifiRetryCount);

        // Portal aÃ§Ä±k deÄŸilse ve ilk denemede portal aÃ§
        if (!_portalActive && _wifiRetryCount == 1) {
            LOG_PRINTLN("[WiFi] Portal aciliyor...");
            _startWiFiPortal();
            // âœ… Portal aÃ§Ä±lÄ±nca WiFi bağlantı denemesi YAPMA
            // Sadece kullanÄ±cÄ± Android'den yapÄ±landÄ±rma yapana kadar bekle
            return;
        }

        // âœ… Portal aktifken STA bağlantı denemesi YAPMA (WIFI_AP modu)
        if (_portalActive) {
            LOG_PRINTLN("[WiFi] Portal aktif, STA baglantisi bekliyor...");
            return;
        }

        // KayÄ±tlÄ± WiFi'leri dene (async) - Sadece portal aktif DEÄžÄ°LSE
        _currentWiFiCredentialIndex = 0;
        _wifiConnectState = WIFI_CONNECTING;
        _wifiConnectStartTime = millis();

        // Ä°lk credential ile baÄŸlanmayÄ± dene
        if (_currentWiFiCredentialIndex < MAX_WIFI_CREDENTIALS &&
            _savedWiFiList[_currentWiFiCredentialIndex].valid &&
            strlen(_savedWiFiList[_currentWiFiCredentialIndex].ssid) > 0) {
            LOG_PRINTF("[WiFi] Baglaniyor: %s (30 saniye timeout)\n", _savedWiFiList[_currentWiFiCredentialIndex].ssid);

            // âœ… STA moduna geç (portal kapalÄ± çünkü)
            WiFi.mode(WIFI_STA);

            WiFi.begin(_savedWiFiList[_currentWiFiCredentialIndex].ssid,
                      _savedWiFiList[_currentWiFiCredentialIndex].password);
        } else {
            // KayÄ±tlÄ± WiFi yok, reconnect dene
            LOG_PRINTLN("[WiFi] KayÄ±tlÄ± WiFi yok, reconnect deneniyor...");
            WiFi.reconnect();
        }
    } else if (_wifiConnectState == WIFI_CONNECTING) {
        // BaÄŸlantÄ± durumunu kontrol et (non-blocking)
        if (WiFi.status() == WL_CONNECTED) {
            LOG_PRINTLN("[WiFi] Reconnect baÅŸarÄ±lÄ±!");
            _wifiRetryCount = 0;
            _wifiConnectState = WIFI_IDLE;

            // Portal kapatıldı
            if (_portalActive) {
                _portalActive = false;
                _portalStatusServer.stop();  // WebServer'ı kapat
                WiFi.softAPdisconnect(true);  // SoftAP'yi kapat
                WiFi.mode(WIFI_STA);          // Sadece Station mode
                LOG_PRINTLN("[WiFi] Portal kapatıldı (SoftAP + WebServer durduruldu)");

                // Heap temizliği için kısa bir bekleme (fragmentation azaltma)
                delay(100);
                uint32_t freeHeap = ESP.getFreeHeap();
                LOG_PRINTF("[Memory] Portal sonrası Free Heap: %u bytes\n", freeHeap);

                publishEvent("portal_closed", "WiFi bağlantısı kuruldu, portal kapatıldı");
            }

            // BaÄŸlanÄ±lan WiFi'yi kaydet
            _saveCurrentWiFi();

            // MQTT retry counter'Ä± sÄ±fÄ±rla
            _mqttRetryCount = 0;
        } else if (safeMillisDiff(millis(), _wifiConnectStartTime) >= WIFI_CONNECT_TIMEOUT) {
            // Timeout - sonraki credential'i dene
            LOG_PRINTF("[WiFi] Bağlantı timeout (30 saniye), sonraki ağ deneniyor...\n");
            _currentWiFiCredentialIndex++;

            if (_currentWiFiCredentialIndex < MAX_WIFI_CREDENTIALS &&
                _savedWiFiList[_currentWiFiCredentialIndex].valid &&
                strlen(_savedWiFiList[_currentWiFiCredentialIndex].ssid) > 0) {
                LOG_PRINTF("[WiFi] Sonraki WiFi deneniyor: %s (30 saniye timeout)\n", _savedWiFiList[_currentWiFiCredentialIndex].ssid);
                WiFi.begin(_savedWiFiList[_currentWiFiCredentialIndex].ssid,
                          _savedWiFiList[_currentWiFiCredentialIndex].password);
                _wifiConnectStartTime = millis();  // Reset timer
            } else {
                // Tüm credential'ler denendi, başarısız
                LOG_PRINTLN("[WiFi] Tüm kayıtlı WiFi'lere bağlanamadı. Portal açık kalmaya devam ediyor...");
                _wifiConnectState = WIFI_IDLE;
            }
        }
        // Portal aktif durumda WiFi bağlantısını bekliyoruz
    }
}

bool NetworkManager::_tryConnectToSavedWiFi() {
    // Bu fonksiyon artÄ±k _reconnectWiFi() iÃ§inde state machine ile yÃ¶netiliyor
    // Sadece ilk baÄŸlantÄ± denemesi iÃ§in kullanÄ±lÄ±r
    if (_wifiConnectState == WIFI_IDLE) {
        _currentWiFiCredentialIndex = 0;
        _wifiConnectState = WIFI_CONNECTING;
        _wifiConnectStartTime = millis();

        // Ä°lk geÃ§erli credential'i bul
        for (int i = 0; i < MAX_WIFI_CREDENTIALS; i++) {
            if (_savedWiFiList[i].valid && strlen(_savedWiFiList[i].ssid) > 0) {
                _currentWiFiCredentialIndex = i;
                LOG_PRINTF("[WiFi] BaÄŸlanÄ±lÄ±yor: %s\n", _savedWiFiList[i].ssid);
                WiFi.begin(_savedWiFiList[i].ssid, _savedWiFiList[i].password);
                return false;  // HenÃ¼z baÄŸlanmadÄ±, update() iÃ§inde kontrol edilecek
            }
        }
        _wifiConnectState = WIFI_IDLE;
        return false;  // GeÃ§erli credential yok
    }

    // State machine kontrolÃ¼ update() iÃ§inde yapÄ±lÄ±yor
    return WiFi.status() == WL_CONNECTED;
}

void NetworkManager::_startWiFiPortal() {
    if (_portalActive) {
        return;  // Portal zaten açık
    }

    LOG_PRINTLN("[WiFi] WiFi Portal açılıyor...");

    // SoftAP başlat (WiFiManager yerine)
    char apName[32];
    snprintf(apName, sizeof(apName), "PEMF-Coil-%d", _coilId);

    // Portal acilmadan once haber ver (Eger baglanti varsa)
    if (_mqttClient.connected()) {
        publishEvent("portal_opened", "WiFi Portal aciliyor. Baglanti kesilecek.");
        _mqttClient.loop(); // Mesajin gitmesi icin sans tani
        delay(200);
    }

    // âœ… WiFi mode: SADECE AP (STA deÄŸil)
    // Dual mode (AP+STA) bazÄ± Android cihazlarda portal'Ä±n görünmemesine neden olur
    // Portal açıkken STA bağlantısı devre dışı bırakılmalı
    WiFi.mode(WIFI_AP);  // Sadece Access Point modu

    // SoftAP başlat (şifresiz, açık ağ, kanal 6, broadcast=true)
    // Parametreler: (ssid, password, channel, hidden, max_connections)
    // âœ… Kanal 6: En yaygÄ±n desteklenen WiFi kanalÄ± (1 yerine)
    bool apStarted = WiFi.softAP(apName, NULL, 6, false, 4);

    if (apStarted) {
        IPAddress apIp = WiFi.softAPIP();
        LOG_PRINTLN("Portal başlatıldı:");
        LOG_PRINTF("  SSID: %s\n", apName);
        LOG_PRINTF("  IP: %d.%d.%d.%d\n", apIp[0], apIp[1], apIp[2], apIp[3]);
        LOG_PRINTF("  Şifre: yok (açık ağ)\n");

        _portalActive = true;
        _portalStartTime = millis();

        // HTTP server başlat (config ve status için)
        _setupPortalStatusServer();

        if (_mqttClient.connected()) {
            publishEvent("portal_opened", "WiFi Portal açıldı");
        }
    } else {
        LOG_PRINTLN("[WiFi] HATA: Portal başlatılamadı!");
    }
}

void NetworkManager::_setupMQTT() {
    _mqttClient.setBufferSize(768);  // Status mesajÄ± (640) + topic (~50) + overhead (~78) iÃ§in
    _mqttClient.setServer(_localMqttHost.c_str(), _localMqttPort);
    _mqttClient.setCallback(_mqttCallbackHelper);
}

void NetworkManager::_switchMqttClient(BrokerType brokerType) {
    if (brokerType == BROKER_LOCAL) {
        _mqttClient.setClient(_netClientPlain);
        _mqttClient.setServer(_localMqttHost.c_str(), _localMqttPort);
    } else if (brokerType == BROKER_CLOUD) {
        _mqttClient.setClient(_netClientSecure);
        _mqttClient.setServer(_cloudMqttHost.c_str(), _cloudMqttPort);
    }
}

bool NetworkManager::_connectToLocalBroker() {
    if (_localMqttHost.length() == 0) return false;
    _switchMqttClient(BROKER_LOCAL);

    char clientId[64];
    snprintf(clientId, sizeof(clientId), "PEMF-Coil-%d-%lX", _coilId, millis());

    // D-4 (2026-08-19): LWT (last-will) — S3 ile birebir. Cihaz ANİ koparsa broker bu mesajı
    // pemf/coil/{id}/events'e yayınlar → backend bobini ~keepalive'da "koptu" işaretler (eskiden
    // yalnız 30 sn staleness ile geç fark ediliyordu). Format S3'ün offline event'iyle aynı.
    char lwtTopic[32];
    snprintf(lwtTopic, sizeof(lwtTopic), "pemf/coil/%d/events", _coilId);
    static char lwtMsg[48];
    snprintf(lwtMsg, sizeof(lwtMsg), "{\"event_type\":\"offline\",\"coil_id\":%d}", _coilId);

    LOG_PRINTF("[MQTT] Local Broker (%s:%d) deneniyor...\n", _localMqttHost.c_str(), _localMqttPort);
    if (_mqttClient.connect(clientId, lwtTopic, 1, true, lwtMsg)) {
        LOG_PRINTLN("[MQTT] Local Broker'a baglanildi.");
        return true;
    }
    LOG_PRINTF("[MQTT] Local baglanti hatasi, RC=%d\n", _mqttClient.state());
    return false;
}

bool NetworkManager::_connectToCloudBroker() {
    if (_cloudMqttHost.length() == 0) return false;
    _switchMqttClient(BROKER_CLOUD);

    char clientId[64];
    snprintf(clientId, sizeof(clientId), "PEMF-Coil-%d-%lX", _coilId, millis());

    // D-4 (2026-08-19): LWT — local ile aynı (S3 birebir). Cloud broker'da da koptuğunda
    // backend'in bobini "offline" görmesi için will şart.
    char lwtTopic[32];
    snprintf(lwtTopic, sizeof(lwtTopic), "pemf/coil/%d/events", _coilId);
    static char lwtMsg[48];
    snprintf(lwtMsg, sizeof(lwtMsg), "{\"event_type\":\"offline\",\"coil_id\":%d}", _coilId);

    LOG_PRINTF("[MQTT] Cloud Broker (%s:%d) deneniyor...\n", _cloudMqttHost.c_str(), _cloudMqttPort);
    if (_mqttClient.connect(clientId, _mqttUser, _mqttPass, lwtTopic, 1, true, lwtMsg)) {
        LOG_PRINTLN("[MQTT] Cloud Broker'a baglanildi.");
        return true;
    }
    LOG_PRINTF("[MQTT] Cloud baglanti hatasi, RC=%d\n", _mqttClient.state());
    return false;
}

void NetworkManager::_tryResolveMdnsGateway() {
    if (safeMillisDiff(millis(), _lastMdnsResolve) < 60000) return; // 1 dk onbellek
    _lastMdnsResolve = millis();

    /* 2026-08-19: eski kod MDNS.queryHost("pemf-gateway") cagiriyordu - o API ESP32nin,
     * ESP8266 cekirdeginde HIC OLMADI (S3 varyantindan kopyalanmis; dosya bu haliyle
     * derlenmiyordu). Mimarinin gercegi daha basit ve saglam: yerel broker, PEMF-Gateway
     * hotspotunu acan makinede kosar - yani AG GECIDININ KENDISI. mDNSe gerek yok. */
    IPAddress gw = WiFi.gatewayIP();
    if (gw != IPAddress((uint32_t)0)) {
        _resolvedGatewayIp = gw.toString();
        _localMqttHost = _resolvedGatewayIp;
        LOG_PRINTF("[MQTT] Yerel broker = ag gecidi: %s\n", _resolvedGatewayIp.c_str());
    } else {
        _localMqttHost = DEFAULT_LOCAL_MQTT_HOST;
    }
}

void NetworkManager::_reconnectMQTT() {
    if (_mqttClient.connected()) {
        return;
    }

    // WiFi baÄŸlÄ± deÄŸilse MQTT'ye baÄŸlanma
    if (WiFi.status() != WL_CONNECTED) {
        _localRetryCount = 0;
        return;
    }

    _tryResolveMdnsGateway();

    // 1. Local broker dene (max 3 kez)
    if (_localRetryCount < MQTT_LOCAL_MAX_RETRIES) {
        if (_connectToLocalBroker()) {
            _activeBroker = BROKER_LOCAL;
            _localRetryCount = 0;
            _mqttClient.subscribe(_controlTopic);
            _mqttClient.subscribe(_globalControlTopic);
            publishEvent("mqtt_connected", "Local MQTT'ye bağlandı");
            return;
        }
        _localRetryCount++;
    }

    // 2. Local başarısız → Cloud'a geç
    if (_connectToCloudBroker()) {
        _activeBroker = BROKER_CLOUD;
        _mqttClient.subscribe(_controlTopic);
        _mqttClient.subscribe(_globalControlTopic);
        publishEvent("mqtt_connected", "HiveMQ Cloud'a baÄŸlandÄ±");
        return;
    }
    // 2026-08-19: buradaki FAZLA "}" kaldirildi (175/176 dengesizligi - dosya hic derlenmemisti)
}

void NetworkManager::sendCommandAck(const char* command_id, bool success) {
    if (!_mqttClient.connected()) {
        return;
    }

    // Stack optimizasyonu: Statik bufferlar
    static char ackTopic[32];
    snprintf_P(ackTopic, sizeof(ackTopic), PSTR("pemf/coil/%d/ack"), _coilId);

    // JSON buffer statik
    static char jsonBuffer[256];
    int jsonLen = snprintf_P(jsonBuffer, sizeof(jsonBuffer),
        PSTR("{\"coil_id\":%d,\"command_id\":\"%s\",\"success\":%s,\"timestamp\":%lu}"),
        _coilId, command_id, success ? "true" : "false", millis()
    );

    // Mesaj boyutu kontrolü
    if (jsonLen < 0 || jsonLen >= (int)sizeof(jsonBuffer)) {
        LOG_PRINTF("[MQTT] ACK mesaji sigmadi: %d\n", jsonLen);
        return;
    }

    // QoS 0 (retain = true)
    bool publishSuccess = _mqttClient.publish(ackTopic, jsonBuffer, true);

    if (!publishSuccess) {
        LOG_PRINTLN("[MQTT] CRITICAL: ACK gonderilemedi! (Queue removed)");
    }
}

void NetworkManager::_loadWiFiCredentials() {
    LOG_PRINTLN("[WiFi] KayÄ±tlÄ± WiFi bilgileri yÃ¼kleniyor...");

    int address = EEPROM_WIFI_START;
    bool foundCorruptedData = false;

    for (int i = 0; i < MAX_WIFI_CREDENTIALS; i++) {
        EEPROM.get(address, _savedWiFiList[i].valid);
        address += sizeof(bool);

        if (_savedWiFiList[i].valid) {
            EEPROM.get(address, _savedWiFiList[i].ssid);
            address += 33;
            EEPROM.get(address, _savedWiFiList[i].password);
            address += 65;

            // SSID doÄŸrulama - sadece yazdÄ±rÄ±labilir karakterler olmalÄ±
            bool isValid = true;
            for (int j = 0; j < 33 && _savedWiFiList[i].ssid[j] != '\0'; j++) {
                if (_savedWiFiList[i].ssid[j] < 32 || _savedWiFiList[i].ssid[j] > 126) {
                    isValid = false;
                    foundCorruptedData = true;
                    break;
                }
            }

            if (isValid && strlen(_savedWiFiList[i].ssid) > 0 && strlen(_savedWiFiList[i].ssid) <= 32) {
                LOG_PRINTF("  [%d] SSID: %s\n", i+1, _savedWiFiList[i].ssid);
            } else {
                LOG_PRINTF("  [%d] SSID: BOZUK VERİ (temizlenecek)\n", i+1);
                _savedWiFiList[i].valid = false;
                _savedWiFiList[i].ssid[0] = '\0';
                _savedWiFiList[i].password[0] = '\0';
                foundCorruptedData = true;
            }
        } else {
            _savedWiFiList[i].ssid[0] = '\0';
            _savedWiFiList[i].password[0] = '\0';
            address += 33 + 65;
        }
    }

    if (foundCorruptedData) {
        LOG_PRINTLN("[WiFi] âš ï¸ Bozuk veri tespit edildi, EEPROM temizleniyor...");
        clearAllWiFiCredentials();
    }

    LOG_PRINTLN("[WiFi] WiFi bilgileri yÃ¼klendi");
}

void NetworkManager::_saveWiFiCredentials() {
    LOG_PRINTLN("[WiFi] WiFi bilgileri kaydediliyor...");

    int address = EEPROM_WIFI_START;
    for (int i = 0; i < MAX_WIFI_CREDENTIALS; i++) {
        EEPROM.put(address, _savedWiFiList[i].valid);
        address += sizeof(bool);
        EEPROM.put(address, _savedWiFiList[i].ssid);
        address += 33;
        EEPROM.put(address, _savedWiFiList[i].password);
        address += 65;
    }

    EEPROM.commit();
    LOG_PRINTLN("[WiFi] WiFi bilgileri kaydedildi");
}

void NetworkManager::_saveCurrentWiFi() {
    // Stack'te char array kullan (heap'e dokunma)
    char currentSSID[33];
    char currentPassword[65];

    // WiFi.SSID() String dÃ¶ner, ama c_str() ile direkt kopyala
    strlcpy(currentSSID, WiFi.SSID().c_str(), sizeof(currentSSID));
    strlcpy(currentPassword, WiFi.psk().c_str(), sizeof(currentPassword));

    if (strlen(currentSSID) == 0) {
        return;
    }

    // EEPROM zaten baÅŸlatÄ±lmÄ±ÅŸ olmalÄ± (begin() iÃ§inde)
    if (!_eepromInitialized) {
        EEPROM.begin(EEPROM_SIZE);
        _eepromInitialized = true;
    }

    // SSID kontrolÃ¼ (strcmp ile)
    for (int i = 0; i < MAX_WIFI_CREDENTIALS; i++) {
        if (_savedWiFiList[i].valid && strcmp(currentSSID, _savedWiFiList[i].ssid) == 0) {
            strlcpy(_savedWiFiList[i].password, currentPassword, sizeof(_savedWiFiList[i].password));
            _saveWiFiCredentials();
            LOG_PRINTF("[WiFi] WiFi gÃ¼ncellendi: %s\n", currentSSID);
            return;
        }
    }

    // Yeni WiFi kaydet
    for (int i = 0; i < MAX_WIFI_CREDENTIALS; i++) {
        if (!_savedWiFiList[i].valid) {
            strlcpy(_savedWiFiList[i].ssid, currentSSID, sizeof(_savedWiFiList[i].ssid));
            strlcpy(_savedWiFiList[i].password, currentPassword, sizeof(_savedWiFiList[i].password));
            _savedWiFiList[i].valid = true;
            _saveWiFiCredentials();
            LOG_PRINTF("[WiFi] Yeni WiFi kaydedildi: %s (slot %d)\n", currentSSID, i+1);
            return;
        }
    }

    // TÃ¼m slotlar dolu, en eski olanÄ± deÄŸiÅŸtir
    strlcpy(_savedWiFiList[0].ssid, currentSSID, sizeof(_savedWiFiList[0].ssid));
    strlcpy(_savedWiFiList[0].password, currentPassword, sizeof(_savedWiFiList[0].password));
    _savedWiFiList[0].valid = true;
    _saveWiFiCredentials();
    LOG_PRINTF("[WiFi] WiFi kaydedildi (eski kayÄ±t deÄŸiÅŸtirildi): %s\n", currentSSID);
}

void NetworkManager::_setupPortalStatusServer() {
    _portalStatusServer.on("/status", [this]() {
        _handlePortalStatus();
    });

    _portalStatusServer.on("/config", HTTP_POST, [this]() {
        _handleWiFiConfig();
    });

    // CORS pre-flight (OPTIONS) için
    _portalStatusServer.on("/config", HTTP_OPTIONS, [this]() {
        LOG_PRINTLN("[WiFi] OPTIONS request alindi (CORS preflight)");
        _portalStatusServer.sendHeader("Access-Control-Allow-Origin", "*");
        _portalStatusServer.sendHeader("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
        _portalStatusServer.sendHeader("Access-Control-Allow-Headers", "Content-Type, Accept");
        _portalStatusServer.sendHeader("Access-Control-Max-Age", "86400");
        _portalStatusServer.send(204);
    });

    _portalStatusServer.on("/", []() {
        _instance->_portalStatusServer.send(200, "text/html",
            "<!DOCTYPE html><html><head><meta charset='UTF-8'><title>PEMF Coil Portal</title></head>"
            "<body style='font-family: Arial; text-align: center; padding: 50px;'>"
            "<h1>PEMF Coil Portal</h1>"
            "<p>WiFi yapÄ±landÄ±rma portalÄ± aktif.</p>"
            "<p>Durum bilgisi iÃ§in: <a href='/status'>/status</a></p>"
            "</body></html>");
    });

    _portalStatusServer.begin();
    LOG_PRINTLN("[WiFi] Portal durumu HTTP server baÅŸlatÄ±ldÄ± (port 80)");
}

void NetworkManager::_handlePortalStatus() {
    // Stack optimizasyonu: Tek statik buffer kullan
    static char jsonBuffer[384];

    // IP adreslerini stringe cevir (stack yerine statik)
    static char portalIpBuffer[16];
    IPAddress portalIp = WiFi.softAPIP();
    snprintf(portalIpBuffer, sizeof(portalIpBuffer), "%d.%d.%d.%d", portalIp[0], portalIp[1], portalIp[2], portalIp[3]);

    // Stack optimizasyonu: Statik bufferlar
    static char wifiIpBuffer[16];
    static char wifiSsidBuffer[33];

    if (WiFi.status() == WL_CONNECTED) {
        strlcpy(wifiSsidBuffer, WiFi.SSID().c_str(), sizeof(wifiSsidBuffer));
        IPAddress wifiIp = WiFi.localIP();
        snprintf(wifiIpBuffer, sizeof(wifiIpBuffer), "%d.%d.%d.%d", wifiIp[0], wifiIp[1], wifiIp[2], wifiIp[3]);
    } else {
        wifiSsidBuffer[0] = '\0';
        wifiIpBuffer[0] = '\0';
    }

    int savedWiFiCount = 0;
    for (int i = 0; i < MAX_WIFI_CREDENTIALS; i++) {
        if (_savedWiFiList[i].valid && strlen(_savedWiFiList[i].ssid) > 0) {
            savedWiFiCount++;
        }
    }

    unsigned long portalUptime = safeMillisDiff(millis(), _portalStartTime) / 1000;

    int jsonLen = snprintf_P(jsonBuffer, sizeof(jsonBuffer),
        PSTR("{\"coil_id\":%d,\"portal_active\":%s,\"portal_ssid\":\"PEMF-Coil-%d\",\"portal_ip\":\"%s\","
             "\"wifi_connected\":%s,\"wifi_ssid\":\"%s\",\"wifi_ip\":\"%s\",\"saved_wifi_count\":%d,"
             "\"portal_uptime_seconds\":%lu}"),
        _coilId, _portalActive ? "true" : "false", _coilId, portalIpBuffer,
        (WiFi.status() == WL_CONNECTED) ? "true" : "false", wifiSsidBuffer, wifiIpBuffer, savedWiFiCount,
        portalUptime
    );

    // Mesaj boyutu kontrolü
    if (jsonLen < 0 || jsonLen >= (int)sizeof(jsonBuffer)) {
        LOG_PRINTF("[Portal] Status mesaji sigmadi: %d\n", jsonLen);
    } // Sigmasa bile truncate edilmis hali gonderelim, JSON bozuk olabilir ama crash etmez

    // CORS headers ekle
    _portalStatusServer.sendHeader("Access-Control-Allow-Origin", "*");
    _portalStatusServer.send(200, "application/json", jsonBuffer);
}

void NetworkManager::_handleWiFiConfig() {
    if (_portalStatusServer.method() != HTTP_POST) {
        LOG_PRINTLN("[WiFi] Hata: POST metodu bekleniyordu");
        _portalStatusServer.send(405, "application/json", "{\"error\":\"Method not allowed\"}");
        return;
    }

    // POST body'yi oku - ESP8266WebServer arg("plain") kullanır
    // Stack optimizasyonu: String yerine direkt const char* kullan (mümkünse)
    const String& bodyStr = _portalStatusServer.arg("plain");
    const char* body = bodyStr.c_str();

    LOG_PRINTF("[WiFi] POST request alindi - Body uzunlugu: %d bytes\n", bodyStr.length());
    LOG_PRINTF("[WiFi] Content-Type: %s\n",
        _portalStatusServer.hasHeader("Content-Type") ? _portalStatusServer.header("Content-Type").c_str() : "yok");

    if (bodyStr.length() == 0) {
        LOG_PRINTLN("[WiFi] Hata: POST body bos!");
        LOG_PRINTF("[WiFi] Arg sayisi: %d\n", _portalStatusServer.args());
        for (int i = 0; i < _portalStatusServer.args(); i++) {
            LOG_PRINTF("[WiFi]   Arg[%d]: %s = %s\n",
                i, _portalStatusServer.argName(i).c_str(), _portalStatusServer.arg(i).c_str());
        }
        _portalStatusServer.send(400, "application/json", "{\"error\":\"Empty request body\"}");
        return;
    }

    LOG_PRINTF("[WiFi] WiFi yapilandirma istegi alindi: %s\n", body);

    // Stack optimizasyonu: Küçük JSON buffer (256 -> 200)
    StaticJsonDocument<200> jsonDoc;
    DeserializationError error = deserializeJson(jsonDoc, body);

    if (error) {
        _portalStatusServer.send(400, "application/json", "{\"error\":\"Invalid JSON\"}");
        return;
    }

    // String yerine char array kullan
    char ssid[33];
    char password[65];

    const char* ssidStr = jsonDoc["ssid"] | "";
    const char* passwordStr = jsonDoc["password"] | "";
    strlcpy(ssid, ssidStr, sizeof(ssid));
    strlcpy(password, passwordStr, sizeof(password));

    if (strlen(ssid) == 0) {
        _portalStatusServer.send(400, "application/json", "{\"error\":\"SSID required\"}");
        return;
    }

    // ✅ ESP32 MANTIK: Gelen bilgileri pending değişkenlere kaydet
    strlcpy(_pendingSSID, ssid, sizeof(_pendingSSID));
    strlcpy(_pendingPass, password, sizeof(_pendingPass));

    LOG_PRINTF("[WiFi] Hedef ağ: %s (Portal aktif: %s)\n", ssid, _portalActive ? "EVET" : "HAYIR");

    // Gelen bilgileri EEPROM'a da kaydet (henüz bağlanmadan)
    // Aynı SSID varsa üzerine yaz, yoksa boş slot bul
    int slotToUse = -1;
    for (int i = 0; i < MAX_WIFI_CREDENTIALS; i++) {
        if (_savedWiFiList[i].valid && strcmp(_savedWiFiList[i].ssid, ssid) == 0) {
            slotToUse = i;
            break;
        }
    }
    if (slotToUse == -1) {
        for (int i = 0; i < MAX_WIFI_CREDENTIALS; i++) {
            if (!_savedWiFiList[i].valid) {
                slotToUse = i;
                break;
            }
        }
    }
    if (slotToUse == -1) {
        slotToUse = 0;  // Fallback: ilk slotu kullan
    }

    strlcpy(_savedWiFiList[slotToUse].ssid, ssid, sizeof(_savedWiFiList[slotToUse].ssid));
    strlcpy(_savedWiFiList[slotToUse].password, password, sizeof(_savedWiFiList[slotToUse].password));
    _savedWiFiList[slotToUse].valid = true;
    _saveWiFiCredentials();
    LOG_PRINTF("[WiFi] Hedef WiFi kaydedildi: %s (slot %d)\n", ssid, slotToUse+1);

    // WiFi bağlantı isteğini bekleyeceğimizi işaretle
    _pendingWifiConnect = true;
    _pendingWifiConnectTime = millis();
    LOG_PRINTLN("[WiFi] Baglanti istegi kuyruga alindi (1 sn gecikmeli)");

    // İstemciye HEMEN yanıt dön (Portal ağı kapatılmadan önce yanıt gitsin)
    // Stack optimizasyonu: JSON buffer yerine snprintf
    char responseBuffer[256];
    snprintf_P(responseBuffer, sizeof(responseBuffer),
        PSTR("{\"success\":true,\"message\":\"WiFi bilgileri alindi, baglaniliyor...\",\"ssid\":\"%s\",\"status\":\"pending\"}"),
        ssid
    );

    LOG_PRINTF("[WiFi] Yanit gonderiliyor (202 Accepted): %s\n", responseBuffer);

    // CORS headers ekle (Android için önemli)
    _portalStatusServer.sendHeader("Access-Control-Allow-Origin", "*");
    _portalStatusServer.sendHeader("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
    _portalStatusServer.sendHeader("Access-Control-Allow-Headers", "Content-Type");
    _portalStatusServer.send(202, "application/json", responseBuffer);

    LOG_PRINTLN("[WiFi] Yanit gonderildi, 1 saniye sonra WiFi baglanmaya calisilacak");
}


void NetworkManager::_mqttCallbackHelper(char* topic, byte* payload, unsigned int length) {
    // Callback lock: Simultaneous access'Ä± Ã¶nle
    unsigned long lockStart = millis();
    while (_callbackLock && (millis() - lockStart < CALLBACK_LOCK_TIMEOUT)) {
        yield();  // Deadlock'u Ã¶nle, diÄŸer iÅŸlemlere CPU verme fÄ±rsatÄ± ver
    }

    // Lock'u al
    _callbackLock = millis();

    if (_instance == nullptr || _instance->_msgCallback == nullptr ||
        !_instance->_mqttPayloadBuffer) {
        _callbackLock = 0;  // Lock'u serbest bÄ±rak
        return;
    }

    // Stack optimizasyonu: Class member buffer kullan (stack yerine)
    if (length >= MQTT_PAYLOAD_SIZE) {
        length = MQTT_PAYLOAD_SIZE - 1;  // Truncate
    }

    memcpy(_instance->_mqttPayloadBuffer, payload, length);
    _instance->_mqttPayloadBuffer[length] = '\0';

    // Callback'i Ã§aÄŸÄ±r (heap buffer ile - stack'e dokunmadan)
    _instance->_msgCallback(topic, _instance->_mqttPayloadBuffer);

    // Lock'u serbest bÄ±rak
    _callbackLock = 0;
}

unsigned long NetworkManager::safeMillisDiff(unsigned long current, unsigned long previous) {
    if (current >= previous) {
        return current - previous;
    } else {
        return (ULONG_MAX - previous) + current + 1;
    }
}

// ============================================================================
// WiFi Credential Temizleme
// ============================================================================
void NetworkManager::clearAllWiFiCredentials() {
    LOG_PRINTLN("[WiFi] Tum WiFi bilgileri temizleniyor...");

    // EEPROM baslatilmamissa baslat
    if (!_eepromInitialized) {
        EEPROM.begin(EEPROM_SIZE);
        _eepromInitialized = true;
    }

    // Tum WiFi credential'lari temizle
    for (int i = 0; i < MAX_WIFI_CREDENTIALS; i++) {
        _savedWiFiList[i].valid = false;
        memset(_savedWiFiList[i].ssid, 0, sizeof(_savedWiFiList[i].ssid));
        memset(_savedWiFiList[i].password, 0, sizeof(_savedWiFiList[i].password));
    }

    // EEPROM'u tamamen temizle (sifirla)
    for (int i = 0; i < EEPROM_SIZE; i++) {
        EEPROM.write(i, 0);
    }

    EEPROM.commit();
    LOG_PRINTLN("[WiFi] EEPROM tamamen temizlendi");

    // WiFi ayarlarini da sifirla
    WiFi.disconnect(true);  // true = erase WiFi credentials from SDK
    delay(100);

    LOG_PRINTLN("[WiFi] WiFi credentials silindi");
}

// ============================================================================
// Sistem Loglama (Log Seviyelerine Gore)
// ============================================================================
void NetworkManager::publishSystemLog(LogLevel level, const char* message) {
    // 1. Once her seyi Seri Porta yaz (Gelistirici gorsun)
    const char* levelStr = "";
    if (level == LOG_LEVEL_INFO) {
        levelStr = "[INFO]";
    } else if (level == LOG_LEVEL_WARN) {
        levelStr = "[WARN]";
    } else if (level == LOG_LEVEL_ERROR) {
        levelStr = "[ERROR]";
    }

    // Makro kullanarak yazdir (DEBUG_MODE 0 ise burasi derlenmez)
    LOG_PRINTF("%s %s\n", levelStr, message);

    // 2. Filtreleme: Sadece ONEMLI olanlar buluta gitsin
    // INFO seviyesi buluta GITMEZ (Kota dostu)
    if (level == LOG_LEVEL_WARN || level == LOG_LEVEL_ERROR) {
        if (_mqttClient.connected()) {
            // Stack optimizasyonu: Statik buffer kullan (String yerine)
            static char logTopic[64];
            static char logPayload[256];

            snprintf(logTopic, sizeof(logTopic), "pemf/coil/%d/system/log", _coilId);
            snprintf(logPayload, sizeof(logPayload),
                     "{\"level\":%d,\"msg\":\"%s\",\"heap\":%u}",
                     level, message, ESP.getFreeHeap());

            _mqttClient.publish(logTopic, logPayload, false);
        }
    }
}
