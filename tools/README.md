# tools/ — Geliştirici / Operasyon Araçları

Donanımsız geliştirme, firmware hata-ayıklama ve test-verisi üretimi için yardımcılar.

## İçerik
| Dosya | Görev |
|---|---|
| `stm32_simulator.py` | Python STM32 emülatörü — TCP **socket 127.0.0.1:5100**, birebir **121 bayt** ikili + CRC32 (7 bobin; sayı kaynakta `PKT_SIZE`, kapı: tests/test_readme_baglanti_ve_sayi_BAYATLAMAZ.py); watchdog/süre/NACK davranışını yansıtır. Donanımsız STM testi (`PEMF_STM_PORT=socket://127.0.0.1:5100`) |
| `com_sniffer.py` | Ham seri döküm — `PORT` sabiti (COM10) @115200, ST-Link VCP → kartın USART3'ü (firmware debug); sessizlikte olası nedenleri (ilk paketten sonra banner kesilir) yazar |
| `generate_test_data.py` | Sentetik AI eğitim/test verisi (ECG/HRV/predictor/monitor `.npy`/`.csv`) |
| `organize_resources.py` | Eski Qt arayüzü dönemi aracı: betiğin KENDİ dizinindeki (`tools/`) dağınık asset dosyalarını `tools/pemf_gui/resources/{icons,images,styles,templates}`'e kopyalar (hedef `base_dir = Path(__file__).parent`'a göre — kök `pemf_gui/` DEĞİL) |
| `e2e_smoke.py` | Uçtan uca duman testi — gerçek backend'i izole alt-portta (8123, `PEMF_E2E_PORT`) ayrı süreçte başlatır, `PEMF_SIMULATE=1` + geçici veri dizini. Denetim-regresyonlarını kilitler. Çalışan 8000'e DOKUNMAZ |
| `e2e_full.py` | TAM uçtan uca test — `e2e_smoke` denetim-regresyonlarını kilitlerken bu betik **KULLANICI AKIŞLARINI** sınar: hasta CRUD + sayfalama, seans yaşam-döngüsü (STM 1-7 / ESP slot 8 / 8-bobin) ⚠️ 2026-09-11'de topoloji güncellendi; `PEMF_ESP_ENABLED=1` ile koşar ki ESP'ye dönüş yolu da kapsansın, bobin kontrolü, canlı telemetri (WS), geçmiş + KPI, üç profil (ev sahibi/veteriner/araştırma) kapsamları. İzole alt-port (8124, `PEMF_E2E_PORT`) + geçici `PEMF_DATA_DIR`; 8000'e DOKUNMAZ |
| `kurtarma.py` | **Felaket kurtarma** — donanım arızasından sonra yedekleri yeni makinede açar. `--kodu-goster` / `--zarf … --kod … --yaz`. **Sahada** (Python yok) launcher'ın kurduğu EXE'nin alt komutu: `PEMF_Backend.exe --kurtarma …` (D2.75; komut `utils.backup_recovery.kurtarma_komutu`). Bkz. [RUNBOOK](../docs/RUNBOOK.md) |
| `destek_paketi.py` | **Destek paketi üretici** (CLI) — backend çökmüşken de çalışır; PII-maskeli `.zip` üretir (`apps/backend/utils/support_bundle`). Arayüzdeki `POST /api/support/bundle` düğmesinin backend-ayakta-değilken alternatifi. `--cikti` / `--veri-dizini` / `--log-tavani`. **Sahada** (Python yok) launcher'ın kurduğu EXE'nin alt komutu: `PEMF_Backend.exe --destek-paketi …` (D6.47 · Y32). Bkz. [RUNBOOK](../docs/RUNBOOK.md) |

> ESP simülatörü burada değil — ESP sim [`../apps/backend/servers/api_server.py`](../apps/backend/servers/README.md) içindeki `PEMF_SIMULATE` yoludur.

## ⚠️ Not
- Backend'in STM portu `PEMF_STM_PORT` ile seçilir: verilmezse sabit COM10, `auto` ST-Link oto-algılama, `socket://127.0.0.1:5100` simülatör (`apps/backend/utils/stm32_transport.py` → `serial_for_url`). `stm32_simulator.py --set-port` yalnız bu bilgiyi yazar, ayar UYGULAMAZ. Reconnect/self-heal testi: memory [[pemf-reconnect-selfheal]].

---
İlgili: [tests/](../tests/README.md) · [firmware/](../firmware/README.md) · [apps/backend/utils/stm32_transport](../apps/backend/utils/README.md)
