# esp8266_pemf_coil — ESP8266 Bobin Sürücüsü (bobin 8, yarım-köprü, TEK FAZ)

**Donanım:** ESP8266 (NodeMCU/ESP-12) · yarım-köprü tek pin (D5) · MLX90614 + MLX90393 + ACS712.
⚠️ **Kart devreye LEHİMLİ — pin haritası DEĞİŞTİRİLEMEZ** (sahip kararı, 2026-08-19).

## Derleme (Arduino IDE)

| Tools ayarı | Değer |
|---|---|
| Board | **NodeMCU 1.0 (ESP-12E Module)** — kod `D5` pin adını kullanır, NodeMCU haritası şart |
| Diğerleri | varsayılan |

Kartsız derleme = **✓ Verify**. Kütüphaneler: WiFiManager (tzapu) · PubSubClient ·
ArduinoJson · Adafruit MLX90614 · Adafruit MLX90393 (+bağımlılıkları).

## 2026-08-19 kararları (kod baş yorumlarında gerekçeli)

- **Donanım senkronu YOK**: eski tanım GPIO7 idi — 8266'da flash SPI hattı, kullanılamaz;
  bu bobin **tek faz** sürülür. STM'ye sync kablosu BAĞLAMAYIN.
- **STOP hız sınırlayıcıdan muaf** + aynı `command_id`'li STOP tekrarına ACK yenilenir.
- **Yerel termal kesme**: 48 °C durdur / 45 °C histerezisli kilit (`thermal_stop`/`thermal_lock` olayları).
- **Backend sözleşmesi**: `duration` SANİYE · `freq` float kabul · aktifken `start` = güncelle ·
  `duty<1` = STOP · status **efektif** duty raporlar (%50 donanım tavanı sonrası gerçek çıkış).

## Flash öncesi

`Secrets.h`'taki `<<GERCEK-DEGERI-FLASH-ONCESI-GIR>>` alanlarını doldur (kaynak:
`C:\Users\merta\Desktop\guii`) — **COMMIT ETME**. `WIFI_SSID_CONST` boşsa WiFiManager
portalı devreye girer (normal akış).

## Tezgâh listesi

1. Seri monitörde `[SYNC] ESP8266: donanim senkronu KULLANILMIYOR` satırı.
2. start (1 Hz, %30, 120 sn) → çıkışta 1 Hz, status `pwm_duration: 120` + efektif duty.
3. Süre dolunca kendiliğinden durur; aktifken ikinci start parametre günceller (red YOK).
4. Üst üste 8-10 STOP → hepsi işler.
5. Sensörü 48 °C üstüne ısıt → kesme + kilit + `thermal_stop`; soğuyunca start serbest.
6. Reboot ortası seans → EEPROM'dan kalan süreyle devam.
