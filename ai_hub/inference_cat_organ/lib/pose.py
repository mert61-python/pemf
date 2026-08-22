# Author: mertaygn, cglrgrkn
"""pose.py - Pose classification (sphinx/lateral/dorsal/oblique/frontal)."""
from __future__ import annotations
import numpy as np

from .canonical import KEYPOINT_NAMES


POSE_TYPES = ["lateral", "sphinx", "standing", "dorsal", "frontal", "oblique"]



def classify_pose(kp_dict: dict, mask_xy: list | None, bbox: np.ndarray) -> dict:
    """Pose tipini tespit eder.

    Heuristics:
      - Mask aspect ratio (W/H)
      - head/tail visible mi
      - back keypoints visible mi (lateral icin kritik)
      - body_middle_right vs left ikisi de var mi (frontal/dorsal'da TEK taraf gorur)
      - head ortalama position vs body center

    Returns: {"type", "confidence", "reasons"}
    """
    reasons = []
    # bbox geometri
    bw = float(bbox[2] - bbox[0])
    bh = float(bbox[3] - bbox[1])
    aspect = bw / max(bh, 1e-6)

    # Mask siluet (eger varsa)
    mask_aspect = aspect
    if mask_xy is not None and len(mask_xy) > 5:
        pts = np.asarray(mask_xy, dtype=np.float64)
        # PCA -> major/minor extent
        c = pts.mean(0)
        cov = ((pts - c).T @ (pts - c)) / max(1, len(pts) - 1)
        eigvals = np.sort(np.linalg.eigvalsh(cov))[::-1]
        mask_aspect = float(np.sqrt(eigvals[0] / max(eigvals[1], 1e-6)))

    head_kp = [n for n in ("nose", "left_eye", "right_eye", "left_earbase",
                              "right_earbase", "neck_base") if n in kp_dict]
    tail_kp = [n for n in ("tail_base", "tail_end", "back_end") if n in kp_dict]
    back_kp = [n for n in ("back_base", "back_middle", "back_end") if n in kp_dict]
    has_head = len(head_kp) >= 3
    has_tail = len(tail_kp) >= 1
    has_back = len(back_kp) >= 2

    # Omurga ekseni gercekten "uzanmış" mı? (back keypointleri arası mesafe)
    bbox_diag = float(np.sqrt((bbox[2] - bbox[0]) ** 2 + (bbox[3] - bbox[1]) ** 2))
    spine_extent_ratio = 0.0
    if has_back:
        back_pts = np.array([kp_dict[n] for n in back_kp])
        # En uzak iki nokta arasi
        max_d = 0.0
        for i in range(len(back_pts)):
            for j in range(i + 1, len(back_pts)):
                d = float(np.linalg.norm(back_pts[i] - back_pts[j]))
                if d > max_d:
                    max_d = d
        spine_extent_ratio = max_d / max(bbox_diag, 1e-6)
    # spine_extent_ratio > 0.30 -> omurga gerçek
    # 0.10-0.30 -> omurga belirsiz
    # < 0.10 -> back keypointleri sıkışık, omurga 2D'de görünmüyor (frontal)
    has_real_spine = spine_extent_ratio > 0.25

    # body_middle_right vs left
    has_r = "body_middle_right" in kp_dict
    has_l = "body_middle_left" in kp_dict
    both_sides = has_r and has_l
    one_side = (has_r or has_l) and not both_sides

    # Head ve tail mesafesi (pose uzunlugu)
    if has_head and has_tail:
        head_avg = np.mean([kp_dict[n] for n in head_kp[:3]], axis=0)
        tail_avg = np.mean([kp_dict[n] for n in tail_kp], axis=0)
        head_tail_dist = float(np.linalg.norm(head_avg - tail_avg))
        bbox_diag = float(np.sqrt(bw**2 + bh**2))
        ht_ratio = head_tail_dist / max(bbox_diag, 1e-6)
    else:
        ht_ratio = 0.0
        head_tail_dist = 0.0
        head_avg = None
        tail_avg = None

    # ----- Yeni Karar Agaci -----
    # Mantik: back keypointleri lateral pose icin guvenilir gosterge
    # Tail keypoint sphinx/oturan kedilerde altında gizlendigi icin guvenilmez
    #
    # Pose ayirici cekirdek metrik: "kac body keypoint'i goruyoruz?"
    #   - back keypointleri (>=2) + tek yan        -> LATERAL (kedi yan profilinde)
    #   - back keypointleri (>=2) + iki yan        -> DORSAL (üstten) ya da SPHINX
    #   - back yok / 1 nokta + head var + tail yok -> FRONTAL (sadece kafa)
    pose = "oblique"
    conf = 0.5

    # ----- Karar Agaci v3 -----
    # Temel mantik: KEDI'NIN OMURGA EKSENI ALGILANIYOR MU?
    # Eger evet → lateral/sphinx fark etmez, yatay/dikey eksen otomatik tespit edilir
    # Eger hayir → frontal/oblique
    spine_visible = has_back and (has_head or has_tail)
    bw = float(bbox[2] - bbox[0])
    bh = float(bbox[3] - bbox[1])
    is_vertical_bbox = bh > bw * 1.15
    is_horizontal_bbox = bw > bh * 1.15

    # v5: spine_extent_ratio ile gercek omurga var/yok kontrol
    # Spine kisa = back keypointleri 2D'de sikisik = kedi kameraya bakıyor.
    # Bu durumda bbox aspect ratio'yu kullan:
    #   - dikey veya kare bbox + (head/tail var) -> sphinx (oturmus face-on kedi)
    #   - yatay bbox -> dorsal/oblique (uzanmis ama gizli omurga)
    #   - hicbiri -> frontal
    is_square_bbox = (not is_vertical_bbox) and (not is_horizontal_bbox)
    if not has_real_spine:
        if has_head and has_tail and (is_vertical_bbox or is_square_bbox):
            pose, conf = "sphinx", 0.70
            reasons.append(f"spine_extent={spine_extent_ratio:.2f} kisa, head+tail var, "
                            f"{'dikey' if is_vertical_bbox else 'kare'} bbox -> sphinx (face-on)")
        elif has_head and has_tail and is_horizontal_bbox:
            pose, conf = "oblique", 0.55
            reasons.append(f"spine_extent={spine_extent_ratio:.2f} kisa, yatay bbox -> oblique")
        elif has_head and not has_tail:
            pose, conf = "frontal", 0.75
            reasons.append(f"spine_extent={spine_extent_ratio:.2f} kisa, sadece head -> frontal")
        else:
            pose, conf = "frontal", 0.80
            reasons.append(f"spine_extent={spine_extent_ratio:.2f} cok kisa -> frontal (vucut yok)")
    else:
        # Omurga gercek (back keypointleri uzanmış)
        if is_vertical_bbox:
            pose, conf = "sphinx", 0.85
            reasons.append(f"spine_extent={spine_extent_ratio:.2f}, dikey bbox -> sphinx")
        elif is_horizontal_bbox and not both_sides:
            pose, conf = "lateral", 0.92
            reasons.append(f"spine_extent={spine_extent_ratio:.2f}, yatay+tek yan -> lateral")
        elif is_horizontal_bbox and both_sides:
            pose, conf = "dorsal", 0.80
            reasons.append(f"spine_extent={spine_extent_ratio:.2f}, yatay+iki yan -> dorsal")
        elif one_side:
            pose, conf = "lateral", 0.75
            reasons.append(f"spine_extent={spine_extent_ratio:.2f}, kare+tek yan -> lateral")
        else:
            pose, conf = "oblique", 0.60
            reasons.append(f"spine_extent={spine_extent_ratio:.2f}, kare+iki yan -> oblique")

    return {
        "type": pose,
        "confidence": round(conf, 3),
        "reasons": reasons,
        "metrics": {
            "bbox_aspect": round(aspect, 3),
            "mask_aspect": round(mask_aspect, 3),
            "head_tail_ratio": round(ht_ratio, 3),
            "n_head_kp": len(head_kp),
            "n_tail_kp": len(tail_kp),
            "n_back_kp": len(back_kp),
            "both_body_sides": both_sides,
        },
    }



# ============================================================================
# Keypoint-driven anatomical atlas
# ============================================================================
# Her organ DOGRUDAN ANATOMIK KEYPOINT'lere bagli:
#   - anchors: (keypoint_adi, agirlik) listesi — agirlikli ortalama
#   - offset_kp: "ventral" (belly yonunde) / "dorsal" (sirt yonunde) / None
#   - offset_frac: body_diameter * fraksiyon (lateral kayma)
#
# back_middle = gercek omurga noktasi → bobrek anchor
# belly_bottom = gercek karin noktasi → mesane/bagirsak anchor
# neck_base = boyun-omuz birlesimi → karaciger/mide anchor
# tail_base + back_thai'lar = pelvis bolgesi → mesane anchor
