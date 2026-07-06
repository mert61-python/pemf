# phantom_cv

**Sentetik böbrek fantom modelinde** mavi tümör odaklarını tespit eder, kalibre **(x, y, z) mm koordinatlarını** çıkarır ve [`inference_em_fantom.py`](../inference_em_fantom.py) (BiLSTM_XXL_Raw, R²=0.9955) modeline besleyerek PEMF sürücü parametrelerini üretir.

Kabin sistemi [`inference_cat_organ`](../../inference_cat_organ/) ile **birebir aynı** pattern.

---

## Sentetik Böbrek Fantom Modeli

**Fantom** = jel/silikon malzemeden böbrek şekline döküm. Mavi tümör odakları üzerinde işaretli.

| Renk | Anlam | organ_id |
|---|---|---|
| **MAVİ noktalar** | Tümör/kanser odakları (fantom üzerinde) | `1` |
| **BEYAZ silikon** | Sağlıklı böbrek dokusu (silikon gövde) | `0` |

---

## Algoritma — Watershed-Tabanlı Fantom Tespit

```
RGB görüntü
   ↓
1. cv2.undistort  (K + D, kalibrasyon yoksa approx)
   ↓
2. KALİBRASYON  ──  ArUco varsa?
      VAR  →  solvePnP (tek marker, kedi pattern)  →  CabinPose
      YOK  →  --phantom-length-cm × 10 / bbox_max_kenar = mm/px
      Hiçbiri → piksel modu (mm = px)
   ↓
3. FANTOM TESPİT (find_phantoms)
      a) Mavi nokta adayları → cancer_blue HSV
      b) Beyaz HSV mask + closing
      c) Distance Transform + Watershed → ayrık segmentler
      d) Her segment için:
           • mavi nokta ≥ 1 ŞART
           • area > %1 görüntü
           • solidity > 0.40
      e) En yüksek skor = TEK FANTOM
   ↓
4. TÜMÖR SEGMENTASYONU  (fantom convex hull dilate içinde)
      • cancer_blue HSV (SIKI: S≥45, V≥40)
      • morfoloji open(3) + close(7)
      • connectedComponents
      • min area = 20 px (FP engel)
   ↓
5. PİKSEL → CABIN MM
      ArUco modu: ray-plane intersection
      Length modu: (px − fantom_centroid) × mm/px
   ↓
6. PhantomPredictor.predict(x,y,z, organ_id=1, B, duty)
      → D[7] duty, P[7] faz, E_healthy, E_cancer, E_avg
   ↓
7. JSON + 7-panel TR/EN overlay (adaptif font)
```

### Hibrit Tespit: HSV Otomatik + Manuel Tıklama

Pipeline önce **otomatik HSV** ile dener; başarısız olursa **OpenCV window açılır**:

```
HSV otomatik → kalite kontrol → BAŞARISIZ → Manuel tıkla seed → phantom_from_seed
```

CLI `--no-manual` ile fallback kapatılır (batch/server için).

---

## Çıktı Yapısı (kedi pattern)

```
results/<image_stem>/
├── result.json                   ← schema v1.1
├── tr/                           ← Türkçe 7 panel
│   ├── 01_input.jpg              ← orijinal
│   ├── 02_phantom_detect.jpg     ← fantom konturu + centroid
│   ├── 03_phantom_mask.jpg       ← fantom mask + bbox
│   ├── 04_tumors.jpg             ← mavi tümör çemberleri
│   ├── 05_local_coords.jpg       ← cabin-frame mm koordinatları
│   ├── 06_predictions.jpg        ← D[7] bar + E_kanser
│   └── 07_combined.jpg           ← 6 panel 3×2 grid
└── en/                           ← aynı 7 panel İngilizce
```

### result.json şeması (v1.1)

```json
{
  "schema_version": "v1.1",
  "success": true,
  "cabin_id": "phantom_helmholtz_v1",
  "image_name": "foto.jpeg",
  "method": "phantom_length",        ← "aruco_pnp" / "phantom_length" / "pixel"
  "mm_per_px": 0.493,
  "n_tumor": 2, "n_healthy": 1,
  "phantom_detection": {
    "n_phantoms": 1,
    "primary": {
      "centroid_px": [120, 88],
      "area_px": 13966,
      "solidity": 0.85,
      "n_blue_inside": 2,
      "score": 25.0
    },
    "all_centroids_px": [[120, 88]],
    "all_areas_px": [13966],
    "detect_method": "auto_hsv"      ← "auto_hsv" / "manual_click"
  },
  "cabin_pose": { ... },             ← ArUco modunda dolu
  "camera_calib": {"K":[..], "D":[..], "approx": true},
  "tumor_regions": [
    {
      "organ_id": 1, "label": "tumor",
      "centroid_px": [144, 41],
      "centroid_cabin_mm": [+13.6, +23.8, 0.0],
      "area_px": 164, "area_mm2": 39.8,
      "D": [d1..d7], "P": [p1..p7],
      "E_healthy": 0.0001, "E_cancer": 0.0984
    }
  ],
  "healthy_regions": [...],
  "timing_ms": {"total": 95, "phantom_detect": 35, ...}
}
```

---

## Hızlı Kurulum

### 1. Marker bas (opsiyonel — ArUco modu için)

```python
import cv2
d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)
cv2.imwrite("marker_id0.png", cv2.aruco.generateImageMarker(d, 0, 500))
```

5 cm × 5 cm yazdır. ArUco olmasa da pipeline çalışır (`--phantom-length-cm`).

### 2. Kamera kalibre et (opsiyonel — ArUco modunda)

```bash
python ../../inference_cat_organ/calibrate_camera.py \
    --images calib/ --pattern 9x6 --square-cm 2.5 \
    --output calib_phantom_v1.npz
```

### 3. YAML düzenle

```bash
cp cabin_config_example.yaml cabin_config.yaml
```

| Alan | Açıklama |
|---|---|
| `segmentation.cancer_blue` | HSV mavi tümör (sıkı: S≥45, V≥40) |
| `segmentation.healthy_white` | HSV beyaz silikon (S<70, V>100) |
| `aruco.real_cm` | ArUco yazıcı boyu (modu açıksa) |
| `camera.intrinsics_npz` | `calib_*.npz` (yoksa approx) |
| `phantom.achieved_B / duty_sum` | PhantomPredictor parametreleri |

### 4. Çalıştır

```bash
cd inference/inference_em_fantom

# Tek görüntü + fantom uzunluğu (10 cm)
python -m phantom_cv.cli -c phantom_cv/cabin_config.yaml \
    -i test.jpg --out results --phantom-length-cm 10.0

# Klasör batch + manuel fallback kapalı
python -m phantom_cv.cli -c phantom_cv/cabin_config.yaml \
    --batch test_img/ --out results --phantom-length-cm 10.0 --no-manual

# Canlı kamera tek frame
python -m phantom_cv.cli -c phantom_cv/cabin_config.yaml \
    --camera 0 --out results
```

---

## CLI Çıktı Örneği

```
[CABIN  ] cabin=phantom_helmholtz_v1 aruco=DICT_5X5_100/5.0cm ...
[PHANTOM] length = 10.0 cm (None=piksel mod)
[MANUAL ] fallback = OFF
[BATCH ] 4 goruntu islenecek

[2/4] foto.jpeg
  success                : True
  method                 : phantom_length
  n_tumor                : 2
  n_healthy              : 1
  phantom_center_px      : (120, 88)
  phantom_area_px        : 13966
  phantom_solidity       : 0.853
  phantom_score          : 25.0
  mm_per_px              : 0.4932
  total_ms               : 95.0
    TUMOR  ( +13.6,  +23.8,  +0.0)mm  E_c=0.0984  area=164
    TUMOR  (  -6.1,   +0.2,  +0.0)mm  E_c=0.0963  area=77
  -> results/foto/
```

---

## Python API

```python
import cv2
from phantom_cv import PhantomCvPipeline

pl = PhantomCvPipeline("cabin_config.yaml",
                       phantom_length_cm=10.0,
                       manual_fallback=True)
result, ctx = pl.process_file("test.jpg")

if result.success:
    print(f"Fantom: {result.phantom_detection['n_phantoms']}")
    for r in result.tumor_regions:
        x, y, z = r.centroid_cabin_mm
        print(f"TUMOR @ ({x:+.1f}, {y:+.1f}, {z:+.1f})mm  "
              f"E_c={r.E_cancer:.4f}  area={r.area_mm2:.1f}mm²")

# 7-panel render
panels_tr = pl.render_panels(ctx, result, lang="tr")
panels_en = pl.render_panels(ctx, result, lang="en")
cv2.imwrite("combined_tr.jpg", panels_tr["07_combined"])
```

---

## 3 Çıktı Modu

| Mod | Komut | Tüketen |
|---|---|---|
| **CLI / JSON** | `python -m phantom_cv.cli -i img.jpg` | dosya, manuel |
| **FastAPI** | `python -m phantom_cv.api -c cabin.yaml` | web frontend, GUI |
| **MQTT** | YAML `output.mqtt.enabled: true` + `--mqtt` | ESP32-S3 broker |

MQTT payload (compact): `pemf/coil/state` topic'ine **ortalama D[7]+P[7]** + tümör centroidleri.

---

## Klasör Yapısı

```
phantom_cv/
├── cabin_config.py            ← YAML loader (kedi pattern)
├── cabin_config_example.yaml  ← örnek konfigürasyon
├── coord_transform.py         ← ArUco PnP + piksel→cabin mm
├── color_segment.py           ← Watershed find_phantoms + tümör HSV
├── render.py                  ← 7-panel TR+EN overlay (adaptif font)
├── pipeline.py                ← Uçtan uca orkestrasyon
├── manual_select.py           ← OpenCV tıklama GUI (fallback)
├── cli.py / api.py / mqtt_publish.py   ← çıktı katmanları
├── test_img/                  ← örnek test görüntüleri
└── results/                   ← otomatik üretilir
```

---

## Doğruluk (test görüntüleriyle)

| Görüntü | n_phantoms | Tümör | mm/px | Total |
|---|---|---|---|---|
| 19.09.31.jpeg (tek fantom, 2 mavi) | 1 ✓ | 2/2 ✓ | 0.493 | 95 ms |
| 19.09.31(1).jpeg (tek fantom, 2 mavi) | 1 ✓ | 2/2 ✓ | 0.606 | 89 ms |
| 19.09.32(1).jpeg (yakın çekim, 2 mavi) | 1 ✓ | 2/2 ✓ | 0.333 | 92 ms |
| 19.09.32.jpeg (yakın çekim, 2 mavi) | 1 ✓ | 2/2 ✓ | 0.328 | 90 ms |

**4/4 görüntüde 2 tümör + tek fantom doğru tespit. FP yok.**

> **Not**: Pipeline `max_phantoms=1` default — en yüksek skorlu segment seçilir. Multi-fantom istiyorsan `color_segment.find_phantoms(max_phantoms=N)` doğrudan çağrılabilir.

---

## FP Engelleme Stratejisi

| Filtre | Değer | Etkisi |
|---|---|---|
| `cancer_blue.s_min` | **45** | Soluk gri-mavi atılır (S<30 = arka plan tonu) |
| `cancer_blue.v_min` | **40** | Karanlık lekeler atılır (yanık tonları) |
| `cancer_blue.h_min/max` | **90-135** | Dar mavi spektrum (cyan/yeşil-mavi yok) |
| Tümör morfoloji | `open(3)+close(7)` | Küçük gürültü temizlenir |
| Tümör `min_area_px` | **20** | Minik FP elenir |
| Fantom kabul | mavi ≥ 1 ŞART | Mavi içermeyen segment = arka plan |
| Fantom `area > %1` | adaptif | Gürültü segmentleri elenir |
| Fantom `solidity > 0.40` | sabit | Parçalı şekiller atılır |

---

## Bağımlılıklar

```bash
pip install opencv-python>=4.8 PyYAML>=6.0 numpy onnxruntime joblib pandas
# opsiyonel:
pip install "fastapi[all]" uvicorn paho-mqtt>=2.0
```

---

## Yeniden Kullanılan Kod

| Kaynak | Amaç |
|---|---|
| [`calibrate_camera.py`](../../inference_cat_organ/calibrate_camera.py) | OpenCV checkerboard → K + D |
| [`lib/cabin_config.py`](../../inference_cat_organ/lib/cabin_config.py) | Cabin YAML pattern |
| [`lib/qr.py`](../../inference_cat_organ/lib/qr.py) | ArUco en küçük ID pattern |
| [`inference_em_fantom.py`](../inference_em_fantom.py) | BiLSTM_XXL_Raw ONNX, R²=0.9955 |
