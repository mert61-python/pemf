# PEMF VETERİNER TEDAVİ SİSTEMİ — TAM SİSTEM RAPORU

**Hazırlayan:** GitHub Copilot
**Tarih:** 1 Mart 2026
**Versiyon:** 1.0

---

## İÇİNDEKİLER

1. [Sistem Genel Bakış](#1-sistem-genel-bakış)
2. [Donanım Bileşenleri](#2-donanım-bileşenleri)
3. [Yazılım Mimarisi](#3-yazılım-mimarisi)
4. [Ağ ve Haberleşme Altyapısı](#4-ağ-ve-haberleşme-altyapısı)
5. [Tüm Haberleşme Senaryoları](#5-tüm-haberleşme-senaryoları)
6. [MQTT Topic Haritası](#6-mqtt-topic-haritası)
7. [LattePanda — Yapılacaklar Listesi](#7-lattepanda--yapılacaklar-listesi)
8. [Servis Yönetimi Komutları](#8-servis-yönetimi-komutları)
9. [Sorun Giderme](#9-sorun-giderme)
10. [Güvenlik Notları](#10-güvenlik-notları)

---

## 1. SİSTEM GENEL BAKIŞ

```
ESP32-S3 Cihazları (×8)
    │  WiFi (MQTT 1883)
    ▼
LattePanda (Gateway)
 ├── Mosquitto Broker      (port 1883 — local hub)
 ├── Python MQTT Bridge    (Windows Servisi — GUI kapalıyken de çalışır)
 │       │  TLS 8883
 │       ▼
 │   HiveMQ Cloud
 │       │
 │       ▼
 │   Android Uygulama / Uzak İzleme
 └── Python GUI (PyQt6)    (isteğe bağlı açık)
         │
         └── Gateway Status Widget (köprü durumu göstergesi)
```

### Sistem Amacı

8 adet ESP32-S3 tabanlı PEMF (Pulsed Electromagnetic Field) tedavi cihazından gelen sensör verilerini (sıcaklık, manyetik alan, akım, güç, frekans) LattePanda üzerinde toplamak, hem lokal GUI'de görüntülemek hem de HiveMQ Cloud üzerinden Android uygulamasına iletmek.

---

## 2. DONANIM BİLEŞENLERİ

### 2.1 ESP32-S3 Tedavi Modülleri (×8)

| Özellik | Değer |
|---------|-------|
| Mikrodenetleyici | ESP32-S3 DevKit |
| Firmware | C++ (Arduino Framework) |
| WiFi | LattePanda hotspot'una bağlanır (SSID: pemf_hotspot) |
| MQTT Broker | 192.168.137.1:1883 (LattePanda hotspot IP) |
| Sensörler | MLX90614 (IR sıcaklık), MLX90393 (manyetik), ADC akım sensörü |
| Çıkış | PWM → PEMF coil (12-bit, 0–4095) |
| Tanımlama | Her cihazın benzersiz client_id'si var (pemf_coil_1 ... pemf_coil_8) |
| OTA | HTTP üzerinden firmware güncelleme desteği |
| BLE | WiFi/MQTT konfigürasyon için (ilk kurulum) |
| Watchdog | FreeRTOS WDT — takılma durumunda otomatik reset |

**Pin Haritası:**
```
GPIO 4  — PWM çıkış (PEMF coil)
GPIO 8  — I2C SDA (MLX90614 sıcaklık)
GPIO 9  — I2C SCL (MLX90614 sıcaklık)
GPIO 10 — I2C SDA (MLX90393 manyetik)
GPIO 11 — I2C SCL (MLX90393 manyetik)
GPIO 1  — ADC akım sensörü (ADC1_CH0)
GPIO 2  — Durum LED'i
```

### 2.2 LattePanda (Merkezi Gateway)

| Özellik | Değer |
|---------|-------|
| İşletim Sistemi | Windows 10/11 |
| WiFi Hotspot | SSID: pemf_hotspot, IP: 192.168.137.1 |
| MQTT Broker | Mosquitto 2.0.18 (Windows Service) |
| Python Ortamı | C:\Users\merta\.conda\envs\gui\python.exe |
| Proje Klasörü | C:\Users\merta\.conda\envs\gui\gui |

### 2.3 HiveMQ Cloud

| Özellik | Değer |
|---------|-------|
| Host | 8593bfdb2f324ad88d08b54b5e37c0a9.s1.eu.hivemq.cloud |
| Port | 8883 (TLS zorunlu) |
| Kullanıcı | ***REDACTED*** |
| Şifre | ***REDACTED*** |
| Protokol | MQTT v3.1.1 over TLS 1.2 |

### 2.4 Android Uygulaması

- HiveMQ Cloud'a doğrudan TLS bağlantı kurar
- `pemf/#` topic'lerini dinler
- Tedavi komutları gönderebilir (bulut → LattePanda → ESP)

---

## 3. YAZILIM MİMARİSİ

### 3.1 Servis Katmanı (GUI'den Bağımsız)

```
Windows Servisleri:
  ┌─────────────────────────────────────────┐
  │  mosquitto (SERVICE_AUTO_START)         │
  │   ├── port 1883 (local, no auth)        │
  │   └── conf.d/ (placeholder.conf)        │
  └─────────────────────────────────────────┘
  ┌─────────────────────────────────────────┐
  │  PemfMqttBridge (SERVICE_AUTO_START)    │
  │   ├── Bağımlı: mosquitto servisi        │
  │   ├── python services/mqtt_bridge.py   │
  │   ├── Log: LOCALAPPDATA\PEMF_System\   │
  │   │         logs\mqtt_bridge_service.log│
  │   └── Crash recovery: 5s sonra restart  │
  └─────────────────────────────────────────┘
```

### 3.2 GUI Katmanı (İsteğe Bağlı)

```
windows/gui_pyqt_v11.py (Ana pencere)
 ├── services/mosquitto_manager.py
 │    ├── MosquittoManager (Mosquitto başlat/durdur)
 │    └── start_bridge() → MQTTBridge (GUI'ye ek bridge)
 ├── windows/gateway_status_widget.py
 │    ├── MQTT Broker durumu (Çalışıyor/Durdu)
 │    └── Cloud Bridge durumu (Bağlı/Bağlanıyor/Bağlantı Yok)
 └── windows/unified_control_window.py
      └── Cihaz kontrol paneli
```

### 3.3 Python MQTT Bridge (`services/mqtt_bridge.py`)

```
MQTTBridge Sınıfı:
  ├── _local_client  → 127.0.0.1:1883 (Mosquitto)
  ├── _cloud_client  → HiveMQ Cloud :8883 (TLS)
  ├── Topic aboneliği: pemf/# (her iki tarafta)
  ├── Yönlendirme:
  │    Local → Cloud: tüm pemf/# mesajları
  │    Cloud → Local: tüm pemf/# mesajları
  ├── Döngü önleme: mesaj hash cache (500 kayıt)
  ├── Internet yoksa: cloud bağlantısı kesilir, lokal çalışmaya devam
  ├── Internet gelince: otomatik yeniden bağlanır
  └── pemf/bridge/status → "1" (aktif) / "0" (kapalı)
```

---

## 4. AĞ VE HABERLEŞME ALTYAPISI

### 4.1 Neden Native Mosquitto Bridge Değil?

> **Kritik Neden:** Mosquitto 2.0.18 Windows sürümünde `bridge_cafile` parametresiyle TLS bağlantısı kurulamıyor. Aynı sertifika ve kimlik bilgileriyle `mosquitto_pub --cafile` çalışmasına rağmen, bridge modu "CONNECT → Client closed its connection" hatası veriyor. Bu Mosquitto 2.0.18 Windows'a özgü bir bug'dır.

**Çözüm:** Python paho-mqtt + certifi kütüphanesi ile bridge yazıldı. Native bridge devre dışı bırakıldı (`bridge_hivemq.conf.disabled`).

### 4.2 Port ve Protokol Tablosu

| Bağlantı | Kaynak | Hedef | Port | Protokol | TLS |
|----------|--------|-------|------|----------|-----|
| ESP → LattePanda | 192.168.137.x | 192.168.137.1 | 1883 | MQTT 3.1.1 | Hayır |
| GUI → Mosquitto | 127.0.0.1 | 127.0.0.1 | 1883 | MQTT 3.1.1 | Hayır |
| Python Bridge → HiveMQ | LattePanda | HiveMQ Cloud | 8883 | MQTT 3.1.1 | Evet (TLS 1.2) |
| Android → HiveMQ | Android | HiveMQ Cloud | 8883 | MQTT 3.1.1 | Evet (TLS 1.2) |
| BLE yapılandırma | Android | ESP32-S3 | BLE | GATT | Hayır |

---

## 5. TÜM HABERLEŞME SENARYOLARI

### Senaryo 1: Normal Çalışma — GUI Açık, İnternet Var ✅

```
ESP32-S3 (x8)
  │ WiFi 1883
  ▼
Mosquitto (127.0.0.1:1883)
  │                    │
  ▼                    ▼
GUI (subscribe)    Python Bridge
  │ görüntüler         │ TLS 8883
                       ▼
                   HiveMQ Cloud
                       │
                       ▼
                   Android Uygulama
```

**Veri akışı:**
- ESP, `pemf/coil_1/sensor` topic'ine sensör verisi yayınlar
- Mosquitto tüm subscriber'lara dağıtır
- GUI anlık görüntüler
- Python Bridge çiftyönlü forward eder → HiveMQ'ya gider
- Android HiveMQ Cloud'dan alır

**Komut akışı (Android → ESP):**
- Android, HiveMQ'ya `pemf/coil_1/command` topic'ine publish eder
- Python Bridge cloud mesajını local'e forward eder
- Mosquitto ESP'ye iletir
- ESP komutu işler

---

### Senaryo 2: GUI Kapalı, İnternet Var ✅

```
ESP32-S3 (x8)
  │ WiFi 1883
  ▼
Mosquitto (Windows Service, çalışıyor)
  │
  ▼
PemfMqttBridge (Windows Service, çalışıyor)
  │ TLS 8883
  ▼
HiveMQ Cloud
  │
  ▼
Android Uygulama
```

**Bu senaryo en önemli yenilik:** GUI kapalı olsa bile Windows servisi olarak arkaplanda veri akmaya devam eder. LattePanda açıkken her zaman çalışır.

---

### Senaryo 3: İnternet Kesildi — GUI Açık ⚠️

```
ESP32-S3 (x8)
  │ WiFi 1883
  ▼
Mosquitto (çalışıyor)
  │
  ├── GUI (çalışıyor, lokal veri görüntüleniyor) ✅
  │
  └── Python Bridge
        ├── Cloud bağlantısı kesildi ❌
        ├── Internet kontrol döngüsü (her 30s) çalışıyor
        ├── pemf/bridge/status = "0" yayınlar
        └── Lokal mesajlar kuyrukta BEKLEMEZ (tamamen kesilir)
```

**GUI'de görülen:** Bridge durumu → "Bağlantı Yok" (kırmızı)
**ESP'ler:** Normal çalışmaya devam eder, lokal komutlar çalışır
**Android:** HiveMQ'ya bağlanamaz, veri gelmez

---

### Senaryo 4: İnternet Geldi — Otomatik Yeniden Bağlanma ✅

```
Python Bridge internet_check_loop():
  ├── 30s'de bir socket.connect("google.com", 443) dener
  ├── Başarılı → cloud_client.reconnect() çağrılır
  ├── Bağlantı kurulur
  ├── pemf/bridge/status = "1" yayınlar
  └── Normal köprüleme devam eder
```

**Reconnect stratejisi:** Üstel geri çekilme (5s → 10s → 20s → ... → 60s max)

---

### Senaryo 5: LattePanda Yeniden Başladı ✅

```
Windows başlangıç sırası:
  1. mosquitto  servisi otomatik başlar (SERVICE_AUTO_START)
  2. PemfMqttBridge servisi başlar (mosquitto bağımlılığı var → mosquitto önce başlar)
  3. Python Bridge Mosquitto'ya bağlanır
  4. İnternet varsa HiveMQ Cloud'a bağlanır
  5. ESP'ler hotspot'a bağlanır
  6. Normal veri akışı başlar

(GUI açılmazsa da 1-5 arası otomatik tamamlanır)
```

---

### Senaryo 6: ESP32 Bağlantısı Kesildi ve Geri Geldi ✅

```
ESP32-S3 (WiFi düştü):
  ├── MQTT bağlantısı kesilir
  ├── Mosquitto Last Will mesajı yayınlar:
  │    pemf/coil_1/status = "offline"
  ├── GUI ve Bridge bunu alır
  └── ESP yeniden bağlandığında:
       ├── pemf/coil_1/status = "online" yayınlar
       └── Normal veri akışı devam eder
```

---

### Senaryo 7: Python Bridge Servisi Çöktü — Crash Recovery ✅

```
PemfMqttBridge servisi crash:
  ├── NSSM fark eder (AppExit = Restart)
  ├── 5000ms (5s) bekler
  ├── Servisi yeniden başlatır
  └── Log dosyasına hata kaydedilir:
       C:\Users\merta\AppData\Local\PEMF_System\logs\
         mqtt_bridge_service.log
         mqtt_bridge_service_error.log
```

---

### Senaryo 8: Android → ESP32 Komut Gönderme ✅

```
Android:
  └── HiveMQ'ya publish:
       topic: pemf/coil_3/command
       payload: {"action":"start","frequency":10,"duty":50,"duration":300}

HiveMQ Cloud:
  └── Python Bridge (cloud subscriber) alır

Python Bridge:
  └── Local Mosquitto'ya forward eder:
       topic: pemf/coil_3/command
       (döngü önleme: aynı mesajı tekrar cloud'a göndermez)

Mosquitto:
  └── ESP32-S3 cihaz 3'e iletir

ESP32-S3 (cihaz 3):
  ├── Komutu işler
  ├── PEMF coil çalıştırır
  └── Yanıt yayınlar:
       topic: pemf/coil_3/response
       payload: {"status":"started","frequency":10}
```

---

### Senaryo 9: BLE ile ESP32 Konfigürasyonu (İlk Kurulum) ✅

```
Android BLE Uygulaması:
  └── ESP32'ye GATT write:
       BLE_CHAR_WIFI_SSID_UUID ← "pemf_hotspot"
       BLE_CHAR_WIFI_PASS_UUID ← "şifre"
       BLE_CHAR_MQTT_CFG_UUID  ← {"broker":"192.168.137.1","port":1883}

ESP32:
  ├── Preferences (Flash) kayıt eder
  ├── 1.5s sonra yeniden başlar
  └── Yeni WiFi/MQTT ile bağlanır
```

---

### Senaryo 10: ESP32 OTA Firmware Güncelleme ✅

```
GUI veya MQTT komutu:
  └── topic: pemf/coil_*/ota
      payload: {"url":"http://192.168.137.1:8080/firmware.bin"}

ESP32:
  ├── HTTP bağlantısı açar
  ├── Firmware indirir
  ├── Doğrular ve flash'a yazar
  └── Yeniden başlar (yeni firmware)
```

---

### Senaryo 11: Lokal GUI — Cloud Olmadan Çalışma ✅

```
İnternet yokken GUI:
  ├── Mosquitto local çalışıyor
  ├── ESP'ler bağlı, veri geliyor
  ├── GUI tüm kontrolleri yapabiliyor
  ├── Hasta verileri lokal DB'ye kaydediliyor
  └── Bridge durumu: "Bağlantı Yok" (kırmızı)
       Lokal işlevsellik tam, sadece bulut sync yok
```

---

## 6. MQTT TOPIC HARİTASI

```
pemf/
 ├── coil_{1-8}/
 │    ├── sensor        → ESP yayınlar: {temp, mag_x, mag_y, mag_z, current, power}
 │    ├── status        → ESP yayınlar: "online" / "offline" (LW)
 │    ├── command       → GUI/Android yazar: {action, frequency, duty, duration}
 │    ├── response      → ESP yanıtlar: {status, ...}
 │    ├── ota           → OTA güncelleme komutu
 │    └── config        → Cihaz konfigürasyonu
 │
 └── bridge/
      ├── status        → Python Bridge yayınlar: "1" (aktif) / "0" (kapalı)
      └── test/         → Test amaçlı (geliştirme)
```

---

## 7. LATTEPANDA — YAPILACAKLAR LİSTESİ

### 7.1 Ön Koşullar (Kontrol Et)

- [ ] Mosquitto Windows Service kurulu ve çalışıyor
  ```powershell
  Get-Service mosquitto
  # Status: Running olmalı
  ```

- [ ] Python ortamı mevcut
  ```powershell
  Test-Path "C:\Users\merta\.conda\envs\gui\python.exe"
  # True olmalı
  ```

- [ ] Gerekli Python paketleri kurulu
  ```powershell
  C:\Users\merta\.conda\envs\gui\python.exe -c "import paho.mqtt.client; import certifi; print('OK')"
  # OK çıktısı gelmeli
  ```

- [ ] Proje klasörü mevcut
  ```powershell
  Test-Path "C:\Users\merta\.conda\envs\gui\gui\services\mqtt_bridge.py"
  # True olmalı
  ```

### 7.2 Adım 1 — Mosquitto Yapılandırması

Mosquitto conf.d klasörünün doğru ayarlandığını doğrula:

```powershell
# Native bridge devre dışı olmalı
Test-Path "C:\ProgramData\mosquitto\conf.d\bridge_hivemq.conf.disabled"

# Placeholder conf var olmalı
Test-Path "C:\ProgramData\mosquitto\conf.d\placeholder.conf"
```

Eğer `placeholder.conf` yoksa oluştur:
```powershell
"# empty" | Out-File -Encoding ASCII "C:\ProgramData\mosquitto\conf.d\placeholder.conf"
Restart-Service mosquitto
```

### 7.3 Adım 2 — Windows Servisini Kur (Ana Adım)

**Yönetici PowerShell aç** (Sağ tık → "Yönetici Olarak Çalıştır"):

```powershell
cd "C:\Users\merta\.conda\envs\gui\gui\scripts"
.\install_bridge_service.ps1
```

Script otomatik olarak yapacakları:
1. Yönetici yetkisi kontrolü
2. Python varlığı kontrolü
3. NSSM yoksa `https://nssm.cc/release/nssm-2.24.zip` indirir → `C:\nssm\nssm.exe`
4. Eski `PemfMqttBridge` servisini kaldırır (varsa)
5. Yeni servisi kurar: `python services/mqtt_bridge.py`
6. Servis ayarları:
   - Başlangıç: Otomatik (SERVICE_AUTO_START)
   - Çalışma dizini: `C:\Users\merta\.conda\envs\gui\gui`
   - PYTHONPATH ve PYTHONUNBUFFERED ayarları
   - Log rotasyonu (10 MB × 5 dosya)
   - Crash recovery (5s sonra yeniden başlat)
7. Mosquitto bağımlılığını ekler
8. Firewall outbound kuralı ekler
9. Servisi başlatır

### 7.4 Adım 3 — Kurulumu Doğrula

```powershell
# Servis çalışıyor mu?
C:\nssm\nssm.exe status PemfMqttBridge
# Çıktı: SERVICE_RUNNING olmalı

# Canlı log izle
Get-Content "$env:LOCALAPPDATA\PEMF_System\logs\mqtt_bridge_service.log" -Tail 30 -Wait

# Log'da bu satırlar görünmeli:
# PEMF MQTT Bridge — Baslatiliyor
# Bridge calisiyor
# [Heartbeat] Aktif: True | L->C: ... | C->L: ...
```

### 7.5 Adım 4 — Hotspot Başlat

LattePanda'nın hotspot'u aktif olmalı (ESP'ler bağlanabilsin):

```powershell
# Hotspot durumu kontrol
netsh wlan show hostednetwork

# Hotspot başlat (kapalıysa)
netsh wlan start hostednetwork
```

Veya Windows Ayarlar → Ağ → Mobil Hotspot → Açık

**Hotspot ayarları:**
```
SSID    : pemf_hotspot
Şifre   : (kayıtlı şifre)
Band    : 2.4 GHz
IP      : 192.168.137.1
```

### 7.6 Adım 5 — ESP32 Cihazlarını Doğrula

ESP'lerin bağlandığını doğrula:

```powershell
# Mosquitto'ya abonelik ile ESP mesajlarını izle
# (GUI açıkken veya mosquitto_sub ile)
mosquitto_sub -h 127.0.0.1 -p 1883 -t "pemf/#" -v
# Her ESP'den "pemf/coil_X/sensor" mesajları gelmeli
```

### 7.7 Adım 6 — Cloud Bağlantısını Test Et

```powershell
# HiveMQ Cloud'u ayrı bir pencereden izle (Python ile)
C:\Users\merta\.conda\envs\gui\python.exe -c "
import ssl, certifi, time
import paho.mqtt.client as mqtt

def on_msg(c, u, msg):
    print(f'CLOUD ALDI: {msg.topic} = {msg.payload.decode()}')

c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
c.username_pw_set('***REDACTED***', '***REDACTED***')
c.tls_set(ca_certs=certifi.where(), tls_version=ssl.PROTOCOL_TLSv1_2)
c.on_message = on_msg
c.connect('8593bfdb2f324ad88d08b54b5e37c0a9.s1.eu.hivemq.cloud', 8883)
c.subscribe('pemf/#', 1)
print('HiveMQ izleniyor... (Ctrl+C ile dur)')
c.loop_forever()
"
# ESP mesajlarının Cloud'a ulaştığı görülmeli
```

### 7.8 Adım 7 — Servisin Windows Başlangıcında Çalışacağını Test Et

```powershell
# Yeniden başlatmayı simüle et
Stop-Service PemfMqttBridge
Start-Sleep 3
Start-Service PemfMqttBridge
Start-Sleep 5
C:\nssm\nssm.exe status PemfMqttBridge
# SERVICE_RUNNING olmalı
```

---

## 8. SERVİS YÖNETİMİ KOMUTLARI

### Günlük Kullanım

```powershell
# Durum kontrolü
C:\nssm\nssm.exe status PemfMqttBridge

# Canlı log izle
Get-Content "$env:LOCALAPPDATA\PEMF_System\logs\mqtt_bridge_service.log" -Tail 50 -Wait

# Servisi durdur
C:\nssm\nssm.exe stop PemfMqttBridge

# Servisi başlat
C:\nssm\nssm.exe start PemfMqttBridge

# Servisi yeniden başlat
C:\nssm\nssm.exe restart PemfMqttBridge
```

### Servis Kaldırma

```powershell
C:\nssm\nssm.exe stop PemfMqttBridge
C:\nssm\nssm.exe remove PemfMqttBridge confirm
```

### Servis Güncelleme (Kod Değişikliğinde)

```powershell
# Kodu güncelledikten sonra sadece yeniden başlat
C:\nssm\nssm.exe restart PemfMqttBridge
```

### Log Dosyaları

| Dosya | İçerik |
|-------|---------|
| `LOCALAPPDATA\PEMF_System\logs\mqtt_bridge_service.log` | Normal çalışma logları (10 MB max, 5 dosya rotasyon) |
| `LOCALAPPDATA\PEMF_System\logs\mqtt_bridge_service_error.log` | Hata ve stderr çıktısı |

**LOCALAPPDATA dizini:** `C:\Users\merta\AppData\Local`

---

## 9. SORUN GİDERME

### Sorun: Servis "STOPPED" görünüyor

```powershell
# Hata loguna bak
Get-Content "$env:LOCALAPPDATA\PEMF_System\logs\mqtt_bridge_service_error.log" -Tail 30

# Manuel çalıştır (hata ayıklama)
cd "C:\Users\merta\.conda\envs\gui\gui"
C:\Users\merta\.conda\envs\gui\python.exe services\mqtt_bridge.py
```

### Sorun: Mosquitto başlamıyor

```powershell
# Mosquitto loguna bak
Get-Content "C:\Program Files\mosquitto\mosquitto.log" -Tail 20

# conf.d'de .conf dosyası var mı?
Get-ChildItem "C:\ProgramData\mosquitto\conf.d\" -Filter "*.conf"
# placeholder.conf görünmeli

# Manuel başlat (test)
& "C:\Program Files\mosquitto\mosquitto.exe" -c "C:\Program Files\mosquitto\mosquitto.conf" -v
```

### Sorun: ESP'ler bağlanamıyor

```powershell
# Hotspot aktif mi?
netsh wlan show hostednetwork

# 1883 portu açık mı?
netstat -an | findstr ":1883"

# Firewall kuralı var mı?
Get-NetFirewallRule -DisplayName "*Mosquitto*" | Select-Object Name, Enabled, Action
```

### Sorun: HiveMQ'ya bağlanamıyor

```powershell
# DNS çözümleme
Resolve-DnsName "8593bfdb2f324ad88d08b54b5e37c0a9.s1.eu.hivemq.cloud"

# Port erişimi
Test-NetConnection -ComputerName "8593bfdb2f324ad88d08b54b5e37c0a9.s1.eu.hivemq.cloud" -Port 8883
# TcpTestSucceeded: True olmalı

# Python ile doğrudan test
C:\Users\merta\.conda\envs\gui\python.exe -c "
import ssl, certifi
import paho.mqtt.client as mqtt
c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
c.username_pw_set('***REDACTED***', '***REDACTED***')
c.tls_set(ca_certs=certifi.where(), tls_version=ssl.PROTOCOL_TLSv1_2)
c.connect('8593bfdb2f324ad88d08b54b5e37c0a9.s1.eu.hivemq.cloud', 8883, 10)
c.loop_start()
import time; time.sleep(3)
print('Bağlı!', c.is_connected())
c.disconnect()
"
```

### Sorun: Bridge döngüsü (mesajlar sonsuz tekrarlıyor)

Bu durum normalde olmamalıdır (hash cache var). Eğer olursa:
```powershell
# Log'da "Possible loop" mesajı ara
Select-String -Path "$env:LOCALAPPDATA\PEMF_System\logs\mqtt_bridge_service.log" -Pattern "loop|döngü"
```

---

## 10. GÜVENLİK NOTLARI

| Bileşen | Durum | Not |
|---------|-------|-----|
| LattePanda ↔ ESP | Şifresiz | Local ağ, kabul edilebilir |
| LattePanda ↔ HiveMQ | TLS 1.2 + kullanıcı/şifre | Güvenli |
| Android ↔ HiveMQ | TLS 1.2 + kullanıcı/şifre | Güvenli |
| MQTT kimlik doğrulama | Local: yok, Cloud: var | Local'de auth eklenmeli (production için) |
| HiveMQ şifresi | ***REDACTED*** (zayıf) | Production'da güçlü şifre önerilir |
| BLE | Kimlik doğrulamasız | İlk kurulum için kabul edilebilir |

---

## ÖZET TABLO

| Bileşen | Dosya | Durum |
|---------|-------|-------|
| Python MQTT Bridge sınıfı | `services/mqtt_bridge.py` | ✅ Tamamlandı |
| Servisi kuran PowerShell scripti | `scripts/install_bridge_service.ps1` | ✅ Tamamlandı |
| Mosquitto yönetim kodu | `services/mosquitto_manager.py` | ✅ Tamamlandı |
| GUI köprü entegrasyonu | `windows/gui_pyqt_v11.py` | ✅ Tamamlandı |
| Gateway durum widget'ı | `windows/gateway_status_widget.py` | ✅ Tamamlandı |
| Mosquitto native bridge | `config/mosquitto/bridge_hivemq.conf.disabled` | ✅ Devre dışı |
| Mosquitto conf.d placeholder | `C:\ProgramData\mosquitto\conf.d\placeholder.conf` | ✅ Oluşturuldu |
| Gereksinim dosyası | `requirements.txt` (certifi eklendi) | ✅ Güncellendi |

---

*Bu rapor PEMF sisteminin 1 Mart 2026 tarihindeki durumunu yansıtmaktadır.*
