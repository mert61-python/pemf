# esps3_pemf_coil — ESP32-S3 Bobin Sürücüsü (bobin 6-7, tam-köprü bipolar)

> ⚠️ **GÜNCELLEME 2026-09-11 — `stm32_pemf_unipolar` AYNA PROJESİ KALDIRILDI.**
> Sürüş kipi artık `PEMF_BOBIN_UNIPOLAR_MASKESI` ile **bobin başına** seçiliyor
> (`0x60` = bobin 1-5 bipolar, 6-7 unipolar) → ikinci bir derleme gerekmiyor.
> **TEK kaynak: `firmware/stm32_pemf`.** `scripts/stm_unipolar_senkronla.py` ve
> ayna kapısı da silindi. Aşağıdaki iki-proje anlatımı TARİHÇEDİR.


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
2. `phase: 90` komutu → desen çeyrek periyot kaymalı. **Faz kilidi seans başında ve her
   freq değişiminde ilk PB1 darbesinde EDİNİLİR** (darbe periyot ortasında gelse bile) —
   aynı frekanslı ama sabit faz-ofsetli çiftte bile komut edilen faz farkı skopta görünmeli
   ([E4], 2026-08-24; edinim olmadan orta-darbe 'ignored'a düşüp faz HİÇ kilitlenmezdi).
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

## Bobin yönü (polarite) ölçümü — `[MAG]` seri raporu (2026-09-08)

Firmware her **1 sn** seri porta (115200) şunu yazar:

```
[MAG] x=+0.012 y=-0.031 z=+0.418 B=0.421 mT
```

x, y, z = son 1 sn'deki örneklerin ortalaması (**DC bileşen**; kontrol döngüsü 5 Hz, MLX90393 gain
2.5×, OSR 1, filtre 3), `B = √(x²+y²+z²)` aynı ortalamalardan. Yer manyetik alanı + sensör ofseti
~0,03–0,06 mT olarak bu değerlerde hep vardır (aşağıda "sıfır").

**100 Hz / %50 duty ile bobin yönü ölçümü:**

1. **Sürüş kipi:** yön için **tek-bacak (unipolar)** STM projesi `stm32_pemf_unipolar` ile sür
   (tek yönlü darbe → net DC ≠ 0 → `ort` işareti polariteyi verir). Simetrik **bipolar** sürüşte
   ortalama ≈ 0 çıkar, yalnız `|B|max` büyür — yön **okunamaz** (o kipte sadece büyüklük ölçülür).
2. **Sensör duruşu:** MLX90393'ü bobin yüzeyinin ortasına, çip üzerindeki eksen işaretine göre
   **her bobinde AYNI yönle** koy (öneri: sensör **Z** ekseni bobin eksenine paralel, çip üst yüzü
   bobine bakıyor; kablo hep aynı tarafta). Bobinden bobine sensörü döndürürsen işaretler
   karşılaştırılamaz.
3. **Sıfır:** bobin kapalıyken `z`'yi (seçtiğin eksen) not al = ofset. Bobin açıkken okunan
   `z` − ofset = bobinin DC alanı.
4. **Yön:** fark **pozitifse** alan sensörün +ekseni yönünde (o yüz sensöre göre KUZEY gibi davranır),
   **negatifse** ters. Beş bobini aynı duruşla ölç; işareti diğerlerinden farklı çıkan bobin **ters
   bağlıdır** (sargı yönü ya da IN_A/IN_B sırası). ⚠️ Unipolar projede **bobin 1 darbeyi IN_B'den
   (PD12)** alır: köprü simetrikse bobin 1'in işareti diğerlerine göre **ters çıkar — beklenen**;
   bipolar kutupluluk kıyasında bunu hesaba kat.
5. **Büyüklük:** %50 duty tek-bacakta okunan ortalama ≈ tepe alanın yarısı (5 Hz örnekleme tepeyi
   göstermez; tepe için skop/probe). 0,10 mT altında kalıyorsa mesafeyi azalt / akımı kontrol et
   (self-test eşiği de 0,10 mT).
6. **Kayıt:** Arduino IDE Serial Monitor (115200) ya da
   `python -m serial.tools.miniterm COMx 115200 | tee bobinN.txt` — her bobin için ~10 satır yeter.
