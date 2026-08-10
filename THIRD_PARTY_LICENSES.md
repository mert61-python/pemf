# Üçüncü Taraf Lisansları

PEMF Vet, aşağıdaki açık kaynak bileşenleri içerir. Her bileşen kendi lisansı altında dağıtılır;
telif hakları ilgili sahiplerine aittir.

⚠️ **Bu dosya atıf (NOTICE) yükümlülüğü içindir.** Kopyleft lisansların (AGPL/GPL) kaynak açma
yükümlülüğünü KARŞILAMAZ — bkz. [`docs/AGPL-KARARI.md`](docs/AGPL-KARARI.md).

## Dağıtılan pakette tespit edilen bileşenler

Aşağıdaki liste `pemf-app-packages/base-deps.zip` içindeki `dist-info/METADATA` dosyalarından
ÜRETİLMİŞTİR (elle yazılmamıştır). PyInstaller çoğu paketin metadata'sını ayıkladığından liste
tam envanter DEĞİLDİR; tam liste `build_tools/myenv-requirements.txt` dosyasındadır.

| Paket | Sürüm | Lisans |
|---|---|---|
| `attrs` | 26.1.0 | belirtilmemiş |
| `click` | 8.3.3 | belirtilmemiş |
| `cryptography` | 50.0.0 | belirtilmemiş |
| `curl_cffi` | 0.15.0 | belirtilmemiş |
| `h2` | 4.3.0 | The MIT License (MIT) |
| `imageio_ffmpeg` | 0.6.0 | BSD-2-Clause |
| `importlib_metadata` | 9.0.0 | belirtilmemiş |
| `keyring` | 25.7.0 | belirtilmemiş |
| `lazy_loader` | 0.5 | belirtilmemiş |
| `librosa` | 0.11.0 | ISC |
| `llvmlite` | 0.44.0 | BSD |
| `markupsafe` | 3.0.3 | belirtilmemiş |
| `msgpack` | 1.1.2 | belirtilmemiş |
| `numba` | 0.61.2 | BSD |
| `onnx` | 1.15.0 | Apache License v2.0 |
| `pooch` | 1.9.0 | belirtilmemiş |
| `pydantic` | 2.13.4 | belirtilmemiş |
| `pyreadline3` | 3.5.4 | BSD |
| `soundfile` | 0.13.1 | BSD 3-Clause License |
| `sqlcipher3` | 0.6.2 | belirtilmemiş |
| `torch` | 2.1.2+cpu | BSD-3 |
| `torchvision` | 0.16.2+cpu | BSD |
| `tqdm` | 4.67.3 | MPL-2.0 AND MIT |
| `ultralytics` | 8.4.47 | AGPL-3.0 |
| `websockets` | 15.0.1 | BSD-3-Clause |

## ⚠️ Kopyleft uyarısı

`ultralytics` **AGPL-3.0** ile lisanslıdır ve kapalı kaynak, ücretli bir üründe dağıtılması
kaynak açma yükümlülüğü doğurur. Durum tespiti, kullanım haritası ve seçenekler:
[`docs/AGPL-KARARI.md`](docs/AGPL-KARARI.md). Bu madde **açıktır ve karar beklemektedir**.

Ultralytics'in önceden eğitilmiş model ağırlıkları da AGPL kapsamındadır; kütüphaneyi
kaldırmak tek başına ağırlık lisansı sorusunu çözmeyebilir.

---
Bu dosya `scripts/` altındaki bir üreticiyle değil, denetim sırasında paketten okunarak
oluşturulmuştur. Paket bileşenleri değişince yeniden üretilmelidir
(bkz. `tests/test_license_surface.py` — yeni kopyleft bağımlılıkta test düşer).
