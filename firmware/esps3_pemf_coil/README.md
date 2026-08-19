# esps3_pemf_coil — ESP32-S3 Bobin Sürücüsü (bobin 6-7, tam-köprü bipolar)

**Donanım:** ESP32-S3-WROOM **N16R8** (16 MB flash, 8 MB PSRAM) · tam-köprü sürüş (GPIO4/5)
· STM32 donanım faz senkronu (PB1 → GPIO7) · MLX90614 + MLX90393 + ACS712.

## Derleme (Arduino IDE) — ölçülen çalışan ayarlar (2026-08-19, çekirdek 3.3.11)

| Tools ayarı | Değer | Neden |
|---|---|---|
| Board | **ESP32S3 Dev Module** | |
| **Partition Scheme** | **Minimal SPIFFS (1.9MB APP with OTA)** | ⚠️ ZORUNLU: varsayılan 1.25 MB'a ikili (1,38 MB) SIĞMAZ. Adında **"with OTA"** geçen şema şart — firmware'de `UPDATE_FIRMWARE` (HTTPS OTA) var; "No OTA" şeması onu ÖLDÜRÜR |
| **Flash Size** | **16MB (128Mb)** | N16R8'in gerçeği; 4MB ayarı da çalışır ama flash'ın 3/4'ünü kullanılmaz bırakır |
| PSRAM | Disabled | Firmware kullanmıyor (RAM %17); gerekirse N16R8'de "OPI PSRAM" |
| Flash Mode | QIO 80MHz | WROOM standardı |
| Diğerleri | varsayılan | Erase All Flash: **Disabled** kalsın — NVS'teki provizyon yüklemeler arası korunur |

Kartsız derleme = **✓ Verify** (Upload değil; port istemez). Gerekli kütüphaneler:
WiFiManager (tzapu) · PubSubClient · ArduinoJson · Adafruit MLX90614 · Adafruit MLX90393 (+bağımlılıkları).

⚠️ **Çekirdek 3.x notu:** kod Arduino-ESP32 **3.x API'sine** göre (timerBegin(frekans)/timerAlarm,
esp_random.h, soc/gpio_struct.h). 2.x çekirdekte DERLENMEZ — sürüm düşürmeyin.

## Flash öncesi

1. `Secrets.h`'taki `<<GERCEK-DEGERI-FLASH-ONCESI-GIR>>` alanlarını doldur (kaynak:
   `C:\Users\merta\Desktop\guii` kopyası) — **COMMIT ETME**, gitleaks zaten durdurur.
2. Bölümleme şeması değiştiği için ilk flash NVS'i taşıyabilir → WiFi/MQTT ayarları
   silinir, BLE ile yeniden provizyon gerekir (tek seferlik).
3. Seri monitör: bu ayarlarla loglar **UART/COM köprü portundan** akar (USB CDC On Boot:
   Disabled). Native USB portundan log istersen o ayarı Enabled yap.

## ⚠️ Tezgâh doğrulaması ŞART (2026-08-19 yeniden yazımı)

`CoilController.cpp` kayıptı (8266 kopyasıyla ezilmişti) ve sözleşmelerden yeniden yazıldı —
dalga biçimi **rekonstrüksiyon**, skopla doğrulanmadan kliniğe güvenilmez:

1. A/B çıkışları (GPIO4/5) iki kanalda: simetrik bipolar, örtüşme YOK, geçişlerde ≥40 µs boşluk
   (DEAD_TIME_TICKS=2), duty ≤ %50 tavanı.
2. `phase: 90` komutu → desen çeyrek periyot kaymalı.
3. STM bağlı + aynı frekans → status'ta `sync_ignored` sabit; kasıtlı farklı frekans →
   `sync_ignored` artar AMA çıkış bozulmaz (toleranslı kilit).
4. **DC-yapışma latch'i (HG-3, 2026-08-19):** STM freq'i ESP'nin ≳50 katına çıkar (örn. STM
   100 Hz + ESP 1 Hz) → latch öncesi ~8 darbelik DC penceresini SKOPLA ölç, sonra status'ta
   `sync_disabled: true` görülmeli ve çıkış kendi frekansında bipolar sürmeli. Yeni freq
   komutu latch'i sıfırlar; aynı-freq keepalive sıfırlaMAZ.
5. Termal: sensör 48 °C üstü → PWM durur + `thermal_stop`; 45 °C altına inmeden start reddedilir.
6. STOP seli (üst üste 8-10 adet) → hepsi işler; süre (saniye!) dolunca kendiliğinden durur.
7. **Süresiz-mod tavanı (Plan A-1):** `duration: 0` ile başlat → 7200 sn'de (2 saat) cihaz
   kendiliğinden durur; tavan KÜMÜLATİF — çalışırken reboot edip resume ettir, pencere
   kaldığı yerden sayar (yalnız YENİ start komutu sıfırlar). Süreli seans etkilenmez.
8. Reboot ortası seans → NVS'ten kalan süreyle devam eder.

Değişikliklerin tam gerekçeleri: bu klasördeki dosyaların baş yorumları + commit geçmişi
(`git log -- firmware/esps3_pemf_coil`).
