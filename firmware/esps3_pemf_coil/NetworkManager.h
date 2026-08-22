#ifndef NETWORK_MANAGER_H
#define NETWORK_MANAGER_H

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <WebServer.h>       // Eklendi
#include <ESPmDNS.h>         // mDNS: pemf-gateway.local → dinamik IP çözümlünür
#include "BLEProvisioning.h"
#include "SharedDefs.h"
#include "Secrets.h"

// ============================================================================
// ENDÜSTRİYEL DÖNÜŞÜM: WiFi, MQTT ve Sistem Yönetimi (Core 0)
// ============================================================================

// Broker tipi: Hangi broker'a bağlıyız?
enum BrokerType {
    BROKER_NONE = 0,
    BROKER_LOCAL = 1,   // LattePanda Mosquitto (192.168.137.1:1883)
    BROKER_CLOUD = 2    // HiveMQ Cloud (TLS:8883)
};

class PemfNetworkManager {
public:
    PemfNetworkManager();
    void begin();

    // Core 0 Task Loop
    void process();

    // Veri Yayınlama
    void publishStatus(const SystemStatusMsg& msg);
    void publishSensorData(const SensorReadings& data);
    void publishEvent(const char* eventType, const char* message);
    void sendCommandAck(const char* command_id, bool success);
    void publishSystemLog(LogLevel level, const char* message);

    // Durum Sorgulama
    bool isMqttConnected();
    bool isPortalActive() { return false; }
    bool isBLEActive();
    BrokerType getActiveBroker() { return _activeBroker; }

    // Helper
    void triggerRestart(unsigned long delayMs);

    // ✅ Internal Command Processor
    void _processIncomingCommand(char* topic, byte* payload, unsigned int length);

private:
    // Network Objects — Dual client: plain TCP + TLS
    WiFiClient* _netClientPlain;         // Yerel broker (TLS yok)
    WiFiClientSecure* _netClientSecure;  // Cloud broker (TLS)
    PubSubClient* _mqtt;                 // Pointer — client dinamik atanır
    Preferences _prefs;
    WebServer* _server;                  // Pointer
    BLEProvisioning* _bleProvisioning;   // NimBLE Provisioning modülü

    // State
    bool _wifiConnected = false;
    bool _bleProvisioningActive = false; // BLE yayını aktif mi?

    // HATA-3 FIX: Non-blocking WiFi reconnect state
    bool _wifiReconnecting = false;
    unsigned long _wifiReconnectStart = 0;
    int _wifiRetryCount = 0; // HATA-6 FIX: WiFi tekrar deneme limitörü

    // Restart Control
    bool _restartPending = false;
    unsigned long _restartTargetTime = 0;

    // Config — Dual Broker
    String _ssid;
    String _password;

    // Local broker config
    String _localMqttHost;
    int    _localMqttPort;

    // Cloud broker config
    String _cloudMqttHost;
    int    _cloudMqttPort;

    // Active broker tracking
    BrokerType _activeBroker = BROKER_NONE;
    int _localRetryCount = 0;

    // Legacy fields (active broker bilgileri)
    String _mqttServer;
    int _mqttPort;
    int _coilId;

    // Topics
    String _topicStatus;
    String _topicControl;
    String _topicEvents;

    // Async WiFi Scan for Hotspot Upgrade
    unsigned long _lastScanTime = 0;
    bool _isScanning = false;

    void _loadConfig();

    // WiFi Bağlantı State Machine (Async — Core 0'lsuböloclama yok)
    enum WiFiConnectState {
        WIFI_SM_IDLE,
        WIFI_SM_CONNECTING_PRIMARY,   // LattePanda Hotspot denemesi
        WIFI_SM_CONNECTING_SECONDARY, // NVS SSID denemesi
        WIFI_SM_CONNECTED,
        WIFI_SM_FAILED
    };
    WiFiConnectState _wifiConnectState = WIFI_SM_IDLE;
    unsigned long _wifiConnectStart = 0;

    // mDNS: Çözülen gateway IP'si ("192.168.137.1" hardcode yerine)
    String _resolvedGatewayIp;  // boşsa hardcoded fallback kullanilir
    unsigned long _lastMdnsResolve = 0; // mDNS cache tazeleme

    void _tickWiFiStateMachine();
    void _tryResolveMdnsGateway(); // pemf-gateway.local → IP

    void _reconnectMQTT();
    void _checkBLEProvisioning();       // BLE config kontrolü
    bool _connectToLocalBroker();
    bool _connectToCloudBroker();
    void _switchMqttClient(BrokerType brokerType);
    static void _mqttCallback(char* topic, byte* payload, unsigned int length);
};

#endif
