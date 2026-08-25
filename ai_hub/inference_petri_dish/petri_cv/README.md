# petri_cv

**Her petri kuyucuğunun** kabin frame **(x, y, z) mm koordinatını** çıkarır (kedi'deki 10 organ koord gibi), HSV ile kuyucuk içinde mavi kanser olup olmadığını sınıflar (kanser/sağlıklı), ve [`../../inference_em_petri/inference_em_petri.py`](../../inference_em_petri/inference_em_petri.py) (BaggingRegressor, R²=0.9849) modeline besleyerek **her kuyucuk için ayrı** PEMF sürücü parametreleri üretir.

**Kuyucuk tespiti** = eğitilmiş **YOLO11m-seg** modeli (mAP50=0.984, mAP50-95=0.961, 22.3M param) — model yolu: [`../yolo11m-seg.pt`](../yolo11m-seg.pt) (aynı klasör).

Kabin sistemi [`inference_cat_organ`](../../inference_cat_organ/) ile **birebir aynı** pattern (ArUco DICT_5X5_100 + solvePnP).

---

## Mimari (Kedi Pattern'i Birebir)

| Bileşen | Kedi (`inference_cat_organ`) | Petri (`petri_cv`) |
|---|---|---|
| **Detection AI** | YOLOv8m-seg + RTMPose 39-landmark | **YOLO11m-seg** |
| Model yolu | `models/cat_*.pt` | [`../yolo11m-seg.pt`](../yolo11m-seg.pt) |
| Performans | mAP@50=0.866, OKS=0.94 | **mAP50=0.984, mAP50-95=0.961** |
| **Hedef nokta** | **10 organ (kalp, böbrek...)** | **N kuyucuk (W1, W2, ...)** |
| Çıktı x,y,z | 10 organ cabin frame mm | **N kuyucuk cabin frame mm** |
| Kalibrasyon | ArUco DICT_5X5_50 + solvePnP | **ArUco DICT_5X5_100 + solvePnP** |
| Cabin pattern | `cabin_config.yaml` | `cabin_config.yaml` (aynı) |
| Predictor | Hibrit Çok-Başlı | **PetriPredictor** (BaggingRegressor R²=0.9849) |

---

## Algoritma — Kedi Multi-Organ Pattern'ine Paralel

```
RGB görüntü
   ↓
1. cv2.undistort  (K + D, kalibrasyon yoksa approx)
   ↓
2. ArUco PnP — Kedi paterni
      Marker varsa → solvePnP → CabinPose (TAM 6-DOF)
   ↓
3. YOLO11m-seg KUYUCUK DETECTION (ZORUNLU)
      → list[PetriDetection]  (N kuyucuk: bbox + mask + conf)
      → Sıralama: sol-üst → sağ-alt (W1, W2, W3, ...)
   ↓
4. KALİBRASYON mm/px (referans: en büyük kuyucuk)
      A) ArUco varsa → ray-plane intersection (PnP, kedi gibi)
      B) --petri-diameter-cm × 10 / bbox_max = mm/px
      C) Default → piksel modu
   ↓
5. HER KUYUCUK İÇİN: HSV mavi piksel sayısı
      • cancer_blue HSV (S≥45, V≥40)
      • YOLO mask içinde piksel say
      • >= cancer_pixel_threshold (default 30) → kanser
      • Aksi → sağlıklı
   ↓
6. HER KUYUCUĞA AYRI: piksel → cabin mm + PetriPredictor
      ArUco modu: ray-plane intersection
      Diameter modu: (px − ref_centroid) × mm/px
      PetriPredictor.predict(x,y,z, organ_id, B, duty)
      → D[7] duty, P[7] faz, E_healthy, E_cancer, E_avg
   ↓
7. JSON + 7-panel TR/EN overlay (her kuyucuk W1, W2, ...)
```

**Kedi paralel:**
- Kedi: 1 görüntü → 10 organ → her organa x,y,z + tahmin
- Petri: 1 görüntü → N kuyucuk → her kuyucuğa x,y,z + tahmin

---

## Çıktı Yapısı (Kedi Pattern)

```
results/<image_stem>/
├── result.json                   ← schema v3.0
├── tr/                           ← Türkçe 7 panel
│   ├── 01_input.jpg              ← orijinal
│   ├── 02_yolo_dets.jpg          ← YOLO N kuyucuk + W1..WN + conf
│   ├── 03_yolo_masks.jpg         ← YOLO mask renkli (kanser/sağlıklı)
│   ├── 04_classify.jpg           ← her kuyucuk W1: KANSER/SAĞLIKLI
│   ├── 05_local_coords.jpg       ← W1-WN cabin-frame mm koord
│   ├── 06_predictions.jpg        ← her kuyucuk D[7] bar + E_kanser
│   └── 07_combined.jpg           ← 6 panel 3×2 grid
└── en/                           ← aynı 7 panel İngilizce
```

### result.json şeması (v3.1)

```json
{
  "schema_version": "v3.1",                 // +R_matrix, pnp_fit, mask_xy, reliability
  "success": true,
  "cabin_id": "petri_helmholtz_v1",
  "image_name": "petri.jpg",
  "method": "aruco_pnp",                    // "aruco_pnp" / "petri_diameter" / "pixel"
  "mm_per_px": 0.0,                         // ArUco modunda 0 (ray-plane)
  "n_wells": 8, "n_cancer": 3, "n_healthy": 5,
  "cabin_pose": {
    "marker_id": 0,
    "tvec_mm": [-62.7, -62.7, 250.0],
    "reproj_error_px": 0.003
  },
  "camera_calib": {"K": [...], "D": [...], "approx": true},

  // -------- Kedi paterninden yeni alanlar (ArUco modunda dolu) --------
  "R_matrix": [                             // cabin <- marker rotation
    [+1.0000, +0.0000, -0.0000],
    [+0.0000, -1.0000, +0.0000],
    [-0.0000, -0.0000, -1.0000]
  ],
  "pnp_fit": {                              // kedi pnp_fit gibi
    "yaw_deg": 0.001,
    "pitch_deg": 0.002,
    "roll_deg": -179.998,
    "residual_px": 0.003,
    "marker_id": 0,
    "marker_pos_cabin_mm": [0.0, 0.0, -100.0],
    "rvec": [3.142, 0.0, 0.0]
  },

  "wells": [
    {
      "well_id": "W1",
      "organ_id": 1, "label": "cancer",
      "conf": 0.928,                        // YOLO confidence
      "reliability": 0.933,                 // conf × solidity (kedi reliability)
      "centroid_px": [467, 253],
      "centroid_cabin_mm": [0.0, 0.0, 0.0],
      "centroid_cabin_cm": [0.0, 0.0, 0.0],
      "bbox_px": [368, 154, 196, 196],
      "area_px": 29633, "area_mm2": 1681.5,
      "n_cancer_pixels": 1245,
      "mask_xy": [                          // kontur (kedi segmentation.mask_xy)
        [504.0, 268.0], [502.0, 274.0], [470.0, 285.0], ...   // simplified ~24 nokta
      ],
      "D": [d1..d7], "P": [p1..p7],
      "E_healthy": 0.0001, "E_cancer": 0.1006
    },
    { "well_id": "W2", ... }
  ],
  "timing_ms": {"total": 2820, "yolo_detect": 2750, "predict_all": 60}
}
```

### Kedi `organs.json` Alanları ile Eşleşme

| Kedi (v2.1) | Petri (v3.1) | Açıklama |
|---|---|---|
| `organs.{id}.coord_cabin_cm` | `wells[i].centroid_cabin_cm` | Cabin frame koordinat |
| `organs.{id}.pixel_xy` | `wells[i].centroid_px` | Piksel koordinat |
| `organs.{id}.reliability` | **`wells[i].reliability`** | YOLO conf × mask solidity |
| `segmentation.mask_xy` | **`wells[i].mask_xy`** | Her kuyucuk için ayrı kontur |
| `pnp_fit.yaw_deg/pitch_deg/roll_deg` | **`pnp_fit.yaw/pitch/roll_deg`** | Euler açıları |
| `pnp_fit.residual_px` | **`pnp_fit.residual_px`** | solvePnP yeniden-projeksiyon |
| `R_matrix` | **`R_matrix`** | 3×3 rotation matrix |
| `t_vec` | `cabin_pose.tvec_mm` | Translation vector |

---

## Hızlı Kurulum

### 1. ArUco marker bas (opsiyonel)

```python
import cv2
d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)
cv2.imwrite("marker_id0.png", cv2.aruco.generateImageMarker(d, 0, 500))
```

5 cm × 5 cm yazdır, kabinin sol duvarına yapıştır. ArUco yoksa `--petri-diameter-cm` ile kalibrasyon.

### 2. Kamera kalibre et (opsiyonel — ArUco modunda)

```bash
python ../../inference_cat_organ/calibrate_camera.py \
    --images calib/ --pattern 9x6 --square-cm 2.5 \
    --output calib_petri_v1.npz
```

### 3. YAML düzenle

```bash
cp cabin_config_example.yaml cabin_config.yaml
```

| Alan | Açıklama |
|---|---|
| `cabin_id` | Sabit benzersiz ID |
| `aruco.real_cm` | ArUco yazıcı boyu (modu açıksa) |
| `camera.intrinsics_npz` | `calib_*.npz` (yoksa approx) |
| `segmentation.cancer_blue` | HSV mavi kanser (sıkı: S≥45, V≥40) |
| `phantom.achieved_B / duty_sum` | PetriPredictor parametreleri |

### 4. Çalıştır

```bash
cd inference/inference_petri_dish

# Tek görüntü (petri çapı = 5 cm)
python -m petri_cv.cli -c petri_cv/cabin_config.yaml \
    -i test.jpg --out results --petri-diameter-cm 5.0

# Klasör batch
python -m petri_cv.cli -c petri_cv/cabin_config.yaml \
    --batch test_img/ --out results --petri-diameter-cm 5.0

# YOLO conf eşiği yükselt:
python -m petri_cv.cli -c petri_cv/cabin_config.yaml \
    -i test.jpg --yolo-conf 0.5 --petri-diameter-cm 5.0

# CPU mode (GPU yoksa):
python -m petri_cv.cli -c petri_cv/cabin_config.yaml \
    -i test.jpg --yolo-device cpu --petri-diameter-cm 5.0

# Canlı kamera tek frame
python -m petri_cv.cli -c petri_cv/cabin_config.yaml \
    --camera 0 --out results
```

### CLI Flag'ler

| Flag | Default | Açıklama |
|---|---|---|
| `--petri-diameter-cm` | None | Petri çapı (cm) — kalibrasyon (ArUco yoksa) |
| `--yolo-conf` | 0.25 | YOLO confidence eşiği |
| `--yolo-iou` | 0.7 | YOLO IoU eşiği |
| `--yolo-imgsz` | 640 | YOLO inference boyut |
| `--yolo-device` | "0" | GPU device veya "cpu" |
| `--yolo-model` | auto | Özel YOLO model yolu |
| `--cancer-pixel-threshold` | 30 | Kuyucukta ≥N mavi piksel = kanser |
| `--lang` | both | tr / en / both |
| `--mqtt` | false | MQTT publish |
| `--quiet` | false | Sessiz mod |

### 3 Kalibrasyon Modu

| Mod | Tetiklenme | mm_per_px | area_mm2 hesabı |
|---|---|---|---|
| **`aruco_pnp`** | ArUco DICT_5X5_100 marker varsa | 0.0 | Contour cabin-frame integration (ray-plane) |
| **`petri_diameter`** | `--petri-diameter-cm` verilmiş | sabit | `area_px × mm_per_px²` |
| **`pixel`** | İkisi de yok | 1.0 | `area_px` (px = mm) |

---

## CLI Çıktı Örneği

```
[CABIN  ] cabin=petri_helmholtz_v1 aruco=DICT_5X5_100/5.0cm ...
[PETRI  ] diameter = 5.0 cm (None=piksel mod)
[YOLO   ] yolo11m-seg.pt conf=0.25 imgsz=640

[1/1] real_petri.jpg
  success               : True
  method                : petri_diameter
  n_wells               : 8           ← YOLO 8 kuyucuk
  n_cancer              : 8           ← 8 kanser (HSV mavi)
  n_healthy             : 0
  mm_per_px             : 0.2382
  total_ms              : 2806.7
    W1   [C] (  +0.0,   +0.0,  +0.0)mm  conf=0.92  E_c=0.1006  area=29633px
    W2   [C] ( +50.0,   -2.8,  +0.0)mm  conf=0.89  E_c=0.1006  area=27733px
    W3   [C] (  -2.0,  -38.6,  +0.0)mm  conf=0.92  E_c=0.1010  area=26264px
    W4   [C] ( +47.6,  -41.1,  +0.0)mm  conf=0.93  E_c=0.1016  area=24701px
    W5   [C] (  -5.1,  -75.6,  +0.0)mm  conf=0.92  E_c=0.1016  area=25659px
    W6   [C] ( +45.3,  -76.8,  +0.0)mm  conf=0.90  E_c=0.1016  area=23402px
    W7   [C] (  -3.7, -111.8,  +0.0)mm  conf=0.92  E_c=0.1020  area=24790px
    W8   [C] ( +44.8, -112.3,  +0.0)mm  conf=0.92  E_c=0.1020  area=22524px
  -> results/real_petri/
```

> `[C]` = Cancer (mavi var), `[H]` = Healthy (mavi yok).
> W1 origin (en büyük kuyucuk merkezi) → diğer kuyucuklar buna relative.

---

## Python API

```python
from petri_cv import PetriCvPipeline

pl = PetriCvPipeline("cabin_config.yaml",
                     petri_diameter_cm=5.0,
                     yolo_conf=0.25,
                     yolo_iou=0.7,
                     yolo_device="0",
                     cancer_pixel_threshold=30)   # >=30 mavi px = kanser
result, ctx = pl.process_file("test.jpg")

if result.success:
    print(f"Toplam kuyucuk: {result.n_wells}")
    print(f"Kanser: {result.n_cancer}, Sağlıklı: {result.n_healthy}")
    for w in result.wells:
        x, y, z = w.centroid_cabin_mm
        print(f"{w.well_id} [{w.label}] @ ({x:+.1f}, {y:+.1f}, {z:+.1f})mm  "
              f"conf={w.conf:.2f}  E_c={w.E_cancer:.4f}")
        # PEMF parametreleri
        print(f"   D[7]={w.D}")
        print(f"   P[7]={w.P}")

# 7-panel render
import cv2
panels_tr = pl.render_panels(ctx, result, lang="tr")
cv2.imwrite("combined_tr.jpg", panels_tr["07_combined"])
```

---

## 3 Çıktı Modu

| Mod | Komut | Tüketen |
|---|---|---|
| **CLI / JSON** | `python -m petri_cv.cli -i img.jpg` | dosya, manuel |
| **FastAPI** | `python -m petri_cv.api -c cabin.yaml` | web frontend, GUI |
| **MQTT** | YAML `output.mqtt.enabled: true` + `--mqtt` | ESP32-S3 broker |

---

## Klasör Yapısı

```
inference_petri_dish/
├── yolo11m-seg.pt              ← YOLO11m-seg model (22.3M, mAP50-95=0.961; büyük ağırlık → /models mount)
├── inference_petri_dish.py     ← YOLO standalone (mevcut)
├── plausibility.py             ← makullik denetimi: yanlış modül fotoğrafını (fantom/kedi) sessizce işlemeyi engeller
├── results/                    ← YOLO standalone çıktı
└── petri_cv/                   ← YOLO + ArUco + Predictor pipeline
    ├── __init__.py
    ├── cabin_config.py         ← YAML loader (kedi pattern)
    ├── cabin_config_example.yaml
    ├── coord_transform.py      ← ArUco PnP + piksel→cabin mm
    ├── petri_detector.py       ← YOLO11m-seg wrapper
    ├── color_segment.py        ← Petri mask içinde kanser HSV
    ├── render.py               ← 7-panel TR+EN overlay
    ├── pipeline.py             ← Uçtan uca orkestrasyon
    ├── cli.py / api.py / mqtt_publish.py
    ├── test_img/               ← örnek test görüntüleri
    └── results/                ← otomatik üretilir
```

---

## Bağımlılıklar

```bash
pip install opencv-python>=4.8 PyYAML>=6.0 numpy onnxruntime joblib pandas
pip install ultralytics>=8.0    # YOLO11m-seg
# opsiyonel:
pip install "fastapi[all]" uvicorn paho-mqtt>=2.0
```

---

## Yeniden Kullanılan Kod

| Kaynak | Amaç |
|---|---|
| [`yolo11m-seg.pt`](../yolo11m-seg.pt) | Petri detection (aynı klasör) |
| [`inference_petri_dish.py`](../inference_petri_dish.py) | YOLO standalone wrapper |
| [`calibrate_camera.py`](../../inference_cat_organ/calibrate_camera.py) | OpenCV checkerboard → K + D |
| [`lib/cabin_config.py`](../../inference_cat_organ/lib/cabin_config.py) | Cabin YAML pattern |
| [`lib/qr.py`](../../inference_cat_organ/lib/qr.py) | ArUco en küçük ID pattern |
| [`../../inference_em_petri/inference_em_petri.py`](../../inference_em_petri/inference_em_petri.py) | PetriPredictor BaggingRegressor R²=0.9849 |
