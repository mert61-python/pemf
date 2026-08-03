# controllers/ — Donanım Kontrol Katmanı (STM32 bobinler)

STM32 bobin komutlarının **tek geçiş noktası** (choke-point). API katmanı ile seri-port sürücüsü arasında durur.

> Not: bu klasörde `__init__.py` **yoktur** — modül yoldan import edilir (`controllers.hardware_controller`).

## Dosyalar
| Dosya | Görev |
|---|---|
| `hardware_controller.py` | **`HardwareController`** — STM32 bobin paketlerini kurar/normalize eder ve core kuyruğuna iter. Bellek-içi 5-bobin durumunu `RLock` altında tutar; **1 Hz keep-alive** thread'i çalıştırır; **bobin-başı monotonik süre-deadline'ı** (donanım-tarafı güvenlik watchdog'u) uygular; STOP teslimini **garanti eder** (düşen STOP çerçevelerini yeniden gönderir). Sınırlar için [`../utils/stm32_protocol_limits.py`](../utils/README.md) kullanır. |

## Sistemdeki yeri
```
servers/api_server.py  →  HardwareController  →  HeadlessCore HW kuyruğu  →  utils/stm32_transport (seri, COM10) → STM32 (bobin 1-5)
                          (ESP bobinler 6-8 AYRI yoldan: api_server → MQTT publish)
```
- Canlı bobin durumu ayrıca [`../servers/live_state.py`](../servers/README.md)'de aynalanır.
- STM32 seri portu [`../headless_core.py`](../README.md)'un sahip olduğu `Stm32SerialTransport`'tur.

## ⚠️ Dikkat
- **Süre-deadline ve keep-alive hasta güvenliğidir** — bu davranışları zayıflatma. `emergency_stop` / süre-watchdog ile birlikte katmanlı korumadır.
- Duty/freq/faz **Python-tarafı satürasyon yok** (bilinçli, B-1.5); firmware sınırda doyurur. Sınır sabitleri `utils/stm32_protocol_limits.py`'de.

---
İlgili: [servers/](../servers/README.md) · [utils/](../utils/README.md) · [firmware/](../firmware/README.md) · [mimari](../docs/ARCHITECTURE.md)
