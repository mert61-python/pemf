# tests/ — Pytest Test Paketi (CI kritik-yol)

Backend'in otomatik testleri. Her push/PR'da CI çalıştırır ([`../.github/`](../.github/README.md) `tests.yml`).

## Çalıştırma
```bash
pytest tests -v --cov            # guii kökünden (embedded python ile)
```
- `conftest.py`: `guii` kökünü `sys.path`'e ekler; **`temp_app_data`** fixture'ı `%APPDATA%`'yı izole eder (gerçek veriye dokunmaz).
- Özel marker yok; düz fonksiyon testleri (`pytest.ini` yok).

## Kapsam (138 `test_*.py` · ~1300 test + conftest)

> Sayı 2026-08-18'de güncellendi (eski "28" donmuş kalmıştı). Aşağıdaki tablo TAM LİSTE değil,
> alan başına **seçkidir**; güncel sayım: `ls tests/test_*.py | wc -l`.
| Alan | Örnek dosyalar |
|---|---|
| Firmware/protokol güvenliği | `test_stm32_protocol_limits.py` (NaN/inf clamp, `FREQ_MAX`, `AI_PRO_DUTY_MAX`), `test_hardware_controller_safety.py` (deadline auto-stop, watchdog, reconnect re-fire), `test_coil_transport.py`, `test_session_watchdog.py` |
| Auth / rate-limit | token, 429 throttle |
| KVKK / PII | şifreleme + anonimleştirme |
| Seans yaşam-döngüsü | başlat/bitir, kalıcılık |
| API sözleşme/tasarım/güvenlik, gözlemlenebilirlik, OTA rollback | ilgili `test_*` dosyaları |

## Simülasyon modu
- `PEMF_SIMULATE=1` (sanal STM+ESP+8-bobin sensör) [`../servers/api_server.py`](../servers/README.md) + `deploy/*.env` + `docker/*`'te kablolu — **ama pytest varsayılanı değil** (CI `PEMF_SIMULATE:""` set eder; bazı testler gerçek-yolu zorlamak için env'i temizler).
- STM sanal test: `../tools/stm32_simulator.py` (socket 5100).

---
İlgili: [firmware/](../firmware/README.md) · [controllers/](../controllers/README.md) · [tools/ (simülatörler)](../tools/README.md) · [.github/ (CI)](../.github/README.md)
