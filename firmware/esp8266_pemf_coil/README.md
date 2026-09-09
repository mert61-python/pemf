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
- **LWT (D-4, 2026-08-19 akşam)**: iki broker bağlantısı da last-will'li — ani kopuşta broker
  `pemf/coil/8/events`e `offline` yayınlar (S3 ile birebir; eskiden yalnız ~30 sn staleness
  ile geç fark ediliyordu).
- **Süresiz-mod mutlak tavanı (Plan A-1)**: `duration=0` modda 7200 sn cihaz-yerel son-tarih;
  KÜMÜLATİF (EEPROM 30 sn'de bir geçeni yazar, resume devralır — crash-loop pencereyi
  tazeleyemez); yalnız YENİ start sıfırlar. Süreli seans + "ağ koparsa PWM durmaz" değişmezi
  etkilenmez.
- ⚠️ **IRAM %94 dolu** — yeni `IRAM_ATTR`/`ICACHE_RAM_ATTR` kod eklerken taşma riski var;
  önce ✓ Verify ile ölçün.

## 3. tur denetimi öz-iyileşme (2026-08-24)

- **WiFi portal öz-iyileşme ([B2])**: çalışırken hotspot düşerse cihaz ÖNCE kayıtlı ağları
  yeniden dener; portal yalnız kayıtlı kredi YOKKEN (gerçek provizyon ihtiyacı) süresiz açık
  kalır, kayıtlı kredi VARKEN süreli (`PORTAL_TIMEOUT`) sökülüp kayıtlı ağlar yeniden denenir.
  Amaç: ~40 sn'lik geçici hotspot kesintisinde AP-portalında ASILI KALMAMAK (S3 paritesi).
- **Yerel broker geri-dönüş ([B3])**: buluttayken yerel Mosquitto (ağ-geçidi) 15 sn'de bir
  plain soketle yoklanır; ayağa kalkınca mevcut bulut bağlantısı düşürülür ve yerel ÖNCE
  denenir → cihaz yerele döner. Yoklama başarısızsa hiçbir şey yapılmaz (bulut STABİL kalır,
  E-stop aynası korunur). Broker seçimi yerel-önce / bulut-yedek (`_reconnectMQTT`).
- **EEPROM adres haritası çakışması ([D4])** (yukarıdaki 2026-08-19 LWT `D-4`'ten AYRI bulgu):
  non-WiFi adresler (PWM/BROKER/CONFIG_VER, eski 256/300/304) 5-slotluk WiFi kimlik bölgesinin
  ([0,495)) İÇİNDEYDİ → 30 sn'lik `savePWMState` kayıtlı WiFi'yi, portal WiFi yazımı `CONFIG_VER`'i
  bozup her boot'ta yanlış sürüm-uyuşmazlığı + wipe tetikliyordu. Non-WiFi blok bölgenin sonrasına
  (`≥512`) taşındı, `CONFIG_VERSION 1→2`; **5-slot kapasitesi korundu** (`SharedDefs.h`). Yalnız
  portal-tabanlı kurulumları etkiliyordu (gömülü `Secrets.h` kimlikli mutlu yol EEPROM'a yazmaz).
  ⚠️ Reflash sonrası tek-seferlik WiFi wipe olur → yeniden provizyon gerekir.

## Flash öncesi

`Secrets.h`'taki `<<GERCEK-DEGERI-FLASH-ONCESI-GIR>>` alanlarını doldur (kaynak:
`C:\Users\merta\Desktop\guii`) — **COMMIT ETME**. `WIFI_SSID_CONST` boşsa WiFiManager
portalı devreye girer (normal akış).

## Bobin yönü (polarite) ölçümü — `[MAG]` seri raporu (2026-09-09)

S3 varyantındaki ölçümün 8266 paritesi. Firmware her **1 sn** seri porta (115200) şunu yazar:

```
[MAG] x=+0.012 y=-0.031 z=+0.418 B=0.421 mT
```

x, y, z = pencere ortalaması (**DC bileşen**), `B = √(x²+y²+z²)` aynı ortalamalardan, birim
**mT** — S3 ile aynı biçim ve aynı birim, yani iki kartın sayıları yan yana karşılaştırılabilir.
Sensör okunamıyorsa satır yerine `[MAG] sensor okunamadi — MLX90393 I2C baglantisini kontrol edin`
gelir.

⚠️ **8266'da örnekleme 1 Hz** (S3'te 5 Hz — `SensorManager::SENSOR_INTERVAL` 1000 ms). Rapor,
500 ms'lik termal denetimin zaten okuduğu veriyi kullanır (ekstra I2C yok), dolayısıyla pratikte
**her satır ≈ tek gerçek örnek** demektir: **işaret (polarite) güvenilir**, büyüklük darbe fazına
göre oynar. Kararlı bir DC değeri için birkaç satırı birlikte oku.

⚠️ Bu ölçüm için **MLX90393 bağlı olmalı** (I2C 0x18). Sensörsüz modda (`SENSÖRSÜZ MOD AKTİF`)
yalnız uyarı satırı gelir — PWM çalışmaya devam eder ama yön okunamaz.

**100 Hz / %50 duty ile ölçüm — S3 ile aynı yöntem:**

1. **Sürüş kipi — 8266'da ZATEN UYGUN, ekstra bir şey yapmana gerek yok.** Yön ölçümü
   **tek-bacak (unipolar)** sürüş ister (tek yönlü darbe → net DC ≠ 0 → ortalamanın işareti
   polariteyi verir); bu kart **yarım-köprü, TEK pin** (`D5`) sürer, yani sürüş doğası gereği
   unipolardır. ⚠️ Bu yüzden S3'teki "ölçüm için `stm32_pemf_unipolar` projesine geç" adımı
   **6-8 numaralı bobinler için GEÇERSİZDİR** — kendi start komutuyla ölç.
   (Karşılaştırma için: S3 tam-köprü **bipolar** sürer, orada ortalama ≈ 0 çıkar ve yalnız
   `|B|max` büyür — yön o kartta bu şekilde **okunamaz**.)
2. **Sensör duruşu:** MLX90393'ü bobin yüzeyinin ortasına, **her bobinde AYNI yönle** koy (öneri:
   sensör **Z** ekseni bobin eksenine paralel, çip üst yüzü bobine bakıyor, kablo hep aynı tarafta).
   Bobinden bobine sensörü döndürürsen işaretler karşılaştırılamaz. Bobinin üstüne **ok** çiz ve
   sensörün +Z yönünü o oka hizala — böylece işaret ↔ fiziksel yön eşleşmesi kayıt altına girer.
3. **Sıfır:** bobin kapalıyken `z`'yi not al = ofset (yer alanı + sensör ofseti ~0,03–0,06 mT
   burada da vardır). Bobin açıkken okunan `z` − ofset = bobinin DC alanı.
4. **Yön:** fark **pozitifse** alan sensörün +ekseni yönünde, **negatifse** ters. Yan bobinleri
   (6-8) aynı duruşla ölç; işareti diğerlerinden farklı çıkan bobin **ters bağlıdır** (sargı yönü
   ya da çıkış kablolarının sırası).
5. **Kayıt:** Arduino IDE Serial Monitor (115200) ya da
   `python -m serial.tools.miniterm COMx 115200 | tee bobinN.txt` — her bobin için ~10 satır yeter.

## Tezgâh listesi

1. Seri monitörde `[SYNC] ESP8266: donanim senkronu KULLANILMIYOR` satırı.
2. start (1 Hz, %30, 120 sn) → çıkışta 1 Hz, status `pwm_duration: 120` + efektif duty.
3. Süre dolunca kendiliğinden durur; aktifken ikinci start parametre günceller (red YOK).
4. Üst üste 8-10 STOP → hepsi işler.
5. Sensörü 48 °C üstüne ısıt → kesme + kilit + `thermal_stop`; soğuyunca start serbest.
6. Reboot ortası seans → EEPROM'dan kalan süreyle devam.
7. WiFi'yi ANİDEN kes (fişten çek) → backend ~keepalive süresinde `pemf/coil/8/events`
   üzerinden `offline` görmeli (LWT; eskiden ~30 sn staleness beklenirdi).
8. `duration: 0` (süresiz) başlat → 7200 sn'de kendiliğinden durur; ortada reboot →
   resume sonrası tavan kaldığı yerden sayar (kümülatif).
