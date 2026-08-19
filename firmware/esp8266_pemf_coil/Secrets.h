// SIRLAR AYIKLANDI (repo PUBLIC): gercek degerler MASAUSTU kopyasinda
// (C:/Users/merta/Desktop/guii) durur. Flash oncesi buraya elle gir, COMMIT ETME -
// gitleaks kancasi zaten durdurur.
#ifndef SECRETS_H
#define SECRETS_H

// ============================================================================
// KONFIGURASYON VE GIZLI BILGILER
// ============================================================================
// Bu dosya ConfigManager yerine kullanilmaktadir.
// Degiskenler derleme zamaninda sabitlenir, RAM ve Flash tasarrufu saglar.
// ============================================================================

// --- CIHAZ AYARLARI ---
#define COIL_ID_CONST       8           // Cihaz ID'si (1-8 arasi)
#define PWM_FREQ_CONST      100        // PWM Frekansi (Hz)

// --- BOOT AYARLARI ---
#define SERIAL_BAUD_RATE    115200

// --- WI-FI AYARLARI ---
// Eger bos birakilirsa WiFiManager AP moduna duser
/* 2026-08-19: `static` eklendi — bu ikisi dosyadaki diğer tanımların aksine static
 * DEĞİLDİ (işaretçi dış bağlantılı olur); Secrets.h ikinci bir .cpp'ye include
 * edilince linker "multiple definition" verdi. */
static const char* WIFI_SSID_CONST = "";
static const char* WIFI_PASS_CONST = "";

// --- MQTT AYARLARI ---
// LOCAL MQTT (LattePanda Mosquitto) — öncelikli
static const char* DEFAULT_LOCAL_MQTT_HOST = "192.168.137.1";
static const int   DEFAULT_LOCAL_MQTT_PORT = 1883;  // Plain TCP

// CLOUD MQTT (HiveMQ) — fallback
static const char* DEFAULT_CLOUD_MQTT_HOST = "<<GERCEK-DEGERI-FLASH-ONCESI-GIR>>";
static const int   DEFAULT_CLOUD_MQTT_PORT = 8883;  // TLS
static const char* DEFAULT_CLOUD_MQTT_USER = "<<GERCEK-DEGERI-FLASH-ONCESI-GIR>>";
static const char* DEFAULT_CLOUD_MQTT_PASS = "<<GERCEK-DEGERI-FLASH-ONCESI-GIR>>";

#define MQTT_LOCAL_MAX_RETRIES  3
#define MQTT_BROKER_SWITCH_DELAY 2000

#define CONFIG_VERSION  1

#endif // SECRETS_H
