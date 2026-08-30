# scripts/ — Operasyon & Yardımcı Scriptler (PowerShell / Python)

Build, yayın, servis-kurulum, gateway/hotspot ve kaldırma scriptleri.

## Build & yayın
| Script | Görev |
|---|---|
| `build_backend_exe.ps1` | **(Pipeline 1)** PyInstaller frozen backend → `../PEMF_BUILD/dist/PEMF_Backend`; env izole, headless-guard, taze web export |
| `check_headless_imports.py` | **Guard** — statik AST import-grafiği: headless backend'e Qt/GUI sızmadığını doğrular (kırmızıysa build durur) |
| `pyz_koruma_kapisi.py` | **(5. koruma kapısı, `build_backend_exe.ps1`)** — sevk EXE'nin PYZ arşivinde düz `ai_hub` bytecode'u KALMADIĞINI denetler. Önceki 4 kapı yalnız "diskte düz .py kaldı mı?" soruyordu; ölçülünce PYZ içinde 87 ai_hub girişi okunabilir bytecode olarak duruyordu (Cython koruma katkısı=0) → gerçek koruma bu kapıyla kanıtlanır (denetim 2026-08-28 #07) |
| `sevk_agaci_ai_hub_kapisi.py` | **(6. koruma kapısı, `build_backend_exe.ps1`)** — kaynaktaki HER `ai_hub` modülünün sevk ağacına girdiğini doğrular. `xai_tabular/ig_torch.py` adında "torch" geçtiği için torch-eleme filtresine takılıp üründe yalnız PYZ bytecode'u olarak yaşıyordu → yol-çıpasız filtrenin sessiz düşürmesini yakalar (denetim 2026-08-28 #07) |
| `make_manifest.py` | `../pemf-app-packages/manifest.json` üretir (sha256/size hesaplı) — elle düzenlemeyi bitirir |
| `publish_release.ps1` | GitHub release oluştur + asset yükle + `latest.json` güncelle (`-Branch exe\|mobil`) |
| `restore_assets.ps1` | Boş/yeni makinede depoyu çalışır kılar — yayınlardaki AI model ağırlıklarını (`home/vet/research.zip` + deps katmanından çekirdek `cat_organ`) indirip `../release_assets/ai_models`'a açar |
| `site_indirme_dogrula.py` | Yayın **SON adımı** — sitedeki (`pemf-vet-web/src/config.ts`) indirme bağlantıları GERÇEKTEN yayında mı (HTTP 200) doğrular; "yerelde üretildi ama sürümsüz adla yüklendi → 404" tuzağını yakalar |
| `check_changelog_surum.py` | Pre-commit kancası — `../versions.json` sürümleri `../CHANGELOG.md`'de geçmeden commit'i durdurur (CI testiyle birebir mantık) |

## Servis kurulumu (klinik/sunucu)
| Script | Görev |
|---|---|
| `setup_services.ps1` | Dağıtılmış yerleşimde üretim kurulumu — `{app}`'ten backend+mosquitto servisleri; `-Mode device\|server\|staging`, `-Uninstall`; Inno `.iss` çağırır |
| `install_backend_service.ps1` | `PemfBackend`'i NSSM Windows servisi olarak kur (frozen EXE'yi tercih eder; mosquitto'ya `depends`) |
| `install_mosquitto.ps1` / `install_mosquitto_service.ps1` | Mosquitto broker kur/yapılandır (gateway) / bağımsız oto-başlar servis (offline) |

## Gateway / hotspot (LattePanda klinik mini-PC)
| Script | Görev |
|---|---|
| `setup_gateway.ps1` | Boot: Windows Mobile Hotspot'u aç, Mosquitto'yu garanti et, GUI başlat |
| `start_hotspot.ps1` | `PEMF-Gateway` Wi-Fi hotspot'unu başlat (ESP bobinler katılır); logon Scheduled Task |

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
| `soak_publish_5hz_8coil.py` | Test: sentetik 8-bobin MQTT sensör yükü (ayarlanır Hz, soak testi) |
| `supabase_sql.py` | Supabase'e SQL çalıştır + canlı sorgu/kilit izleme (Management API + PAT); şema özeti/göç kaydı — panele elle-yapıştırma yerine (⚠️PAT git-dışı) |

## ⚠️ Dikkat
- Cihaz-güvenliği: teardown/uninstall bobinleri **her kill'den önce** E-stop'lar (regresyon yapma).
- `pemf_footprint.ps1` tek-kaynaktır — yeni artefakt eklersen önce burayı güncelle.

---
İlgili: [BUILD.md](../BUILD.md) · [deploy/](../deploy/README.md) · [build_tools/](../build_tools/README.md) · [launcher/](../launcher/README.md)
