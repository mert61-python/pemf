# .github/ — Sürekli Entegrasyon (CI) & Dependabot

GitHub Actions iş akışları + bağımlılık güncelleme. Her workflow kendi başlık yorumunda kendini belgeler.

## Dosyalar
| Yol | Görev |
|---|---|
| `dependabot.yml` | Haftalık pip + actions güncellemesi (AI bağımlılıkları pinli) |
| `workflows/tests.yml` | **Kritik-yol pytest** (push/PR; `PEMF_SIMULATE:""`, coverage) → [`../tests/`](../tests/README.md) |
| `workflows/lint.yml` | Ruff `F+E9+I` kontrolü + bloklamayan format kontrolü |
| `workflows/security.yml` | `pip-audit` (çekirdek + dağıtılan AI ağacı), haftalık cron, bloklamaz |
| `workflows/linux-backend.yml` | PyInstaller onedir → `base-linux.zip` (tag `backend-linux-v*`) |
| `workflows/mac-backend.yml` | `build_mac.sh` (`macos-14`, arm64) → `base-mac.zip` + Rust E2E artifact testi |
| `workflows/launcher.yml` | Tauri launcher (mac/Win/Linux); macOS **kod-imzala + notarize/staple** (`APPLE_*` secrets) |
| `workflows/upload-testflight.yml` | `xcrun altool` ile IPA → TestFlight (branch `upload-testflight`) |

## Not
- macOS/imzalama sırları GitHub **Secrets**'tadır — repo ağacındaki [`../apple-mac-cert/`](../apple-mac-cert/README.md) yerel kopyaları CI kullanmaz.
- Windows launcher **yerel** derlenip elle yayınlanır (self-update); CI Win launcher'ı `launcher.yml`'de opsiyoneldir.

---
İlgili: [tests/](../tests/README.md) · [launcher/](../launcher/README.md) · [BUILD.md](../BUILD.md)
