#ifndef NETWORK_MANAGER_H
#define NETWORK_MANAGER_H

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <WebServer.h> // Eklendi
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "SharedDefs.h"
#include "Secrets.h"

// ============================================================================
// ENDÜSTRİYEL DÖNÜŞÜM: WiFi, MQTT ve Sistem Yönetimi (Core 0)
// ============================================================================

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
    bool isPortalActive() { return _apMode; }
    
    // Helper
    void triggerRestart(unsigned long delayMs);

    // ✅ Internal Command Processor (Made Public for BLE Callback access)
    void _processIncomingCommand(char* topic, byte* payload, unsigned int length);

private:
    // Network Objects

    WiFiClientSecure* _netClient;    // Pointer
    PubSubClient* _mqtt;             // Pointer
    Preferences _prefs;
    WebServer* _server;              // Pointer

    // State
    bool _apMode = false; // AP modunda miyiz? (Depreciated -> BLE)
    bool _bleActive = false;
    bool _wifiConnected = false;
    
    // Restart Control
    bool _restartPending = false;
    unsigned long _restartTargetTime = 0;

    // BLE Objects
    BLECharacteristic* _pStatusChar = nullptr;

    // Config
    String _ssid;
    String _password;
    String _mqttServer;
    int _mqttPort;
    int _coilId;

    // Topics
    String _topicStatus;
    String _topicControl;
    String _topicEvents;

    // Helpers
    void _loadConfig();
    void _connectWiFi();
    void _startBLEService(); // AP Mode yerine BLE
    void _stopBLEService(); // Baglanti kurulunca
    
    // BLE Callbacks handled via static wrappers or friend classes usually, 
    // but for simplicity we can define logic in .cpp
    
    void _reconnectMQTT();
    static void _mqttCallback(char* topic, byte* payload, unsigned int length);
};

#endif
