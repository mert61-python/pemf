// SIRLAR AYIKLANDI (repo PUBLIC): gercek degerler MASAUSTU kopyasinda
// (C:/Users/merta/Desktop/guii) durur. Flash oncesi buraya elle gir, COMMIT ETME -
// gitleaks kancasi zaten durdurur.
#ifndef SECRETS_H
#define SECRETS_H

// ============================================================================
// KONFIGURASYON VE GIZLI BILGILER
// ============================================================================
// Preferences.h kullanıldığı için buradaki değerler "Factory Default" olarak
// kabul edilir. İlk açılışta veya reset durumunda kullanılır.
// ============================================================================

// --- CIHAZ AYARLARI ---
#define FACTORY_COIL_ID       5           // Cihaz ID'si (1-8 arasi)
#define FACTORY_PWM_FREQ      100         // Varsayılan PWM Frekansi (Hz)

// --- CONFIG VERSION ---
// Bu değer artırıldığında ESP, NVS'deki WiFi/MQTT ayarlarını sıfırlar.
// Yeni gateway yapılandırmasında eski NVS verilerinin temizlenmesi için kullanılır.
#define CONFIG_VERSION        2           // Artır → NVS WiFi/MQTT reset

// --- SERİ PORT ---
#define SERIAL_BAUD_RATE      115200

// --- WI-FI AYARLARI (Varsayılan) ---
// LattePanda WiFi Hotspot'una bağlanmak için PEMF-Gateway SSID kullanılır
static const char* DEFAULT_WIFI_SSID = "PEMF-Gateway";
static const char* DEFAULT_WIFI_PASS = "<<GERCEK-DEGERI-FLASH-ONCESI-GIR>>";

// ============================================================================
// MQTT AYARLARI — DUAL BROKER (LOCAL + CLOUD)
// ============================================================================
// Öncelik: LOCAL broker (LattePanda Mosquitto) → Fallback: CLOUD broker (HiveMQ)
// LOCAL broker internet olmadan da çalışır (offline-first)
// CLOUD broker internet varsa Mosquitto bridge ile otomatik senkronize olur.

// --- LOCAL MQTT (LattePanda Mosquitto) ---
static const char* DEFAULT_LOCAL_MQTT_HOST = "192.168.137.1";  // Windows Hotspot default gateway
static const int   DEFAULT_LOCAL_MQTT_PORT = 1883;              // Plain TCP (TLS yok)
static const bool  DEFAULT_LOCAL_MQTT_TLS  = false;
static const char* DEFAULT_LOCAL_MQTT_USER = "";                // Anonymous (yerel ağ)
static const char* DEFAULT_LOCAL_MQTT_PASS = "";

// --- CLOUD MQTT (HiveMQ Cloud) — Fallback ---
static const char* DEFAULT_CLOUD_MQTT_HOST = "<<GERCEK-DEGERI-FLASH-ONCESI-GIR>>";
static const int   DEFAULT_CLOUD_MQTT_PORT = 8883;              // SSL/TLS
static const bool  DEFAULT_CLOUD_MQTT_TLS  = true;
static const char* DEFAULT_CLOUD_MQTT_USER = "<<GERCEK-DEGERI-FLASH-ONCESI-GIR>>";
static const char* DEFAULT_CLOUD_MQTT_PASS = "<<GERCEK-DEGERI-FLASH-ONCESI-GIR>>";

// BLE Security (ESP-IDF BLE Security üzerinden PIN/Passkey)
#define DEFAULT_BLE_PASSKEY      123456

// BLE komut imzalama anahtarı (HMAC-SHA256)
// Uretimde cihaz-bazli guclu bir anahtar ile degistirilmelidir.
static const char* DEFAULT_BLE_CMD_HMAC_KEY = "<<GERCEK-DEGERI-FLASH-ONCESI-GIR>>";

// --- BACKWARDS COMPATIBILITY (eski kodla uyum) ---
static const char* DEFAULT_MQTT_SERVER = DEFAULT_LOCAL_MQTT_HOST;
static const int   DEFAULT_MQTT_PORT   = DEFAULT_LOCAL_MQTT_PORT;
static const char* DEFAULT_MQTT_USER   = DEFAULT_LOCAL_MQTT_USER;
static const char* DEFAULT_MQTT_PASS   = DEFAULT_LOCAL_MQTT_PASS;

// --- BROKER BAĞLANTI AYARLARI ---
#define MQTT_LOCAL_MAX_RETRIES    3       // Yerel broker'a max deneme
#define MQTT_BROKER_SWITCH_DELAY  2000    // Broker değiştirme arası bekleme (ms)

// --- PREFERENCES KEYS (NVS) ---
// Namespace: "pemf_config"
#define PREF_KEY_WIFI_SSID        "wifi_ssid"
#define PREF_KEY_WIFI_PASS        "wifi_pass"
#define PREF_KEY_COIL_ID          "coil_id"
#define PREF_KEY_MQTT_SERVER      "mqtt_server"
#define PREF_KEY_MQTT_PORT        "mqtt_port"
#define PREF_KEY_PWM_STATE        "pwm_state"     // Struct olarak saklanır
#define PREF_KEY_LOCAL_MQTT_HOST  "lmqtt_host"
#define PREF_KEY_LOCAL_MQTT_PORT  "lmqtt_port"
#define PREF_KEY_CLOUD_MQTT_HOST  "cmqtt_host"
#define PREF_KEY_CLOUD_MQTT_PORT  "cmqtt_port"
#define PREF_KEY_CONFIG_VERSION   "cfg_ver"

#endif // SECRETS_H
