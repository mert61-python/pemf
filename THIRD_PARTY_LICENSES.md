# Üçüncü Taraf Lisansları

PEMF Vet, aşağıdaki açık kaynak bileşenleri içerir. Her bileşen kendi lisansı altında dağıtılır;
telif hakları ilgili sahiplerine aittir.

⚠️ **Bu dosya atıf (NOTICE) yükümlülüğü içindir.** Kopyleft lisansların (AGPL/GPL) kaynak açma
yükümlülüğünü KARŞILAMAZ — bkz. [`docs/AGPL-KARARI.md`](docs/AGPL-KARARI.md).

## Araştırma veri kümeleri (atıf)

⚠️ **Bu bölüm ÜRETECİN yazdığı bölümün ÖNÜNDE durmalıdır.**
`scripts/lisans_envanteri_uret.py` dosyayı aşağıdaki başlıktan itibaren yeniden yazar;
bu bölüm oraya taşınırsa bir sonraki koşuda **sessizce silinir.**
Kapı: `tests/test_veri_kumesi_atfi.py`

Depo, `training_archive/ai_data/real_clinical_data/` altında üçüncü taraf araştırma
veri kümelerini yeniden dağıtır. Bunlar **üründe sevk edilmez** (donmuş eğitim arşivi),
ancak PUBLIC depoda bulundukları için atıf gerektirir:

| Veri kümesi | Kaynak | Not |
|---|---|---|
| MIT-BIH Arrhythmia Database | PhysioNet | İnsan EKG'si; transfer öğrenme için. Kaynağında kimliksizleştirilmiş |
| PhysioZoo (köpek · tavşan · fare EKG) | PhysioNet | Veteriner EKG referansı |
| Zenodo — "Paws in Pain" | Zenodo | Köpek ağrı değerlendirmesi (EKG'li) |

⚠️ **Hasta kimliği içermez** — ölçüldü: yalnız türetilmiş metrikler (`SDNN`, `RMSSD`,
`LF/HF`, `mag_field_*`, `temp_*`). Dizin adı (`real_clinical_data`) "sentetik olmayan
sinyal" anlamındadır, bu kliniğin hasta verisi değildir. Ayrıntı:
[`training_archive/ai_data/real_clinical_data/README.md`](training_archive/ai_data/real_clinical_data/README.md).

⚠️ **Ticari dağıtımdan önce** her kümenin güncel lisans koşulları (ticari kullanım,
yeniden dağıtım, atıf biçimi) hukukçuya doğrulatılmalıdır. Bu tablo bir kayıttır,
hukuki görüş değildir.

## Dağıtılan pakette tespit edilen bileşenler

Aşağıdaki liste **üretilmiştir** (`scripts/lisans_envanteri_uret.py`); elle
düzenlemeyin. Kaynaklar: `requirements.txt` (sevk edilen çalışma-zamanı
bağımlılıkları) + `pemf-app-packages/base-deps.zip` içindeki `dist-info/METADATA`.

⚠️ PyInstaller çoğu paketin metadata'sını ayıkladığı için sürüm/lisans alanları
pakette bulunamayan satırlarda doğrulanmış sabit tablodan gelir.

| Paket | Sürüm | Lisans |
|---|---|---|
| `albucore` | 0.0.24 | MIT License |
| `albumentations` | 2.0.8 | MIT License |
| `annotated-doc` | 0.0.4 | MIT |
| `anyio` | 4.13.0 | MIT |
| `attrs` | 26.1.0 | MIT |
| `audioread` | 3.1.0 | MIT |
| `captum` | 0.8.0 | BSD-3 |
| `celldetection` | 0.4.9 | Apache License, Version 2.0 |
| `certifi` | 2026.4.22 | MPL-2.0 |
| `cffi` | 2.0.0 | MIT |
| `charset-normalizer` | 3.4.7 | MIT |
| `click` | 8.3.3 | BSD-3-Clause |
| `cloudpickle` | 3.1.2 | BSD-3-Clause |
| `colorama` | 0.4.6 | BSD License |
| `coloredlogs` | 15.0.1 | MIT |
| `contourpy` | 1.3.2 | BSD 3-Clause License |
| `cryptography` | 50.0.0 | Apache-2.0 OR BSD-3-Clause |
| `curl-cffi` | 0.15.0 | MIT |
| `cycler` | 0.12.1 | Copyright (c) 2015, matplotlib project |
| `decorator` | 5.3.1 | BSD-2-Clause |
| `exceptiongroup` | 1.3.1 | MIT License |
| `fastapi` | — | MIT |
| `filelock` | 3.29.0 | MIT |
| `flatbuffers` | 25.12.19 | Apache 2.0 |
| `fonttools` | 4.63.0 | MIT |
| `fsspec` | 2026.4.0 | BSD-3-Clause |
| `grad-cam` | 1.5.7 | MIT License |
| `h11` | 0.16.0 | MIT |
| `h2` | 4.3.0 | The MIT License (MIT) |
| `hf-xet` | 1.5.0 | Apache-2.0 |
| `httpcore` | 1.0.9 | BSD-3-Clause |
| `httpx` | 0.28.1 | BSD-3-Clause |
| `huggingface-hub` | 1.14.0 | Apache-2.0 |
| `humanfriendly` | 10.0 | MIT |
| `idna` | 3.13 | BSD-3-Clause |
| `imageio` | 2.37.4 | BSD-2-Clause |
| `imageio-ffmpeg` | 0.6.0 | BSD-2-Clause |
| `importlib-metadata` | 9.0.0 | Apache-2.0 |
| `jinja2` | 3.1.6 | BSD License |
| `joblib` | 1.5.3 | BSD-3-Clause |
| `keyring` | 25.7.0 | MIT |
| `kiwisolver` | 1.5.0 | ========================= |
| `lazy-loader` | 0.5 | BSD-3-Clause |
| `librosa` | 0.11.0 | ISC |
| `lightning-utilities` | 0.15.3 | Apache-2.0 |
| `llvmlite` | 0.44.0 | BSD |
| `markdown-it-py` | 4.2.0 | MIT License |
| `markupsafe` | 3.0.3 | BSD-3-Clause |
| `matplotlib` | 3.10.9 | License agreement for matplotlib versions 1.3.0 and later |
| `mdurl` | 0.1.2 | MIT License |
| `mpmath` | 1.3.0 | BSD |
| `msgpack` | 1.1.2 | Apache-2.0 |
| `networkx` | 3.4.2 | BSD License |
| `numba` | 0.61.2 | BSD |
| `numpy` | 1.26.4 | Copyright (c) 2005-2023, NumPy Developers. |
| `onnx` | 1.15.0 | Apache License v2.0 |
| `onnxruntime` | 1.19.2 | MIT License |
| `opencv-python` | — | Apache-2.0 |
| `packaging` | 26.2 | Apache-2.0 OR BSD-2-Clause |
| `paho-mqtt` | — | EPL-2.0 / EDL-1.0 |
| `pandas` | 2.3.3 | BSD 3-Clause License |
| `pi-heif` | 1.4.0 | BSD-3-Clause |
| `pillow` | 12.3.0 | MIT-CMU |
| `platformdirs` | 4.10.0 | MIT |
| `pooch` | 1.9.0 | BSD-3-Clause |
| `protobuf` | 3.20.3 | BSD-3-Clause |
| `pycparser` | 3.0 | BSD-3-Clause |
| `pydantic` | 2.13.4 | MIT |
| `pygments` | 2.20.0 | BSD-2-Clause |
| `pyparsing` | 3.3.2 | MIT |
| `pyreadline3` | 3.5.4 | BSD |
| `pyserial` | — | BSD-3-Clause |
| `python-dateutil` | 2.9.0.post0 | Dual License |
| `python-multipart` | — | Apache-2.0 |
| `pytorch-lightning` | 2.6.5 | Apache-2.0 |
| `pytz` | 2026.2 | MIT |
| `pyyaml` | 6.0.3 | MIT |
| `reportlab` | — | BSD-3-Clause |
| `requests` | 2.33.1 | Apache-2.0 |
| `rich` | 15.0.0 | MIT |
| `safetensors` | 0.8.0 | Apache Software License |
| `scikit-image` | 0.25.2 | Files: * |
| `scikit-learn` | 1.7.2 | BSD-3-Clause |
| `scipy` | 1.15.3 | Copyright (c) 2001-2002 Enthought, Inc. 2003-2024, SciPy Developers. |
| `sentry-sdk` | — | MIT |
| `shap` | 0.49.1 | MIT License |
| `shellingham` | 1.5.4 | ISC License |
| `six` | 1.17.0 | MIT |
| `slicer` | 0.0.8 | MIT License |
| `soundfile` | 0.13.1 | BSD 3-Clause License |
| `soxr` | 1.1.0 | LGPL-2.1-or-later |
| `sqlcipher3` | 0.6.2 | MIT |
| `starlette` | — | BSD-3-Clause |
| `supabase` | — | MIT |
| `sympy` | 1.14.0 | BSD |
| `threadpoolctl` | 3.6.0 | BSD-3-Clause |
| `tifffile` | 2025.5.10 | BSD-3-Clause |
| `timm` | 1.0.28 | Apache-2.0 |
| `torch` | 2.1.2+cpu | BSD-3 |
| `torchmetrics` | 1.9.0 | Apache-2.0 |
| `torchvision` | 0.16.2+cpu | BSD |
| `tqdm` | 4.67.3 | MPL-2.0 AND MIT |
| `ttach` | — | MIT |
| `typer` | 0.25.1 | MIT |
| `typing-extensions` | 4.15.0 | PSF-2.0 |
| `tzdata` | 2026.2 | Apache-2.0 |
| `ultralytics` | 8.4.47 | AGPL-3.0 |
| `urllib3` | 2.6.3 | MIT |
| `uvicorn` | — | BSD-3-Clause |
| `websockets` | 15.0.1 | BSD-3-Clause |
| `werkzeug` | 3.1.8 | BSD-3-Clause |
| `xgboost` | — | Apache-2.0 |
| `zeroconf` | — | LGPL-2.1 |
