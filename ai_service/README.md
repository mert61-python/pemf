# ai_service/ — Bağımsız GPU (CUDA) Inference Mikroservisi

`ai_hub` inference kodunu **GPU'da** servis eden ayrı bir FastAPI uygulaması. `onnxruntime-CUDA` +
otomatik **CPU fallback**. Çekirdek backend bunu içeriden çağırır (core→GPU çağrıları auth-muaf;
ör. AI-Pro kapalı-döngü sürücüsü `/infer/em_kedi`'yi çağırır). İstemci tarafı: [`../servers/ai_client.py`](../servers/README.md).

## Dosyalar
| Dosya | Görev |
|---|---|
| `app.py` | FastAPI `PEMF AI Service (GPU) v0.3.0` — tüm uçlar, upload-boyut + eşzamanlılık DoS middleware, sertleştirilmiş ffmpeg (ses), genel hata yakalayıcı |
| `predictors.py` | Lazy-yükle + thread-safe `REGISTRY` (13 predictor); her birini `ai_hub` sınıfına ve `MODELS_DIR` altındaki ağırlığına bağlar |
| `gpu.py` | Tek-kaynak GPU algılama: torch-CUDA + **ayrı** onnxruntime-CUDA probe (Blackwell/sm_120 farkında); `torch_device()`/`yolo_device()`/`onnx_providers()`, hepsi cache'li, hata→CPU |
| `requirements-ai.txt` | Kendi bağımlılıkları: `onnxruntime-gpu==1.19.2`, `ultralytics`, `librosa`, `xgboost`, `fastapi`… (torch/torchvision **cu128** burada DEĞİL — Dockerfile'da ayrı kurulur) |

## Çalıştırma / dağıtım
- **Docker:** [`../docker/Dockerfile.ai`](../docker/DOCKER_README.md) + `docker-compose.ai.yml`.
  `CMD uvicorn ai_service.app:app --host 0.0.0.0 --port 8100` · `EXPOSE 8100`.
- Temel imaj `nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04`, torch 2.7.1 **cu128**, `--gpus all`,
  ağırlıklar salt-okunur mount: `../release_assets/ai_models:/models` (`PEMF_AI_MODELS_DIR=/models`).

## Uçlar (port 8100)
- Keşif/sağlık: `GET /health`, `/models`, `/infer/models`, `/benchmark`.
- **14 `POST /infer/*`**: `histopath`, `sound`, `kidney_ct`, `segmentation`, `landmark`, `thermal`,
  `cat_organ`, `disease`, `kidney_disease`, `rna`, `reticulocytes`, `em_fantom`, `em_petri`, `em_kedi`.
  (`kidney_disease` ucu `REGISTRY` dışıdır: gömülü ONNX'i `predict_one` ile doğrudan çağırır → `predictors.py` 13 predictor + bu 1 uç = 14.)

## ⚠️ Dikkat
- **GPU = RTX 5090 (Blackwell)** → CUDA **12.8 + PyTorch cu128 ŞART**; eski sürüm Docker AI'yı çökertir.
- Bu servis opsiyoneldir: tek-EXE backend AI'yı gömülü çalıştırabilir; mikroservis GPU ölçekleme içindir (bkz. [`../docker/DOCKER_README.md`](../docker/DOCKER_README.md)).

---
İlgili: [ai_hub/ (model kodu)](../ai_hub/README.md) · [release_assets/ (ağırlıklar)](../release_assets/README.md) · [docker/](../docker/DOCKER_README.md) · [servers/ai_client](../servers/README.md)
