# ai_hub/ — Teşhis Modeli Kayıt Defteri (inference KODU + gömülü küçük ağırlıklar + test girdileri)

Her teşhis modelinin **inference kodunun** evi. **Küçük** modeller (tabular/ONNX/scaler) buraya gömülüdür;
**büyük** görüntü/YOLO/histopatoloji ağırlıkları burada YOKtur → `/models` mount'undan
([`../release_assets/ai_models`](../release_assets/ai_models/)) çözülür. Runtime çözümü
[`../utils/model_downloader.py`](../apps/backend/utils/README.md) ile **yalnız yerel** (Hugging Face indirme yok).

## Bu klasördeki mevcut kılavuzlar
| Dosya | İçerik |
|---|---|
| `KABIN_KURULUM_KILAVUZU.md` | Kabin / ArUco koordinat-kalibrasyon kurulumu — bugün **kedi** AI Pro hattı (petri / fantom için kabin konumu artık **sabit düzlem kalibrasyonundan**, aşağıda `cv_ortak/`) |
| `PEMF_ArUco_Marker_5X5_50_ID0_10cm_A4.pdf` / `.png` | Yazdırılabilir ArUco fiducial (kabin kalibrasyonu) — kenar **10,0 cm** (saha ölçüsü 2026-10-14), `aruco.real_cm` ile AYNI olmak ZORUNDA (yanlış kenar = sessiz ölçek hatası); üretim: `python scripts/kabin_marker_a4.py` (2026-09-09 – 10-14 arası üretilen 15 cm sayfa kaldırıldı) |
| `PEMF_AI_Test_Girdileri/00_README_OKU.txt` | Her model için **gerçek test girdisi** + beklenen çıktı haritası (E2E test) |
| `inference_human_kidney_disease/README.md` | CKD (24 klinik özellik) modeli notu |
| `inference_em_fantom/phantom_cv_v3/`, `inference_petri_dish/petri_cv_v2/` | Klasik-CV pipeline paketleri — Çağlar Hoca'nın fantom v3 / petri v2'si (AI-2, 2026-10-12; v1 `phantom_cv` / `petri_cv` emekli) |

## Model alt-klasörleri (her birinde `inference_*.py`)
| Klasör | Model / rol |
|---|---|
| `cat_landmark/` | YOLO-pose FGS ağrı skoru (`compute_fgs`) |
| `cat_segmentation/` | YOLOv8m-seg kedi segmentasyonu |
| `cat_thermal/` | GhostNetV2 ONNX termal ikili sağlık |
| `cat_disease/` | Semptom→hastalık; **`XGBoost.pkl` (53 MB, gömülü)** + encoder/scaler |
| `feline_reticulocytes/` | YOLOv8s hücre sayımı |
| `inference_cat_sound/` | librosa mel + EfficientNet_Lite0 ONNX (10 sınıf) |
| `inference_cat_organ/` | **10-organ 3B lokalizasyon** (3 ONNX `/models`'ten) + `lib/` (pipeline/render/geometry/pose/qr/camera); **veteriner modu AI-Pro** hedef konumu bunu kullanır (`KediSaglayici`); sürüş faz / duty'si ODAK'tan, kedi sürüşü bayrakla KAPALI |
| `inference_em_fantom/` | Fantom-tümör klasik-CV (`phantom_cv_v3`, tümör tespiti — AI Pro hedefi) + hocanın BiLSTM doz modeli (`PhantomPredictor`; **sürüş kaynağı DEĞİL**, silinmedi) |
| `inference_em_petri/` + `inference_petri_dish/` | Petri kuyu tespiti (`inference_petri_dish`: YOLO11m-seg + `plate_grid` / Hough + ECC; yarı dolu plaka görülen kuyulardan oturtulur) — AI Pro hedefi. `inference_em_petri` hocanın BaggingRegressor doz modeli (**sürüş kaynağı DEĞİL**, silinmedi). Kabin kamerasında YOLO aday bulamıyorsa kare toplama: `scripts/petri_kare_topla.py` |
| `inference_human_kidney_ct/` | YOLOv8s ONNX (taş/kist/normal) |
| `inference_human_kidney_disease/` | **Gömülü ONNX zoo** (CatBoost/ExtraTrees/LogReg/RandomForest) + preprocessor — CKD |
| `inference_human_kidney_rna/` | RNA-seq KIRC MLP (`mlp_medium_kirc.onnx` gömülü) + scaler |
| `inference_renal_histopath_kmc/` | Grade 0–4 histopatoloji (ağırlık `/models`'ten) |
| `inference_paper_dilek_hoca/` | **Yara Kapanma (Scratch)**: CPN hücre segmentasyonu + TScratch closure metrikleri (872MB PT `/models`'ten; `cell/` paketi ✅ teslim alındı 2026-08-26 — `inference_paper_dilek_hoca/cell/`, modül README'sine bakın) |
| `em_kedi/` | Hocanın kedi bobin-sürme BiLSTM'i (x/y/z/organ → duty/phase); **sürüş kaynağı DEĞİL** (ODAK ayarı yoksa kedi sürülmez), silinmedi; scaler'lar gömülü |
| `odak/` | **ODAK — AI Pro faz + duty'si** (petri / fantom / kedi): `alan.py` (kabin ↔ CST TEK dönüşüm yeri, bobin alanı, duty → tepe akım, zaman domeni doz) · `model.py` (ONNX KNN k = 1 + yerel alan; 5 kip × frekans) · `oneri.py` (plan + fizik denetimi + kuyu haritası) · `kuyu_e.py` (kuyu sıvısı içindeki E). Alan tablosu + modeller **veteriner / araştırma model paketlerinde** (açık depoda yok); kalibrasyon veri kökünde, tezgâhta MLX ile ölçülür. Fizik denetimi karar vermez, denetler: doz sapması > %10, kalibrasyon yok / eski, hedef kabin dışı → SÜRMEZ |
| `cv_ortak/` | Ortak görüntü katmanı: `sabit_duzlem.py` (**ArUco'suz sabit düzlem kalibrasyonu** — üst kapakta sabit kamera, iki konumlu ortak çözüm, piksel → kabin mm), `coord_transform.py` / `cabin_config.py` (ArUco yolu, kedi hattı), `pemf_kapisi.py` (sürüş kapısı nedenleri), kamera iç parametreleri `kalibrasyon/` |

## Gömme deseni
- **Gömülü** (kaynakta): küçük tabular/ONNX (kidney_disease, kidney_rna, cat_disease XGBoost) + tüm `scaler_*.pkl`.
- **Mount'tan** (`/models`): büyük görüntü/YOLO/histopatoloji/ses ağırlıkları.

## Sistemdeki yeri
- Backend içi: [`../servers/ai_router.py`](../apps/backend/servers/README.md) bu sınıfları lazy yükler (tek-EXE, offline).
- Ayrı GPU: [`../ai_service/`](../ai_service/README.md) aynı `ai_hub.*` kodunu import edip CUDA'da servis eder.

---
İlgili: [ai_service/ (GPU)](../ai_service/README.md) · [release_assets/ (ağırlıklar)](../release_assets/ai_models/) · [ai/ (öneri katmanı)](../ai/README.md)
