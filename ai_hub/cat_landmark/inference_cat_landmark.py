#!/usr/bin/env python3
"""
inference_cat_landmark.py — Kedi Yuz Landmark + FGS Agri Skorlamasi
===================================================================
48 keypoint detection + FGS (Feline Grimace Scale) pain scoring
5 Action Unit (AU1-AU5), toplam 0-10, >=4 = agri var

Kullanim:
  python inference_cat_landmark.py --image kedi.jpg
  python inference_cat_landmark.py --source images_folder/ --save
  python inference_cat_landmark.py  # interaktif mod
"""

import os
import sys
import argparse
import numpy as np
import json

_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_DIR, "yolo26m-pose.onnx")

# ============================================================
# 48 KEYPOINT TANIMLARI — CatFLW DATASET SEMASI (dataset/labels'tan dogrulanmis)
# ============================================================
KEYPOINT_NAMES = {
    # Merkez/orta hat (3 nokta)
    0:  "nose_tip",                # burun ucu / üst dudak orta üst
    1:  "left_eye_center",         # sol göz pupil/center
    2:  "lower_lip_center",        # alt dudak orta

    # Sag goz konturu (5 nokta + 3 iris)
    3:  "right_eye_center",        # sag göz pupil/center
    4:  "right_eye_top_outer",
    5:  "right_eye_bottom",
    6:  "right_eye_top_inner",
    7:  "right_eye_outer_corner",
    36: "right_eye_iris_1",
    37: "right_eye_iris_2",
    38: "right_eye_iris_3",

    # Sol goz konturu (4 nokta + 3 iris)
    8:  "left_eye_outer",
    9:  "left_eye_inner",
    10: "left_eye_top",
    11: "left_eye_bottom",
    39: "left_eye_iris_1",
    40: "left_eye_iris_2",
    41: "left_eye_iris_3",

    # Burun bolgesi (4 nokta)
    12: "nose_right_top",
    13: "nose_left_top",
    14: "nostril_right",
    15: "nostril_left",

    # Agiz (6 nokta)
    16: "philtrum",                # ust dudak orta (filtrum)
    17: "upper_lip_center",
    18: "mouth_right_corner",
    19: "mouth_right_lower",
    20: "mouth_left_corner",
    21: "mouth_left_lower",

    # Sag kulak (5 nokta: base_outer -> outer_mid -> tip -> inner_mid -> base_inner)
    22: "right_ear_base_outer",
    23: "right_ear_outer_mid",
    24: "right_ear_tip",
    25: "right_ear_inner_mid",
    26: "right_ear_base_inner",

    # Sol kulak (5 nokta: simetrik)
    27: "left_ear_base_inner",
    28: "left_ear_inner_mid",
    29: "left_ear_tip",
    30: "left_ear_outer_mid",
    31: "left_ear_base_outer",

    # Yanak / yuz konturu (10 nokta)
    32: "right_cheek_outer",
    33: "right_cheek_lower",
    34: "left_cheek_lower",
    35: "left_cheek_outer",
    42: "right_cheek_inner",
    43: "left_cheek_inner",
    44: "muzzle_right",            # burun-agiz gecis sag
    45: "muzzle_left",
    46: "right_chin_outer",
    47: "left_chin_outer",
}


# ============================================================
# THRESHOLDS — CatFLW dataset percentile'larindan kalibre edilmis
# Dosya: thresholds_calibrated.json (varsa yuklenir, yoksa inline fallback)
# ============================================================
_THRESH_JSON = os.path.join(_DIR, "thresholds_calibrated.json")

# Fallback degerler (calibrate ile JSON yazilana kadar)
_THRESH_DEFAULT = {
    "ear_angle":         {"p5": 43.307, "p25": 58.984, "p50": 63.332, "p75": 67.121, "p95": 71.714},
    "ear_elev":          {"p5": 0.143,  "p25": 0.227,  "p50": 0.256,  "p75": 0.281,  "p95": 0.320},
    "ear_spread":        {"p5": 1.383,  "p25": 1.488,  "p50": 1.559,  "p75": 1.638,  "p95": 1.768},
    "eye_ratio_avg":     {"p5": 0.950,  "p25": 1.118,  "p50": 1.320,  "p75": 1.650,  "p95": 2.681},
    "mouth_aspect":      {"p5": 0.905,  "p25": 1.371,  "p50": 1.779,  "p75": 2.262,  "p95": 3.371},
    "muzzle_compact":    {"p5": 1.023,  "p25": 1.243,  "p50": 1.439,  "p75": 1.685,  "p95": 2.193},
    "whisker_tension":   {"p5": 0.565,  "p25": 0.602,  "p50": 0.625,  "p75": 0.647,  "p95": 0.679},
    "head_center_y":     {"p5": 0.528,  "p25": 0.582,  "p50": 0.608,  "p75": 0.631,  "p95": 0.663},
}


def _load_thresholds():
    """thresholds_calibrated.json varsa oradan yukle, yoksa fallback default kullan."""
    if os.path.exists(_THRESH_JSON):
        try:
            with open(_THRESH_JSON) as f:
                data = json.load(f)
            # Beklenen anahtarlar var mi?
            for k in _THRESH_DEFAULT:
                if k not in data:
                    data[k] = _THRESH_DEFAULT[k]
            return data
        except Exception:
            pass
    return dict(_THRESH_DEFAULT)


THRESH = _load_thresholds()


# ============================================================
# FGS — Feline Grimace Scale (Université de Montréal, 2019)
# Nature Scientific Reports validated, >90% accuracy
# 5 Action Units, each 0-2, total 0-10, >=4 = pain
# ============================================================
def compute_fgs(keypoints):
    """
    48 keypoint'ten FGS (Feline Grimace Scale) hesapla.
    Référence: Evangelista et al., 2019, Nature Scientific Reports.

    Args:
        keypoints: (48, 2) array — x, y normalized coordinates (bbox-relative)

    Returns:
        dict: {
            "fgs_total": int (0-10),
            "pain": bool (fgs >= 4),
            "pain_level": "No Pain" | "Mild" | "Moderate" | "Severe",
            "action_units": {AU1..AU5 each 0-2 with description},
            "measurements": {raw geometric values}
        }
    """
    kp = np.array(keypoints)
    if kp.shape[0] < 48:
        return {"fgs_total": -1, "pain": False, "pain_level": "Unknown",
                "action_units": {}, "measurements": {}}

    eps = 1e-8

    # ================================================================
    # GEOMETRIC MEASUREMENTS — CatFLW dogrulanmis mapping
    # ================================================================

    # --- AU1: Ear Position (sag: 22-26, sol: 27-31) ---
    # tip = 24 (sag), 29 (sol); base ortalamasi = (base_outer + base_inner) / 2
    right_ear_tip  = kp[24]
    right_ear_base = (kp[22] + kp[26]) / 2.0
    left_ear_tip   = kp[29]
    left_ear_base  = (kp[27] + kp[31]) / 2.0

    # Tip base'den yukarida mi? (y kucuk = yukari)
    right_ear_elevation = -(right_ear_tip[1] - right_ear_base[1])
    left_ear_elevation  = -(left_ear_tip[1]  - left_ear_base[1])
    avg_ear_elevation = (right_ear_elevation + left_ear_elevation) / 2.0

    # Kulak acisi: 90° = dik, 0° = yatik
    right_ear_vec = right_ear_tip - right_ear_base
    left_ear_vec  = left_ear_tip  - left_ear_base
    right_ear_angle = abs(np.degrees(np.arctan2(-right_ear_vec[1], abs(right_ear_vec[0]) + eps)))
    left_ear_angle  = abs(np.degrees(np.arctan2(-left_ear_vec[1],  abs(left_ear_vec[0])  + eps)))
    avg_ear_angle = (right_ear_angle + left_ear_angle) / 2.0

    # Spread: tip'ler arasi / base'ler arasi (>1 = acilmis, <1 = duzlesmis)
    ear_tips_dist  = np.linalg.norm(right_ear_tip  - left_ear_tip)
    ear_bases_dist = np.linalg.norm(right_ear_base - left_ear_base)
    ear_spread = ear_tips_dist / (ear_bases_dist + eps)

    # --- AU2: Orbital Tightening (sag: 3-7, sol: 1,8,9,10,11) ---
    # Sag goz: top=(4+6)/2, bottom=5, outer=7, center=3 (pupil)
    right_eye_top    = (kp[4] + kp[6]) / 2.0
    right_eye_bottom = kp[5]
    right_eye_outer  = kp[7]
    right_eye_center = kp[3]
    right_eye_h = np.linalg.norm(right_eye_top - right_eye_bottom)
    # Width: outer ile center arasi yaklasik gozun yari genisligi → ×2
    right_eye_w = np.linalg.norm(right_eye_outer - right_eye_center) * 2.0
    right_eye_ratio = right_eye_h / (right_eye_w + eps)

    # Sol goz: top=10, bottom=11, outer=8, inner=9
    left_eye_top    = kp[10]
    left_eye_bottom = kp[11]
    left_eye_outer  = kp[8]
    left_eye_inner  = kp[9]
    left_eye_h = np.linalg.norm(left_eye_top - left_eye_bottom)
    left_eye_w = np.linalg.norm(left_eye_outer - left_eye_inner)
    left_eye_ratio = left_eye_h / (left_eye_w + eps)

    avg_eye_ratio = (right_eye_ratio + left_eye_ratio) / 2.0

    # --- AU3: Muzzle Tension (nose=0, mouth=16-21, lips=17/2) ---
    nose_tip       = kp[0]
    upper_lip      = kp[17]
    lower_lip      = kp[2]
    mouth_right    = kp[18]
    mouth_left     = kp[20]

    # Muzzle length: burun ucundan ust dudaga
    muzzle_length = np.linalg.norm(nose_tip - upper_lip)

    # Mouth aspect: genislik / yukseklik (oval = gergin)
    mouth_w = np.linalg.norm(mouth_right - mouth_left)
    mouth_h = np.linalg.norm(upper_lip - lower_lip)
    mouth_aspect = mouth_w / (mouth_h + eps)

    # Nose width (nostriller arasi)
    nose_w = np.linalg.norm(kp[14] - kp[15])
    muzzle_compactness = nose_w / (mouth_w + eps)

    # --- AU4: Whisker Position (yanak gerginliginden tahmin) ---
    # 32/35 = sag/sol cheek_outer, 42/43 = cheek_inner, 44/45 = muzzle, 46/47 = chin
    cheek_outer_dist = np.linalg.norm(kp[32] - kp[35])   # dis yanak genisligi
    cheek_inner_dist = np.linalg.norm(kp[42] - kp[43])   # ic yanak genisligi
    muzzle_dist      = np.linalg.norm(kp[44] - kp[45])   # burun-agiz gecis genisligi
    chin_dist        = np.linalg.norm(kp[46] - kp[47])   # cene altı

    # Whisker tension: gergin biyik → yanak iceri çekilir (cheek_inner azalir vs outer)
    whisker_tension = cheek_inner_dist / (cheek_outer_dist + eps)
    # Yuz alt bolge kompaktligi
    face_lower_compact = chin_dist / (cheek_outer_dist + eps)

    # --- AU5: Head Position (tum y koordinatlari) ---
    head_center_y = np.mean(kp[:, 1])

    # Bas egimi: kulak baselari (alin proxy) -> alt dudak
    forehead_center = (kp[26] + kp[27]) / 2.0  # ic kulak base'lerinin ortasi
    chin_center     = lower_lip
    head_tilt_vec   = chin_center - forehead_center
    head_tilt_angle = np.degrees(np.arctan2(head_tilt_vec[0], head_tilt_vec[1]))

    # Bas dusuklugu: alt dudak y (1.0 = en alt)
    head_drop = lower_lip[1]

    measurements = {
        "ear_elevation": round(float(avg_ear_elevation), 4),
        "ear_angle_avg": round(float(avg_ear_angle), 1),
        "ear_spread": round(float(ear_spread), 4),
        "eye_aperture_ratio": round(float(avg_eye_ratio), 4),
        "right_eye_ratio": round(float(right_eye_ratio), 4),
        "left_eye_ratio": round(float(left_eye_ratio), 4),
        "muzzle_length": round(float(muzzle_length), 4),
        "mouth_aspect": round(float(mouth_aspect), 4),
        "muzzle_compactness": round(float(muzzle_compactness), 4),
        "whisker_tension": round(float(whisker_tension), 4),
        "face_lower_compact": round(float(face_lower_compact), 4),
        "head_center_y": round(float(head_center_y), 4),
        "head_tilt_angle": round(float(head_tilt_angle), 1),
        "head_drop": round(float(head_drop), 4),
    }

    # ================================================================
    # ACTION UNIT SCORING — CatFLW dataset percentile-based (N=2079)
    # AU=0 normal (p25-p75 araligi), AU=1 hafif sapma (p5-p25 / p75-p95),
    # AU=2 belirgin anormal (<p5 veya >p95).
    # ================================================================

    T = THRESH  # kalibre eşikler (JSON'dan yuklendi)

    # AU1: Ear (yuksek angle + elev = dik; dusuk = yatik)
    if (avg_ear_angle >= T["ear_angle"]["p25"]
        and avg_ear_elevation >= T["ear_elev"]["p25"]
        and T["ear_spread"]["p25"] <= ear_spread <= T["ear_spread"]["p75"]):
        au1 = 0  # forward & upright (normal: p25-p75 araligi)
    elif (avg_ear_angle < T["ear_angle"]["p5"]
          or avg_ear_elevation < T["ear_elev"]["p5"]
          or ear_spread < T["ear_spread"]["p5"]
          or ear_spread > T["ear_spread"]["p95"]):
        au1 = 2  # flattened / extreme
    else:
        au1 = 1  # slightly pulled apart

    # AU2: Orbital Tightening (yuksek ratio = acik)
    if avg_eye_ratio >= T["eye_ratio_avg"]["p25"]:
        au2 = 0
    elif avg_eye_ratio < T["eye_ratio_avg"]["p5"]:
        au2 = 2  # closed/tightly squinted
    else:
        au2 = 1

    # AU3: Muzzle Tension
    if (mouth_aspect <= T["mouth_aspect"]["p75"]
        and T["muzzle_compact"]["p25"] <= muzzle_compactness <= T["muzzle_compact"]["p75"]):
        au3 = 0  # relaxed, round
    elif (mouth_aspect > T["mouth_aspect"]["p95"]
          or muzzle_compactness < T["muzzle_compact"]["p5"]
          or muzzle_compactness > T["muzzle_compact"]["p95"]):
        au3 = 2  # taut, oval/elongated
    else:
        au3 = 1

    # AU4: Whisker / cheek tension (iki uc da anormal)
    if T["whisker_tension"]["p25"] <= whisker_tension <= T["whisker_tension"]["p75"]:
        au4 = 0
    elif whisker_tension < T["whisker_tension"]["p5"] or whisker_tension > T["whisker_tension"]["p95"]:
        au4 = 2
    else:
        au4 = 1

    # AU5: Head Position (yuksek head_center_y = bas asagida)
    if head_center_y <= T["head_center_y"]["p75"]:
        au5 = 0
    elif head_center_y > T["head_center_y"]["p95"]:
        au5 = 2  # below shoulders (extreme)
    else:
        au5 = 1

    fgs_total = au1 + au2 + au3 + au4 + au5
    has_pain = fgs_total >= 4

    if fgs_total <= 1:
        pain_level = "No Pain"
    elif fgs_total <= 3:
        pain_level = "Mild"
    elif fgs_total <= 6:
        pain_level = "Moderate"
    else:
        pain_level = "Severe"

    au_descriptions = {
        0: {0: "Forward & upright", 1: "Slightly pulled apart", 2: "Flattened & rotated outwardly"},
        1: {0: "Open", 1: "Moderately squinted", 2: "Closed/tightly squinted"},
        2: {0: "Relaxed, round", 1: "Moderate tension", 2: "Taut, oval/elongated"},
        3: {0: "Loose & straight", 1: "Slightly curved/pulled back", 2: "Straight, stiff & forward"},
        4: {0: "Above shoulders", 1: "Aligned with shoulders", 2: "Below shoulders, lowered"},
    }

    action_units = {
        "AU1_Ear_Position": {"score": au1, "description": au_descriptions[0][au1]},
        "AU2_Orbital_Tightening": {"score": au2, "description": au_descriptions[1][au2]},
        "AU3_Muzzle_Tension": {"score": au3, "description": au_descriptions[2][au3]},
        "AU4_Whisker_Position": {"score": au4, "description": au_descriptions[3][au4]},
        "AU5_Head_Position": {"score": au5, "description": au_descriptions[4][au5]},
    }

    return {
        "fgs_total": fgs_total,
        "pain": has_pain,
        "pain_level": pain_level,
        "action_units": action_units,
        "measurements": measurements,
    }


# ============================================================
# YARDIMCI: 48 keypoint'i INDEX numarasiyla cizdir (debug viz)
# ============================================================
def _get_kp_colors(n=48):
    import colorsys
    return [tuple(int(255*c) for c in colorsys.hsv_to_rgb(i/n, 0.9, 0.9)) for i in range(n)]


def _get_font(size=14):
    try:
        from PIL import ImageFont
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:
        from PIL import ImageFont
        return ImageFont.load_default()


def viz_indexed_keypoints(image_path, model, out_dir, conf=0.25, device="0"):
    """YOLO inference + her keypoint'i indeks numarasiyla ciz, kaydet."""
    from PIL import Image, ImageDraw
    os.makedirs(out_dir, exist_ok=True)
    colors = _get_kp_colors(48)
    font = _get_font(14)

    results = model.predict(source=image_path, conf=conf, device=device, verbose=False)
    r = results[0]
    if r.keypoints is None or len(r.boxes) == 0:
        print(f"  {os.path.basename(image_path)}: tespit yok")
        return None

    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    for cat_idx in range(len(r.boxes)):
        kp = r.keypoints.xy[cat_idx].cpu().numpy()
        kp_conf = r.keypoints.conf[cat_idx].cpu().numpy() if r.keypoints.conf is not None else None
        x1, y1, x2, y2 = r.boxes.xyxy[cat_idx].tolist()
        bbox_conf = float(r.boxes.conf[cat_idx])

        draw.rectangle([x1, y1, x2, y2], outline="blue", width=3)
        draw.text((x1+5, y1+5), f"cat_face {bbox_conf:.2f}", fill="blue", font=font)

        bw = x2 - x1
        radius = max(4, int(bw * 0.008))

        for i, (x, y) in enumerate(kp):
            if x <= 0 and y <= 0:
                continue
            ci = float(kp_conf[i]) if kp_conf is not None else 1.0
            color = colors[i]
            if ci < 0.3:
                draw.ellipse([x-2, y-2, x+2, y+2], outline=color, width=1)
            else:
                draw.ellipse([x-radius, y-radius, x+radius, y+radius],
                             fill=color, outline="white", width=1)
                draw.text((x+radius+2, y-7), str(i), fill="white",
                          font=font, stroke_width=2, stroke_fill="black")

    out_path = os.path.join(out_dir, os.path.basename(image_path).rsplit('.', 1)[0] + "_kp_idx.jpg")
    img.save(out_path, quality=92)
    print(f"  -> {out_path}")
    return out_path


def viz_dataset_annotation(json_label_path, dataset_images_dir, out_dir):
    """Bir CatFLW ham annotation JSON'unu okuyup keypoint'leri indeksli ciz.
    Mapping dogrulamak icin kullanilir."""
    from PIL import Image, ImageDraw
    os.makedirs(out_dir, exist_ok=True)
    colors = _get_kp_colors(48)
    font = _get_font(14)

    with open(json_label_path) as f:
        data = json.load(f)
    kps = data["labels"]
    bbox = data["bounding_boxes"]
    x1, y1, x2, y2 = bbox

    base = os.path.basename(json_label_path).replace('.json', '')
    img_path = None
    for ext in ('.jpg', '.jpeg', '.png'):
        p = os.path.join(dataset_images_dir, base + ext)
        if os.path.exists(p):
            img_path = p
            break
    if img_path is None:
        print(f"  Image bulunamadi: {base}")
        return None

    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.rectangle([x1, y1, x2, y2], outline="blue", width=3)
    draw.text((x1+5, y1+5), "GT bbox", fill="blue", font=font)

    bw = x2 - x1
    radius = max(4, int(bw * 0.008))
    for i, (x, y) in enumerate(kps):
        color = colors[i]
        draw.ellipse([x-radius, y-radius, x+radius, y+radius],
                     fill=color, outline="white", width=1)
        draw.text((x+radius+2, y-7), str(i), fill="white",
                  font=font, stroke_width=2, stroke_fill="black")

    out_path = os.path.join(out_dir, base + "_GT_indexed.jpg")
    img.save(out_path, quality=92)
    print(f"  -> {out_path}")
    return out_path


# ============================================================
# CALIBRATE — CatFLW dataset'inden percentile-based threshold uret
# ============================================================
def _measure_from_kp(kp_pix, bbox):
    """48 ham keypoint + bbox'tan compute_fgs ile ayni olcumleri uret (bbox-relative)."""
    x1, y1, x2, y2 = bbox
    bw, bh = x2 - x1, y2 - y1
    if bw <= 0 or bh <= 0:
        return None
    kp = np.zeros_like(np.array(kp_pix))
    arr = np.array(kp_pix)
    kp[:, 0] = (arr[:, 0] - x1) / bw
    kp[:, 1] = (arr[:, 1] - y1) / bh
    eps = 1e-8

    # AU1
    rt, rb = kp[24], (kp[22] + kp[26]) / 2.0
    lt, lb = kp[29], (kp[27] + kp[31]) / 2.0
    ear_elev = (-(rt[1] - rb[1]) + -(lt[1] - lb[1])) / 2.0
    rv, lv = rt - rb, lt - lb
    ear_angle = (abs(np.degrees(np.arctan2(-rv[1], abs(rv[0]) + eps)))
                 + abs(np.degrees(np.arctan2(-lv[1], abs(lv[0]) + eps)))) / 2.0
    ear_spread = np.linalg.norm(rt - lt) / (np.linalg.norm(rb - lb) + eps)

    # AU2
    rt_eye = (kp[4] + kp[6]) / 2.0
    r_ratio = np.linalg.norm(rt_eye - kp[5]) / (np.linalg.norm(kp[7] - kp[3]) * 2.0 + eps)
    l_ratio = np.linalg.norm(kp[10] - kp[11]) / (np.linalg.norm(kp[8] - kp[9]) + eps)
    eye_ratio_avg = (r_ratio + l_ratio) / 2.0

    # AU3
    mw = np.linalg.norm(kp[18] - kp[20])
    mh = np.linalg.norm(kp[17] - kp[2])
    mouth_aspect = mw / (mh + eps)
    nw = np.linalg.norm(kp[14] - kp[15])
    muzzle_compact = nw / (mw + eps)

    # AU4
    co = np.linalg.norm(kp[32] - kp[35])
    ci = np.linalg.norm(kp[42] - kp[43])
    whisker_tension = ci / (co + eps)

    # AU5
    head_center_y = float(np.mean(kp[:, 1]))

    return {
        "ear_angle": float(ear_angle), "ear_elev": float(ear_elev),
        "ear_spread": float(ear_spread), "eye_ratio_avg": float(eye_ratio_avg),
        "mouth_aspect": float(mouth_aspect), "muzzle_compact": float(muzzle_compact),
        "whisker_tension": float(whisker_tension), "head_center_y": head_center_y,
    }


def calibrate_from_dataset(labels_dir, output_json=None):
    """Dataset annotation JSON'larindan percentile threshold'larini cikar ve kaydet."""
    from glob import glob
    if output_json is None:
        output_json = _THRESH_JSON

    files = sorted(glob(os.path.join(labels_dir, "*.json")))
    if not files:
        print(f"HATA: '{labels_dir}' icinde JSON yok.")
        return None
    print(f"[Calibrate] {len(files)} etiket isleniyor...")

    records = []
    for fp in files:
        try:
            with open(fp) as f:
                d = json.load(f)
            kp = np.array(d["labels"])
            if kp.shape[0] != 48:
                continue
            m = _measure_from_kp(kp, d["bounding_boxes"])
            if m is not None:
                records.append(m)
        except Exception:
            continue
    print(f"[Calibrate] Basarili: {len(records)}/{len(files)}")
    if not records:
        return None

    keys = list(records[0].keys())
    stats = {}
    print(f"\n{'Measurement':<22} {'p5':>8} {'p25':>8} {'p50':>8} {'p75':>8} {'p95':>8}")
    print("-" * 65)
    for k in keys:
        vals = np.array([r[k] for r in records])
        s = {
            "p5":  float(np.percentile(vals, 5)),
            "p25": float(np.percentile(vals, 25)),
            "p50": float(np.percentile(vals, 50)),
            "p75": float(np.percentile(vals, 75)),
            "p95": float(np.percentile(vals, 95)),
            "mean": float(np.mean(vals)), "std": float(np.std(vals)),
        }
        stats[k] = s
        print(f"{k:<22} {s['p5']:>8.3f} {s['p25']:>8.3f} {s['p50']:>8.3f} {s['p75']:>8.3f} {s['p95']:>8.3f}")

    with open(output_json, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\n[Calibrate] Kaydedildi: {output_json}")
    return stats


# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Kedi Yuz Landmark + FGS Agri Skorlamasi (YOLO26m-pose, 48 keypoint)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ornekler — INFERENCE:
  python inference_cat_landmark.py --image kedi.jpg --save --json
  python inference_cat_landmark.py --source test_img/ --save --json
  python inference_cat_landmark.py --source test_img/ --viz-indexed   # her keypoint indeksiyle

DEBUG / KALIBRASYON:
  python inference_cat_landmark.py --calibrate <dataset>/labels
  python inference_cat_landmark.py --viz-dataset <dataset>/labels --dataset-images <dataset>/images
""")
    # Inference args
    parser.add_argument("--image", type=str, help="Tek goruntu")
    parser.add_argument("--source", type=str, help="Klasor veya video")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--device", type=str, default="0", help="Device")
    parser.add_argument("--save", action="store_true", help="Annotated sonuclari kaydet")
    parser.add_argument("--json", action="store_true", help="JSON cikti kaydet")
    parser.add_argument("--output", type=str, default="results", help="Cikti klasoru")
    parser.add_argument("--viz-indexed", action="store_true",
                        help="Her keypoint'i INDEX numarasiyla goster (debug)")

    # Calibration mode
    parser.add_argument("--calibrate", type=str, metavar="LABELS_DIR",
                        help="Verilen dataset labels klasoru icin percentile threshold uret")

    # Dataset annotation viz mode
    parser.add_argument("--viz-dataset", type=str, metavar="LABELS_DIR",
                        help="Dataset GT annotation'larindan indeksli viz (mapping dogrulamak icin)")
    parser.add_argument("--dataset-images", type=str, default=None,
                        help="--viz-dataset ile birlikte: images klasoru")
    parser.add_argument("--dataset-limit", type=int, default=5,
                        help="--viz-dataset icin maksimum ornek sayisi (default 5)")

    args = parser.parse_args()

    # MODE: CALIBRATE
    if args.calibrate:
        calibrate_from_dataset(args.calibrate)
        # Yeniden yukle ki sonraki cagrilarda kullanılabilsin
        global THRESH
        THRESH = _load_thresholds()
        return

    # MODE: DATASET VIZ
    if args.viz_dataset:
        labels_dir = args.viz_dataset
        images_dir = args.dataset_images or os.path.join(os.path.dirname(labels_dir), "images")
        out_dir = os.path.join(_DIR, "dataset_kp_viz")
        files = sorted(os.listdir(labels_dir))[:args.dataset_limit]
        print(f"[Dataset Viz] {len(files)} ornek -> {out_dir}")
        for fn in files:
            if fn.endswith(".json"):
                viz_dataset_annotation(os.path.join(labels_dir, fn), images_dir, out_dir)
        return

    # MODE: INFERENCE

    from ultralytics import YOLO

    print("=" * 60)
    print("Kedi Yuz Landmark + FGS Agri Skorlamasi")
    print(f"Model: YOLO26m-pose (48 keypoint, mAP50-95=0.729)")
    print(f"FGS: 5 AU (0-2), Toplam 0-10, >=4 = Agri")
    print(f"Thresholds: {'thresholds_calibrated.json (kalibre)' if os.path.exists(_THRESH_JSON) else 'inline fallback'}")
    print("=" * 60)

    model = YOLO(MODEL_PATH, task="pose")

    # Indexed viz icin output klasoru
    indexed_out_dir = os.path.join(_DIR, args.output + "_indexed") if args.viz_indexed else None

    source = args.image or args.source

    if source is None:
        # Interaktif mod
        print("\nInteraktif mod (cikmak icin 'q')")
        print("-" * 60)
        while True:
            try:
                path = input("\nGoruntu yolu: ").strip()
                if path.lower() in ('q', 'quit', 'exit', ''):
                    break
                if not os.path.exists(path):
                    print(f"  Dosya bulunamadi: {path}")
                    continue

                results = model.predict(
                    source=path, conf=args.conf, device=args.device,
                    save=True, project=_DIR, name=args.output, exist_ok=True,
                    verbose=False
                )

                for r in results:
                    _print_result(r, args.json)

                if args.viz_indexed:
                    viz_indexed_keypoints(path, model, indexed_out_dir,
                                          conf=args.conf, device=args.device)

            except KeyboardInterrupt:
                print("\n  Cikis.")
                break
            except Exception as e:
                print(f"  Hata: {e}")
    else:
        print(f"\nKaynak: {source}")
        results = model.predict(
            source=source, conf=args.conf, device=args.device,
            save=args.save, project=_DIR, name=args.output, exist_ok=True,
            verbose=False
        )

        all_results = []
        for r in results:
            result_data = _print_result(r, args.json)
            if result_data:
                all_results.append(result_data)
            if args.viz_indexed:
                viz_indexed_keypoints(r.path, model, indexed_out_dir,
                                      conf=args.conf, device=args.device)

        if args.json and all_results:
            json_path = os.path.join(_DIR, args.output, "results.json")
            os.makedirs(os.path.join(_DIR, args.output), exist_ok=True)
            with open(json_path, 'w') as f:
                json.dump(all_results, f, indent=2)
            print(f"\nJSON: {json_path}")

        print(f"\nToplam: {len(results)} goruntu, {sum(len(r.boxes) for r in results)} kedi")
        if args.save:
            print(f"Kaydedildi: {_DIR}/{args.output}/")


def _print_result(r, save_json=False):
    """Print and optionally return result for one image."""
    n_cats = len(r.boxes) if r.boxes is not None else 0
    print(f"\n  Tespit: {n_cats} kedi yuzu")

    result_data = {"image": r.path, "cats": []}

    if r.keypoints is not None and n_cats > 0:
        for i in range(n_cats):
            conf = float(r.boxes.conf[i])
            kp = r.keypoints.xy[i].cpu().numpy()  # (48, 2)
            kp_conf = r.keypoints.conf[i].cpu().numpy() if r.keypoints.conf is not None else None

            # Bbox
            x1, y1, x2, y2 = r.boxes.xyxy[i].tolist()

            # Normalize keypoints to bbox
            w, h = x2 - x1, y2 - y1
            if w > 0 and h > 0:
                kp_norm = np.zeros_like(kp)
                kp_norm[:, 0] = (kp[:, 0] - x1) / w
                kp_norm[:, 1] = (kp[:, 1] - y1) / h
            else:
                kp_norm = kp

            # FGS Scoring
            fgs = compute_fgs(kp_norm)

            print(f"\n  Kedi {i+1} (conf={conf:.2f}):")
            print(f"    Bbox: [{x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}]")
            print(f"    Keypoints: {len(kp)} nokta")
            if kp_conf is not None:
                avg_kp_conf = float(kp_conf.mean())
                print(f"    Keypoint ortalama conf: {avg_kp_conf:.2f}")

            # FGS Output
            pain_icon = "🔴" if fgs["fgs_total"] >= 7 else "🟡" if fgs["fgs_total"] >= 4 else "🟢"
            print(f"\n    {pain_icon} FGS Score: {fgs['fgs_total']}/10 — {fgs['pain_level']}")
            if fgs["pain"]:
                print(f"    ⚠️  AGRI TESPIT EDILDI (FGS ≥ 4) → Analjezik tedavi gerekli")
            else:
                print(f"    ✅ Agri yok (FGS < 4)")

            print(f"\n    Action Units:")
            for au_name, au_data in fgs["action_units"].items():
                bar = "█" * au_data["score"] + "░" * (2 - au_data["score"])
                print(f"      {au_name:28s} {au_data['score']}/2 {bar}  {au_data['description']}")

            print(f"\n    Olcumler:")
            for k, v in fgs["measurements"].items():
                print(f"      {k:22s}: {v}")

            cat_data = {
                "confidence": conf,
                "bbox": [x1, y1, x2, y2],
                "fgs_total": fgs["fgs_total"],
                "pain": fgs["pain"],
                "pain_level": fgs["pain_level"],
                "action_units": fgs["action_units"],
                "measurements": fgs["measurements"],
            }
            result_data["cats"].append(cat_data)

    return result_data if save_json else None


if __name__ == "__main__":
    main()
