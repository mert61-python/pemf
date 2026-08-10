# services/ — Headless Destek Servisleri (Qt-siz)

Backend'in altyapı servisleri: MQTT broker denetimi, ağ-durumu, LAN keşfi, cihaz kimlik-bilgileri ve DB bakımı.
Hepsi **Qt-bağımsızdır** (headless EXE'ye uygun).

## Dosyalar
| Dosya | Görev |
|---|---|
| `headless_services.py` | Üç denetleyici: **`MosquittoSupervisor`** (MQTT broker'ı bul/başlat/izle), **`NetworkStatusService`** (internet/hotspot/gateway-modu yoklama), **`UdpDiscoveryService`** (LAN UDP keşif yanıtlayıcı) |
| `credential_manager.py` | **`CredentialManager`** — ESP bobin / köprü / Android için cihaz-başı MQTT kimlik-bilgilerini (`DeviceCredential`) deterministik türetir; Mosquitto parola+ACL / HiveMQ / ESP-secrets dosyalarını dışa yazar |
| `mdns_service.py` | **`MDNSService`** — bağımsız mDNS ilancısı; host IP değişince servisi (ve MQTT'yi) yeniden kaydeden IP-izleme döngüsü |
| `headless_db_maintenance.py` | **`HeadlessDBMaintenance`** — periyodik thread: disk-alanı kontrolü, DB bakımı, yedek + yedek rotasyonu, saha-dışı kopya |

## Sistemdeki yeri
- `MosquittoSupervisor` yerel broker'ı (`bin/mosquitto`) yönetir → ESP bobinler ve API buna bağlanır.
- `credential_manager` [`config/credentials/`](../config/README.md) altındaki Mosquitto parola/ACL dosyalarını üretir.
- Bu servisler `headless_core.py` tarafından oluşturulur; API katmanından [`event_bus`](../README.md) ile gevşek bağlıdır.

---
İlgili: [proje geneli](../README.md) · [servers/](../servers/README.md) · [config/](../config/README.md) · [mimari](../docs/ARCHITECTURE.md)
