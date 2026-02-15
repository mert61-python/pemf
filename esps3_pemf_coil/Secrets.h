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

// --- SERİ PORT ---
#define SERIAL_BAUD_RATE      115200

// --- WI-FI AYARLARI (Varsayılan) ---
static const char* DEFAULT_WIFI_SSID = "";       
static const char* DEFAULT_WIFI_PASS = "";

// --- MQTT AYARLARI ---
static const char* DEFAULT_MQTT_SERVER = "8593bfdb2f324ad88d08b54b5e37c0a9.s1.eu.hivemq.cloud";
static const int   DEFAULT_MQTT_PORT   = 8883;   // SSL portu
static const char* DEFAULT_MQTT_USER   = "afsuampemf";
static const char* DEFAULT_MQTT_PASS   = "Pemf1234";

// --- PREFERENCES KEYS (NVS) ---
// Namespace: "pemf_config"
#define PREF_KEY_WIFI_SSID    "wifi_ssid"
#define PREF_KEY_WIFI_PASS    "wifi_pass"
#define PREF_KEY_COIL_ID      "coil_id"
#define PREF_KEY_MQTT_SERVER  "mqtt_server"
#define PREF_KEY_MQTT_PORT    "mqtt_port"
#define PREF_KEY_PWM_STATE    "pwm_state" // Struct olarak saklanır

#endif // SECRETS_H
