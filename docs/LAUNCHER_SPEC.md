# PEMF Vet Client — Launcher Sözleşmesi (yeniden yazım)

**Durum:** taslak · **Karar tarihi:** 2026-07-21
**Kapsam:** Windows + macOS + Linux, **tek kaynak** · **Geriye dönük uyumlu**

## Neden yeniden yazılıyor

Mevcut launcher (`PEMFVetClient-Setup.exe`, `.deb`, `.AppImage`, `.rpm` —
`pemf-update/releases/tag/launcher-v1.8.0`) **kaynağı elimizde olmayan** bir bileşen.
`mert61-python/pemf` deposunun hiçbir commit'inde, hiçbir branch'inde izi yok
(`git log --all --diff-filter=AD` → sıfır sonuç; `Cargo.toml` / `.rs` / `tauri.conf.json` /
`.nsi` / Electron bağımlılığı yok). Kaynağı olmayan bir bileşen düzeltilemez, imzalanamaz,
yeni platforma taşınamaz — macOS'in tıkanma sebebi tam olarak budur.

## Teknoloji

**Tauri (Rust).** Gerekçe: mevcut launcher ~2.9 MB (NSIS) ve release notunda "zip crate"
geçiyor → zaten Rust. Tauri bundler tek koddan `.exe` / `.dmg` / `.deb` / `.AppImage` /
`.rpm` üretir — bugün yayında olan varlık kümesinin **tamamı**.

## Akış

```
manifest.json indir  →  profil seç (home/vet/research)  →  platforma uygun base + profil zip indir
   →  SHA256 doğrula  →  aç  →  backend'i başlat  →  /api/health bekle  →  tarayıcıyı aç
```

## Model yerleşimi — EN KRİTİK SÖZLEŞME

`utils/model_downloader.py::_candidate_model_roots()` model arama köklerini şu öncelikle çözer:

| # | Kök | Platform |
|---|---|---|
| 1 | `$PEMF_AI_MODELS_DIR` | hepsi |
| 2 | `%PROGRAMDATA%\PEMF_GUI\ai_models` | **yalnız Windows** (`PROGRAMDATA` yoksa atlanır) |
| 3 | `get_app_data_directory()/.ai_models` | hepsi |
| 4 | proje-yanı `release_assets/ai_models` | geliştirme |
| 5 | PyInstaller bundle içi `ai_models` | gömülü build |

`find_installed_model("ai_hub/em_kedi/X.onnx")` bu köklerin altında `<kök>/ai_hub/em_kedi/X.onnx`
arar. Profil zip'lerinin içeriği tam olarak `ai_models/ai_hub/<model>/<dosya>` biçiminde
(doğrulandı: `vet.zip` → `ai_models/ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx`).

> **Karar:** Launcher, backend'i başlatırken **`PEMF_AI_MODELS_DIR=<kurulum>/ai_models`**
> ortam değişkenini verir. Kök #1 en yüksek öncelikli ve **üç platformda da aynı** çalışır;
> kök #2 macOS/Linux'ta hiç yok. Böylece Windows'un mevcut ProgramData düzenine
> dokunmadan mac/Linux çalışır.

**Yükseltme kuralı:** Windows'ta `%PROGRAMDATA%\PEMF_GUI\ai_models` doluysa launcher onu
kullanır, profil paketini **yeniden indirmez** (2 GB'a kadar gereksiz indirme olurdu).

## Base paketi — modeller GÖMÜLMEZ

Yayındaki `base.zip` 1.29 GB / 6191 dosya ve **sıfır** `ai_models` girdisi içeriyor
(doğrulandı). Modeller yalnızca profil paketlerinden gelir. `PEMF_Backend_onedir.spec`
içindeki `PEMF_EMBED_MODELS` bayrağı bu hizayı korur (`0` = gömme).

Gömülseydi: kullanıcı aynı 2.1 GB'ı iki kez indirirdi ve profil ayrımı anlamsızlaşırdı
(vet kullanıcısında research modelleri de bulunurdu).

## manifest sözleşmesi

Bugünkü format (v1) ad-hoc platform anahtarları kullanıyor: `base`, `base_linux`.
`pemf-app-packages/publish.ps1` bu tasarımın bir kez ısırdığını kayda geçmiş:

> *"base-linux.zip … Eksikse Linux client sessizce Windows base.zip indirir → backend hiç çalışmaz."*

**v2 hedefi** — açık platform anahtarları, **eksik anahtarda sessiz fallback YOK, sert hata**:

```json
{
  "schema": 2,
  "version": "1.8.0",
  "runtimes": {
    "win-x64":   { "url": "…", "sha256": "…", "size": 0 },
    "linux-x64": { "url": "…", "sha256": "…", "size": 0 },
    "mac-arm64": { "url": "…", "sha256": "…", "size": 0 }
  },
  "models": {
    "home": { "url": "…", "sha256": "…", "size": 0 },
    "vet":  { "url": "…", "sha256": "…", "size": 0 },
    "research": { "url": "…", "sha256": "…", "size": 0 }
  }
}
```

Launcher **iki formatı da okur** (v1 → sahadaki v1.8.0 kurulumları bozulmasın).

## Backend başlatma

| Değişken | Değer |
|---|---|
| `PEMF_AI_MODELS_DIR` | `<kurulum>/ai_models` |
| `PEMF_DATA_DIR` | platform app-data (aşağıda) |
| `PEMF_API_PORT` | `8000` (varsayılan; meşgulse artır) |

Hazırlık kontrolü: `GET /api/health` (`servers/system_router.py`). 200 dönene kadar bekle,
sonra tarayıcıyı aç. Zaman aşımında backend log'unu göster — sessizce başarısız olma.

`get_app_data_directory()` (`utils/path_utils.py`) zaten üç platformu doğru çözüyor:
Windows `%APPDATA%\PEMF_GUI`, macOS `~/Library/Application Support/PEMF_GUI`,
Linux `~/.local/share/PEMF_GUI`. **Launcher bunu taklit etmeli, yeniden icat etmemeli.**

## Güvenlik gereksinimleri

1. **SHA256 zorunlu.** Doğrulama başarısızsa kur**ma** ve dosyayı sil.
2. **HTTPS + host pinleme.** `servers/update_manager.py::_ALLOWED_UPDATE_HOSTS` aynı
   listeyi kullanıyor; launcher da aynısını uygulamalı (manifest ele geçse bile keyfi
   sunucudan çalıştırılabilir kod indirilmesin).
3. **Zip-slip koruması.** Açarken her girdinin hedef yolu kurulum kökünün altında kalmalı
   (`..` ile dışarı çıkan girdi reddedilir).
4. **İmzalama.** macOS: Developer ID + notarization. Windows: Authenticode.
   Sertifikalar **yalnız CI Secrets'ta** — working tree'de değil (bkz. `.gitignore`).

## Paketleme hedefleri

| Platform | Çıktı | Runner |
|---|---|---|
| Windows | `PEMFVetClient-Setup.exe` | `windows-latest` |
| macOS | `PEMFVetClient.dmg` (arm64) | `macos-14` |
| Linux | `.deb` · `.AppImage` · `.rpm` | `ubuntu-22.04` |

## Açık sorular

- [ ] Sahadaki Windows kurulumunun **kurulum dizini** nedir? (eski launcher kaynağı yok →
      kurulu bir makineden tespit edilmeli; yükseltmenin veri kaybetmemesi buna bağlı)
- [ ] Eski launcher backend'i **servis** olarak mı kaydediyor, yoksa süreç olarak mı
      başlatıyor? (`scripts/install_backend_service.ps1` + NSSM mevcut)
- [ ] `.dmg` içinde backend'in ilk açılışta karantina (`com.apple.quarantine`) sorunu —
      notarization kapsamı base paketini de kapsamalı mı?
