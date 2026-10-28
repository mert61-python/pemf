# tests/

> **2026-09-11'de eklenen kapılar** (hepsi mutasyonla kırmızı kanıtlandı):
> | Dosya | Neyi kilitler |
> |---|---|
> | `test_stm_printf_float_kapisi.py` | newlib-nano float printf — silinirse TÜM sensör telemetrisi ölür |
> | `test_masaustu_sizintisi.py` | süit sahibin gerçek masaüstüne dosya bırakamaz |
> | `test_disa_aktarim_diske_kaydet.py` | "Excel/CSV İndir" + "Tümünü PDF İndir" (WebView2'de `<a download>` ölü) |
> | `test_internetsiz_ve_esp_kapali.py` | internet≠cihaz ağı · ESP `PEMF_ESP_ENABLED` ile kapalı, kod SİLİNMEZ |
> | `test_stm_surus_kipi_ucu.py` | bipolar/unipolar kipi — yetenek tavanı delinemez |
 — Pytest Test Paketi (CI kritik-yol)

Backend'in otomatik testleri. Her push/PR'da CI çalıştırır ([`../.github/`](../.github/README.md) `tests.yml`).

## Çalıştırma
```bash
..\python.exe -m pytest tests -q -rfEs   # guii kökünden, gömülü build Python'ıyla (çıplak `pytest` PATH'te YOK)
# CI: pytest tests -v -rfEs --no-header [--cov ...]   (.github/workflows/tests.yml)
```
- `conftest.py`: `guii` kökünü VE `apps/backend`'i `sys.path`'e ekler. **Asıl izolasyon MODÜL düzeyindedir** (toplama ÖNCESİ,
  hiçbir fixture çalışmadan): oturum için `PEMF_DATA_DIR` + `APPDATA` geçici dizine ezilir (`conftest.py` "TOPLAMA-ZAMANI
  KORUMASI"); üstüne autouse bekçiler (simülatör / E-stop mandalı / operatör / ortam sızıntısı) ve ağ kafesi. **`temp_app_data`**
  test başına ayrı geçici kök verir — autouse DEĞİL, isteyen test alır. ~~`temp_app_data` fixture'ı `%APPDATA%`'yı izole eder~~
  (tek izolasyon o değil).
- Kayıtlı marker'lar `pyproject.toml` `[tool.pytest.ini_options]`'ta: `entegrasyon` (gerçek model ağırlıkları; yoksa
  `tests/capraz.py` ile ATLANIR — `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1` atlamayı hataya çevirir) ve `operator_sizintisi_beklenir`.
  ~~Özel marker yok~~; `pytest.ini` yok.

## Kapsam (sayı bu belgede TUTULMAZ — elle yazılan sayı bayatlıyordu)

> Güncel sayım KOMUTLA: dosya `git ls-files 'tests/test_*.py' | wc -l` · toplanan test
> `..\python.exe -m pytest tests --collect-only -q | tail -1`. Aşağıdaki tablo TAM LİSTE değil, alan başına **seçkidir**.
| Alan | Örnek dosyalar |
|---|---|
| Firmware/protokol güvenliği | `test_stm32_protocol_limits.py` (NaN/inf clamp, `FREQ_MAX`, `AI_PRO_DUTY_MAX`), `test_hardware_controller_safety.py` (deadline auto-stop, watchdog, reconnect re-fire), `test_coil_transport.py`, `test_session_watchdog.py` |
| Donanım-uyum turu (2026-08-19, `docs/DONANIM-UYUM-ANALIZI-2026-08-19.md`) | `test_stm_dalga_sozlesmesi.py` (HG-2 simetrik bipolar: net DC=0, asla-ikisi-HIGH, NTC-kapılı kapısı), `test_s3_sync_dc_yapisma.py` (HG-3 ISR modeli), `test_esp_ack_roundtrip.py` (HG-4 E-stop onayı), `test_plan_a_deadman.py` (süresiz-tavan/bulut-ayna/reconcile), `test_esp_control_topic.py` (D-1), `test_esp_freq_clamp.py` (D-3), `test_esp_lwt.py` (D-4), `test_stm_main_saglik.py` (tek-kaynak kapısı) |
| Auth / rate-limit | token, 429 throttle |
| KVKK / PII | şifreleme + anonimleştirme |
| Seans yaşam-döngüsü | başlat/bitir, kalıcılık |
| API sözleşme/tasarım/güvenlik, gözlemlenebilirlik, OTA rollback | ilgili `test_*` dosyaları |

## Simülasyon modu
- `PEMF_SIMULATE=1` (sanal STM+ESP+8-bobin sensör) [`../servers/api_server.py`](../apps/backend/servers/README.md) + `deploy/*.env` + `docker/*`'te kablolu — **ama pytest varsayılanı değil**: [`conftest.py`](conftest.py) süreç başında TEK normalizasyonla siler (dış kabuk/CI `PEMF_SIMULATE:""` ya da `1` verse de), test modülleri yazmaz, bir test env'de bırakırsa KIRMIZI olur (D0Ö.11 — kapı: [`test_pemf_simulate_tek_kaynak.py`](test_pemf_simulate_tek_kaynak.py)). Sim davranışı gereken test döngüyü doğrudan ve sınırlı turla koşturur.
- STM sanal test: `../tools/stm32_simulator.py` (socket 5100).

---
İlgili: [firmware/](../firmware/README.md) · [apps/backend/controllers/](../apps/backend/controllers/README.md) · [tools/ (simülatörler)](../tools/README.md) · [.github/ (CI)](../.github/README.md)
