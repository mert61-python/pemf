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
| `credential_manager.py` | **`CredentialManager`** — **elle koşulan CLI** (`python -m services.credential_manager generate / list / export / provision`); çalışan backend onu içe aktarmaz / örneklemez. ESP bobin / köprü / Android için cihaz-başı MQTT kimlik-bilgilerini (`DeviceCredential`) deterministik türetir; Mosquitto parola+ACL / HiveMQ / ESP-secrets dosyalarını dışa yazar. Silinmez (Y7 sınıfı) |
| `mdns_service.py` | **`MDNSService`** — bağımsız mDNS ilancısı; host IP değişince servisi (ve MQTT'yi) yeniden kaydeden IP-izleme döngüsü |
| `headless_db_maintenance.py` | **`HeadlessDBMaintenance`** — periyodik thread: disk-alanı kontrolü, DB bakımı, yedek + yedek rotasyonu, saha-dışı kopya |

## Sistemdeki yeri
- `MosquittoSupervisor` yerel broker'ı (`bin/mosquitto`) yönetir → ESP bobinler ve API buna bağlanır.
- `credential_manager` yalnız **elle koşulunca** (CLI) Mosquitto parola/ACL dosyalarını `<veri kökü>/config/credentials/` altına üretir (`CREDENTIALS_DIR`; deponun [`config/`](../../../config/README.md) dizini DEĞİL). Sahada Python yoktur; yerel broker kimliğini bugün `PEMF_Backend.exe --mqtt-kimlik hazirla` (`utils/mqtt_kimlik.py`, A-04) hazırlar.
- `MosquittoSupervisor`, `NetworkStatusService` ve `UdpDiscoveryService` `headless_core.py` tarafından oluşturulur; `MDNSService`'i `MosquittoSupervisor` oluşturur (`headless_services.py`), `HeadlessDBMaintenance` `backend_service.py` → `start_headless_db_maintenance` ile başlar. API katmanından [`event_bus`](../event_bus.py) ile gevşek bağlıdırlar.

---
İlgili: [proje geneli](../../../README.md) · [servers/](../servers/README.md) · [config/](../../../config/README.md) · [mimari](../../../docs/ARCHITECTURE.md)
