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
| `cycler` | 0.12.1 | BSD License |
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
| `kiwisolver` | 1.5.0 | BSD License |
| `lazy-loader` | 0.5 | BSD-3-Clause |
| `librosa` | 0.11.0 | ISC |
| `lightning-utilities` | 0.15.3 | Apache-2.0 |
| `llvmlite` | 0.44.0 | BSD |
| `markdown-it-py` | 4.2.0 | MIT License |
| `markupsafe` | 3.0.3 | BSD-3-Clause |
| `matplotlib` | 3.10.9 | Python Software Foundation License |
| `mdurl` | 0.1.2 | MIT License |
| `mpmath` | 1.3.0 | BSD |
| `msgpack` | 1.1.2 | Apache-2.0 |
| `networkx` | 3.4.2 | BSD License |
| `numba` | 0.61.2 | BSD |
| `numpy` | 1.26.4 | BSD License |
| `onnx` | 1.15.0 | Apache License v2.0 |
| `onnxruntime` | 1.19.2 | MIT License |
| `opencv-python` | — | Apache-2.0 |
| `packaging` | 26.2 | Apache-2.0 OR BSD-2-Clause |
| `paho-mqtt` | — | EPL-2.0 / EDL-1.0 |
| `pandas` | 2.3.3 | BSD 3-Clause License |
| `pi-heif` | 1.4.0 | BSD-3-Clause (sınıflandırıcı: GNU Lesser General Public License v3 (LGPLv3)) |
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
| `python-dateutil` | 2.9.0.post0 | BSD License / Apache Software License |
| `python-multipart` | — | Apache-2.0 |
| `pytorch-lightning` | 2.6.5 | Apache-2.0 |
| `pytz` | 2026.2 | MIT |
| `pyyaml` | 6.0.3 | MIT |
| `reportlab` | — | BSD-3-Clause |
| `requests` | 2.33.1 | Apache-2.0 |
| `rich` | 15.0.0 | MIT |
| `safetensors` | 0.8.0 | Apache Software License |
| `scikit-image` | 0.25.2 | BSD License |
| `scikit-learn` | 1.7.2 | BSD-3-Clause |
| `scipy` | 1.15.3 | BSD License |
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

### Arayüz, site, DEMA ve launcher (npm)

Kaynak: `apps/ui/package-lock.json` + `apps/web/package-lock.json` + `dema-terapi-simülatörü/package-lock.json` + `launcher/app/package-lock.json` — her kilit dosyasındaki BÜTÜN çalışma-zamanı girdileri
(geliştirme bağımlılıkları hariç; sürüm ve lisans kilit dosyasından). Küme derleme araçlarının bir kısmını da kapsar
(fazla atıf güvenli taraftır). Çift lisanslı girdilerde (`A OR B`) izin veren seçenek kullanılır.

| Paket | Sürüm | Lisans | Kullanan |
|---|---|---|---|
| `@adobe/css-tools` | 4.5.0 | MIT | arayüz |
| `@babel/code-frame` | 7.29.0 | MIT | DEMA |
| `@babel/code-frame` | 7.29.7 | MIT | arayüz |
| `@babel/compat-data` | 7.29.0 | MIT | DEMA |
| `@babel/compat-data` | 7.29.7 | MIT | arayüz |
| `@babel/core` | 7.29.0 | MIT | DEMA |
| `@babel/core` | 7.29.7 | MIT | arayüz |
| `@babel/generator` | 7.29.1 | MIT | DEMA |
| `@babel/generator` | 7.29.7 | MIT | arayüz |
| `@babel/helper-annotate-as-pure` | 7.29.7 | MIT | arayüz |
| `@babel/helper-compilation-targets` | 7.28.6 | MIT | DEMA |
| `@babel/helper-compilation-targets` | 7.29.7 | MIT | arayüz |
| `@babel/helper-create-class-features-plugin` | 7.29.7 | MIT | arayüz |
| `@babel/helper-create-regexp-features-plugin` | 7.29.7 | MIT | arayüz |
| `@babel/helper-define-polyfill-provider` | 0.6.8 | MIT | arayüz |
| `@babel/helper-globals` | 7.28.0 | MIT | DEMA |
| `@babel/helper-globals` | 7.29.7 | MIT | arayüz |
| `@babel/helper-member-expression-to-functions` | 7.29.7 | MIT | arayüz |
| `@babel/helper-module-imports` | 7.28.6 | MIT | DEMA |
| `@babel/helper-module-imports` | 7.29.7 | MIT | arayüz |
| `@babel/helper-module-transforms` | 7.28.6 | MIT | DEMA |
| `@babel/helper-module-transforms` | 7.29.7 | MIT | arayüz |
| `@babel/helper-optimise-call-expression` | 7.29.7 | MIT | arayüz |
| `@babel/helper-plugin-utils` | 7.28.6 | MIT | DEMA |
| `@babel/helper-plugin-utils` | 7.29.7 | MIT | arayüz |
| `@babel/helper-remap-async-to-generator` | 7.29.7 | MIT | arayüz |
| `@babel/helper-replace-supers` | 7.29.7 | MIT | arayüz |
| `@babel/helper-skip-transparent-expression-wrappers` | 7.29.7 | MIT | arayüz |
| `@babel/helper-string-parser` | 7.27.1 | MIT | DEMA |
| `@babel/helper-string-parser` | 7.29.7 | MIT | arayüz |
| `@babel/helper-validator-identifier` | 7.28.5 | MIT | DEMA |
| `@babel/helper-validator-identifier` | 7.29.7 | MIT | arayüz |
| `@babel/helper-validator-option` | 7.27.1 | MIT | DEMA |
| `@babel/helper-validator-option` | 7.29.7 | MIT | arayüz |
| `@babel/helper-wrap-function` | 7.29.7 | MIT | arayüz |
| `@babel/helpers` | 7.29.2 | MIT | DEMA |
| `@babel/helpers` | 7.29.7 | MIT | arayüz |
| `@babel/parser` | 7.29.2 | MIT | DEMA |
| `@babel/parser` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-proposal-decorators` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-proposal-export-default-from` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-syntax-decorators` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-syntax-dynamic-import` | 7.8.3 | MIT | arayüz |
| `@babel/plugin-syntax-export-default-from` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-syntax-flow` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-syntax-jsx` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-syntax-nullish-coalescing-operator` | 7.8.3 | MIT | arayüz |
| `@babel/plugin-syntax-optional-chaining` | 7.8.3 | MIT | arayüz |
| `@babel/plugin-syntax-typescript` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-async-generator-functions` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-async-to-generator` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-block-scoping` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-class-properties` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-class-static-block` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-classes` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-destructuring` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-export-namespace-from` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-flow-strip-types` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-for-of` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-logical-assignment-operators` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-modules-commonjs` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-named-capturing-groups-regex` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-nullish-coalescing-operator` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-object-rest-spread` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-optional-catch-binding` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-optional-chaining` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-parameters` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-private-methods` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-private-property-in-object` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-react-display-name` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-react-jsx` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-react-jsx-development` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-react-jsx-self` | 7.27.1 | MIT | DEMA |
| `@babel/plugin-transform-react-jsx-source` | 7.27.1 | MIT | DEMA |
| `@babel/plugin-transform-react-pure-annotations` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-runtime` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-typescript` | 7.29.7 | MIT | arayüz |
| `@babel/plugin-transform-unicode-regex` | 7.29.7 | MIT | arayüz |
| `@babel/preset-typescript` | 7.29.7 | MIT | arayüz |
| `@babel/runtime` | 7.29.7 | MIT | arayüz, site |
| `@babel/template` | 7.28.6 | MIT | DEMA |
| `@babel/template` | 7.29.7 | MIT | arayüz |
| `@babel/traverse` | 7.29.0 | MIT | DEMA |
| `@babel/traverse` | 7.29.7 | MIT | arayüz |
| `@babel/types` | 7.29.0 | MIT | DEMA |
| `@babel/types` | 7.29.7 | MIT | arayüz |
| `@expo-google-fonts/inter` | 0.4.2 | MIT AND OFL-1.1 | arayüz |
| `@expo-google-fonts/material-symbols` | 0.4.38 | MIT AND Apache-2.0 | arayüz |
| `@expo/cli` | 56.1.15 | MIT | arayüz |
| `@expo/code-signing-certificates` | 0.0.6 | MIT | arayüz |
| `@expo/config` | 56.0.9 | MIT | arayüz |
| `@expo/config-plugins` | 56.0.9 | MIT | arayüz |
| `@expo/config-types` | 56.0.6 | MIT | arayüz |
| `@expo/devcert` | 1.2.1 | MIT | arayüz |
| `@expo/devtools` | 56.0.2 | MIT | arayüz |
| `@expo/dom-webview` | 56.0.5 | MIT | arayüz |
| `@expo/env` | 2.3.0 | MIT | arayüz |
| `@expo/expo-modules-macros-plugin` | 0.2.2 | MIT | arayüz |
| `@expo/fingerprint` | 0.19.4 | MIT | arayüz |
| `@expo/image-utils` | 0.10.1 | MIT | arayüz |
| `@expo/inline-modules` | 0.0.11 | MIT | arayüz |
| `@expo/json-file` | 10.2.0 | MIT | arayüz |
| `@expo/local-build-cache-provider` | 56.0.8 | MIT | arayüz |
| `@expo/log-box` | 56.0.13 | MIT | arayüz |
| `@expo/metro` | 56.0.0 | MIT | arayüz |
| `@expo/metro-config` | 56.0.14 | MIT | arayüz |
| `@expo/metro-file-map` | 56.0.3 | MIT | arayüz |
| `@expo/metro-runtime` | 56.0.15 | MIT | arayüz |
| `@expo/osascript` | 2.6.0 | MIT | arayüz |
| `@expo/package-manager` | 1.12.1 | MIT | arayüz |
| `@expo/plist` | 0.7.0 | MIT | arayüz |
| `@expo/prebuild-config` | 56.0.15 | MIT | arayüz |
| `@expo/require-utils` | 56.1.3 | MIT | arayüz |
| `@expo/router-server` | 56.0.14 | MIT | arayüz |
| `@expo/schema-utils` | 56.0.1 | MIT | arayüz |
| `@expo/sdk-runtime-versions` | 1.0.0 | MIT | arayüz |
| `@expo/spawn-async` | 1.8.0 | MIT | arayüz |
| `@expo/sudo-prompt` | 9.3.2 | MIT | arayüz |
| `@expo/ui` | 56.0.17 | MIT | arayüz |
| `@expo/ws-tunnel` | 2.0.0 | MIT | arayüz |
| `@expo/xcpretty` | 4.4.4 | BSD-3-Clause | arayüz |
| `@google/genai` | 1.49.0 | Apache-2.0 | DEMA |
| `@isaacs/ttlcache` | 1.4.1 | ISC | arayüz |
| `@jest/schemas` | 29.6.3 | MIT | arayüz |
| `@jest/types` | 29.6.3 | MIT | arayüz |
| `@jridgewell/gen-mapping` | 0.3.13 | MIT | arayüz, DEMA |
| `@jridgewell/remapping` | 2.3.5 | MIT | arayüz, DEMA |
| `@jridgewell/resolve-uri` | 3.1.2 | MIT | arayüz, DEMA |
| `@jridgewell/source-map` | 0.3.11 | MIT | arayüz |
| `@jridgewell/sourcemap-codec` | 1.5.5 | MIT | arayüz, DEMA |
| `@jridgewell/trace-mapping` | 0.3.31 | MIT | arayüz, DEMA |
| `@postman/form-data` | 3.1.1 | MIT | site |
| `@postman/tough-cookie` | 4.1.3-postman.1 | BSD-3-Clause | site |
| `@postman/tunnel-agent` | 0.6.8 | Apache-2.0 | site |
| `@protobufjs/aspromise` | 1.1.2 | BSD-3-Clause | DEMA |
| `@protobufjs/base64` | 1.1.2 | BSD-3-Clause | DEMA |
| `@protobufjs/codegen` | 2.0.4 | BSD-3-Clause | DEMA |
| `@protobufjs/eventemitter` | 1.1.0 | BSD-3-Clause | DEMA |
| `@protobufjs/fetch` | 1.1.0 | BSD-3-Clause | DEMA |
| `@protobufjs/float` | 1.0.2 | BSD-3-Clause | DEMA |
| `@protobufjs/inquire` | 1.1.0 | BSD-3-Clause | DEMA |
| `@protobufjs/path` | 1.1.2 | BSD-3-Clause | DEMA |
| `@protobufjs/pool` | 1.1.0 | BSD-3-Clause | DEMA |
| `@protobufjs/utf8` | 1.1.0 | BSD-3-Clause | DEMA |
| `@radix-ui/primitive` | 1.1.3 | MIT | arayüz |
| `@radix-ui/react-collection` | 1.1.7 | MIT | arayüz |
| `@radix-ui/react-compose-refs` | 1.1.2 | MIT | arayüz |
| `@radix-ui/react-context` | 1.1.2 | MIT | arayüz |
| `@radix-ui/react-dialog` | 1.1.15 | MIT | arayüz |
| `@radix-ui/react-direction` | 1.1.1 | MIT | arayüz |
| `@radix-ui/react-dismissable-layer` | 1.1.11 | MIT | arayüz |
| `@radix-ui/react-focus-guards` | 1.1.3 | MIT | arayüz |
| `@radix-ui/react-focus-scope` | 1.1.7 | MIT | arayüz |
| `@radix-ui/react-id` | 1.1.1 | MIT | arayüz |
| `@radix-ui/react-portal` | 1.1.9 | MIT | arayüz |
| `@radix-ui/react-presence` | 1.1.5 | MIT | arayüz |
| `@radix-ui/react-primitive` | 2.1.3 | MIT | arayüz |
| `@radix-ui/react-roving-focus` | 1.1.11 | MIT | arayüz |
| `@radix-ui/react-slot` | 1.2.0 | MIT | arayüz |
| `@radix-ui/react-slot` | 1.2.3 | MIT | arayüz |
| `@radix-ui/react-tabs` | 1.1.13 | MIT | arayüz |
| `@radix-ui/react-use-callback-ref` | 1.1.1 | MIT | arayüz |
| `@radix-ui/react-use-controllable-state` | 1.2.2 | MIT | arayüz |
| `@radix-ui/react-use-effect-event` | 0.0.2 | MIT | arayüz |
| `@radix-ui/react-use-escape-keydown` | 1.1.1 | MIT | arayüz |
| `@radix-ui/react-use-layout-effect` | 1.1.1 | MIT | arayüz |
| `@react-native-async-storage/async-storage` | 2.2.0 | MIT | arayüz |
| `@react-native-community/netinfo` | 11.5.2 | MIT | arayüz |
| `@react-native-masked-view/masked-view` | 0.3.2 | MIT | arayüz |
| `@react-native/assets-registry` | 0.85.3 | MIT | arayüz |
| `@react-native/babel-plugin-codegen` | 0.85.3 | MIT | arayüz |
| `@react-native/codegen` | 0.85.3 | MIT | arayüz |
| `@react-native/community-cli-plugin` | 0.85.3 | MIT | arayüz |
| `@react-native/debugger-frontend` | 0.85.3 | BSD-3-Clause | arayüz |
| `@react-native/debugger-shell` | 0.85.3 | MIT | arayüz |
| `@react-native/dev-middleware` | 0.85.3 | MIT | arayüz |
| `@react-native/gradle-plugin` | 0.85.3 | MIT | arayüz |
| `@react-native/js-polyfills` | 0.85.3 | MIT | arayüz |
| `@react-native/normalize-colors` | 0.74.89 | MIT | arayüz |
| `@react-native/normalize-colors` | 0.85.3 | MIT | arayüz |
| `@react-native/virtualized-lists` | 0.85.3 | MIT | arayüz |
| `@rolldown/pluginutils` | 1.0.0-rc.3 | MIT | DEMA |
| `@sinclair/typebox` | 0.27.10 | MIT | arayüz |
| `@supabase/auth-js` | 2.108.1 | MIT | arayüz |
| `@supabase/auth-js` | 2.109.0 | MIT | site |
| `@supabase/functions-js` | 2.108.1 | MIT | arayüz |
| `@supabase/functions-js` | 2.109.0 | MIT | site |
| `@supabase/phoenix` | 0.4.2 | MIT | arayüz |
| `@supabase/phoenix` | 0.4.4 | MIT | site |
| `@supabase/postgrest-js` | 2.108.1 | MIT | arayüz |
| `@supabase/postgrest-js` | 2.109.0 | MIT | site |
| `@supabase/realtime-js` | 2.108.1 | MIT | arayüz |
| `@supabase/realtime-js` | 2.109.0 | MIT | site |
| `@supabase/storage-js` | 2.108.1 | MIT | arayüz |
| `@supabase/storage-js` | 2.109.0 | MIT | site |
| `@supabase/supabase-js` | 2.108.1 | MIT | arayüz |
| `@supabase/supabase-js` | 2.109.0 | MIT | site |
| `@tailwindcss/node` | 4.2.2 | MIT | DEMA |
| `@tailwindcss/oxide` | 4.2.2 | MIT | DEMA |
| `@tailwindcss/oxide-android-arm64` | 4.2.2 | MIT | DEMA |
| `@tailwindcss/oxide-darwin-arm64` | 4.2.2 | MIT | DEMA |
| `@tailwindcss/oxide-darwin-x64` | 4.2.2 | MIT | DEMA |
| `@tailwindcss/oxide-freebsd-x64` | 4.2.2 | MIT | DEMA |
| `@tailwindcss/oxide-linux-arm-gnueabihf` | 4.2.2 | MIT | DEMA |
| `@tailwindcss/oxide-linux-arm64-gnu` | 4.2.2 | MIT | DEMA |
| `@tailwindcss/oxide-linux-arm64-musl` | 4.2.2 | MIT | DEMA |
| `@tailwindcss/oxide-linux-x64-gnu` | 4.2.2 | MIT | DEMA |
| `@tailwindcss/oxide-linux-x64-musl` | 4.2.2 | MIT | DEMA |
| `@tailwindcss/oxide-wasm32-wasi` | 4.2.2 | MIT | DEMA |
| `@tailwindcss/oxide-win32-arm64-msvc` | 4.2.2 | MIT | DEMA |
| `@tailwindcss/oxide-win32-x64-msvc` | 4.2.2 | MIT | DEMA |
| `@tailwindcss/vite` | 4.2.2 | MIT | DEMA |
| `@testing-library/jest-dom` | 6.9.1 | MIT | arayüz |
| `@testing-library/user-event` | 14.6.1 | MIT | arayüz |
| `@types/babel__core` | 7.20.5 | MIT | DEMA |
| `@types/babel__generator` | 7.27.0 | MIT | DEMA |
| `@types/babel__template` | 7.4.4 | MIT | DEMA |
| `@types/babel__traverse` | 7.28.0 | MIT | DEMA |
| `@types/emscripten` | 1.41.5 | MIT | arayüz |
| `@types/istanbul-lib-coverage` | 2.0.6 | MIT | arayüz |
| `@types/istanbul-lib-report` | 3.0.3 | MIT | arayüz |
| `@types/istanbul-reports` | 3.0.4 | MIT | arayüz |
| `@types/node` | 22.19.17 | MIT | DEMA |
| `@types/node` | 26.1.0 | MIT | arayüz |
| `@types/retry` | 0.12.0 | MIT | DEMA |
| `@types/yargs` | 17.0.35 | MIT | arayüz |
| `@types/yargs-parser` | 21.0.3 | MIT | arayüz |
| `@ungap/structured-clone` | 1.3.1 | ISC | arayüz |
| `@vitejs/plugin-react` | 5.2.0 | MIT | DEMA |
| `@xmldom/xmldom` | 0.8.13 | MIT | arayüz |
| `@xmldom/xmldom` | 0.9.10 | MIT | arayüz |
| `abort-controller` | 3.0.0 | MIT | arayüz |
| `accepts` | 1.3.8 | MIT | arayüz, DEMA |
| `accepts` | 2.0.0 | MIT | arayüz |
| `acorn` | 8.16.0 | MIT | arayüz |
| `agent-base` | 7.1.4 | MIT | arayüz, site, DEMA |
| `anser` | 1.4.10 | MIT | arayüz |
| `ansi-escapes` | 4.3.2 | MIT | arayüz |
| `ansi-regex` | 4.1.1 | MIT | arayüz |
| `ansi-regex` | 5.0.1 | MIT | arayüz |
| `ansi-styles` | 3.2.1 | MIT | arayüz |
| `ansi-styles` | 4.3.0 | MIT | arayüz |
| `ansi-styles` | 5.2.0 | MIT | arayüz |
| `arg` | 5.0.2 | MIT | arayüz |
| `argparse` | 2.0.1 | Python-2.0 | arayüz |
| `aria-hidden` | 1.2.6 | MIT | arayüz |
| `aria-query` | 5.3.2 | Apache-2.0 | arayüz |
| `array-flatten` | 1.1.1 | MIT | DEMA |
| `asap` | 2.0.6 | MIT | arayüz |
| `asn1` | 0.2.6 | MIT | site |
| `assert-plus` | 1.0.0 | MIT | site |
| `asynckit` | 0.4.0 | MIT | site |
| `aws-sign2` | 0.7.0 | Apache-2.0 | site |
| `aws4` | 1.13.2 | MIT | site |
| `babel-plugin-polyfill-corejs2` | 0.4.17 | MIT | arayüz |
| `babel-plugin-polyfill-corejs3` | 0.13.0 | MIT | arayüz |
| `babel-plugin-polyfill-regenerator` | 0.6.8 | MIT | arayüz |
| `babel-plugin-react-compiler` | 1.0.0 | MIT | arayüz |
| `babel-plugin-react-native-web` | 0.21.2 | MIT | arayüz |
| `babel-plugin-syntax-hermes-parser` | 0.33.3 | MIT | arayüz |
| `babel-plugin-transform-flow-enums` | 0.0.2 | MIT | arayüz |
| `babel-preset-expo` | 56.0.15 | MIT | arayüz |
| `balanced-match` | 4.0.4 | MIT | arayüz |
| `barcode-detector` | 3.1.3 | MIT | arayüz |
| `base64-js` | 1.5.1 | MIT | arayüz, DEMA |
| `baseline-browser-mapping` | 2.10.17 | Apache-2.0 | DEMA |
| `baseline-browser-mapping` | 2.10.33 | Apache-2.0 | arayüz |
| `bcrypt-pbkdf` | 1.0.2 | BSD-3-Clause | site |
| `big-integer` | 1.6.52 | Unlicense | arayüz |
| `bignumber.js` | 9.3.1 | MIT | DEMA |
| `bluebird` | 2.11.0 | MIT | site |
| `body-parser` | 1.20.4 | MIT | DEMA |
| `boolbase` | 1.0.0 | ISC | arayüz |
| `bplist-creator` | 0.1.0 | MIT | arayüz |
| `bplist-parser` | 0.3.1 | MIT | arayüz |
| `bplist-parser` | 0.3.2 | MIT | arayüz |
| `brace-expansion` | 5.0.6 | MIT | arayüz |
| `braces` | 3.0.3 | MIT | arayüz |
| `browserslist` | 4.28.2 | MIT | arayüz, DEMA |
| `bser` | 2.1.1 | Apache-2.0 | arayüz |
| `buffer-equal-constant-time` | 1.0.1 | BSD-3-Clause | DEMA |
| `buffer-from` | 1.1.2 | MIT | arayüz |
| `bytes` | 3.1.2 | MIT | arayüz, DEMA |
| `call-bind-apply-helpers` | 1.0.2 | MIT | site, DEMA |
| `call-bound` | 1.0.4 | MIT | site, DEMA |
| `camelcase` | 6.3.0 | MIT | arayüz |
| `caniuse-lite` | 1.0.30001787 | CC-BY-4.0 | DEMA |
| `caniuse-lite` | 1.0.30001793 | CC-BY-4.0 | arayüz |
| `caseless` | 0.12.0 | Apache-2.0 | site |
| `chalk` | 2.4.2 | MIT | arayüz |
| `chalk` | 4.1.2 | MIT | arayüz |
| `chrome-launcher` | 0.15.2 | Apache-2.0 | arayüz |
| `chromium-edge-launcher` | 0.3.0 | Apache-2.0 | arayüz |
| `ci-info` | 2.0.0 | MIT | arayüz |
| `ci-info` | 3.9.0 | MIT | arayüz |
| `cli-cursor` | 2.1.0 | MIT | arayüz |
| `cli-spinners` | 2.9.2 | MIT | arayüz |
| `client-only` | 0.0.1 | MIT | arayüz |
| `cliui` | 8.0.1 | ISC | arayüz |
| `clone` | 1.0.4 | MIT | arayüz |
| `color` | 4.2.3 | MIT | arayüz |
| `color-convert` | 1.9.3 | MIT | arayüz |
| `color-convert` | 2.0.1 | MIT | arayüz |
| `color-name` | 1.1.3 | MIT | arayüz |
| `color-name` | 1.1.4 | MIT | arayüz |
| `color-string` | 1.9.1 | MIT | arayüz |
| `combined-stream` | 1.0.8 | MIT | site |
| `commander` | 12.1.0 | MIT | arayüz |
| `commander` | 2.20.3 | MIT | arayüz |
| `commander` | 7.2.0 | MIT | arayüz |
| `compressible` | 2.0.18 | MIT | arayüz |
| `compression` | 1.8.1 | MIT | arayüz |
| `connect` | 3.7.0 | MIT | arayüz |
| `content-disposition` | 0.5.4 | MIT | DEMA |
| `content-type` | 1.0.5 | MIT | DEMA |
| `convert-source-map` | 2.0.0 | MIT | arayüz, DEMA |
| `cookie` | 0.7.2 | MIT | DEMA |
| `cookie` | 1.1.1 | MIT | site |
| `cookie-signature` | 1.0.7 | MIT | DEMA |
| `core-js-compat` | 3.49.0 | MIT | arayüz |
| `core-util-is` | 1.0.2 | MIT | site |
| `cross-fetch` | 3.2.0 | MIT | arayüz |
| `cross-spawn` | 7.0.6 | MIT | arayüz |
| `css-in-js-utils` | 3.1.0 | MIT | arayüz |
| `css-select` | 5.2.2 | BSD-2-Clause | arayüz |
| `css-tree` | 1.1.3 | MIT | arayüz |
| `css-what` | 6.2.2 | BSD-2-Clause | arayüz |
| `css.escape` | 1.5.1 | MIT | arayüz |
| `dashdash` | 1.14.1 | MIT | site |
| `data-uri-to-buffer` | 4.0.1 | MIT | DEMA |
| `debug` | 2.6.9 | MIT | arayüz, DEMA |
| `debug` | 3.2.7 | MIT | arayüz |
| `debug` | 4.4.3 | MIT | arayüz, site, DEMA |
| `decode-uri-component` | 0.2.2 | MIT | arayüz |
| `deepmerge` | 4.3.1 | MIT | arayüz |
| `defaults` | 1.0.4 | MIT | arayüz |
| `delayed-stream` | 1.0.0 | MIT | site |
| `depd` | 2.0.0 | MIT | arayüz, DEMA |
| `destroy` | 1.2.0 | MIT | arayüz, DEMA |
| `detect-libc` | 2.1.2 | Apache-2.0 | arayüz, DEMA |
| `detect-node-es` | 1.1.0 | MIT | arayüz |
| `dnssd-advertise` | 1.1.6 | MIT | arayüz |
| `dom-accessibility-api` | 0.6.3 | MIT | arayüz |
| `dom-serializer` | 2.0.0 | MIT | arayüz |
| `domelementtype` | 2.3.0 | BSD-2-Clause | arayüz |
| `domhandler` | 5.0.3 | BSD-2-Clause | arayüz |
| `domutils` | 3.2.2 | BSD-2-Clause | arayüz |
| `dotenv` | 17.4.1 | BSD-2-Clause | DEMA |
| `dunder-proto` | 1.0.1 | MIT | site, DEMA |
| `ecc-jsbn` | 0.1.2 | MIT | site |
| `ecdsa-sig-formatter` | 1.0.11 | Apache-2.0 | DEMA |
| `ee-first` | 1.1.1 | MIT | arayüz, DEMA |
| `electron-to-chromium` | 1.5.334 | ISC | DEMA |
| `electron-to-chromium` | 1.5.364 | ISC | arayüz |
| `emoji-regex` | 8.0.0 | MIT | arayüz |
| `encodeurl` | 1.0.2 | MIT | arayüz |
| `encodeurl` | 2.0.0 | MIT | arayüz, DEMA |
| `enhanced-resolve` | 5.20.1 | MIT | DEMA |
| `entities` | 4.5.0 | BSD-2-Clause | arayüz |
| `error-stack-parser` | 2.1.4 | MIT | arayüz |
| `es-define-property` | 1.0.1 | MIT | site, DEMA |
| `es-errors` | 1.3.0 | MIT | arayüz, site, DEMA |
| `es-object-atoms` | 1.1.1 | MIT | DEMA |
| `es-object-atoms` | 1.1.2 | MIT | site |
| `escalade` | 3.2.0 | MIT | arayüz, DEMA |
| `escape-html` | 1.0.3 | MIT | arayüz, DEMA |
| `escape-string-regexp` | 1.0.5 | MIT | arayüz |
| `escape-string-regexp` | 4.0.0 | MIT | arayüz |
| `etag` | 1.8.1 | MIT | arayüz, DEMA |
| `event-target-shim` | 5.0.1 | MIT | arayüz |
| `events` | 3.3.0 | MIT | arayüz |
| `expo` | 56.0.11 | MIT | arayüz |
| `expo-asset` | 56.0.17 | MIT | arayüz |
| `expo-audio` | 56.0.12 | MIT | arayüz |
| `expo-blur` | 56.0.3 | MIT | arayüz |
| `expo-build-properties` | 56.0.18 | MIT | arayüz |
| `expo-camera` | 56.0.8 | MIT | arayüz |
| `expo-constants` | 56.0.18 | MIT | arayüz |
| `expo-document-picker` | 56.0.4 | MIT | arayüz |
| `expo-file-system` | 56.0.8 | MIT | arayüz |
| `expo-font` | 56.0.7 | MIT | arayüz |
| `expo-glass-effect` | 56.0.4 | MIT | arayüz |
| `expo-haptics` | 56.0.3 | MIT | arayüz |
| `expo-image-loader` | 56.0.3 | MIT | arayüz |
| `expo-image-manipulator` | 56.0.20 | MIT | arayüz |
| `expo-image-picker` | 56.0.17 | MIT | arayüz |
| `expo-keep-awake` | 56.0.3 | MIT | arayüz |
| `expo-linear-gradient` | 56.0.4 | MIT | arayüz |
| `expo-linking` | 56.0.14 | MIT | arayüz |
| `expo-modules-autolinking` | 56.0.15 | MIT | arayüz |
| `expo-modules-core` | 56.0.16 | MIT | arayüz |
| `expo-modules-jsi` | 56.0.9 | MIT | arayüz |
| `expo-router` | 56.2.10 | MIT | arayüz |
| `expo-secure-store` | 56.0.4 | MIT | arayüz |
| `expo-server` | 56.0.5 | MIT | arayüz |
| `expo-sharing` | 56.0.18 | MIT | arayüz |
| `expo-status-bar` | 56.0.4 | MIT | arayüz |
| `expo-symbols` | 56.0.6 | MIT | arayüz |
| `expo-system-ui` | 56.0.5 | MIT | arayüz |
| `exponential-backoff` | 3.1.3 | Apache-2.0 | arayüz |
| `express` | 4.22.1 | MIT | DEMA |
| `extend` | 3.0.2 | MIT | site, DEMA |
| `extsprintf` | 1.3.0 | MIT | site |
| `fast-deep-equal` | 3.1.3 | MIT | arayüz |
| `fb-dotslash` | 0.5.8 | (MIT OR Apache-2.0) | arayüz |
| `fb-watchman` | 2.0.2 | Apache-2.0 | arayüz |
| `fbjs` | 3.0.5 | MIT | arayüz |
| `fbjs-css-vars` | 1.0.2 | MIT | arayüz |
| `fdir` | 6.5.0 | MIT | arayüz |
| `fetch-blob` | 3.2.0 | MIT | DEMA |
| `fetch-nodeshim` | 0.4.10 | MIT | arayüz |
| `fill-range` | 7.1.1 | MIT | arayüz |
| `filter-obj` | 1.1.0 | MIT | arayüz |
| `finalhandler` | 1.1.2 | MIT | arayüz |
| `finalhandler` | 1.3.2 | MIT | DEMA |
| `flow-enums-runtime` | 0.0.6 | MIT | arayüz |
| `fontfaceobserver` | 2.3.0 | BSD-2-Clause | arayüz |
| `forever-agent` | 0.6.1 | Apache-2.0 | site |
| `formdata-polyfill` | 4.0.10 | MIT | DEMA |
| `forwarded` | 0.2.0 | MIT | DEMA |
| `framer-motion` | 12.38.0 | MIT | DEMA |
| `fresh` | 0.5.2 | MIT | arayüz, DEMA |
| `function-bind` | 1.1.2 | MIT | arayüz, site, DEMA |
| `gaxios` | 7.1.4 | Apache-2.0 | DEMA |
| `gcp-metadata` | 8.1.2 | Apache-2.0 | DEMA |
| `gensync` | 1.0.0-beta.2 | MIT | arayüz, DEMA |
| `get-caller-file` | 2.0.5 | ISC | arayüz |
| `get-intrinsic` | 1.3.0 | MIT | site, DEMA |
| `get-nonce` | 1.0.1 | MIT | arayüz |
| `get-proto` | 1.0.1 | MIT | site, DEMA |
| `getenv` | 2.0.0 | MIT | arayüz |
| `getpass` | 0.1.7 | MIT | site |
| `glob` | 13.0.6 | BlueOak-1.0.0 | arayüz |
| `google-auth-library` | 10.6.2 | Apache-2.0 | DEMA |
| `google-logging-utils` | 1.1.3 | Apache-2.0 | DEMA |
| `gopd` | 1.2.0 | MIT | site, DEMA |
| `graceful-fs` | 4.2.11 | ISC | arayüz, DEMA |
| `has-flag` | 3.0.0 | MIT | arayüz |
| `has-flag` | 4.0.0 | MIT | arayüz |
| `has-symbols` | 1.1.0 | MIT | site, DEMA |
| `hasown` | 2.0.2 | MIT | DEMA |
| `hasown` | 2.0.4 | MIT | arayüz, site |
| `hermes-compiler` | 250829098.0.10 | MIT | arayüz |
| `hermes-estree` | 0.33.3 | MIT | arayüz |
| `hermes-estree` | 0.35.0 | MIT | arayüz |
| `hermes-parser` | 0.33.3 | MIT | arayüz |
| `hermes-parser` | 0.35.0 | MIT | arayüz |
| `hosted-git-info` | 7.0.2 | ISC | arayüz |
| `html-parse-stringify` | 4.0.1 | MIT | arayüz, site |
| `http-errors` | 2.0.1 | MIT | arayüz, DEMA |
| `http-signature` | 1.4.0 | MIT | site |
| `https-proxy-agent` | 7.0.6 | MIT | arayüz, DEMA |
| `hyphenate-style-name` | 1.1.0 | BSD-3-Clause | arayüz |
| `i18next` | 26.4.2 | MIT | arayüz, site |
| `iceberg-js` | 0.8.1 | MIT | arayüz, site |
| `iconv-lite` | 0.4.24 | MIT | DEMA |
| `ignore` | 5.3.2 | MIT | arayüz |
| `image-size` | 1.2.1 | MIT | arayüz |
| `indent-string` | 4.0.0 | MIT | arayüz |
| `inherits` | 2.0.4 | ISC | arayüz, DEMA |
| `inline-style-prefixer` | 7.0.1 | MIT | arayüz |
| `invariant` | 2.2.4 | MIT | arayüz |
| `ip-address` | 10.2.0 | MIT | site |
| `ipaddr.js` | 1.9.1 | MIT | DEMA |
| `is-arrayish` | 0.3.4 | MIT | arayüz |
| `is-core-module` | 2.16.2 | MIT | arayüz |
| `is-docker` | 2.2.1 | MIT | arayüz |
| `is-fullwidth-code-point` | 3.0.0 | MIT | arayüz |
| `is-number` | 7.0.0 | MIT | arayüz |
| `is-plain-obj` | 2.1.0 | MIT | arayüz |
| `is-typedarray` | 1.0.0 | MIT | site |
| `is-wsl` | 2.2.0 | MIT | arayüz |
| `isexe` | 2.0.0 | ISC | arayüz |
| `isstream` | 0.1.2 | MIT | site |
| `iyzipay` | 2.0.69 | MIT | site |
| `jest-get-type` | 29.6.3 | MIT | arayüz |
| `jest-util` | 29.7.0 | MIT | arayüz |
| `jest-validate` | 29.7.0 | MIT | arayüz |
| `jest-worker` | 29.7.0 | MIT | arayüz |
| `jimp-compact` | 0.16.1 | MIT | arayüz |
| `jiti` | 2.6.1 | MIT | DEMA |
| `js-tokens` | 4.0.0 | MIT | arayüz, DEMA |
| `js-yaml` | 4.2.0 | MIT | arayüz |
| `jsbn` | 0.1.1 | MIT | site |
| `jsc-safe-url` | 0.2.4 | 0BSD | arayüz |
| `jsesc` | 3.1.0 | MIT | arayüz, DEMA |
| `json-bigint` | 1.0.0 | MIT | DEMA |
| `json-schema` | 0.4.0 | (AFL-2.1 OR BSD-3-Clause) | site |
| `json-stringify-safe` | 5.0.1 | ISC | site |
| `json5` | 2.2.3 | MIT | arayüz, DEMA |
| `jsprim` | 2.0.2 | MIT | site |
| `jwa` | 2.0.1 | MIT | DEMA |
| `jws` | 4.0.1 | MIT | DEMA |
| `kleur` | 3.0.3 | MIT | arayüz |
| `lan-network` | 0.2.1 | MIT | arayüz |
| `leven` | 3.1.0 | MIT | arayüz |
| `lighthouse-logger` | 1.4.2 | Apache-2.0 | arayüz |
| `lightningcss` | 1.32.0 | MPL-2.0 | arayüz, DEMA |
| `lightningcss-android-arm64` | 1.32.0 | MPL-2.0 | arayüz, DEMA |
| `lightningcss-darwin-arm64` | 1.32.0 | MPL-2.0 | arayüz, DEMA |
| `lightningcss-darwin-x64` | 1.32.0 | MPL-2.0 | arayüz, DEMA |
| `lightningcss-freebsd-x64` | 1.32.0 | MPL-2.0 | arayüz, DEMA |
| `lightningcss-linux-arm-gnueabihf` | 1.32.0 | MPL-2.0 | arayüz, DEMA |
| `lightningcss-linux-arm64-gnu` | 1.32.0 | MPL-2.0 | arayüz, DEMA |
| `lightningcss-linux-arm64-musl` | 1.32.0 | MPL-2.0 | arayüz, DEMA |
| `lightningcss-linux-x64-gnu` | 1.32.0 | MPL-2.0 | arayüz, DEMA |
| `lightningcss-linux-x64-musl` | 1.32.0 | MPL-2.0 | arayüz, DEMA |
| `lightningcss-win32-arm64-msvc` | 1.32.0 | MPL-2.0 | arayüz, DEMA |
| `lightningcss-win32-x64-msvc` | 1.32.0 | MPL-2.0 | arayüz, DEMA |
| `lodash.debounce` | 4.0.8 | MIT | arayüz |
| `lodash.throttle` | 4.1.1 | MIT | arayüz |
| `log-symbols` | 2.2.0 | MIT | arayüz |
| `long` | 5.3.2 | Apache-2.0 | DEMA |
| `loose-envify` | 1.4.0 | MIT | arayüz |
| `lru-cache` | 10.4.3 | ISC | arayüz |
| `lru-cache` | 11.5.1 | BlueOak-1.0.0 | arayüz |
| `lru-cache` | 5.1.1 | ISC | arayüz, DEMA |
| `lucide-react` | 0.546.0 | ISC | DEMA |
| `lucide-react-native` | 0.546.0 | ISC | arayüz |
| `magic-string` | 0.30.21 | MIT | DEMA |
| `makeerror` | 1.0.12 | BSD-3-Clause | arayüz |
| `marky` | 1.3.0 | Apache-2.0 | arayüz |
| `math-intrinsics` | 1.1.0 | MIT | site, DEMA |
| `mdn-data` | 2.0.14 | CC0-1.0 | arayüz |
| `media-typer` | 0.3.0 | MIT | DEMA |
| `memoize-one` | 5.2.1 | MIT | arayüz |
| `memoize-one` | 6.0.0 | MIT | arayüz |
| `merge-descriptors` | 1.0.3 | MIT | DEMA |
| `merge-options` | 3.0.4 | MIT | arayüz |
| `merge-stream` | 2.0.0 | MIT | arayüz |
| `methods` | 1.1.2 | MIT | DEMA |
| `metro` | 0.84.4 | MIT | arayüz |
| `metro-babel-transformer` | 0.84.4 | MIT | arayüz |
| `metro-cache` | 0.84.4 | MIT | arayüz |
| `metro-cache-key` | 0.84.4 | MIT | arayüz |
| `metro-config` | 0.84.4 | MIT | arayüz |
| `metro-core` | 0.84.4 | MIT | arayüz |
| `metro-file-map` | 0.84.4 | MIT | arayüz |
| `metro-minify-terser` | 0.84.4 | MIT | arayüz |
| `metro-resolver` | 0.84.4 | MIT | arayüz |
| `metro-runtime` | 0.84.4 | MIT | arayüz |
| `metro-source-map` | 0.84.4 | MIT | arayüz |
| `metro-symbolicate` | 0.84.4 | MIT | arayüz |
| `metro-transform-plugins` | 0.84.4 | MIT | arayüz |
| `metro-transform-worker` | 0.84.4 | MIT | arayüz |
| `micromatch` | 4.0.8 | MIT | arayüz |
| `mime` | 1.6.0 | MIT | arayüz, DEMA |
| `mime-db` | 1.52.0 | MIT | arayüz, site, DEMA |
| `mime-db` | 1.54.0 | MIT | arayüz |
| `mime-types` | 2.1.35 | MIT | arayüz, site, DEMA |
| `mime-types` | 3.0.2 | MIT | arayüz |
| `mimic-fn` | 1.2.0 | MIT | arayüz |
| `min-indent` | 1.0.1 | MIT | arayüz |
| `minimatch` | 10.2.5 | BlueOak-1.0.0 | arayüz |
| `minipass` | 7.1.3 | BlueOak-1.0.0 | arayüz |
| `mkdirp` | 1.0.4 | MIT | arayüz |
| `motion` | 12.38.0 | MIT | DEMA |
| `motion-dom` | 12.38.0 | MIT | DEMA |
| `motion-utils` | 12.36.0 | MIT | DEMA |
| `ms` | 2.0.0 | MIT | arayüz, DEMA |
| `ms` | 2.1.3 | MIT | arayüz, site, DEMA |
| `multitars` | 1.0.0 | MIT | arayüz |
| `nanoid` | 3.3.12 | MIT | arayüz |
| `negotiator` | 0.6.3 | MIT | arayüz, DEMA |
| `negotiator` | 0.6.4 | MIT | arayüz |
| `negotiator` | 1.0.0 | MIT | arayüz |
| `node-domexception` | 1.0.0 | MIT | DEMA |
| `node-fetch` | 2.7.0 | MIT | arayüz |
| `node-fetch` | 3.3.2 | MIT | DEMA |
| `node-forge` | 1.4.0 | (BSD-3-Clause OR GPL-2.0) | arayüz |
| `node-int64` | 0.4.0 | MIT | arayüz |
| `node-releases` | 2.0.37 | MIT | DEMA |
| `node-releases` | 2.0.46 | MIT | arayüz |
| `npm-package-arg` | 11.0.3 | ISC | arayüz |
| `nth-check` | 2.1.1 | BSD-2-Clause | arayüz |
| `nullthrows` | 1.1.1 | MIT | arayüz |
| `oauth-sign` | 0.9.0 | Apache-2.0 | site |
| `ob1` | 0.84.4 | MIT | arayüz |
| `object-assign` | 4.1.1 | MIT | arayüz |
| `object-inspect` | 1.13.4 | MIT | site, DEMA |
| `on-finished` | 2.3.0 | MIT | arayüz |
| `on-finished` | 2.4.1 | MIT | arayüz, DEMA |
| `on-headers` | 1.1.0 | MIT | arayüz |
| `onetime` | 2.0.1 | MIT | arayüz |
| `open` | 7.4.2 | MIT | arayüz |
| `ora` | 3.4.0 | MIT | arayüz |
| `p-retry` | 4.6.2 | MIT | DEMA |
| `parse-png` | 2.1.0 | MIT | arayüz |
| `parseurl` | 1.3.3 | MIT | arayüz, DEMA |
| `path-key` | 3.1.1 | MIT | arayüz |
| `path-parse` | 1.0.7 | MIT | arayüz |
| `path-scurry` | 2.0.2 | BlueOak-1.0.0 | arayüz |
| `path-to-regexp` | 0.1.13 | MIT | DEMA |
| `paths-js` | 0.4.11 | Apache-2.0 | arayüz |
| `picocolors` | 1.1.1 | ISC | arayüz, DEMA |
| `picomatch` | 2.3.2 | MIT | arayüz |
| `picomatch` | 4.0.4 | MIT | arayüz |
| `plist` | 3.1.1 | MIT | arayüz |
| `pngjs` | 3.4.0 | MIT | arayüz |
| `point-in-polygon` | 1.1.0 | MIT | arayüz |
| `postcss` | 8.5.15 | MIT | arayüz |
| `postcss-value-parser` | 4.2.0 | MIT | arayüz |
| `postman-request` | 2.88.1-postman.48 | Apache-2.0 | site |
| `pretty-format` | 29.7.0 | MIT | arayüz |
| `proc-log` | 4.2.0 | ISC | arayüz |
| `progress` | 2.0.3 | MIT | arayüz |
| `promise` | 7.3.1 | MIT | arayüz |
| `promise` | 8.3.0 | MIT | arayüz |
| `prompts` | 2.4.2 | MIT | arayüz |
| `protobufjs` | 7.5.4 | BSD-3-Clause | DEMA |
| `proxy-addr` | 2.0.7 | MIT | DEMA |
| `psl` | 1.15.0 | MIT | site |
| `punycode` | 2.3.1 | MIT | site |
| `qs` | 6.14.2 | BSD-3-Clause | site, DEMA |
| `query-string` | 7.1.3 | MIT | arayüz |
| `querystringify` | 2.2.0 | MIT | site |
| `queue` | 6.0.2 | MIT | arayüz |
| `range-parser` | 1.2.1 | MIT | arayüz, DEMA |
| `raw-body` | 2.5.3 | MIT | DEMA |
| `react` | 19.2.3 | MIT | arayüz |
| `react` | 19.2.5 | MIT | DEMA |
| `react` | 19.2.7 | MIT | site |
| `react-devtools-core` | 6.1.5 | MIT | arayüz |
| `react-dom` | 19.2.3 | MIT | arayüz |
| `react-dom` | 19.2.5 | MIT | DEMA |
| `react-dom` | 19.2.7 | MIT | site |
| `react-fast-compare` | 3.2.2 | MIT | arayüz |
| `react-freeze` | 1.0.4 | MIT | arayüz |
| `react-i18next` | 17.0.15 | MIT | arayüz, site |
| `react-is` | 18.3.1 | MIT | arayüz |
| `react-is` | 19.2.7 | MIT | arayüz |
| `react-native` | 0.85.3 | MIT | arayüz |
| `react-native-chart-kit` | 6.12.3 | MIT | arayüz |
| `react-native-drawer-layout` | 4.2.5 | MIT | arayüz |
| `react-native-safe-area-context` | 5.7.0 | MIT | arayüz |
| `react-native-screens` | 4.25.2 | MIT | arayüz |
| `react-native-svg` | 15.15.4 | MIT | arayüz |
| `react-native-web` | 0.21.2 | MIT | arayüz |
| `react-native-webview` | 13.16.1 | MIT | arayüz |
| `react-native-zeroconf` | 0.14.0 | MIT | arayüz |
| `react-refresh` | 0.14.2 | MIT | arayüz |
| `react-refresh` | 0.18.0 | MIT | DEMA |
| `react-remove-scroll` | 2.7.2 | MIT | arayüz |
| `react-remove-scroll-bar` | 2.3.8 | MIT | arayüz |
| `react-router` | 7.18.1 | MIT | site |
| `react-router-dom` | 7.18.1 | MIT | site |
| `react-style-singleton` | 2.2.3 | MIT | arayüz |
| `redent` | 3.0.0 | MIT | arayüz |
| `regenerate` | 1.4.2 | MIT | arayüz |
| `regenerate-unicode-properties` | 10.2.2 | MIT | arayüz |
| `regenerator-runtime` | 0.13.11 | MIT | arayüz |
| `regexpu-core` | 6.4.0 | MIT | arayüz |
| `regjsgen` | 0.8.0 | MIT | arayüz |
| `regjsparser` | 0.13.1 | BSD-2-Clause | arayüz |
| `require-directory` | 2.1.1 | MIT | arayüz |
| `requires-port` | 1.0.0 | MIT | site |
| `resolve` | 1.22.12 | MIT | arayüz |
| `resolve-from` | 5.0.0 | MIT | arayüz |
| `resolve-workspace-root` | 2.0.1 | MIT | arayüz |
| `restore-cursor` | 2.0.0 | MIT | arayüz |
| `retry` | 0.13.1 | MIT | DEMA |
| `safe-buffer` | 5.2.1 | MIT | arayüz, site, DEMA |
| `safer-buffer` | 2.1.2 | MIT | site, DEMA |
| `sax` | 1.6.0 | BlueOak-1.0.0 | arayüz |
| `scheduler` | 0.27.0 | MIT | arayüz, site, DEMA |
| `semver` | 6.3.1 | ISC | arayüz, DEMA |
| `semver` | 7.8.1 | ISC | arayüz |
| `send` | 0.19.2 | MIT | arayüz, DEMA |
| `serialize-error` | 2.1.0 | MIT | arayüz |
| `serve-static` | 1.16.3 | MIT | arayüz, DEMA |
| `server-only` | 0.0.1 | MIT | arayüz |
| `set-cookie-parser` | 2.7.2 | MIT | site |
| `setimmediate` | 1.0.5 | MIT | arayüz |
| `setprototypeof` | 1.2.0 | ISC | arayüz, DEMA |
| `sf-symbols-typescript` | 2.2.0 | MIT | arayüz |
| `shallowequal` | 1.1.0 | MIT | arayüz |
| `shebang-command` | 2.0.0 | MIT | arayüz |
| `shebang-regex` | 3.0.0 | MIT | arayüz |
| `shell-quote` | 1.8.4 | MIT | arayüz |
| `side-channel` | 1.1.0 | MIT | DEMA |
| `side-channel` | 1.1.1 | MIT | site |
| `side-channel-list` | 1.0.1 | MIT | site, DEMA |
| `side-channel-map` | 1.0.1 | MIT | site, DEMA |
| `side-channel-weakmap` | 1.0.2 | MIT | site, DEMA |
| `signal-exit` | 3.0.7 | ISC | arayüz |
| `simple-plist` | 1.3.1 | MIT | arayüz |
| `simple-swizzle` | 0.2.4 | MIT | arayüz |
| `sisteransi` | 1.0.5 | MIT | arayüz |
| `slugify` | 1.6.9 | MIT | arayüz |
| `smart-buffer` | 4.2.0 | MIT | site |
| `socks` | 2.8.9 | MIT | site |
| `socks-proxy-agent` | 8.0.5 | MIT | site |
| `source-map` | 0.5.7 | BSD-3-Clause | arayüz |
| `source-map` | 0.6.1 | BSD-3-Clause | arayüz |
| `source-map-js` | 1.2.1 | BSD-3-Clause | arayüz, DEMA |
| `source-map-support` | 0.5.21 | MIT | arayüz |
| `split-on-first` | 1.1.0 | MIT | arayüz |
| `sshpk` | 1.18.0 | MIT | site |
| `stackframe` | 1.3.4 | MIT | arayüz |
| `stacktrace-parser` | 0.1.11 | MIT | arayüz |
| `standard-navigation` | 0.0.5 | MIT | arayüz |
| `statuses` | 1.5.0 | MIT | arayüz |
| `statuses` | 2.0.2 | MIT | arayüz, DEMA |
| `stream-buffers` | 2.2.0 | Unlicense | arayüz |
| `stream-length` | 1.0.2 | WTFPL | site |
| `strict-uri-encode` | 2.0.0 | MIT | arayüz |
| `string-width` | 4.2.3 | MIT | arayüz |
| `strip-ansi` | 5.2.0 | MIT | arayüz |
| `strip-ansi` | 6.0.1 | MIT | arayüz |
| `strip-indent` | 3.0.0 | MIT | arayüz |
| `structured-headers` | 0.4.1 | MIT | arayüz |
| `styleq` | 0.1.3 | MIT | arayüz |
| `supports-color` | 5.5.0 | MIT | arayüz |
| `supports-color` | 7.2.0 | MIT | arayüz |
| `supports-color` | 8.1.1 | MIT | arayüz |
| `supports-hyperlinks` | 2.3.0 | MIT | arayüz |
| `supports-preserve-symlinks-flag` | 1.0.0 | MIT | arayüz |
| `tagged-tag` | 1.0.0 | MIT | arayüz |
| `tailwindcss` | 4.2.2 | MIT | DEMA |
| `tapable` | 2.3.2 | MIT | DEMA |
| `terminal-link` | 2.1.1 | MIT | arayüz |
| `terser` | 5.48.0 | BSD-2-Clause | arayüz |
| `throat` | 5.0.0 | MIT | arayüz |
| `tinyglobby` | 0.2.17 | MIT | arayüz |
| `tmpl` | 1.0.5 | BSD-3-Clause | arayüz |
| `to-regex-range` | 5.0.1 | MIT | arayüz |
| `toidentifier` | 1.0.1 | MIT | arayüz, DEMA |
| `toqr` | 0.1.1 | MIT | arayüz |
| `tr46` | 0.0.3 | MIT | arayüz |
| `tslib` | 2.8.1 | 0BSD | arayüz, site, DEMA |
| `tweetnacl` | 0.14.5 | Unlicense | site |
| `type-fest` | 0.21.3 | (MIT OR CC0-1.0) | arayüz |
| `type-fest` | 0.7.1 | (MIT OR CC0-1.0) | arayüz |
| `type-fest` | 5.7.0 | (MIT OR CC0-1.0) | arayüz |
| `type-is` | 1.6.18 | MIT | DEMA |
| `ua-parser-js` | 1.0.41 | MIT | arayüz |
| `undici-types` | 6.21.0 | MIT | DEMA |
| `undici-types` | 8.3.0 | MIT | arayüz |
| `unicode-canonical-property-names-ecmascript` | 2.0.1 | MIT | arayüz |
| `unicode-match-property-ecmascript` | 2.0.0 | MIT | arayüz |
| `unicode-match-property-value-ecmascript` | 2.2.1 | MIT | arayüz |
| `unicode-property-aliases-ecmascript` | 2.2.0 | MIT | arayüz |
| `universalify` | 0.2.0 | MIT | site |
| `unpipe` | 1.0.0 | MIT | arayüz, DEMA |
| `update-browserslist-db` | 1.2.3 | MIT | arayüz, DEMA |
| `url-parse` | 1.5.10 | MIT | site |
| `use-callback-ref` | 1.3.3 | MIT | arayüz |
| `use-latest-callback` | 0.2.6 | MIT | arayüz |
| `use-sidecar` | 1.1.3 | MIT | arayüz |
| `use-sync-external-store` | 1.7.0 | MIT | arayüz, site |
| `utils-merge` | 1.0.1 | MIT | arayüz, DEMA |
| `uuid` | 7.0.3 | MIT | arayüz |
| `uuid` | 8.3.2 | MIT | site |
| `validate-npm-package-name` | 5.0.1 | ISC | arayüz |
| `vary` | 1.1.2 | MIT | arayüz, DEMA |
| `vaul` | 1.1.2 | MIT | arayüz |
| `verror` | 1.10.0 | MIT | site |
| `vlq` | 1.0.1 | MIT | arayüz |
| `walker` | 1.0.8 | Apache-2.0 | arayüz |
| `warn-once` | 0.1.1 | MIT | arayüz |
| `wcwidth` | 1.0.1 | MIT | arayüz |
| `web-streams-polyfill` | 3.3.3 | MIT | DEMA |
| `webidl-conversions` | 3.0.1 | BSD-2-Clause | arayüz |
| `whatwg-fetch` | 3.6.20 | MIT | arayüz |
| `whatwg-url` | 5.0.0 | MIT | arayüz |
| `whatwg-url-minimum` | 0.1.2 | MIT | arayüz |
| `which` | 2.0.2 | ISC | arayüz |
| `wrap-ansi` | 7.0.0 | MIT | arayüz |
| `ws` | 7.5.11 | MIT | arayüz |
| `ws` | 8.20.0 | MIT | DEMA |
| `ws` | 8.21.0 | MIT | arayüz |
| `xcode` | 3.0.1 | Apache-2.0 | arayüz |
| `xml2js` | 0.6.0 | MIT | arayüz |
| `xmlbuilder` | 11.0.1 | MIT | arayüz |
| `xmlbuilder` | 15.1.1 | MIT | arayüz |
| `y18n` | 5.0.8 | ISC | arayüz |
| `yallist` | 3.1.1 | ISC | arayüz, DEMA |
| `yaml` | 2.9.0 | ISC | arayüz |
| `yargs` | 17.7.2 | MIT | arayüz |
| `yargs-parser` | 21.1.1 | ISC | arayüz |
| `zod` | 3.25.76 | MIT | arayüz |
| `zxing-wasm` | 3.0.3 | MIT | arayüz |
