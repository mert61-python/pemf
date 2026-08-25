# tools/ — Geliştirici / Operasyon Araçları

Donanımsız geliştirme, firmware hata-ayıklama ve test-verisi üretimi için yardımcılar.

## İçerik
| Dosya | Görev |
|---|---|
| `stm32_simulator.py` | Python STM32 emülatörü — TCP **socket 127.0.0.1:5100**, birebir 88-byte ikili + CRC32; watchdog/süre/NACK davranışını yansıtır. Donanımsız STM testi (`PEMF_STM_PORT=socket://127.0.0.1:5100`) |
| `com_sniffer.py` | Ham COM10 @115200 seri döküm (firmware debug) |
| `generate_test_data.py` | Sentetik AI eğitim/test verisi (ECG/HRV/predictor/monitor `.npy`/`.csv`) |
| `organize_resources.py` | Dağınık asset dosyalarını `pemf_gui/resources/{icons,images,...}`'e kopyalar |
| `e2e_smoke.py` | Uçtan uca duman testi — gerçek backend'i izole alt-portta (8123, `PEMF_E2E_PORT`) ayrı süreçte başlatır, `PEMF_SIMULATE=1` + geçici veri dizini. Denetim-regresyonlarını kilitler. Çalışan 8000'e DOKUNMAZ |
| `e2e_full.py` | TAM uçtan uca test — `e2e_smoke` denetim-regresyonlarını kilitlerken bu betik **KULLANICI AKIŞLARINI** sınar: hasta CRUD + sayfalama, seans yaşam-döngüsü (STM 1-5 / ESP 6-8 / 8-bobin), bobin kontrolü, canlı telemetri (WS), geçmiş + KPI, üç profil (ev sahibi/veteriner/araştırma) kapsamları. İzole alt-port (8124, `PEMF_E2E_PORT`) + geçici `PEMF_DATA_DIR`; 8000'e DOKUNMAZ |
| `kurtarma.py` | **Felaket kurtarma** — donanım arızasından sonra yedekleri yeni makinede açar. `--kodu-goster` / `--zarf … --kod … --yaz`. Bkz. [RUNBOOK](../docs/RUNBOOK.md) |
| `destek_paketi.py` | **Destek paketi üretici** (CLI) — backend çökmüşken de çalışır; PII-maskeli `.zip` üretir (`utils/support_bundle`). Arayüzdeki `POST /api/support/bundle` düğmesinin backend-ayakta-değilken alternatifi. `--cikti` / `--veri-dizini` / `--log-tavani` |

> ESP simülatörü burada değil — ESP sim [`../servers/api_server.py`](../servers/README.md) içindeki `PEMF_SIMULATE` yoludur.

## ⚠️ Not
- GUI şu an COM10'a kilitli → `stm32_simulator`'ın socket yolu bir **test yardımıdır** (`set_gui_port` no-op). Reconnect/self-heal testi: memory [[pemf-reconnect-selfheal]].

---
İlgili: [tests/](../tests/README.md) · [firmware/](../firmware/README.md) · [utils/stm32_transport](../utils/README.md)
