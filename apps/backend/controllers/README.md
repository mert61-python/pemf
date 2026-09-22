# controllers/ — Donanım Kontrol Katmanı (STM32 bobinler)

STM32 bobin komutlarının **tek geçiş noktası** (choke-point). API katmanı ile seri-port sürücüsü arasında durur.

> Not: klasör normal bir pakettir (`__init__.py` var); import `controllers.hardware_controller` ya da `apps.backend.controllers.hardware_controller` biçimindedir.

## Dosyalar
| Dosya | Görev |
|---|---|
| `hardware_controller.py` | **`HardwareController`** — STM32 bobin paketlerini kurar/normalize eder ve core kuyruğuna iter. Bellek-içi **7-bobin** durumunu (`STM_BOBIN_SAYISI = 7`) `RLock` altında tutar; **2 Hz keep-alive** (`KEEP_ALIVE_INTERVAL_S = 0.5`) thread'i çalıştırır — firmware'in 1500 ms ölü-adam watchdog'una ~1000 ms pay bırakır, düşürmeyin; **bobin-başı monotonik süre-deadline'ı** (donanım-tarafı güvenlik watchdog'u) uygular; STOP teslimini **garanti eder** (düşen STOP çerçevelerini yeniden gönderir). Sınırlar için [`../utils/stm32_protocol_limits.py`](../utils/README.md) kullanır. |

## Sistemdeki yeri
```
servers/api_server.py  →  HardwareController  →  HeadlessCore HW kuyruğu  →  utils/stm32_transport (seri, COM10) → STM32 (bobin 1-7)
                          (ESP slotu 8 AYRI yoldan: api_server → MQTT publish — ⚠️ `PEMF_ESP_ENABLED` varsayılan 0, kart sökülü; `live_state.esp_etkin()` false iken `_mqtt_publish` yayın YAPMADAN False döner)
```
- Canlı bobin durumu ayrıca [`../servers/live_state.py`](../servers/README.md)'de aynalanır.
- STM32 seri portu [`../headless_core.py`](../headless_core.py)'un sahip olduğu `Stm32SerialTransport`'tur.

## ⚠️ Dikkat
- **Süre-deadline ve keep-alive hasta güvenliğidir** — bu davranışları zayıflatma. `emergency_stop` / süre-watchdog ile birlikte katmanlı korumadır.
- Duty/freq/faz **Python-tarafı satürasyon yok** (bilinçli, B-1.5); firmware sınırda doyurur. Sınır sabitleri `utils/stm32_protocol_limits.py`'de.

---
İlgili: [servers/](../servers/README.md) · [utils/](../utils/README.md) · [firmware/](../../../firmware/README.md) · [mimari](../../../docs/ARCHITECTURE.md)
