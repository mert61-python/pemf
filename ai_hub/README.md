# ai_hub/ — Teşhis Modeli Kayıt Defteri (inference KODU + gömülü küçük ağırlıklar + test girdileri)

Her teşhis modelinin **inference kodunun** evi. **Küçük** modeller (tabular/ONNX/scaler) buraya gömülüdür;
**büyük** görüntü/YOLO/histopatoloji ağırlıkları burada YOKtur → `/models` mount'undan
([`../release_assets/ai_models`](../release_assets/README.md)) çözülür. Runtime çözümü
[`../utils/model_downloader.py`](../utils/README.md) ile **yalnız yerel** (Hugging Face indirme yok).

## Bu klasördeki mevcut kılavuzlar
| Dosya | İçerik |
|---|---|
| `KABIN_KURULUM_KILAVUZU.md` | Kabin / ArUco koordinat-kalibrasyon kurulumu (AI-Pro 3B lokalizasyon) |
| `PEMF_ArUco_Marker_5X5_50_ID0_10cm.png` | Yazdırılabilir ArUco fiducial (kabin kalibrasyonu) |
| `PEMF_AI_Test_Girdileri/00_README_OKU.txt` | Her model için **gerçek test girdisi** + beklenen çıktı haritası (E2E test) |
| `inference_human_kidney_disease/README.md` | CKD (24 klinik özellik) modeli notu |
| `inference_em_fantom/phantom_cv/README.md`, `inference_petri_dish/petri_cv/README.md` | Klasik-CV pipeline paketleri |

## Model alt-klasörleri (her birinde `inference_*.py`)
| Klasör | Model / rol |
|---|---|
| `cat_landmark/` | YOLO-pose FGS ağrı skoru (`compute_fgs`) |
| `cat_segmentation/` | YOLOv8m-seg kedi segmentasyonu |
| `cat_thermal/` | GhostNetV2 ONNX termal ikili sağlık |
| `cat_disease/` | Semptom→hastalık; **`XGBoost.pkl` (53 MB, gömülü)** + encoder/scaler |
| `feline_reticulocytes/` | YOLOv8s hücre sayımı |
| `inference_cat_sound/` | librosa mel + EfficientNet_Lite0 ONNX (10 sınıf) |
| `inference_cat_organ/` | **10-organ 3B lokalizasyon** (3 ONNX `/models`'ten) + `lib/` (pipeline/render/geometry/pose/qr/camera); AI-Pro bunu kullanır |
| `inference_em_fantom/` | Fantom-tümör klasik-CV + BiLSTM (`PhantomPredictor`) |
| `inference_em_petri/` + `inference_petri_dish/` | Petri-kuyu YOLO11m-seg + BaggingRegressor |
| `inference_human_kidney_ct/` | YOLOv8s ONNX (taş/kist/normal) |
| `inference_human_kidney_disease/` | **Gömülü ONNX zoo** (CatBoost/ExtraTrees/LogReg/RandomForest) + preprocessor — CKD |
| `inference_human_kidney_rna/` | RNA-seq KIRC MLP (`mlp_medium_kirc.onnx` gömülü) + scaler |
| `inference_renal_histopath_kmc/` | Grade 0–4 histopatoloji (ağırlık `/models`'ten) |
| `em_kedi/` | AI-Pro bobin-sürme BiLSTM (x/y/z/organ → duty/phase); scaler'lar gömülü |

## Gömme deseni
- **Gömülü** (kaynakta): küçük tabular/ONNX (kidney_disease, kidney_rna, cat_disease XGBoost) + tüm `scaler_*.pkl`.
- **Mount'tan** (`/models`): büyük görüntü/YOLO/histopatoloji/ses ağırlıkları.

## Sistemdeki yeri
- Backend içi: [`../servers/ai_router.py`](../servers/README.md) bu sınıfları lazy yükler (tek-EXE, offline).
- Ayrı GPU: [`../ai_service/`](../ai_service/README.md) aynı `ai_hub.*` kodunu import edip CUDA'da servis eder.

---
İlgili: [ai_service/ (GPU)](../ai_service/README.md) · [release_assets/ (ağırlıklar)](../release_assets/README.md) · [ai/ (öneri katmanı)](../ai/README.md)
