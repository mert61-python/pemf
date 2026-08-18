#ifndef BLE_PROVISIONING_H
#define BLE_PROVISIONING_H

#include <Arduino.h>
#include <Preferences.h>
#include "SharedDefs.h"
#include "Secrets.h"

// ============================================================================
// NimBLE TABANLI BLE PROVISIONING
// ============================================================================
// ESP32-S3 için hafif ve kararlı BLE WiFi yapılandırma modülü.
// Standart ESP-IDF BLE yerine NimBLE kullanarak boot-loop ve WDT
// sorunlarını önler.
//
// Senaryo:
//   1. ESP açılışta WiFi bulamazsa (veya fiziksel buton basılırsa)
//      BLE yayını başlar.
//   2. LattePanda GUI (bleak ile) bağlanıp SSID/Pass gönderir.
//   3. ESP bunu NVS'e yazar, BLE'yi kapatır, WiFi'a bağlanır.
//   4. 120sn timeout: süre dolarsa BLE otomatik kapanır.
// ============================================================================

class BLEProvisioning {
public:
    BLEProvisioning();

    // Modülü hazırla (NimBLE init, ama yayın başlatma)
    void begin();

    // BLE yayınını başlat (GATT server + advertising)
    void startAdvertising();

    // BLE yayınını durdur ve kaynakları serbest bırak
    void stopAdvertising();

    // Ana döngüden çağrılır (timeout kontrolü, config alma kontrolü)
    void process();

    // Durum sorguları
    bool isActive() const { return _active; }
    bool isConfigReceived() const { return _configReceived; }

    // Alınan yapılandırma verilerini oku
    String getReceivedSSID() const { return _receivedSSID; }
    String getReceivedPass() const { return _receivedPass; }
    String getReceivedMqttHost() const { return _receivedMqttHost; }
    int    getReceivedMqttPort() const { return _receivedMqttPort; }
    bool   hasMqttConfig() const { return _mqttConfigReceived; }

    // Yapılandırma bayrağını sıfırla (config işlendikten sonra çağrılır)
    void clearConfigFlag();

    // --- NimBLE Callback'leri tarafından çağrılır (public çünkü static callback erişecek) ---
    void onWiFiSSIDWritten(const String& ssid);
    void onWiFiPassWritten(const String& pass);
    void onMqttConfigWritten(const String& jsonConfig);
    void onClientConnected();
    void onClientDisconnected();

private:
    bool _initialized = false;
    bool _active = false;           // BLE yayını aktif mi?
    bool _configReceived = false;   // WiFi config tamamlandı mı? (SSID + Pass alındı)
    bool _mqttConfigReceived = false;

    // Alınan config verileri
    String _receivedSSID;
    String _receivedPass;
    String _receivedMqttHost;
    int    _receivedMqttPort = 0;

    // Timeout yönetimi
    unsigned long _advertisingStartTime = 0;

    // İstemci bağlı mı?
    bool _clientConnected = false;

    // NVS'e kaydet
    void _saveConfigToNVS();
};

#endif // BLE_PROVISIONING_H
