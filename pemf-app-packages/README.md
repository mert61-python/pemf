# pemf-app-packages/ — Güncelleme-Sunucusu Hazırlık Alanı (manifest + base.zip)

Launcher / güncelleme-sunucusunun tükettiği **manifest + runtime paketi**. Buradaki dosyalar GitHub
`mert61-python/pemf-update` release'lerine yüklenir.

## İçerik
| Dosya | İçerik |
|---|---|
| `base-app.zip` | **Katmanlı paket — app katmanı** (~71 MB): istemci kodu; her sürümde iner (client ≥1.9.13). [`../build_tools/make_base_zip.py`](../build_tools/README.md) çıktısı |
| `base-deps.zip` | **Katmanlı paket — deps katmanı** (~1.46 GB): torch/AI bağımlılıkları + çekirdek `cat_organ` modeli; yalnız bağımlılıklar değişince yenilenir |
| `base.zip` | **Tek-parça runtime** (~1.5 GB, `_internal/ai_models` hariç) — ESKİ launcher'lar (≤1.9.12) için DURUR, silme (bkz. manifest `_layers_note`). [`../build_tools/make_base_zip.py`](../build_tools/README.md) çıktısı |
| `home.zip` | `home` profil model paketi (~318 MB) — [`../build_tools/make_model_zip.py`](../build_tools/README.md) çıktısı (`vet.zip`/`research.zip` yalnız yayında tutulur) |
| `manifest.json` | Şema v2 (+ v1 geriye-uyum). Anahtarlar: `launcher` (version/`installer_url`/sha256/size — self-update), `layers.win-x64.{app,deps,rollout}` (client ≥1.9.13 **birincil**), `runtimes.win-x64` **+** eski `base` (≤1.9.12 geri-uyum), `models`/`profiles` `{home,vet,research}`, `mobile.android` (APK oto-güncelleme). Tüm URL'ler sürüm-başına `mert61-python/pemf-update` etiketine |

## Yayın (özet — tam akış [`../BUILD.md`](../BUILD.md) §6)
```powershell
# PAKETLER surum-basina etikete (⚠️ v1.8.0 DEGIL — 2. tur denetimi [3.4]: 1.9.16'dan beri
# manifest URL'leri surum-basina etikete yazilir; v1.8.0'a yuklenen paket 404 uretir).
gh release upload client-app-v<sürüm> -R mert61-python/pemf-update base-app.zip
# YALNIZ manifest.json SABIT adrese (launcher hep buradan okur):
gh release upload client-app-v1.8.0 -R mert61-python/pemf-update --clobber manifest.json
```

## ⚠️ Dikkat
- **çift-base gotcha:** `base.zip` sha256/size'ı manifest'te **İKİ yere** yazılmalı — `runtimes.win-x64` (6-boşluk girinti) **VE** `base` (4-boşluk girinti). `replace_all` sadece birini yakalar.
- **`--clobber` kesme tuzağı:** önce eski asset'i siler; 1.3 GB yüklemesini yarıda kesme → taze kurulumlar bozulur. Kesildiyse `gh release view --json assets` ile doğrula.
- `manifest.json`'ı base.zip'ten **sonra** yükle (sha eşleşsin).

---
İlgili: [BUILD.md §6 (yayın)](../BUILD.md) · [make_base_zip](../build_tools/README.md) · [scripts/make_manifest](../scripts/README.md) · [launcher/](../launcher/README.md)
