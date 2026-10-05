/* ============================================================================
 * MqttKimlik.h — YEREL MQTT broker kimliği (A-04 · D1.104)
 * ============================================================================
 * Anonim yerel broker'da LAN'daki herhangi bir istemci sahte `pemf/coil/<n>/ack` ile bekleyen E-stop'u "ESP
 * ONAYLADI" gösterebiliyordu (D-2.1). Kimlikli broker'da ack konusuna YALNIZ ESP kimliği yazabilir.
 *
 * Parola DEPOYA GİRMEZ: `MqttKimlikYerel.h` (.gitignore) ağ geçidi makinesinde
 *     PEMF_Backend.exe --mqtt-kimlik hazirla --firmware <bu dizin>
 * ile üretilir (backend'in makine-düzeyi kimlik deposundan; broker'ın parola/yetki dosyalarıyla AYNI adımda).
 * Başlık YOKSA yerel bağlantı KİMLİKSİZ kalır — hazırlanmamış (anonim) broker'la uyumlu; kimlikli broker bu
 * cihazı REDDEDER (bobin bağlanamaz → komut alamaz). ESP dönüş listesi: başlığı üret → derle → yak → başlığı sil.
 * Bu dosya iki sketch'te (esp8266_pemf_coil, esps3_pemf_coil) BAYT BAYT AYNIDIR (kapı denetler).
 * ============================================================================ */
#ifndef PEMF_MQTT_KIMLIK_H
#define PEMF_MQTT_KIMLIK_H

#if defined(__has_include)
#if __has_include("MqttKimlikYerel.h")
#include "MqttKimlikYerel.h"
#endif
#endif

#ifndef PEMF_YEREL_MQTT_KULLANICI
#define PEMF_YEREL_MQTT_KULLANICI ""
#endif
#ifndef PEMF_YEREL_MQTT_PAROLA
#define PEMF_YEREL_MQTT_PAROLA ""
#endif

#endif /* PEMF_MQTT_KIMLIK_H */
