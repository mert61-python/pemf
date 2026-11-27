# .github/ — Sürekli Entegrasyon (CI) & Dependabot

GitHub Actions iş akışları + bağımlılık güncelleme. Her workflow kendi başlık yorumunda kendini belgeler.

## Dosyalar
| Yol | Görev |
|---|---|
| `dependabot.yml` | Haftalık + TOPLU (ekosistem başına tek sürüm PR'ı) pip · npm (`apps/ui`, `apps/web`) · cargo · github-actions — Y3 pinleri dışlı (CT2 e) |
| `workflows/tests.yml` | **Kritik-yol** (push/PR; yalnız `windows-latest` — Y320; Python **3.10.2** = ürün yaması, CT2 b): `backend` (pytest — push'ta **hızlı küme**, production-hardening / main push'u + gece + elle `kip=tam` **tam süit + paket toplamı**; fark kapsamı %100 her kipte — CT2 c) · `launcher` (cargo; hızlı kipte launcher/ değişmediyse atlanır) · `firmware` (STM32 Arm GNU 12.3.rel1 derlemesi + koşum takımı gcc/gcov — CT2 f) · `sir-taramasi` · `ozet` (dal başına tek tablo — CT2 d). Gerekli işler: `scripts/ci_sozlesmesi.json` → [`../tests/`](../tests/README.md) |
| `workflows/lint.yml` | Ruff `F+E9+I` kontrolü + bloklamayan format kontrolü |
| `workflows/frontend.yml` | **apps/ui/** (mobil+web istemci): tsc + jest-expo — yol filtreli (`apps/ui/**`) |
| `workflows/site.yml` | **apps/web/** (ödeme sitesi): check:legal + oxlint + tsc + vitest + build — yol filtreli; **Node 22 şart** |
| `workflows/security.yml` | `pip-audit` (sevk kilidi + test bağımlılıkları) + `npm-audit` (ui · web · DEMA) **BLOKLAYICI** — yalnız `scripts/audit_borcu.json` gerekçeli listesi yoksayılır (cargo audit deseni; bilinen borç cırcırı, [SAHİBE] yükseltme); haftalık cron (CT2 e) |
| ~~`workflows/linux-backend.yml`~~ · ~~`workflows/mac-backend.yml`~~ | **KALDIRILDI** (Y320, 2026-11-26): CI yalnız Windows ürün hattı — Linux / macOS backend paketleme kapsam dışı (Docker da silindi, Y317). Geri: `git log --diff-filter=D -- .github/workflows/linux-backend.yml` ile son sürüm bulunur. Kapı: `tests/test_ci_workflow_gate.py` (Y320) |
| `workflows/launcher.yml` | Tauri launcher **yalnız Windows** paketi (etiket `launcher-v*` / elle; Y320 · CT2 g — macOS / Linux matrisi kaldırıldı) |
| ~~`workflows/upload-testflight.yml`~~ | **ARŞİVLENDİ** (S-4B.4, 2026-10-11): test süitini koşturmadan sırlarla TestFlight'a yükleyen, Y30 DIŞI dağıtım yolu; dalı 2026-08-18'de arşivlenmişti, yüklediği `.ipa` izlenmiyordu. Geri: `git show 83ee5d12:.github/workflows/upload-testflight.yml`. Kapı: dış dağıtım işi pytest/Y30 işine `needs:` ile bağlı olmalı (`tests/test_ci_DIS_DAGITIM_isi_TEST_onkosullu_S4B4.py`) |
| `workflows/supabase-ping.yml` | **Supabase hareketsizlik koruması**: günlük cron (`03:17 UTC`) `resolve_device` RPC'siyle Free-plan projeyi uyanık tutar (~7-gün otomatik durdurmayı önler). 3 denemede de 5xx/540 → iş KIRMIZI = "girişler çökmek üzere" erken uyarısı. Yalnız varsayılan dalda koşar |
| `workflows/gece.yml` | **Gece tam koşu** (cron 00:30 UTC + elle): `tests.yml`'i `kip: tam` ile çağırır — tam süit + gerçek modeller + kapsam raporu eseri. Gerekli DEĞİL (yayın commit'ine durum yazmaz); kırmızısı yayın betiğinde UYARI (CT2 c) |
| `workflows/codeql.yml` | **CodeQL** Python + JavaScript/TypeScript, haftalık (CT2 e) |

## Not
- ⚠️ **Workflow'lar YALNIZ kök `.github/` altından okunur** (tek-depo, 2026-08-18): alt dizine
  (`apps/ui/.github/` gibi) konan yapılandırmayı GitHub sessizce YOK SAYAR.
  `tests/test_ci_workflow_gate.py` bunu kilitler.
- macOS/imzalama sırları GitHub **Secrets**'tadır — geliştirme makinesindeki `apple-mac-cert/` yerel kopyaları (gitignore'lu, git'te izlenmez) CI kullanmaz.
- Windows launcher **yerel** derlenip elle yayınlanır (self-update); `launcher.yml` yalnız Windows (Y320). Yayın betikleri (`publish_release.ps1`, `katmanli_yayin_hazirla.ps1`) Y30'dan sonra **uç commit'in CI'ı yeşil değilse DURUR** (`scripts/yayin_ci_kapisi.ps1` → `scripts/ci_durum.py`, CT2 a). Her `uses:` tam SHA (yorumda sürüm, CT2 e).

---
İlgili: [tests/](../tests/README.md) · [launcher/](../launcher/README.md) · [BUILD.md](../BUILD.md)
