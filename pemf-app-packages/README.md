# pemf-app-packages/ — Güncelleme-Sunucusu Hazırlık Alanı (manifest + base.zip)

Launcher / güncelleme-sunucusunun tükettiği **manifest + runtime paketi**. Buradaki dosyalar GitHub
`mert61-python/pemf-update` release'lerine yüklenir.

## İçerik
| Dosya | İçerik |
|---|---|
| `base.zip` | win-x64 istemci runtime'ı (~1.29 GB) — [`../build_tools/make_base_zip.py`](../build_tools/README.md) çıktısı (`_internal/ai_models` hariç) |
| `manifest.json` | Şema v2 (+ v1 geriye-uyum). Anahtarlar: `launcher` (version/`installer_url`/sha256/size — self-update), `runtimes.{win-x64,mac-arm64,linux-x64}`, `models`/`profiles` `{home,vet,research}`, eski `base`/`base_mac`/`base_linux`. Tüm URL'ler `mert61-python/pemf-update` release'lerine |

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
