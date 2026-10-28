# scripts/ — Operasyon & Yardımcı Scriptler (PowerShell / Python)

Build, yayın, servis-kurulum, gateway/hotspot ve kaldırma scriptleri.

## Firmware (STM32 + ESP-S3)
| Script | Görev |
|---|---|
| `firmware_derle.py` | Her iki firmware'i de **gerçekten derler** (arm-none-eabi-gcc + arduino-cli), CubeIDE/Arduino IDE açmadan. ⚠️ Bağlanan ELF'te `_printf_float` sembolünü **ARAR**; yoksa derlemeyi DÜŞÜRÜR — o sembol olmadan tüm STM sensör telemetrisi sessizce ölür (2026-09-11 saha arızası). ⚠️ Bayrağı KENDİ vermez: CubeIDE'nin üreteceği ikiliyi ölçmek için |
| `stm_workspace_kopyala.py` | Masaüstüne temiz CubeIDE workspace'i çıkarır — derleme artığı TAŞIMAZ (bayat `.elf` flaşlama kazasının kökü) ve kaynağın protokol aşamasını DOĞRULAR: `NUM_COILS=7`, `unipolar_maskesi` (121 bayt), `Coil_KipUygula`, `&_printf_float`. Aynı gün yeniden koşumda eski kopyayı SİLMEZ, `<ad>_yedek_<HHMMSS>`e taşır (yedeği CubeIDE'de açmayın/flaşlamayın) |
| `stm_firmware_kimligi.py` | Karttaki firmware'in açılış banner'ını okur — `7-ch` mi `5-ch` mi (yanlış ikili flaşlandı mı?) |
| `stm_yak.py` | **STM32 güvenli reflash — CLI yüzü.** ⚠️ Mantık burada DEĞİL: [`../apps/backend/utils/stm_yakma.py`](../apps/backend/utils/README.md). Sevk edilen pakete `scripts/` altından yalnız altı `.ps1` girer (`build_tools/make_base_zip.py::ADD_SCRIPTS`), `scripts/*.py` **hiç gitmez** — mantık burada kalsaydı sahada hiç bulunmazdı |

## Build & yayın
| Script | Görev |
|---|---|
| `build_backend_exe.ps1` | **(Pipeline 1)** PyInstaller frozen backend → `../PEMF_BUILD/dist/PEMF_Backend`; env izole, headless-guard, taze web export |
| `check_headless_imports.py` | **Guard** — statik AST import-grafiği: headless backend'e Qt/GUI sızmadığını doğrular (kırmızıysa build durur) |
| `pyz_koruma_kapisi.py` | **(5. koruma kapısı, `build_backend_exe.ps1`)** — sevk EXE'nin PYZ arşivinde düz `ai_hub` bytecode'u KALMADIĞINI denetler. Önceki 4 kapı yalnız "diskte düz .py kaldı mı?" soruyordu; ölçülünce PYZ içinde 87 ai_hub girişi okunabilir bytecode olarak duruyordu (Cython koruma katkısı=0) → gerçek koruma bu kapıyla kanıtlanır (denetim 2026-08-28 #07) |
| `sevk_agaci_ai_hub_kapisi.py` | **(6. koruma kapısı, `build_backend_exe.ps1`)** — kaynaktaki HER `ai_hub` modülünün sevk ağacına girdiğini doğrular. `xai_tabular/ig_torch.py` adında "torch" geçtiği için torch-eleme filtresine takılıp üründe yalnız PYZ bytecode'u olarak yaşıyordu → yol-çıpasız filtrenin sessiz düşürmesini yakalar (denetim 2026-08-28 #07) |
| `make_manifest.py` | `../pemf-app-packages/manifest.json` üretir (sha256/size hesaplı) — elle düzenlemeyi bitirir |
| `publish_release.ps1` | GitHub release oluştur + asset yükle + `latest.json` güncelle (`-Branch exe\|mobil`) |
| `yayin_oncesi_suit.ps1` | **Y30 — yayın öncesi ZORUNLU tam süit** (`PEMF_CAPRAZ_KAYNAK_ZORUNLU=1` + `PEMF_GOLDEN_REQUIRED=1`, `-rfEs` — kırmızılar ve atlama nedenleri kısa özette); `publish_release.ps1` kimlik/ağdan ÖNCE çağırır, süit geçmezse yayın DURUR (atlama anahtarı yok). Kapı: `tests/test_yayin_oncesi_suit_Y30_D410.py` |
| `restore_assets.ps1` | Boş/yeni makinede depoyu çalışır kılar — yayınlardaki AI model ağırlıklarını (`home/vet/research.zip` + deps katmanından çekirdek `cat_organ`) indirip `../release_assets/ai_models`'a açar |
| `site_indirme_dogrula.py` | Yayın **SON adımı** — sitedeki (`apps/web/src/config.ts`) indirme bağlantıları GERÇEKTEN yayında mı (HTTP 200) doğrular; "yerelde üretildi ama sürümsüz adla yüklendi → 404" tuzağını yakalar |
| `check_changelog_surum.py` | Pre-commit kancası — `../versions.json` sürümleri `../CHANGELOG.md`'de geçmeden commit'i durdurur (CI testiyle birebir mantık) |

## Anahtar emaneti & kurtarma
| Script | Görev |
|---|---|
| `hasta_anahtari_emanet.py` | **Hasta verisi anahtarının makine-DIŞI emaneti** (escrow) + doğrulama. Saha DB'leri gerçekten şifreli (ölçüldü) ama açan anahtar tek bir yerde duruyordu — anakart/disk arızasında geçmiş açılamaz |
| `vault_emanet.py` | **HashiCorp Vault** üzerinde hasta-anahtarı emaneti (yedek) yönetimi. ⚠️ Vault uygulamanın ÇALIŞMA-ANI kaynağı DEĞİLDİR (sahip kararı 2026-09-13): backend hâlâ yerel `pemf_secrets.json` (DPAPI) okur; Vault yalnız makine-dışı kopyayı tutar |
| `model_butunluk.py` | **AI model bütünlüğü** — SHA256 manifesti üret / dağıtılan kopyayı doğrula. Ağırlıklar tek kaynakta durur (`release_assets/ai_models`) ama sahaya **kopyalanarak** gider (`%LOCALAPPDATA%\PEMF Vet Client\ai_models`) |

## Kurulum & kapılar
| Script | Görev |
|---|---|
| `bootstrap.ps1` | **SIFIR bir Windows makinesinde** tüm build+publish araç zincirini kurar (Node.js, Git, GitHub CLI, JDK 17, Inno Setup 6, Rust + cargo-tauri, MSVC C++ Build Tools) — portabilite |
| `install_hotspot_task.ps1` | `PEMF-Hotspot` **keep-alive görevini** kullanıcı kapsamında kurar/kaldırır. ⚠️ 2026-09-10'da `setup_services.ps1` içinden ayrıldı: launcher ile kurulan makineler görevi HİÇ almıyordu, hotspot ağ değişiminde/yeniden başlatmada düşüyordu |
| `responsive_kapisi.py` | **Responsive kapısı** — görünüm-alanı taşması + dokunma hedefi (WCAG 2.5.8) + kritik eleman görünürlüğü. `.github/workflows/site.yml` bunu CI'da koşturur. ⚠️ Ölçüm CDP `Emulation.setDeviceMetricsOverride` ile; `--window-size` tek başına düzen görünüm alanını DEĞİŞTİRMEZ |
| `lisans_envanteri_uret.py` | `THIRD_PARTY_LICENSES.md` üreteci — atıf (NOTICE) envanterini yeniden üretir; `--kontrol` yalnız FARKI bildirir (çıkış 1) |
| `urun_senaryolari.py` | **SEVK EDİLEN EXE üzerinde ürün senaryosu ölçümü** — test süiti DEĞİL, onun yerine de geçmez. Süit "fonksiyon doğru mu", bu betik "sevk edilen ikili, gerçek diskte, gerçek açılış sırasıyla doğru mu" diye sorar (2026-09-13: birim testler YEŞİLKEN ürün hasta geçmişini kaybediyordu) |

## Servis kurulumu (klinik/sunucu)
| Script | Görev |
|---|---|
| `setup_services.ps1` | Dağıtılmış yerleşimde üretim kurulumu — `{app}`'ten backend+mosquitto servisleri; `-Mode device\|server\|staging`, `-Uninstall`; Inno `.iss` çağırır |
| `install_backend_service.ps1` | **İkinci desteklenen kurulum yolu** (A-11; sahadaki yol launcher'dır): `PemfBackend`'i NSSM Windows servisi olarak kurar (frozen EXE'yi tercih eder); servis ortamı `deploy\<Mode>.env` profilinden — `setup_services.ps1` ile aynı ayrıştırma (at-rest şifreleme, veri kökü, STM portu, izinli adlar); profil yoksa servise dokunmadan durur; SCM `depend=` YOK; tünel yalnız `-EnableTunnel` ile |
| `install_mosquitto.ps1` / `install_mosquitto_service.ps1` | Mosquitto broker kur/yapılandır (gateway) / bağımsız oto-başlar servis (offline) |

## Gateway / hotspot (LattePanda klinik mini-PC)
| Script | Görev |
|---|---|
| `setup_gateway.ps1` | Boot: Windows Mobile Hotspot'u aç, Mosquitto'yu garanti et, GUI başlat |
| `start_hotspot.ps1` | `PEMF-Gateway` Wi-Fi hotspot'unu başlat (mobil istemciler katılır; ESP kartları 2026-09-11'de söküldü); logon Scheduled Task |

## Kaldırma / teardown (KVKK-farkında)
| Script | Görev |
|---|---|
| `pemf_footprint.ps1` | **Tek-kaynak** — PEMF'in oluşturduğu her artefakt (servis/task/firewall/registry/data); tüm kaldırıcılar bunu tüketir |
| `pemf_teardown.ps1` | Birleşik teardown motoru (`pemf_footprint.ps1` tüketir; backend/tüm-kapsamlar) |
| `pemf_uninstall_all.ps1` | Bağımsız tam kaldırıcı — üç installer'ın izini tek komutta siler (destek/sıfırlama + KVKK kanıtı) |

## Geliştirici araçları
| Script | Görev |
|---|---|
| `analyze_project.py` | AST-tabanlı proje/import analizi |
| `soak_publish_5hz_8coil.py` | ⛔ Test: sentetik 8-bobin MQTT sensör yükü — ESP kapalıyken (varsayılan) hiçbir canlı yolu ölçmez (`docs/VERIFICATION.md` §7); yerine `scripts/soak_http_ws.py` |
| `soak_http_ws.py` | Soak — **HTTP + WebSocket** yolu (VERIFICATION §7'nin bugünkü mimariye uyarlaması) |
| `saha_test_html_uret.py` | `docs/SAHA-TEST-LISTESI.md` → `docs/saha-test-listesi.html` içindeki `const VERI` bloğunu üretir (liste İKİ dosyada elle tutuluyordu, ayrışıyordu) |
| `b_kaydi_topla.py` | `[BKAYIT]` **seri-port toplayıcı** — S3'ün B kaydını masaüstüne 2 kolonlu CSV yazar (alan + zaman); PWM başlayınca başlar, bitince durur (sahip isteği 2026-09-09) |
| `xai_batch_rapor.py` | **Mod-2 toplu XAI raporu** — klasör/dosya tara → modülün tek-kaynak explain fonksiyonu → PNG/JPG + `summary.csv` + `index.html` (`--pdf` ŞİMDİLİK KAPALI — İG-9.50). ⚠️ Canlı döngüye ağır XAI asla girmez; bu araç seans-SONRASI/araştırma yüzeyidir |
| `ai_service_xai_smoke.ps1` | `ai_service` **XAI smoke** — cu128 imaj-içi doğrulama (GPU makinesinde, YAYIN ÖNCESİ): imajı build edip explain ucunu gerçek istekle sınar |
| `ai_service_xai_smoke_istek.py` | Yukarıdakinin **HOST tarafı isteği** — sentetik sıcak-merkezli termal görüntü → `/infer/thermal` `explain=true`; `xai_image_base64`in tekdüze OLMADIĞINI doğrular |
| `ai_service_scratch_smoke_istek.py` | `ai_service` **scratch smoke** (HOST'tan) — gerçek CONTROL-24H TIF → `/infer/scratch`; kapanma metriklerini sahip referanslarıyla toleranslı karşılaştırır |
| `supabase_sql.py` | Supabase'e SQL çalıştır + canlı sorgu/kilit izleme (Management API + PAT); şema özeti/göç kaydı — panele elle-yapıştırma yerine (⚠️PAT git-dışı) |

## Kabin / AI kalibrasyon
| Script | Görev |
|---|---|
| `kabin_marker_a4.py` | **A4 basılabilir ArUco marker sayfası** — kabin kalibrasyonu (DICT_5X5_50 · ID 0 · kenar 15,0 cm), 300 DPI. ⚠️ Eski PNG DPI taşımadığı için yazıcının "sayfaya sığdır"ı ölçeği bozuyor, mm/px ve 3B konum yanlış çıkıyordu; %100 basılmalı (alttaki cetvel çubuğu basımı doğrular). [`../ai_hub/KABIN_KURULUM_KILAVUZU.md`](../ai_hub/KABIN_KURULUM_KILAVUZU.md) bunu çağırır (`--masaustu`) |

## ⚠️ Dikkat
- Cihaz-güvenliği: teardown/uninstall bobinleri **her kill'den önce** E-stop'lar (regresyon yapma).
- `pemf_footprint.ps1` tek-kaynaktır — yeni artefakt eklersen önce burayı güncelle.

---
İlgili: [BUILD.md](../BUILD.md) · [deploy/](../deploy/README.md) · [build_tools/](../build_tools/README.md) · [launcher/](../launcher/README.md)
