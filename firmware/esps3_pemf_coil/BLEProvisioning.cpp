#include "BLEProvisioning.h"
#include <ArduinoJson.h>

// ============================================================================
// NimBLE HEADERS — Hafif BLE stack, boot-loop ve WDT sorunlarını önler
// ============================================================================
#include <NimBLEDevice.h>

// ============================================================================
// GLOBAL INSTANCE (NimBLE callback'leri static olduğu için gerekli)
// ============================================================================
static BLEProvisioning* _bleInstance = nullptr;

// ============================================================================
// NimBLE CALLBACK SINIFLARI
// ============================================================================

// --- Server Callbacks: İstemci bağlandı/ayrıldı ---
class ProvServerCallbacks : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer* pServer, NimBLEConnInfo& connInfo) override {
        LOG_PRINTF("[BLE] İstemci bağlandı: %s\n", connInfo.getAddress().toString().c_str());
        if (_bleInstance) _bleInstance->onClientConnected();
        // Tek bir istemci bağlandıktan sonra yayını durdur (güvenlik)
        NimBLEDevice::stopAdvertising();
    }

    void onDisconnect(NimBLEServer* pServer, NimBLEConnInfo& connInfo, int reason) override {
        LOG_PRINTF("[BLE] İstemci ayrıldı (reason=%d)\n", reason);
        if (_bleInstance) _bleInstance->onClientDisconnected();
        // Config alınmadıysa yeniden yayına başla
        if (_bleInstance && _bleInstance->isActive() && !_bleInstance->isConfigReceived()) {
            LOG_PRINTLN("[BLE] Yeniden yayın başlatılıyor...");
            NimBLEDevice::startAdvertising();
        }
    }
};

// --- WiFi SSID Characteristic Callback ---
class WiFiSSIDCallback : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic* pChar, NimBLEConnInfo& connInfo) override {
        String value = String(pChar->getValue().c_str());
        LOG_PRINTF("[BLE] WiFi SSID alındı: '%s' (%d byte)\n", value.c_str(), value.length());
        if (_bleInstance && value.length() > 0) {
            _bleInstance->onWiFiSSIDWritten(value);
        }
    }
};

// --- WiFi Password Characteristic Callback ---
class WiFiPassCallback : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic* pChar, NimBLEConnInfo& connInfo) override {
        String value = String(pChar->getValue().c_str());
        LOG_PRINTF("[BLE] WiFi Pass alındı (%d byte)\n", value.length());
        if (_bleInstance) {
            _bleInstance->onWiFiPassWritten(value);
        }
    }
};

// --- MQTT Config Characteristic Callback ---
class MqttConfigCallback : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic* pChar, NimBLEConnInfo& connInfo) override {
        String value = String(pChar->getValue().c_str());
        LOG_PRINTF("[BLE] MQTT Config alındı (%d byte)\n", value.length());
        if (_bleInstance && value.length() > 0) {
            _bleInstance->onMqttConfigWritten(value);
        }
    }
};

// --- Status Characteristic Read Callback ---
class StatusReadCallback : public NimBLECharacteristicCallbacks {
    void onRead(NimBLECharacteristic* pChar, NimBLEConnInfo& connInfo) override {
        // Güncel durum bilgisini JSON olarak döndür
        JsonDocument doc;
        doc["coil_id"] = FACTORY_COIL_ID;
        doc["fw_version"] = FIRMWARE_VERSION;
        doc["wifi_configured"] = (_bleInstance && _bleInstance->isConfigReceived());
        doc["wifi_ssid"] = (_bleInstance ? _bleInstance->getReceivedSSID() : "");

        String output;
        serializeJson(doc, output);
        pChar->setValue(output.c_str());
        LOG_PRINTF("[BLE] Status okundu: %s\n", output.c_str());
    }
};

// ============================================================================
// BLEProvisioning IMPLEMENTATION
// ============================================================================

BLEProvisioning::BLEProvisioning() {
    _bleInstance = this;
}

void BLEProvisioning::begin() {
    // NimBLE init'i burada YAPILMAZ — sadece startAdvertising() çağrıldığında yapılır.
    // Bu sayede BLE yığını gereksiz yere bellek tüketmez.
    _initialized = false;
    _active = false;
    _configReceived = false;
    _mqttConfigReceived = false;
    _receivedSSID = "";
    _receivedPass = "";
    _receivedMqttHost = "";
    _receivedMqttPort = 0;
    LOG_PRINTLN("[BLE] Provisioning modülü hazır (yayın başlatılmadı).");
}

void BLEProvisioning::startAdvertising() {
    if (_active) {
        LOG_PRINTLN("[BLE] Zaten yayın yapılıyor, atlanıyor.");
        return;
    }

    LOG_PRINTLN("[BLE] ========================================");
    LOG_PRINTLN("[BLE] NimBLE Provisioning başlatılıyor...");
    LOG_PRINTLN("[BLE] ========================================");

    String deviceName = "PEMF-Coil-" + String(FACTORY_COIL_ID);

    // --- Adım 1: NimBLE cihaz başlat (ilk seferde) ---
    if (!_initialized) {
        NimBLEDevice::init(deviceName.c_str());

        // Pelsiz/Şifresiz hızlı bağlantı için güvenlik ayarlarını devre dışı bıraktık.
        // LattePanda (veya Windows) BLE üzerinden otomatik PIN girmeden bağlanabilmeli.

        // MTU boyutu (JSON mesajlar için yeterli)
        NimBLEDevice::setMTU(256);

        _initialized = true;
        LOG_PRINTF("[BLE] Cihaz adı: %s, PIN: %d\n", deviceName.c_str(), DEFAULT_BLE_PASSKEY);
    }

    // --- Adım 2: GATT Sunucu oluştur ---
    NimBLEServer* pServer = NimBLEDevice::createServer();
    pServer->setCallbacks(new ProvServerCallbacks());

    // --- Adım 3: Provisioning Servisi oluştur ---
    NimBLEService* pService = pServer->createService(BLE_SERVICE_UUID);

    // WiFi SSID Characteristic (Write Only)
    NimBLECharacteristic* pSSIDChar = pService->createCharacteristic(
        BLE_CHAR_WIFI_SSID_UUID,
        NIMBLE_PROPERTY::WRITE
    );
    pSSIDChar->setCallbacks(new WiFiSSIDCallback());

    // WiFi Password Characteristic (Write Only)
    NimBLECharacteristic* pPassChar = pService->createCharacteristic(
        BLE_CHAR_WIFI_PASS_UUID,
        NIMBLE_PROPERTY::WRITE
    );
    pPassChar->setCallbacks(new WiFiPassCallback());

    // MQTT Config Characteristic (Write Only, opsiyonel)
    NimBLECharacteristic* pMqttChar = pService->createCharacteristic(
        BLE_CHAR_MQTT_CFG_UUID,
        NIMBLE_PROPERTY::WRITE
    );
    pMqttChar->setCallbacks(new MqttConfigCallback());

    // Status Characteristic (Read + Notify)
    NimBLECharacteristic* pStatusChar = pService->createCharacteristic(
        BLE_CHAR_STATUS_UUID,
        NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
    );
    pStatusChar->setCallbacks(new StatusReadCallback());
    pStatusChar->setValue("{\"status\":\"ready\"}");

    // --- Adım 4: Servisi başlat ---
    pService->start();

    // --- Adım 5: Yayın parametreleri ---
    NimBLEAdvertising* pAdvertising = NimBLEDevice::getAdvertising();

    // Özel Advertisement Data oluştur (sadece UUID ve Flag'ler sığsın)
    NimBLEAdvertisementData advData;
    // 0x06 (BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP)
    advData.setFlags(0x06);
    advData.setCompleteServices(NimBLEUUID(BLE_SERVICE_UUID));
    pAdvertising->setAdvertisementData(advData);

    // İsim uzun olduğu için Scan Response içerisine koy (Aktif Tarayıcılara iletilir)
    NimBLEAdvertisementData scanData;
    scanData.setName(deviceName.c_str());
    pAdvertising->setScanResponseData(scanData);

    // --- Adım 6: Yayını başlat ---
    pAdvertising->start();
    _active = true;
    _configReceived = false;
    _advertisingStartTime = millis();

    LOG_PRINTLN("[BLE] Yayın başladı. LattePanda'dan bağlantı bekleniyor...");
    LOG_PRINTF("[BLE] Timeout: SINIRSIZ (Kullanım dışı bırakıldı)\n");
}

void BLEProvisioning::stopAdvertising() {
    if (!_active) return;

    LOG_PRINTLN("[BLE] Yayın durduruluyor...");

    // Yayını durdur
    NimBLEDevice::stopAdvertising();

    // NimBLE cihazını tamamen kapat (RAM serbest bırak)
    NimBLEDevice::deinit(true);
    _initialized = false;
    _active = false;
    _clientConnected = false;

    LOG_PRINTLN("[BLE] NimBLE tamamen kapatıldı, bellek serbest bırakıldı.");
    LOG_PRINTF("[BLE] Serbest heap: %u bytes\n", ESP.getFreeHeap());
}

void BLEProvisioning::process() {
    if (!_active) return;

    // --- Sınırsız Süre ---
    // Kullanıcı talebi üzerine 120sn timeout kaldirildi.
    // Gateway'e bağlanılamazsa ESP32 sonsuza kadar komut bekler.

    // Her 30 saniyede bir durum logu
    static unsigned long lastLog = 0;
    if (millis() - lastLog > 30000) {
        lastLog = millis();
        LOG_PRINTF("[BLE] Yayın aktif... İstemci: %s\n",
                   _clientConnected ? "BAĞLI" : "bekleniyor");
    }
}

// ============================================================================
// CALLBACK HANDLERS
// ============================================================================

void BLEProvisioning::onWiFiSSIDWritten(const String& ssid) {
    _receivedSSID = ssid;
    LOG_PRINTF("[BLE] WiFi SSID kaydedildi: '%s'\n", ssid.c_str());

    // Eğer password da geldiyse config tamamdır
    if (_receivedSSID.length() > 0 && _receivedPass.length() > 0) {
        _configReceived = true;
        _saveConfigToNVS();
        LOG_PRINTLN("[BLE] ✓ WiFi yapılandırması tamamlandı!");
    }
}

void BLEProvisioning::onWiFiPassWritten(const String& pass) {
    _receivedPass = pass;
    LOG_PRINTF("[BLE] WiFi Pass kaydedildi (%d karakter)\n", pass.length());

    // Eğer SSID de geldiyse config tamamdır
    if (_receivedSSID.length() > 0 && _receivedPass.length() > 0) {
        _configReceived = true;
        _saveConfigToNVS();
        LOG_PRINTLN("[BLE] ✓ WiFi yapılandırması tamamlandı!");
    }
}

void BLEProvisioning::onMqttConfigWritten(const String& jsonConfig) {
    LOG_PRINTF("[BLE] MQTT Config JSON: %s\n", jsonConfig.c_str());

    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, jsonConfig);
    if (error) {
        LOG_PRINTF("[BLE] MQTT Config JSON parse hatası: %s\n", error.c_str());
        return;
    }

    if (doc.containsKey("host")) {
        _receivedMqttHost = doc["host"].as<String>();
    }
    if (doc.containsKey("port")) {
        _receivedMqttPort = doc["port"].as<int>();
    }

    _mqttConfigReceived = true;

    // NVS'e MQTT bilgisini kaydet
    Preferences prefs;
    prefs.begin("pemf_config", false);
    if (_receivedMqttHost.length() > 0) {
        prefs.putString(PREF_KEY_LOCAL_MQTT_HOST, _receivedMqttHost);
        LOG_PRINTF("[BLE] NVS MQTT Host kaydedildi: %s\n", _receivedMqttHost.c_str());
    }
    if (_receivedMqttPort > 0) {
        prefs.putInt(PREF_KEY_LOCAL_MQTT_PORT, _receivedMqttPort);
        LOG_PRINTF("[BLE] NVS MQTT Port kaydedildi: %d\n", _receivedMqttPort);
    }
    prefs.end();

    LOG_PRINTLN("[BLE] ✓ MQTT yapılandırması kaydedildi!");
}

void BLEProvisioning::onClientConnected() {
    _clientConnected = true;
}

void BLEProvisioning::onClientDisconnected() {
    _clientConnected = false;
}

void BLEProvisioning::clearConfigFlag() {
    _configReceived = false;
    _mqttConfigReceived = false;
    _receivedSSID = "";
    _receivedPass = "";
    _receivedMqttHost = "";
    _receivedMqttPort = 0;
}

// ============================================================================
// NVS PERSISTENCE
// ============================================================================

void BLEProvisioning::_saveConfigToNVS() {
    Preferences prefs;
    prefs.begin("pemf_config", false); // Read-Write

    prefs.putString(PREF_KEY_WIFI_SSID, _receivedSSID);
    prefs.putString(PREF_KEY_WIFI_PASS, _receivedPass);

    // Config version güncelle (NVS'nin geçersiz sayılmaması için)
    prefs.putInt(PREF_KEY_CONFIG_VERSION, CONFIG_VERSION);

    prefs.end();

    LOG_PRINTF("[BLE] NVS'e kaydedildi — SSID: '%s', Pass: %d karakter\n",
               _receivedSSID.c_str(), _receivedPass.length());
}
