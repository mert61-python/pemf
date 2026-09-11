# services/ — Headless Destek Servisleri (Qt-siz)

> ## ⚠️ ESP ALT SİSTEMİ ŞU AN DEVRE DIŞI (2026-09-11)
>
> Sahip ESP kartlarını sistemden **söktü**. Bobin 6-7 zaten 2026-09-10'da STM32'ye taşınmıştı;
> geriye ESP olarak yalnız **slot 8** kalmıştı ve o da artık takılı değil.
>
> **Tek kaldıraç:** `PEMF_ESP_ENABLED` (varsayılan `0`) → `servers/live_state.esp_etkin()`
> * `0` — MQTT dinleyicisi hiç başlamaz, `_mqtt_publish` yayın yapmadan `False` döner,
>   arayüzde "ESP / MQTT" rozeti çizilmez (durum `devre_disi`, arıza değil).
> * `1` — aşağıda anlatılan her şey **aynen** geri gelir.
>
> ⚠️ **KOD SİLİNMEDİ, SİLİNMEYECEK** (sahip: "ileride tekrar hibrit ESP+STM ya da sadece ESP
> sistemine dönebilirim"). Bu belgedeki MQTT/Mosquitto anlatımı **geçerlidir** — yalnız bugün
> kullanılmıyor. Kapı: `tests/test_internetsiz_ve_esp_kapali.py`.


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
