#include "NetworkManager.h"
#include <HTTPUpdate.h>   // ✅ Add OTA Support
#include <esp_task_wdt.h> // WDT FIX: reconnect öncesi WDT reset için
// üzerinden transitif gelmektedir; açık include core 3.x'de derleme hatasına
// yol açar.

// Root CAs: HiveMQ zincir dogrulamasi icin (ISRG Root X1 + DigiCert Global Root
// G2)
static const char *HIVEMQ_ROOT_CA_PEM = R"PEM(
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIIDjjCCAnagAwIBAgIQAzrx5qcRqaC7KGSxHQn65TANBgkqhkiG9w0BAQsFADBh
MQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3
d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBH
MjAeFw0xMzA4MDExMjAwMDBaFw0zODAxMTUxMjAwMDBaMGExCzAJBgNVBAYTAlVT
MRUwEwYDVQQKEwxEaWdpQ2VydCBJbmMxGTAXBgNVBAsTEHd3dy5kaWdpY2VydC5j
b20xIDAeBgNVBAMTF0RpZ2lDZXJ0IEdsb2JhbCBSb290IEcyMIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuzfNNNx7a8myaJCtSnX/RrohCgiN9RlUyfuI
2/Ou8jqJkTx65qsGGmvPrC3oXgkkRLpimn7Wo6h+4FR1IAWsULecYxpsMNzaHxmx
1x7e/dfgy5SDN67sH0NO3Xss0r0upS/kqbitOtSZpLYl6ZtrAGCSYP9PIUkY92eQ
q2EGnI/yuum06ZIya7XzV+hdG82MHauVBJVJ8zUtluNJbd134/tJS7SsVQepj5Wz
tCO7TG1F8PapspUwtP1MVYwnSlcUfIKdzXOS0xZKBgyMUNGPHgm+F6HmIcr9g+UQ
vIOlCsRnKPZzFBQ9RnbDhxSJITRNrw9FDKZJobq7nMWxM4MphQIDAQABo0IwQDAP
BgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB/wQEAwIBhjAdBgNVHQ4EFgQUTiJUIBiV
5uNu5g/6+rkS7QYXjzkwDQYJKoZIhvcNAQELBQADggEBAGBnKJRvDkhj6zHd6mcY
1Yl9PMWLSn/pvtsrF9+wX3N3KjITOYFnQoQj8kVnNeyIv/iPsGEMNKSuIEyExtv4
NeF22d+mQrvHRAiGfzZ0JFrabA0UWTW98kndth/Jsw1HKj2ZL7tcu7XUIOGZX1NG
Fdtom/DzMNU+MeKNhJ7jitralj41E6Vf8PlwUHBHQRFXGU7Aj64GxJUTFy8bJZ91
8rGOmaFvE7FBcf6IKshPECBV1/MUReXgRPTqh5Uykw7+U0b6LJ3/iyK5S9kJRaTe
pLiaWN0bfVKfjllDiIGknibVb63dDcY3fe0Dkhvld1927jyNxF1WW6LZZm6zNTfl
MrY=
-----END CERTIFICATE-----
)PEM";

static PemfNetworkManager *instance = nullptr;

PemfNetworkManager::PemfNetworkManager() {
  instance = this;
  // Dynamic Allocation (Heap) to prevent Stack Overflow & Corruption
  // Dual client: Plain TCP for local, TLS for cloud
  _netClientPlain = new WiFiClient();
  _netClientSecure = new WiFiClientSecure();
  _mqtt = new PubSubClient();
  _server = new WebServer(80);
  _bleProvisioning = new BLEProvisioning();
}

void PemfNetworkManager::_mqttCallback(char *topic, byte *payload,
                                       unsigned int length) {
  if (instance) {
    instance->_processIncomingCommand(topic, payload, length);
  }
}

void PemfNetworkManager::begin() {
  LOG_PRINTLN("[Core 0] NetworkManager başlatılıyor...");

  // 1. Config Yükle
  _loadConfig();

  // 2. BLE Provisioning modülünü hazırla (yayın başlatmaz)
  _bleProvisioning->begin();

  // 3. BLE tetikleme butonu (GPIO0 = BOOT) — INPUT_PULLUP
  pinMode(PIN_BLE_TRIGGER, INPUT_PULLUP);

  // 4. WiFi Başlatma Denemesi
  WiFi.mode(WIFI_STA);
  _tickWiFiStateMachine();

  // (BLE fallback removed from Boot because WiFi is async now. Use BOOT button to trigger BLE if needed)

  // 6. MQTT Ayarla — Başlangıçta yerel broker'a yönlendir
  _netClientSecure->setCACert(
      HIVEMQ_ROOT_CA_PEM);         // Cloud broker TLS (CA doğrulama aktif)
  _switchMqttClient(BROKER_LOCAL); // Varsayılan: yerel broker
  _mqtt->setCallback(_mqttCallback);
  _mqtt->setBufferSize(2048); // CRITICAL FIX: Buffer boyutu artirildi
  _mqtt->setSocketTimeout(
      2); // WDT FIX: TCP timeout 2sn (WDT=5sn, headroom bırak)

  // 7. Topic Hazırla
  _topicStatus = "pemf/coil/" + String(_coilId) + "/status";
  _topicControl = "pemf/coil/" + String(_coilId) + "/control";
  _topicEvents = "pemf/coil/" + String(_coilId) + "/events";
  _topicBroadcast = "pemf/coil/all/control"; // Broadcast topiği eklendi
}

void PemfNetworkManager::_loadConfig() {
  // --- Config version check: yeni firmware NVS'yi sıfırlamalı mı? ---
  _prefs.begin("pemf_config", false); // Read-Write
  int storedVersion = _prefs.getInt(PREF_KEY_CONFIG_VERSION, 0);
  if (storedVersion != CONFIG_VERSION) {
    LOG_PRINTF("[Config] NVS config version %d != firmware %d — WiFi/MQTT "
               "factory reset!\n",
               storedVersion, CONFIG_VERSION);
    _prefs.remove(PREF_KEY_WIFI_SSID);
    _prefs.remove(PREF_KEY_WIFI_PASS);
    _prefs.remove(PREF_KEY_LOCAL_MQTT_HOST);
    _prefs.remove(PREF_KEY_LOCAL_MQTT_PORT);
    _prefs.remove(PREF_KEY_CLOUD_MQTT_HOST);
    _prefs.remove(PREF_KEY_CLOUD_MQTT_PORT);
    _prefs.remove(PREF_KEY_MQTT_SERVER);
    _prefs.remove(PREF_KEY_MQTT_PORT);
    _prefs.putInt(PREF_KEY_CONFIG_VERSION, CONFIG_VERSION);
    LOG_PRINTLN("[Config] Factory defaults restored, config version updated.");
  }

  // HATA-4 FIX: const char* default değerleri String() ile sarmalandı.
  _ssid = _prefs.getString(PREF_KEY_WIFI_SSID, String(DEFAULT_WIFI_SSID));
  _password = _prefs.getString(PREF_KEY_WIFI_PASS, String(DEFAULT_WIFI_PASS));

  // Dual Broker Config — NVS'den oku, yoksa factory default kullan
  _localMqttHost = _prefs.getString(PREF_KEY_LOCAL_MQTT_HOST,
                                    String(DEFAULT_LOCAL_MQTT_HOST));
  _localMqttPort =
      _prefs.getInt(PREF_KEY_LOCAL_MQTT_PORT, DEFAULT_LOCAL_MQTT_PORT);
  _cloudMqttHost = _prefs.getString(PREF_KEY_CLOUD_MQTT_HOST,
                                    String(DEFAULT_CLOUD_MQTT_HOST));
  _cloudMqttPort =
      _prefs.getInt(PREF_KEY_CLOUD_MQTT_PORT, DEFAULT_CLOUD_MQTT_PORT);

  // Legacy fields — yerel broker'ı varsayılan olarak ata
  _mqttServer = _localMqttHost;
  _mqttPort = _localMqttPort;

  // FIX: Force usage of FACTORY_COIL_ID from Secrets.h
  _coilId = FACTORY_COIL_ID;

  _prefs.end();

  LOG_PRINTF("[Config] SSID: '%s', Coil ID: %d\n", _ssid.c_str(), _coilId);
  LOG_PRINTF("[Config] Local MQTT: %s:%d\n", _localMqttHost.c_str(),
             _localMqttPort);
  LOG_PRINTF("[Config] Cloud MQTT: %s:%d\n", _cloudMqttHost.c_str(),
             _cloudMqttPort);
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

  // === BLE TRIGGER BUTON KONTROLÜ ===
  // GPIO0 (BOOT butonu) basılıyken BLE provisioning başlat
  static unsigned long btnPressStart = 0;
  static bool btnTriggered = false;
  if (digitalRead(PIN_BLE_TRIGGER) == LOW) {
    if (btnPressStart == 0)
      btnPressStart = millis();
    // 3 saniye basılı tutulursa BLE başlat
    if (!btnTriggered && (millis() - btnPressStart > 3000)) {
      btnTriggered = true;
      if (!_bleProvisioningActive) {
        LOG_PRINTLN("[BLE] Buton tetiklendi! BLE Provisioning başlatılıyor...");
        WiFi.disconnect(true); // WiFi'ı kes
        WiFi.mode(WIFI_OFF);   // CRITICAL FIX: Radyolar çakışmasın
        _bleProvisioning->startAdvertising();
        _bleProvisioningActive = true;
      }
    }
  } else {
    btnPressStart = 0;
    btnTriggered = false;
  }

  // === BLE PROVISIONING AKTİFSE ===
  if (_bleProvisioningActive) {
    _checkBLEProvisioning();
    // return; SİLİNDİ: BLE aktifken de arka planda async WiFi bağlamayı dene
  }

  static bool lastWiFiState = false;
  static bool lastPortalState = false;

  // 1. WiFi Kontrolü (STA Modu)
  bool currentWiFiState = (WiFi.status() == WL_CONNECTED);

  // WiFi durumu değişti mi?
  if (currentWiFiState != lastWiFiState) {
    if (currentWiFiState) {
      // WiFi bağlandı
      // CRITICAL FIX: WiFi bağlantısı başarılı olduysa, BLE provizyonunu kapat!
      // Bu sayede arka planda "[BLE] Yayın aktif... İstemci: bekleniyor" log spami durur ve kaynaklar serbest kalır.
      if (_bleProvisioningActive && _bleProvisioning) {
        _bleProvisioning->stopAdvertising();
        _bleProvisioningActive = false;
        LOG_PRINTLN("[BLE] WiFi başarılı bağlandı, BLE yayını sonlandırıldı.");
      }

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
    // Non-blocking WiFi state machine (Core 0'ı bloke etmez)
    _tickWiFiStateMachine();

    // WiFi henüz bağlı değil — MQTT döngüsüne gitme, bu tik için çık
    return;
  }

  // WiFi bağlı: reconnect bayrağını temizle
  if (_wifiReconnecting || _wifiRetryCount > 0) {
    LOG_PRINTLN("[WiFi] WiFi yeniden bağllandı. Reconnect state temizleniyor.");
    _wifiReconnecting = false;
    _wifiRetryCount = 0;
    _wifiConnected = true;
  }

  // mDNS: 5 dakikada bir gateway IP'sini yenile (IP değişirse hemen güncelle)
  if (millis() - _lastMdnsResolve > 300000UL) {
    _tryResolveMdnsGateway();
  }

  // 2. MQTT Kontrolü (Sadece WiFi bağlıysa) - Rate limited (5sn arayla deneme)
  static unsigned long lastMqttRetry = 0;
  if (_mqtt && !_mqtt->connected() && WiFi.status() == WL_CONNECTED) {
    if (millis() - lastMqttRetry > 5000) {
      lastMqttRetry = millis();
      esp_task_wdt_reset(); // WDT FIX: Reconnect öncesi WDT besle (connect
                            // bloklayabilir)
      _reconnectMQTT();
    }
  }

  // 3. MQTT Loop
  if (_mqtt && WiFi.status() == WL_CONNECTED) {
    if (_mqtt->connected()) {
      _mqtt->loop();

      // 3.5 Cloud -> Local MQTT Seamless Fallback
      // Eğer LattePanda ağındaysak ama broker olarak Cloud'da kaldıysak (yani GUI kapatılıp açılmışsa), Mosquitto'yu yokla
      if (_activeBroker == BROKER_CLOUD && WiFi.SSID() == String(DEFAULT_WIFI_SSID)) {
        static unsigned long lastLocalMqttProbe = 0;
        if (millis() - lastLocalMqttProbe > 15000) { // 15 saniyede bir dene
          lastLocalMqttProbe = millis();
          WiFiClient probeClient;
          if (probeClient.connect(_localMqttHost.c_str(), _localMqttPort)) {
            probeClient.stop();
            LOG_PRINTLN("\n[MQTT] ✓ Yerel Broker tekrar ulaşıma açıldı! Cloud'dan Yerel ağa geçiş yapılıyor...");
            _mqtt->disconnect();
            _localRetryCount = 0;
          }
        }
      }
    }
  }

  // 4. Hotspot Yükseltme Taraması (Hotspot Upgrade Scan - Senaryo 4)
  // Eğer ESP ikincil bir ağa (Ev/Ofis) bağlıysa, arka planda LattePanda Hotspot'u arar.
  if (WiFi.status() == WL_CONNECTED && WiFi.SSID() != String(DEFAULT_WIFI_SSID)) {
    // 60 saniyede bir tarama başlat (PWM aktifken de tarama yapılabilir, async olduğu için PWM'i etkilemez)
    if (!_isScanning && (millis() - _lastScanTime > 60000)) {
      _lastScanTime = millis();
      LOG_PRINTLN("[WiFi] İkincil ağdayız. Arka planda LattePanda Hotspot aranıyor...");
      WiFi.scanNetworks(true); // Asenkron tarama (Core 0'ı bloke etmez)
      _isScanning = true;
    }

    if (_isScanning) {
      int16_t n = WiFi.scanComplete();
      if (n >= 0) { // Tarama bitti (sonuç bulundu veya boş)
        bool hotspotFound = false;
        for (int i = 0; i < n; ++i) {
          if (WiFi.SSID(i) == String(DEFAULT_WIFI_SSID)) {
            hotspotFound = true;
            break;
          }
        }
        WiFi.scanDelete(); // Belleği temizle
        _isScanning = false;

        if (hotspotFound) {
          LOG_PRINTF("\n[WiFi] ✓ LattePanda Hotspot (%s) tespit edildi! Oraya geçiş yapılıyor...\n", DEFAULT_WIFI_SSID);
          // 1. O anki MQTT bağlantısını kes (WiFi kesilmeden önce)
          if (_mqtt && _mqtt->connected()) {
            publishEvent("wifi_disconnected", "Hotspot Upgrade: LattePanda tespit edildi, geçiş yapılıyor");
            _mqtt->disconnect();
            vTaskDelay(100 / portTICK_PERIOD_MS); // Soketin kapanması için bekle
          }
          // 2. WiFi'yi kes
          WiFi.disconnect(true);
          vTaskDelay(200 / portTICK_PERIOD_MS);

          // 3. State bayraklarını sıfırla ki sistem eski ağına otomatik dönmesin
          _wifiReconnecting = false;
          _wifiConnected = false;

          // 4. Doğrudan 1. öncelikli ağa (Gateway) bağlanmayı başlat
          _tickWiFiStateMachine();
        }
      } else if (n == WIFI_SCAN_FAILED) {
        // Hata durumunda bayrağı indir, bir sonraki döngüde tekrar dener
        _isScanning = false;
      }
    }
  }
}

// ============================================================================
// mDNS GATEWAY RESOLUTION
// pemf-gateway.local → IP adresini çözer ve _resolvedGatewayIp'i günceller.
// Başarılıysa yerel broker IP'si de güncellenir.
// ============================================================================
void PemfNetworkManager::_tryResolveMdnsGateway() {
  if (WiFi.status() != WL_CONNECTED) return;

  _lastMdnsResolve = millis();
  if (!MDNS.begin("pemf-coil")) {
    // mDNS başlatma hatası — kritik değil, hardcoded fallback devreye girer
    LOG_PRINTLN("[mDNS] MDNS.begin() başarısız, hardcoded IP kullanılacak.");
    return;
  }

  // "pemf-gateway.local" için A kaydı sor (UDP Multicast, ~150ms)
  IPAddress ip = MDNS.queryHost("pemf-gateway", 2000 /*ms timeout*/);

  if (ip != INADDR_NONE && ip.toString() != "0.0.0.0") {
    String newIp = ip.toString();
    if (newIp != _resolvedGatewayIp) {
      LOG_PRINTF("[mDNS] pemf-gateway.local → %s (dinamik)\n", newIp.c_str());
      _resolvedGatewayIp = newIp;
      _localMqttHost = newIp;  // Broker IP'sini de güncelle
    }
  } else {
    LOG_PRINTLN("[mDNS] pemf-gateway.local çözülemedi, hardcoded fallback: " + String(DEFAULT_LOCAL_MQTT_HOST));
  }
}

void PemfNetworkManager::_tickWiFiStateMachine() {

  // Bağlantı başarılıysa başarı durumuna geçir
  if (WiFi.status() == WL_CONNECTED) {
    if (_wifiConnectState != WIFI_SM_CONNECTED) {
      _wifiConnectState = WIFI_SM_CONNECTED;
      LOG_PRINTLN("\n[WiFi] ✓ WiFi Bağlandı!");

      if (_bleProvisioningActive) {
        LOG_PRINTLN("[BLE] Ağ tespiti yapıldı! BLE Devreden çıkarılıyor...");
        _bleProvisioning->stopAdvertising();
        _bleProvisioningActive = false;
      }
      LOG_PRINTLN(WiFi.localIP());
      // Bağlantı sonrası mDNS ile gateway IP'sini hemen çöz
      _tryResolveMdnsGateway();
    }
    return;
  }

  // State Machine Stepper
  unsigned long now = millis();

  switch (_wifiConnectState) {
    case WIFI_SM_IDLE:
    case WIFI_SM_CONNECTED:  // Koptuğunda IDLE ve CONNECTED buradan başlar
      _wifiConnectState = WIFI_SM_CONNECTING_PRIMARY;
      _wifiConnectStart = now;
      LOG_PRINTF("[WiFi] 1. Öncelik - LattePanda Hotspot Aranıyor: %s\n", DEFAULT_WIFI_SSID);
      WiFi.disconnect(false);
      WiFi.begin(DEFAULT_WIFI_SSID, DEFAULT_WIFI_PASS);
      break;

    case WIFI_SM_CONNECTING_PRIMARY:
      if (now - _wifiConnectStart > WIFI_CONNECT_TIMEOUT_SEC * 1000UL) {
        LOG_PRINTLN("\n[WiFi] ✗ LattePanda Hotspot bulunamadı veya bağlanılamadı.");
        if (_ssid != "" && _ssid != String(DEFAULT_WIFI_SSID)) {
          _wifiConnectState = WIFI_SM_CONNECTING_SECONDARY;
          _wifiConnectStart = now;
          LOG_PRINTF("[WiFi] 2. Öncelik - Kayıtlı NVS Ağı Aranıyor: %s\n", _ssid.c_str());
          WiFi.disconnect(false);
          WiFi.begin(_ssid.c_str(), _password.c_str());
        } else {
          _wifiConnectState = WIFI_SM_FAILED;
        }
      }
      break;

    case WIFI_SM_CONNECTING_SECONDARY:
      if (now - _wifiConnectStart > WIFI_CONNECT_TIMEOUT_SEC * 1000UL) {
        LOG_PRINTLN("\n[WiFi] ✗ Kayıtlı NVS Ağına bağlanılamadı.");
        _wifiConnectState = WIFI_SM_FAILED;
      }
      break;

    case WIFI_SM_FAILED:
      LOG_PRINTLN("\n[WiFi] ✗ Hiçbir ağa bağlanılamadı.");
      if (!_bleProvisioningActive && _bleProvisioning) {
        LOG_PRINTLN("[BLE] Otomatik BLE Provisioning (Eşleşme) Modu başlatılıyor...");
        WiFi.disconnect(true);
        // WiFi kapatılmıyor ki arka planda ağ aramaya devam etsin!
        _bleProvisioning->startAdvertising();
        _bleProvisioningActive = true;
      }

      // Tekrar deneme için geri dönüş süresi
      {
        static unsigned long failedStart = now;
        if (now - failedStart > 10000UL) { // 10 saniyede bir GateWay'i tekrar yokla
          _wifiConnectState = WIFI_SM_IDLE; // En baştan dene
          failedStart = now;
        }
      }
      break;
  }
}

// Deprecated WebServer Functions (Removed/Placeholder)
// void PemfNetworkManager::_handleWebServer() {}
// void PemfNetworkManager::_handleSaveConfig() {}

void PemfNetworkManager::_switchMqttClient(BrokerType brokerType) {
  // PubSubClient'ın bağlı olduğu network client'ı ve sunucuyu değiştir
  if (brokerType == BROKER_LOCAL) {
    _mqtt->setClient(*_netClientPlain);
    _mqtt->setServer(_localMqttHost.c_str(), _localMqttPort);
    LOG_PRINTF("[MQTT] Client switched to LOCAL: %s:%d\n",
               _localMqttHost.c_str(), _localMqttPort);
  } else {
    _mqtt->setClient(*_netClientSecure);
    _mqtt->setServer(_cloudMqttHost.c_str(), _cloudMqttPort);
    LOG_PRINTF("[MQTT] Client switched to CLOUD: %s:%d\n",
               _cloudMqttHost.c_str(), _cloudMqttPort);
  }
}

bool PemfNetworkManager::_connectToLocalBroker() {
  if (WiFi.status() != WL_CONNECTED)
    return false;

  _switchMqttClient(BROKER_LOCAL);

  String clientId = "PEMF-Coil-" + String(_coilId);
  String lwtTopic = "pemf/coil/" + String(_coilId) + "/events";
  String lwtMsg =
      "{\"event_type\":\"offline\",\"coil_id\":" + String(_coilId) + "}";
  LOG_PRINTF("[MQTT] Yerel broker'a bağlanılıyor: %s:%d\n",
             _localMqttHost.c_str(), _localMqttPort);

  // Yerel broker: anonymous veya kimlik bilgisiyle
  bool result;
  if (strlen(DEFAULT_LOCAL_MQTT_USER) > 0) {
    result = _mqtt->connect(clientId.c_str(), DEFAULT_LOCAL_MQTT_USER,
                            DEFAULT_LOCAL_MQTT_PASS, lwtTopic.c_str(), 1, true,
                            lwtMsg.c_str());
  } else {
    result = _mqtt->connect(clientId.c_str(), lwtTopic.c_str(), 1, true,
                            lwtMsg.c_str());
  }

  if (result) {
    _activeBroker = BROKER_LOCAL;
    _localRetryCount = 0;
    _mqtt->subscribe(_topicControl.c_str());
    _mqtt->subscribe(_topicBroadcast.c_str()); // Broadcast'e de üye ol
    LOG_PRINTLN("[MQTT] ✓ Yerel broker'a bağlandı!");
    publishEvent("mqtt_connected", "Yerel MQTT broker'a bağlandı (Mosquitto)");
    return true;
  }

  LOG_PRINTF("[MQTT] Yerel broker bağlantı hatası, rc=%d\n", _mqtt->state());
  return false;
}

bool PemfNetworkManager::_connectToCloudBroker() {
  if (WiFi.status() != WL_CONNECTED)
    return false;

  _switchMqttClient(BROKER_CLOUD);

  String clientId = "PEMF-Coil-" + String(_coilId);
  String lwtTopic = "pemf/coil/" + String(_coilId) + "/events";
  String lwtMsg =
      "{\"event_type\":\"offline\",\"coil_id\":" + String(_coilId) + "}";
  LOG_PRINTF("[MQTT] Cloud broker'a bağlanılıyor: %s:%d\n",
             _cloudMqttHost.c_str(), _cloudMqttPort);

  bool result = _mqtt->connect(clientId.c_str(), DEFAULT_CLOUD_MQTT_USER,
                               DEFAULT_CLOUD_MQTT_PASS, lwtTopic.c_str(), 1,
                               true, lwtMsg.c_str());

  if (result) {
    _activeBroker = BROKER_CLOUD;
    _localRetryCount = 0;
    _mqtt->subscribe(_topicControl.c_str());
    _mqtt->subscribe(_topicBroadcast.c_str()); // Broadcast'e de üye ol
    LOG_PRINTLN("[MQTT] ✓ Cloud broker'a bağlandı (HiveMQ)!");
    publishEvent("mqtt_connected", "Cloud MQTT broker'a bağlandı (HiveMQ)");
    return true;
  }

  LOG_PRINTF("[MQTT] Cloud broker bağlantı hatası, rc=%d\n", _mqtt->state());
  return false;
}

void PemfNetworkManager::_reconnectMQTT() {
  if (WiFi.status() != WL_CONNECTED)
    return;

  // ==========================================================================
  // DUAL BROKER FALLBACK STRATEGY
  // ==========================================================================
  // 1. Önce LOCAL broker'a bağlanmayı dene (LattePanda Mosquitto)
  //    - Düşük latency, internet bağımlılığı yok
  //    - Mosquitto bridge varsa veriler cloud'a da gider
  // 2. LOCAL başarısız olursa (N deneme sonra) → CLOUD broker'a geç
  //    - Doğrudan HiveMQ Cloud'a bağlan (TLS)
  //    - LattePanda arızası/kapalı durumlarında kullanılır
  // 3. Her iki broker da başarısızsa → sonraki process() tick'inde tekrar dene
  // ==========================================================================

  LOG_PRINTLN("[MQTT] Dual broker bağlantı denemesi...");

  // Adım 1: Yerel broker'ı dene
  if (_connectToLocalBroker()) {
    return; // Başarılı!
  }

  _localRetryCount++;

  // Adım 2: N başarısız deneme sonra cloud'a geç
  if (_localRetryCount >= MQTT_LOCAL_MAX_RETRIES) {
    LOG_PRINTF(
        "[MQTT] Yerel broker %d kez başarısız. Cloud broker deneniyor...\n",
        _localRetryCount);

    if (_connectToCloudBroker()) {
      return; // Cloud'a bağlandı
    }

    // Her iki broker da başarısız — retry count'u sıfırla, baştan dene
    _localRetryCount = 0;
    LOG_PRINTLN("[MQTT] Her iki broker da başarısız. Sonraki denemede tekrar "
                "denenecek.");
  }
}

void PemfNetworkManager::publishStatus(const SystemStatusMsg &msg) {
  if (!_mqtt || !_mqtt->connected())
    return;

  JsonDocument doc;

  // GUI Uyumluluğu için Düz (Flat) JSON Yapısı
  // Python GUI: gui_pyqt_v11.py (on_mqtt_message)

  doc["coil_id"] = _coilId;
  doc["fw_version"] = FIRMWARE_VERSION;
  doc["msg_type"] = "status"; // UYUMSUZ-7: discriminator eklendi
  // UYUMSUZ-2: Unix ms timestamp (NTP sonrası geçerli), uptime ayrı korunuyor
  struct timeval tv_status;
  gettimeofday(&tv_status, NULL);
  unsigned long long unix_ms_status =
      (unsigned long long)tv_status.tv_sec * 1000ULL +
      tv_status.tv_usec / 1000ULL;
  doc["timestamp"] =
      unix_ms_status; // GUI için Unix ms — datetime.fromtimestamp(ts/1000)
                      // doğru çalışır
  doc["uptime"] =
      msg.uptime; // Cihaz açılışından geçen ms (ayrı alan olarak korundu)
  doc["free_heap"] = msg.freeHeap;
  doc["max_alloc_heap"] = msg.maxAllocHeap;
  doc["fragmentation"] = msg.fragmentation;
  doc["sync_fallback_event"] = msg.syncFallbackEvent;

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

  doc["portal_active"] = false; // Portal devre dışı
  {
    doc["portal_ip"] = "";
    doc["portal_ssid"] = "";
  }

  doc["mqtt_connected"] = _mqtt->connected();
  doc["broker_type"] = (_activeBroker == BROKER_LOCAL)   ? "local"
                       : (_activeBroker == BROKER_CLOUD) ? "cloud"
                                                         : "none";

  // PWM Verileri (Flat)
  doc["pwm_active"] = msg.pwm.active;
  doc["pwm_frequency"] = msg.pwm.frequency;
  doc["pwm_duty"] = msg.pwm.dutyCycle;
  doc["pwm_remaining_time"] = msg.pwm.remainingTimeSec;
  doc["pwm_duration"] = msg.pwm.durationMinutes;
  doc["pwm_start_timestamp"] = (unsigned long long)msg.pwm.startTimestamp;

  // Sensör Verileri (Flat ve Key İsimleri GUI ile uyumlu)
  doc["object_temp"] = msg.sensors.tempObject;   // GUI: object_temp
  doc["ambient_temp"] = msg.sensors.tempAmbient; // GUI: ambient_temp
  doc["current"] = msg.sensors.current;
  doc["magnetic_field"] = msg.sensors.magneticField; // GUI: magnetic_field

  // Maksimum değerler (PWM aktifken ölçülen)
  doc["max_magnetic_field"] = msg.sensors.maxMagneticField; // mT
  doc["max_current"] = msg.sensors.maxCurrent;              // A

  // Status Flags
  doc["sensors_ok"] = msg.sensors.allSensorsOk;
  doc["temp_sensor_ok"] = msg.sensors.tempSensorOk;
  doc["magnetic_sensor_ok"] = msg.sensors.magSensorOk;
  doc["current_sensor_ok"] = msg.sensors.currentSensorOk;

  String output;
  serializeJson(doc, output);

  // Asıl status topic'ine gönder
  if (!_mqtt->publish(_topicStatus.c_str(), output.c_str())) {
    LOG_PRINTLN("[MQTT] Status Publish Failed! (Packet too big?)");
  } else {
    // Debug: Sıcaklık verilerinin gönderildiğini logla
    static unsigned long lastTempLog = 0;
    if (millis() - lastTempLog > 10000) { // 10 saniyede bir
      LOG_PRINTF("[MQTT] Status -> Bobin: %.1f°C, Ortam: %.1f°C\n",
                 msg.sensors.tempObject, msg.sensors.tempAmbient);
      lastTempLog = millis();
    }
  }
}

bool PemfNetworkManager::isMqttConnected() {
  if (!_mqtt)
    return false;
  return _mqtt->connected();
}

void PemfNetworkManager::publishSensorData(const SensorReadings &data) {
  if (!_mqtt || !_mqtt->connected())
    return;

  JsonDocument doc;
  doc["coil_id"] = _coilId;
  // ÖNERİ-7: millis() yerine Unix timestamp (NTP sonrası geçerli)
  struct timeval tv_s;
  gettimeofday(&tv_s, NULL);
  doc["timestamp"] =
      (unsigned long long)tv_s.tv_sec * 1000ULL + tv_s.tv_usec / 1000ULL;
  doc["object_temp"] = data.tempObject;
  doc["ambient_temp"] = data.tempAmbient;
  doc["magnetic_field"] = data.magneticField;
  doc["current"] = data.current;
  doc["max_magnetic_field"] = data.maxMagneticField; // Maksimum manyetik alan
  doc["max_current"] = data.maxCurrent;              // Maksimum akım
  doc["temp_sensor_ok"] = data.tempSensorOk;
  doc["magnetic_sensor_ok"] = data.magSensorOk;
  doc["current_sensor_ok"] = data.currentSensorOk;
  doc["sensors_ok"] = data.allSensorsOk;

  String output;
  serializeJson(doc, output);

  String topicSensors = "pemf/coil/" + String(_coilId) + "/sensors";
  if (!_mqtt->publish(topicSensors.c_str(), output.c_str())) {
    LOG_PRINTLN("[MQTT] Sensor data publish failed!");
  } else {
    // Debug: Sıcaklık verilerinin gönderildiğini logla
    static unsigned long lastSensorTempLog = 0;
    if (millis() - lastSensorTempLog > 10000) { // 10 saniyede bir
      LOG_PRINTF("[MQTT] Sensors -> Bobin: %.1f°C, Ortam: %.1f°C\n",
                 data.tempObject, data.tempAmbient);
      lastSensorTempLog = millis();
    }
  }
}

void PemfNetworkManager::publishEvent(const char *eventType,
                                      const char *message) {
  if (!_mqtt->connected())
    return;

  JsonDocument doc;
  doc["coil_id"] = _coilId;
  doc["event_type"] = eventType;
  doc["message"] = message;
  // FIX 5: NTP kontrolü — senkronize değilse uptime kullan, 1970 yılı
  // timestamp'i engelle.
  struct timeval tv;
  gettimeofday(&tv, NULL);
  bool ntpSynced = (tv.tv_sec > 1600000000UL); // 2020+ ise NTP geçerli
  unsigned long long ts =
      ntpSynced
          ? ((unsigned long long)tv.tv_sec * 1000ULL + tv.tv_usec / 1000ULL)
          : (unsigned long long)millis();
  doc["timestamp"] = ts;
  doc["ntp_synced"] = ntpSynced;

  String output;
  serializeJson(doc, output);

  if (!_mqtt->publish(_topicEvents.c_str(), output.c_str())) {
    LOG_PRINTLN("[MQTT] Event publish failed!");
  }
}

void PemfNetworkManager::sendCommandAck(const char *command_id, bool success) {
  if (!_mqtt->connected())
    return;

  JsonDocument doc;
  doc["coil_id"] = _coilId;
  doc["command_id"] = command_id;
  doc["success"] = success;
  // ÖNERİ-7: Unix timestamp
  struct timeval tv;
  gettimeofday(&tv, NULL);
  doc["timestamp"] =
      (unsigned long long)tv.tv_sec * 1000ULL + tv.tv_usec / 1000ULL;

  String output;
  serializeJson(doc, output);

  String topicAck = "pemf/coil/" + String(_coilId) + "/ack";
  if (!_mqtt->publish(topicAck.c_str(), output.c_str(), true)) {
    LOG_PRINTLN("[MQTT] ACK publish failed!");
  }
}

void PemfNetworkManager::publishSystemLog(LogLevel level, const char *message) {
  // Önce seri porta yaz
  const char *levelStr = "";
  if (level == PEMF_LOG_INFO) {
    levelStr = "[INFO]";
  } else if (level == PEMF_LOG_WARN) {
    levelStr = "[WARN]";
  } else if (level == PEMF_LOG_ERROR) {
    levelStr = "[ERROR]";
  }

  LOG_PRINTF("%s %s\n", levelStr, message);

  // Sadece WARN ve ERROR'ları MQTT'ye gönder
  if ((level == PEMF_LOG_WARN || level == PEMF_LOG_ERROR) && _mqtt &&
      _mqtt->connected() && true) { // HATA-7: !_apMode→true
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

void PemfNetworkManager::_processIncomingCommand(char *topic, byte *payload,
                                                 unsigned int length) {
  LOG_PRINTF("[MQTT] Mesaj: %s\n", topic);

  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, payload, length);

  if (error) {
    LOG_PRINTLN("[MQTT] JSON Parse Hatası");
    return;
  }

  ControlCommand cmd;
  String cmdStr = doc["command"];
  cmdStr.toUpperCase(); // Case-insensitive compare (GUI sends 'start', we
                        // expect 'START')

  if (cmdStr == "START") {
    cmd.type = CMD_START;
    cmd.frequency = doc["freq"];
    cmd.dutyCycle = (int)(doc["duty"].as<float>() + 0.5f);
    cmd.phase     = doc.containsKey("phase") ? (int)(doc["phase"].as<float>() + 0.5f) : 0;  // [FIX-3]
    cmd.durationMinutes = doc["duration"];
    if (doc.containsKey("start_at")) {
      unsigned long long raw_ts = doc["start_at"];
      // UYUMSUZ-1: Otomatik ms/sn tespiti
      // 13 haneden küçükse saniye cinsinden gelmiştir, ms'e çevir
      if (raw_ts > 0 && raw_ts < 1000000000000ULL) {
        cmd.timestamp = raw_ts * 1000ULL; // sn → ms
        LOG_PRINTLN("[CMD] start_at: saniye formatı algılandı, ms'e çevrildi");
      } else {
        cmd.timestamp = raw_ts; // Zaten ms
      }
    } else {
      cmd.timestamp = 0;
    }
  } else if (cmdStr == "STOP") {
    cmd.type = CMD_STOP;
  } else if (cmdStr == "UPDATE") {
    cmd.type = CMD_UPDATE_PARAMS;
    cmd.frequency = doc["freq"];
    cmd.dutyCycle = (int)(doc["duty"].as<float>() + 0.5f);
    cmd.phase     = doc.containsKey("phase") ? (int)(doc["phase"].as<float>() + 0.5f) : 0;  // [FIX-3]
  } else if (cmdStr == "SELFTEST") {
    cmd.type = CMD_SELF_TEST;
  }
  // HATA-1 FIX: SET_PARAMS komutu eklendi (Python GUI apply_to_all_coils
  // gönderir)
  else if (cmdStr == "SET_PARAMS") {
    cmd.type = CMD_UPDATE_PARAMS;
    cmd.frequency = doc["freq"];
    cmd.dutyCycle = (int)(doc["duty"].as<float>() + 0.5f);
    cmd.phase     = doc.containsKey("phase") ? (int)(doc["phase"].as<float>() + 0.5f) : 0;  // [FIX-3]
    cmd.durationMinutes = doc["duration"] | 0;  } else if (cmdStr == "SYNC_ALL") {
    // Toplu komut (Broadcast üzerinden gelir)
    if (doc.containsKey("coils")) {
      String myCoilIdStr = String(_coilId);
      if (doc["coils"].containsKey(myCoilIdStr.c_str())) {
        JsonObject myCoil = doc["coils"][myCoilIdStr.c_str()];

        // Kendi bobinimize ait parametreleri START komutu gibi işleyelim
        // Eğer cihaz zaten çalışıyorsa UPDATE gibi davranır (CoilController halleder)
        cmd.type = CMD_START;
        cmd.frequency = myCoil["freq"] | 100;
        cmd.dutyCycle = (int)(myCoil["duty"].as<float>() + 0.5f);
        cmd.phase     = myCoil.containsKey("phase") ? (int)(myCoil["phase"].as<float>() + 0.5f) : 0;  // [FIX-3]
        cmd.durationMinutes = myCoil["duration"] | 0;

        if (myCoil.containsKey("start_at")) {
          unsigned long long raw_ts = myCoil["start_at"];
          if (raw_ts > 0 && raw_ts < 1000000000000ULL) {
            cmd.timestamp = raw_ts * 1000ULL;
          } else {
            cmd.timestamp = raw_ts;
          }
        } else if (doc.containsKey("start_at")) {
          // Global start_at fallback
          unsigned long long raw_ts = doc["start_at"];
          if (raw_ts > 0 && raw_ts < 1000000000000ULL) {
            cmd.timestamp = raw_ts * 1000ULL;
          } else {
            cmd.timestamp = raw_ts;
          }
        } else {
          cmd.timestamp = 0;
        }
      } else {
        // Broadcast geldi ama bu bobin için veri yok, komutu yoksay
        return;
      }
    } else {
      return;
    }  } else if (cmdStr == "UPDATE_FIRMWARE") {
    String url = doc["url"];
    LOG_PRINTF("[OTA] Firmware update requested from: %s\n", url.c_str());

    if (url.length() > 0) {
      if (!url.startsWith("https://")) {
        LOG_PRINTLN("[OTA] Rejected: Only HTTPS OTA URLs are allowed");
        publishEvent("ota_rejected", "Yalniz HTTPS OTA desteklenir");
        return;
      }

      // Stop PWM before update for safety
      ControlCommand stopCmd;
      stopCmd.type = CMD_STOP;
      xQueueSend(commandQueue, &stopCmd, 0);
      delay(500); // Wait for stop

      // Secure OTA: TLS client + CA validation
      _netClientSecure->setCACert(HIVEMQ_ROOT_CA_PEM);
      t_httpUpdate_return ret = httpUpdate.update(*_netClientSecure, url);

      switch (ret) {
      case HTTP_UPDATE_FAILED:
        LOG_PRINTF("[OTA] Update Failed. Error (%d): %s\n",
                   httpUpdate.getLastError(),
                   httpUpdate.getLastErrorString().c_str());
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
  } else {
    LOG_PRINTF("[MQTT] Bilinmeyen Komut: %s\n", cmdStr.c_str());
    return;
  }

  // Komut ID'sini kopyala, CoilController islediginde asenkron olarak ACK yollanacak
  const char *cmd_id = doc["command_id"] | "";
  if (strlen(cmd_id) > 0 && strlen(cmd_id) < 36) {
    strncpy(cmd.command_id, cmd_id, 35);
    cmd.command_id[35] = '\0';
  } else {
    cmd.command_id[0] = '\0';
  }

  // Komutu kuyruğa at
  BaseType_t qResult = xQueueSend(commandQueue, &cmd, 0);
  if (qResult != pdTRUE) {
    LOG_PRINTLN("[Error] Queue Dolu! Komut işlenemedi.");
    if (strlen(cmd.command_id) > 0) {
      // Sadece reddedildiyse hemen fail ACK dondur
      sendCommandAck(cmd.command_id, false);
    }
  }
}

// ============================================================================
// BLE PROVISIONING CHECK — process() içinden çağrılır
// ============================================================================
void PemfNetworkManager::_checkBLEProvisioning() {
  if (!_bleProvisioning)
    return;

  // BLE modülünün kendi timeout/process mantığını çalıştır
  _bleProvisioning->process();

  // --- Config alındı mı? ---
  if (_bleProvisioning->isConfigReceived()) {
    LOG_PRINTLN("[BLE→WiFi] Yapılandırma alındı! Geçiş yapılıyor...");

    // CRITICAL FIX: İstemciye Write ACK'nın gitmesi için biraz zaman tanı
    // Aksi takdirde Python / Windows tarafında "İşlem iptal edildi" hatası oluşur.
    vTaskDelay(500 / portTICK_PERIOD_MS);

    // 1. BLE'yi kapat (RAM serbest bırak)
    _bleProvisioning->stopAdvertising();
    _bleProvisioningActive = false;

    // 2. NVS'den yeni config'i yükle
    _loadConfig();

    // 3. MQTT broker config geldiyse güncelle
    if (_bleProvisioning->hasMqttConfig()) {
      String newHost = _bleProvisioning->getReceivedMqttHost();
      int newPort = _bleProvisioning->getReceivedMqttPort();
      if (newHost.length() > 0) {
        _localMqttHost = newHost;
        _mqttServer = newHost;
      }
      if (newPort > 0) {
        _localMqttPort = newPort;
        _mqttPort = newPort;
      }
      _switchMqttClient(BROKER_LOCAL);
      LOG_PRINTF("[BLE→WiFi] MQTT broker güncellendi: %s:%d\n",
                 _localMqttHost.c_str(), _localMqttPort);
    }

    // 4. Config bayrağını temizle
    _bleProvisioning->clearConfigFlag();

    // 5. WiFi'a bağlan
    LOG_PRINTLN("[BLE→WiFi] Yeni WiFi ayarlarıyla bağlanılıyor...");
    WiFi.mode(WIFI_STA);
    _tickWiFiStateMachine();

    if (WiFi.status() == WL_CONNECTED) {
      LOG_PRINTLN("[BLE→WiFi] ✓ WiFi bağlantısı başarılı!");
    } else {
      LOG_PRINTLN("[BLE→WiFi] ✗ WiFi bağlantısı başarısız. Sonraki döngüde "
                  "tekrar denenecek.");
    }

    return;
  }

  // --- BLE timeout ile kapandı mı? ---
  if (!_bleProvisioning->isActive()) {
    LOG_PRINTLN(
        "[BLE] Timeout doldu veya BLE kapandı. WiFi ile devam ediliyor...");
    _bleProvisioningActive = false;

    // WiFi'a tekrar bağlanmayı dene
    WiFi.mode(WIFI_STA);
    _tickWiFiStateMachine();
  }
}

bool PemfNetworkManager::isBLEActive() {
  if (_bleProvisioning) {
    return _bleProvisioning->isActive();
  }
  return false;
}
