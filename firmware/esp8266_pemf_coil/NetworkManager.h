#ifndef NETWORK_MANAGER_H
#define NETWORK_MANAGER_H

#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h>
#include <ESP8266WebServer.h>
#include <WiFiManager.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <EEPROM.h>
#include "SharedDefs.h"

// MQTT QoS Seviyeleri
enum MQTTQoS {
    QOS_AT_MOST_ONCE = 0,    // Fire and forget
    QOS_AT_LEAST_ONCE = 1,   // Guaranteed delivery
    QOS_EXACTLY_ONCE = 2     // Duplicate-free (kullanmayÄ±n, yavaÅŸ)
};

// MQTT Buffer Size (256 bytes - stack overflow Ã¶nlemek iÃ§in, 512'den dÃ¼ÅŸÃ¼rÃ¼ldÃ¼)
const int MQTT_BUFFER_SIZE = 256;

// WiFi Ã‡oklu KayÄ±t Sistemi
const int MAX_WIFI_CREDENTIALS = 5;
const int EEPROM_SIZE = 1024;
const int EEPROM_WIFI_START = 0;
struct WiFiCredential {
    char ssid[33];
    char password[65];
    bool valid;
};

class NetworkManager {
public:
    NetworkManager(int coilId);
    void begin(const char* wifiSsid, const char* wifiPass, const char* mqttServer, int mqttPort, const char* mqttUser, const char* mqttPass);
    void update();  // Loop'ta surekli cagrilacak
    void setMqttCallback(MqttMessageCallback cb);

    // Publishing (JSON buffer'lar local scope'ta oluÅŸturulur)
    void publishSensorData(const SensorData& data);
    void publishStatus(const StatusData& status);
    void publishEvent(const char* eventType, const char* message);
    void sendCommandAck(const char* command_id, bool success);

    // Durum sorgulama
    bool isWiFiConnected();
    bool isMqttConnected();
    const char* getWiFiSSID();  // Returns pointer to internal buffer (no heap allocation)
    int getWiFiRSSI();
    IPAddress getWiFiIP();
    bool isPortalActive();

    // populateStatus pattern iÃ§in
    void populateStatus(StatusData& data);

    // Sistem loglama (Log seviyelerine gÃ¶re)
    void publishSystemLog(LogLevel level, const char* message);

    // WiFi credential temizleme
    void clearAllWiFiCredentials();

private:
    int _coilId;

    // WiFi ve MQTT nesneleri
    WiFiClient _netClientPlain;          // Local broker (TLS yok)
    WiFiClientSecure _netClientSecure;   // Cloud broker (TLS)
    PubSubClient _mqttClient;
    WiFiManager _wifiManager;
    ESP8266WebServer _portalStatusServer;

    // MQTT ve Broker tipleri
    BrokerType _activeBroker = BROKER_NONE;
    int _localRetryCount = 0;
    String _localMqttHost;
    int _localMqttPort;
    String _cloudMqttHost;
    int _cloudMqttPort;

    // mDNS
    String _resolvedGatewayIp;
    unsigned long _lastMdnsResolve = 0;

    // MQTT callback
    MqttMessageCallback _msgCallback;

    // MQTT broker bilgileri
    char _wifiSsid[33];        // Secrets.h'dan gelecek varsayilan WiFi
    char _wifiPass[65];
    char _mqttBrokerHost[64];  // Config'den gelecek, dinamik olabilir
    int _mqttBrokerPort;
    char _mqttUser[32];
    char _mqttPass[32];

    // Topic string'leri
    char _sensorTopic[32];
    char _controlTopic[32];
    char _statusTopic[32];
    char _eventTopic[32];

    // WiFi credential yÃ¶netimi
    WiFiCredential _savedWiFiList[MAX_WIFI_CREDENTIALS];
    bool _portalActive;
    unsigned long _portalStartTime;
    const unsigned long PORTAL_TIMEOUT = 300000;  // 5 dakika

    // Pending WiFi connection (portal'dan gelen bağlantı isteği için)
    bool _pendingWifiConnect;
    unsigned long _pendingWifiConnectTime;
    char _pendingSSID[33];
    char _pendingPass[65];

    // EEPROM state - sadece bir kez başlatılmalı
    bool _eepromInitialized;

    // ZamanlayÄ±cÄ±lar
    unsigned long _lastWiFiCheck;
    const unsigned long WIFI_CHECK_INTERVAL = 30000;  // 30 saniye
    unsigned long _lastMqttReconnect;
    const unsigned long MQTT_RETRY_DELAY = 2000;  // 2 saniye
    int _wifiRetryCount;
    int _mqttRetryCount;

    // WiFi durum takibi
    bool _lastWiFiState;
    bool _lastPortalState;
    char _lastWiFiSSID[33];  // String yerine char array (max 32 karakter + null terminator)

    // Async WiFi connection state machine
    enum WiFiConnectState {
        WIFI_IDLE,
        WIFI_CONNECTING,
        WIFI_WAITING_CONNECTION
    };
    WiFiConnectState _wifiConnectState;
    unsigned long _wifiConnectStartTime;
    int _currentWiFiCredentialIndex;
    const unsigned long WIFI_CONNECT_TIMEOUT = 30000;  // ✅ 30 saniye timeout (15'ten artırıldı)

    // YardÄ±mcÄ± fonksiyonlar
    void _initTopics();
    void _setupWiFi();
    void _checkWiFiConnection();
    void _reconnectWiFi();
    bool _tryConnectToSavedWiFi();
    bool _hasSavedCredentials();  // 3. tur B2: kayıtlı ağ var mı (portal erteleme/timeout kapısı)
    void _startWiFiPortal();
    void _setupMQTT();
    void _reconnectMQTT();
    bool _connectToLocalBroker();
    bool _connectToCloudBroker();
    void _switchMqttClient(BrokerType brokerType);
    void _tryResolveMdnsGateway();
    void _loadWiFiCredentials();
    void _saveWiFiCredentials();
    void _saveCurrentWiFi();
    void _setupPortalStatusServer();
    void _handlePortalStatus();
    void _handleWiFiConfig();

    // MQTT callback helper (static)
    static void _mqttCallbackHelper(char* topic, byte* payload, unsigned int length);
    static NetworkManager* _instance;  // Static instance pointer

    // Thread-safe callback lock
    static volatile unsigned long _callbackLock;
    static const unsigned long CALLBACK_LOCK_TIMEOUT = 100;  // 100ms max wait

    // Stack optimizasyonu: Heap buffer'lar (class member - sadece 4 byte pointer)
    char* _mqttPayloadBuffer;  // MQTT callback için
    char* _mqttTopicBuffer;    // MQTT JSON parsing için
    static const size_t MQTT_PAYLOAD_SIZE = 256;
    static const size_t MQTT_TOPIC_SIZE = 128;

    // Utility
    unsigned long safeMillisDiff(unsigned long current, unsigned long previous);
};

#endif
