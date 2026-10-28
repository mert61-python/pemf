# controllers/ — Donanım Kontrol Katmanı (STM32 bobinler)

STM32 bobin komutlarının **tek geçiş noktası** (choke-point). API katmanı ile seri-port sürücüsü arasında durur.

> Not: klasör normal bir pakettir (`__init__.py` var); import `controllers.hardware_controller` ya da `apps.backend.controllers.hardware_controller` biçimindedir.

## Dosyalar
| Dosya | Görev |
|---|---|
| `hardware_controller.py` | **`HardwareController`** — STM32 bobin paketlerini kurar/normalize eder ve core kuyruğuna iter. Bellek-içi **7-bobin** durumunu (`STM_BOBIN_SAYISI = 7`) `RLock` altında tutar; **2 Hz keep-alive** (`KEEP_ALIVE_INTERVAL_S = 0.5`) thread'i çalıştırır — firmware'in 1500 ms ölü-adam watchdog'una ~1000 ms pay bırakır, düşürmeyin; **bobin-başı monotonik süre-deadline'ı** (donanım-tarafı güvenlik watchdog'u) uygular; düşen STOP çerçevelerini `STOP_RESEND_TICKS` tur (≈3 sn) **yeniden göndermeyi DENER**. ⚠️ `stop_all_coils` / `update_coil(start=False)` dönüşü "STOP paketi donanım **kuyruğuna VERİLDİ**" demektir — porta teslim ya da fiziksel teyit DEĞİL (kuyruk alamazsa `False`; gönderici iş parçacığı ölmüşken de `True` dönebilir — B-1.23, açık madde). Sınırlar için [`../utils/stm32_protocol_limits.py`](../utils/README.md) kullanır. |

## Sistemdeki yeri
```
servers/api_server.py  →  HardwareController  →  HeadlessCore HW kuyruğu  →  utils/stm32_transport (seri, COM10) → STM32 (bobin 1-7)
                          (ESP slotu 8 AYRI yoldan: api_server → MQTT publish — ⚠️ `PEMF_ESP_ENABLED` varsayılan 0, kart sökülü; `live_state.esp_etkin()` false iken `_mqtt_publish` yayın YAPMADAN False döner)
```
- Canlı bobin durumu ayrıca [`../servers/live_state.py`](../servers/README.md)'de aynalanır.
- STM32 seri portu [`../headless_core.py`](../headless_core.py)'un sahip olduğu `Stm32SerialTransport`'tur.

## ⚠️ Dikkat
- **Süre-deadline ve keep-alive hasta güvenliğidir** — bu davranışları zayıflatma. `emergency_stop` / süre-watchdog ile birlikte katmanlı korumadır.
- **Tedavi güvenlik-sınırı (safety clamp) YOK** (bilinçli, B-1.5; Ö.4-Y9 — geri EKLENMEZ): backend'de STM duty tavanı (`STM32_DUTY_MAX_RATIO = None`) ve sıcaklık eşiği yok, termal kesme hiçbir katmanda yok (A-47). Duty üst sınırı FIRMWARE'dedir ve TAŞIYICIDIR (shoot-through): kart kip tavanının üstünü NACK'ler (`main.c` `DUTY_MAX_BIPOLAR` 0,5 · `DUTY_MAX_UNIPOLAR` 1,0 — D1.101 · Y20), ISR bipolar darbeyi `tpp/2 − DDS_BIPOLAR_GAP_TICKS` ile kıstırır.
- ⚠️ **Protokol-geçerlilik sınırı AYRIDIR ve TAŞIYICIDIR — kaldırmayın:** `update_coil` / `start_all_coils` çağrı yerinde `normalize_frequency_hz` (1–25000 Hz), `normalize_phase_deg` (0–360°) ve `duty_percent_to_ratio` (alt sınır 0) uygulanır (`utils/stm32_protocol_limits.py`). Firmware aralık dışı freq/fazı ve negatif duty'yi NACK'ler (`main.c` `RANGE coil=… field=freq|phase`, `duty < DUTY_MIN`) → sınır kaldırılırsa paket reddedilir ve bobin SESSİZCE sürülmez. ESP yolu (slot 8) ayrıca `normalize_esp_frequency_hz` (≤1000 Hz) kullanır. Kapı: `tests/test_hc_protokol_siniri_TASIYICI.py` (D1.01) — `update_coil`: frekansın İKİ ucu (0,5 Hz → 1 Hz; 99999 → 25000), fazın iki ucu, duty'nin alt ucu; `start_all_coils`: frekansın iki ucu ve fazın üst ucu. 0 Hz bilerek ölçülmez (A-05 → D1.53).

---
İlgili: [servers/](../servers/README.md) · [utils/](../utils/README.md) · [firmware/](../../../firmware/README.md) · [mimari](../../../docs/ARCHITECTURE.md)
