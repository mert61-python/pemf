# Author: mertaygn, cglrgrkn
"""render.py - Tum overlay/visualization fonksiyonlari."""
from __future__ import annotations
import os, sys
from pathlib import Path
import numpy as np

from .canonical import (KEYPOINT_NAMES, CANONICAL_CAT_3D, CANONICAL_ORGANS_3D)
from .geometry import (project_3d_to_2d, project_3d_with_depth,
                                rotation_to_euler_deg, apply_morphology_to_mesh,
                                apply_morphology_to_atlas,
                                apply_beta_to_canonical, apply_beta_to_3d_array)
from .i18n import (STRINGS, ORGAN_COLORS, ORGAN_DESC, SKELETON_EDGES,
                          ORGAN_NAMES_I18N, _s, _organ_name)
from .mesh import get_canonical_mesh, get_per_cat_mesh, get_per_cat_organ_atlas


def _place_labels_no_overlap(anchors: list, img_w: int, img_h: int,
                               label_sizes: list, padding: int = 6) -> list:
    """Anchor noktalarinin etrafindaki en az ust uste binen label konumlarini secer.

    Her anchor icin 8 yondeki aday pozisyon (NE, E, SE, S, SW, W, NW, N) denenir.
    Daha az collision olan secilir.

    Returns: her anchor icin (label_x, label_y) listesi (sol-ust kose).
    """
    n = len(anchors)
    placed = [None] * n
    placed_rects = []                                   # ((x1, y1, x2, y2),)

    def collide(r, others):
        x1, y1, x2, y2 = r
        for (a, b, c, d) in others:
            if not (x2 < a or x1 > c or y2 < b or y1 > d):
                return True
        return False

    # Yakin offset'ler once, uzaklar sonra (collision durumunda kullanilir)
    offsets = [
        # Yakin (8 yon)
        (20, -8), (-20, -8), (20, 16), (-20, 16),
        (0, -22), (0, 26), (28, 6), (-28, 6),
        # Orta uzaklik (kalabalik bolgeler icin)
        (45, -8), (-45, -8), (45, 22), (-45, 22),
        (0, -42), (0, 46), (55, 6), (-55, 6),
        # Uzak (sonsuz collision olunca son care)
        (75, -8), (-75, -8), (75, 30), (-75, 30),
        (0, -65), (0, 70),
    ]
    for i, ((ax, ay), (lw, lh)) in enumerate(zip(anchors, label_sizes)):
        best_rect = None
        best_score = 1e9
        for dx, dy in offsets:
            lx = int(ax + dx)
            ly = int(ay + dy)
            x1, y1 = lx - padding, ly - lh - padding
            x2, y2 = lx + lw + padding, ly + padding
            # Kenar disina cikma cezasi
            penalty = 0
            if x1 < 0: penalty += -x1
            if y1 < 0: penalty += -y1
            if x2 > img_w: penalty += x2 - img_w
            if y2 > img_h: penalty += y2 - img_h
            # Collision sayisi
            n_coll = sum(1 for r in placed_rects if not (
                x2 < r[0] or x1 > r[2] or y2 < r[1] or y1 > r[3]))
            score = n_coll * 1000 + penalty
            if score < best_score:
                best_score = score
                best_rect = (x1, y1, x2, y2)
                placed[i] = (lx, ly)
        if best_rect is not None:
            placed_rects.append(best_rect)
    return placed


def _render_pnp_mesh(img, result, s_scale):
    """PnP-fitted mesh'i subtle translucent overlay olarak compose eder.

    Sade tasarim: wireframe yok, sadece soft fill + ince siluet outline.
    """
    import cv2
    pnp = result.get("pnp_fit")
    if pnp is None:
        return img
    R = np.asarray(result.get("R_matrix"), dtype=np.float64)
    t = np.asarray(result.get("t_vec"), dtype=np.float64)
    s = float(pnp["scale_px_per_cm"])

    mesh = get_per_cat_mesh(result)
    V = mesh["vertices"]
    F = mesh["faces"]

    V_rot = (R @ V.T).T
    V_2d = (s * V_rot[:, :2] + t).astype(np.int32)
    V_z = V_rot[:, 2]

    face_z = V_z[F].mean(axis=1)
    face_order = np.argsort(-face_z)
    face_v = V_rot[F]
    edge1 = face_v[:, 1] - face_v[:, 0]
    edge2 = face_v[:, 2] - face_v[:, 0]
    normals = np.cross(edge1, edge2)
    visible = normals[:, 2] > 0

    # Tek-renkli soft fill (depth lighting subtle)
    z_min, z_max = float(face_z.min()), float(face_z.max())
    z_range = max(z_max - z_min, 1e-3)
    canvas = img.copy()
    for fi in face_order:
        if not visible[fi]:
            continue
        tri = V_2d[F[fi]]
        d = (face_z[fi] - z_min) / z_range
        shade = int(np.clip(190 - 70 * d, 110, 220))            # acik-orta gri-mavi
        cv2.drawContours(canvas, [tri], -1, (shade, shade - 20, shade - 50),
                          thickness=cv2.FILLED)
    img_blend = cv2.addWeighted(canvas, 0.22, img, 0.78, 0)

    # Sadece dis siluet (convex hull) cizilir; tum face outlines GORUNMEZ
    vis_pts = V_2d[F[visible].flatten()]
    if len(vis_pts) >= 3:
        hull = cv2.convexHull(vis_pts)
        cv2.polylines(img_blend, [hull], True, (60, 90, 130),
                       max(1, int(0.8 * s_scale)), cv2.LINE_AA)
    return img_blend


def _segmented_cat_image(image_path: str, result: dict,
                              bg_color: tuple = (30, 30, 30)) -> "np.ndarray | None":
    """YOLO maskesi ile kediyi izole et; arka plani siyah yap.

    Returns: BGR image with cat masked, background = bg_color.
    """
    import cv2
    img = cv2.imread(image_path)
    if img is None:
        return None
    seg = result.get("segmentation") or {}
    if "mask_xy" not in seg:
        return img.copy()
    mask = np.zeros(img.shape[:2], dtype=np.uint8)
    pts = np.asarray(seg["mask_xy"], dtype=np.int32)
    cv2.fillPoly(mask, [pts], 255)
    # Background siyahlat
    bg = np.full_like(img, bg_color, dtype=img.dtype)
    out = np.where(mask[..., None].astype(bool), img, bg)
    return out


def _make_3d_side_plot(result: dict, w_px: int = 360, h_px: int = 360,
                          image_path: str | None = None,
                          target_oid: int | None = None,
                          lang: str = "tr") -> "np.ndarray | None":
    """Matplotlib ile fitted 3D mesh + organlar + (varsa) segmented kedi backdrop.

    Eger image_path verilirse, kedinin segmented image'i 3D scene'in arka
    duzleminde (camera-facing plane) texture olarak gosterilir. Boylece "3D
    icinde gercek o anki kedi" sahnesi olusur. Organlarin isimleri yanlarinda
    kucuk text olarak yer alir.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D                # noqa: F401
    except ImportError:
        return None
    pnp = result.get("pnp_fit")
    if pnp is None:
        return None
    R = np.asarray(result.get("R_matrix"), dtype=np.float64)

    fig = plt.figure(figsize=(w_px / 100, h_px / 100), dpi=100,
                        facecolor=(0.96, 0.96, 0.98))
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor((0.96, 0.96, 0.98))

    mesh = get_canonical_mesh()
    V = mesh["vertices"]
    V_rot = (R @ V.T).T
    F = mesh["faces"]

    # Eksen ortalama / range hesapla (cat extents)
    cat_extent = np.array([V_rot[:, 0].max() - V_rot[:, 0].min(),
                              V_rot[:, 1].max() - V_rot[:, 1].min(),
                              V_rot[:, 2].max() - V_rot[:, 2].min()])
    cat_max = float(cat_extent.max())
    cx = float(V_rot[:, 0].mean())
    cy = float(-V_rot[:, 2].mean())
    cz = float(-V_rot[:, 1].mean())

    # 3D mesh trisurf — anatomik bolge renkleri (canonical X'e gore)
    # Her vertex'i bolgeye gore renklendir, sonra face renk ortalamasi al
    V_x_can = V[:, 0]                                            # canonical X (cm)
    vert_colors = np.zeros((len(V), 3))
    for i, x in enumerate(V_x_can):
        if x > 9.0:                                              # head
            vert_colors[i] = (0.85, 0.55, 0.95)
        elif x > 1.0:                                            # thorax
            vert_colors[i] = (0.55, 0.85, 0.65)
        elif x > -7.0:                                           # abdomen
            vert_colors[i] = (1.0, 0.85, 0.45)
        else:                                                    # pelvis/tail
            vert_colors[i] = (0.50, 0.70, 0.95)
    face_colors = vert_colors[F].mean(axis=1)
    # Alpha kanali
    face_colors_a = np.column_stack([face_colors,
                                          np.full(len(face_colors), 0.78)])

    poly = ax.plot_trisurf(V_rot[:, 0], -V_rot[:, 2], -V_rot[:, 1],
                              triangles=F, alpha=0.78,
                              linewidth=0.08, edgecolor=(0.35, 0.42, 0.55),
                              shade=True)
    poly.set_facecolors(face_colors_a)

    # Coordinate axes (mesh extents'in disinda, kucuk + sade)
    ax_len = cat_max * 0.22                                       # kucultuldu (0.45 -> 0.22)
    ax_org = (V_rot[:, 0].max() + cat_max * 0.10,
                -V_rot[:, 2].min() - cat_max * 0.10,
                -V_rot[:, 1].min() - cat_max * 0.05)
    fs_axis = 6
    # +X cranial
    ax.quiver(ax_org[0], ax_org[1], ax_org[2], ax_len, 0, 0,
                color=(0.95, 0.30, 0.20), lw=1.6, arrow_length_ratio=0.20,
                zorder=20)
    ax.text(ax_org[0] + ax_len * 1.08, ax_org[1], ax_org[2],
              "+X", fontsize=fs_axis, color=(0.85, 0.20, 0.10),
              weight='bold', zorder=20)
    # +Z dorsal (matplotlib Z)
    ax.quiver(ax_org[0], ax_org[1], ax_org[2], 0, 0, ax_len,
                color=(0.20, 0.75, 0.30), lw=1.6, arrow_length_ratio=0.20,
                zorder=20)
    ax.text(ax_org[0], ax_org[1], ax_org[2] + ax_len * 1.10,
              "+Y", fontsize=fs_axis, color=(0.10, 0.65, 0.20),
              weight='bold', zorder=20)
    # +Y matplotlib (-Z anatomic = +Z right)
    ax.quiver(ax_org[0], ax_org[1], ax_org[2], 0, -ax_len, 0,
                color=(0.25, 0.50, 0.95), lw=1.6, arrow_length_ratio=0.20,
                zorder=20)
    ax.text(ax_org[0], ax_org[1] - ax_len * 1.15, ax_org[2],
              "+Z", fontsize=fs_axis, color=(0.15, 0.40, 0.85),
              weight='bold', zorder=20)

    # Organlar — label offset YOK, scatter pozisyonunda dogrudan yazi
    org_colors_mpl = {oid: (c[2] / 255.0, c[1] / 255.0, c[0] / 255.0)
                          for oid, c in ORGAN_COLORS.items()}
    organs = result.get("organs") or {}
    for oid_str, info in organs.items():
        oid = int(oid_str)
        x3, y3, z3 = info["coord_3d_cm"]
        p = R @ np.array([x3, y3, z3], dtype=np.float64)
        # matplotlib coord: (canonical_X, -canonical_Z, -canonical_Y)
        mx, my, mz = float(p[0]), float(-p[2]), float(-p[1])
        is_target = (target_oid is not None and oid == target_oid)
        size = 180 if is_target else 90
        ax.scatter(mx, my, mz, s=size,
                    color=org_colors_mpl.get(oid, (1, 1, 1)),
                    edgecolors=("white" if is_target else "black"),
                    linewidths=(2.0 if is_target else 0.8),
                    depthshade=False, zorder=25)
        txt = _organ_name(oid, lang) + ("*" if is_target else "")
        # Label scatter ile birebir konumda (cok kucuk offset)
        ax.text(mx, my, mz + cat_max * 0.015, txt,
                  fontsize=(8 if is_target else 6),
                  color=org_colors_mpl.get(oid, (0, 0, 0)),
                  weight=("bold" if is_target else "normal"),
                  ha='center', va='bottom', zorder=26)
    ax.set_xlabel("X (cranial)", fontsize=8)
    ax.set_ylabel("Z (right)", fontsize=8)
    ax.set_zlabel("Y (dorsal)", fontsize=8)
    yaw, pitch, roll = pnp["yaw_deg"], pnp["pitch_deg"], pnp["roll_deg"]
    ax.set_title(f"3D scene -- fitted pose: yaw={yaw:.0f}deg "
                  f"pitch={pitch:.0f}deg roll={roll:.0f}deg",
                  fontsize=9)
    ax.view_init(elev=15, azim=-75)
    ax.set_box_aspect((1.5, 1.0, 1.0))
    fig.tight_layout()
    fig.canvas.draw()
    rgba = np.asarray(fig.canvas.buffer_rgba())
    plt.close(fig)
    bgr = rgba[:, :, [2, 1, 0]].copy()

    return bgr


# ============================================================================
# Multi-aspect render helpers (her aspect ayri JPG)
# ============================================================================


def _setup_font(img):
    """Image boyutuna gore font scale/thickness tuple uret (kucuk)."""
    import cv2
    h, w = img.shape[:2]
    s = max(0.5, min(w, h) / 800.0)                              # daha kucuk
    f_scale = 0.42 * s                                            # daha kucuk font
    f_thick = max(1, int(1.5 * s))
    f_shadow = f_thick + max(2, int(2 * s))
    return s, f_scale, f_thick, f_shadow, cv2.FONT_HERSHEY_SIMPLEX


def _label(img, text, pos, color, scale, thick, shadow):
    import cv2
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0),
                 shadow, cv2.LINE_AA)
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color,
                 thick, cv2.LINE_AA)


def _panel_box(img, x, y, w_, h_, alpha=0.55, bg=(20, 20, 20)):
    """Saydam kutu cizer; img mutate edilir."""
    import cv2
    ov = img.copy()
    cv2.rectangle(ov, (x, y), (x + w_, y + h_), bg, -1)
    np.copyto(img, cv2.addWeighted(ov, alpha, img, 1.0 - alpha, 0))


def render_segmentation(image_path: str, result: dict,
                              lang: str = "tr") -> "np.ndarray | None":
    """01: YOLO bbox + mask polygon outline + vertex noktalari."""
    import cv2
    img = cv2.imread(image_path)
    if img is None:
        return None
    s, fs, ft, fsh, _ = _setup_font(img)
    seg = result.get("segmentation") or {}

    # Polygon outline + vertex noktalari
    if seg.get("mask_xy"):
        pts = np.asarray(seg["mask_xy"], dtype=np.int32)
        # Outline (yumusak yesil cizgi)
        cv2.polylines(img, [pts], True, (60, 240, 100),
                        max(2, int(1.5 * s)), cv2.LINE_AA)
        # Her polygon vertex'i kucuk daire (parlak sari)
        step = max(1, len(pts) // 80)                            # ~80 nokta
        for i in range(0, len(pts), step):
            x, y = int(pts[i][0]), int(pts[i][1])
            cv2.circle(img, (x, y), max(2, int(2.5 * s)),
                        (40, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(img, (x, y), max(2, int(2.5 * s)),
                        (20, 80, 30), 1, cv2.LINE_AA)

    bbox = seg.get("bbox") if seg else result.get("bbox")
    if bbox:
        x1, y1, x2, y2 = [int(v) for v in bbox[:4]]
        cv2.rectangle(img, (x1, y1), (x2, y2), (60, 240, 100),
                        max(2, int(2 * s)))
        n_pts = len(seg.get("mask_xy", [])) if seg else 0
        _label(img, f"{_s(lang, 'yolo_seg')}  {_s(lang, 'conf')}="
                      f"{seg.get('conf', 0):.2f}  ({n_pts} poly pts)",
                 (x1, max(int(16 * s), y1 - int(6 * s))),
                 (60, 240, 100), fs * 1.0, ft, fsh)
    return img


# Body-part renkleri (DLC skeleton coloring)


_SKEL_GROUP_COLORS = {
    # BGR — yuksek doygunluk, birbirinden net ayrisik 6 ton (HSV space'de dagilim)
    "head":      ( 80,  80, 250),   # kirmizimsi (vermilion)
    "spine":     (245, 200,  50),   # parlak mavi-cyan
    "front_leg": ( 80, 220,  80),   # parlak yesil (lime)
    "back_leg":  ( 60, 180, 250),   # turuncu (amber)
    "tail":      (220,  90, 200),   # mor-magenta (violet)
    "torso":     (180, 180, 180),   # gri
}
_EDGE_GROUP = {}


def _classify_edge(a, b):
    a_head = any(k in a for k in ("nose", "eye", "earbase", "earend",
                                       "jaw", "mouth", "antler"))
    b_head = any(k in b for k in ("nose", "eye", "earbase", "earend",
                                       "jaw", "mouth", "antler"))
    if a_head or b_head:
        return "head"
    if "front" in a or "front" in b:
        return "front_leg"
    if "back_" in a and ("knee" in a or "paw" in a or "thai" in a):
        return "back_leg"
    if "back_" in b and ("knee" in b or "paw" in b or "thai" in b):
        return "back_leg"
    if "tail" in a or "tail" in b:
        return "tail"
    if any(k in a for k in ("back_base", "back_middle", "back_end",
                                  "neck_base", "neck_end", "throat")):
        if any(k in b for k in ("back_base", "back_middle", "back_end",
                                      "neck_base", "neck_end", "throat",
                                      "tail_base")):
            return "spine"
    return "torso"


def render_keypoints(image_path: str, result: dict,
                          lang: str = "tr") -> "np.ndarray | None":
    """02: DLC skeleton + keypoint + HEAD/TAIL + sag-ust renk legend."""
    import cv2
    img = cv2.imread(image_path)
    if img is None:
        return None
    h, w = img.shape[:2]
    s, fs, ft, fsh, _ = _setup_font(img)
    pad = int(12 * s)

    pose_dict = result.get("pose") or {}
    kp_xy = {n: (int(v[0]), int(v[1])) for n, v in pose_dict.items()
              if v[2] >= 0.3}

    # Skeleton lines (anatomik renklerle, kalinlik scale)
    for a, b in SKELETON_EDGES:
        if a in kp_xy and b in kp_xy:
            color = _SKEL_GROUP_COLORS[_classify_edge(a, b)]
            cv2.line(img, kp_xy[a], kp_xy[b], color,
                      max(2, int(2 * s)), cv2.LINE_AA)
    # Keypoint kisa anatomik etiket sozlugu
    KP_SHORT = {
        "nose": "ns", "upper_jaw": "uj", "lower_jaw": "lj",
        "left_eye": "Le", "right_eye": "Re",
        "left_earbase": "Leb", "right_earbase": "Reb",
        "left_earend": "Lee", "right_earend": "Ree",
        "neck_base": "nb", "neck_end": "ne",
        "throat_base": "tb", "throat_end": "te",
        "back_base": "BB", "back_middle": "BM", "back_end": "BE",
        "tail_base": "TB", "tail_end": "TE",
        "front_left_thai": "FLt", "front_left_knee": "FLk",
        "front_left_paw": "FLp",
        "front_right_thai": "FRt", "front_right_knee": "FRk",
        "front_right_paw": "FRp",
        "back_left_thai": "BLt", "back_left_knee": "BLk",
        "back_left_paw": "BLp",
        "back_right_thai": "BRt", "back_right_knee": "BRk",
        "back_right_paw": "BRp",
        "belly_bottom": "BL", "body_middle_left": "ML",
        "body_middle_right": "MR",
    }
    # Confidence cember yaricapi -> dolgu yaricapi conf'a gore
    for n, pt in kp_xy.items():
        v = pose_dict.get(n, [0, 0, 0])
        conf = float(v[2]) if len(v) >= 3 else 1.0
        # Beyaz halo + dolu nokta + dis halka conf'a gore
        cv2.circle(img, pt, max(4, int(5 * s)), (40, 40, 40), -1, cv2.LINE_AA)
        cv2.circle(img, pt, max(3, int(3.5 * s)), (255, 255, 255), -1,
                    cv2.LINE_AA)
        # Conf ring (yesil-sari-kirmizi gradient)
        ring_col = (int(50 + 100 * (1 - conf)),                  # B
                       int(60 + 180 * conf),                        # G
                       int(60 + 180 * (1 - conf)))                  # R
        cv2.circle(img, pt, max(4, int(5 * s)), ring_col,
                    max(1, int(1.5 * s)), cv2.LINE_AA)
    # Kisa anatomik isim etiketi (low priority, sadece confidence > 0.5 olanlar)
    for n, pt in kp_xy.items():
        v = pose_dict.get(n, [0, 0, 0])
        conf = float(v[2]) if len(v) >= 3 else 1.0
        if conf < 0.5:
            continue
        short = KP_SHORT.get(n, "")
        if short:
            _label(img, short,
                     (pt[0] + int(5 * s), pt[1] - int(5 * s)),
                     (210, 230, 245), fs * 0.55,
                     max(1, ft - 1), max(2, fsh - 2))

    # HEAD/TAIL arrow + small label
    axis = result.get("axis") or {}
    if "head_pixel" in axis and "tail_pixel" in axis:
        hp = tuple(int(v) for v in axis["head_pixel"])
        tp = tuple(int(v) for v in axis["tail_pixel"])
        cv2.arrowedLine(img, tp, hp, (40, 200, 240), max(2, int(2 * s)),
                          tipLength=0.08, line_type=cv2.LINE_AA)
        _label(img, _s(lang, "head"),
                 (hp[0] + int(8 * s), hp[1] - int(6 * s)),
                 (40, 200, 240), fs * 0.95, ft, fsh)
        _label(img, _s(lang, "tail"),
                 (tp[0] + int(8 * s), tp[1] + int(16 * s)),
                 (40, 200, 240), fs * 0.95, ft, fsh)

    # Skeleton color legend (sag-ust) — kucuk
    legend_keys = [
        ("zone_head", "head"),       # kafa
        ("zone_thorax", "spine"),    # omurga -> torax
        ("zone_pelvis", "tail"),     # kuyruk
    ]
    # Daha detayli: kafa/omurga/on-bacak/arka-bacak/kuyruk
    legend_groups = [
        (("Kafa" if lang == "tr" else "Head"), _SKEL_GROUP_COLORS["head"]),
        (("Omurga" if lang == "tr" else "Spine"), _SKEL_GROUP_COLORS["spine"]),
        (("On bacak" if lang == "tr" else "Front leg"),
         _SKEL_GROUP_COLORS["front_leg"]),
        (("Arka bacak" if lang == "tr" else "Back leg"),
         _SKEL_GROUP_COLORS["back_leg"]),
        (("Kuyruk" if lang == "tr" else "Tail"),
         _SKEL_GROUP_COLORS["tail"]),
    ]
    leg_h = int(18 * s)
    leg_w = max(cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, fs * 0.85, ft)[0][0]
                  for t, _ in legend_groups) + int(34 * s)
    leg_x = w - leg_w - pad
    leg_y = pad
    _panel_box(img, leg_x, leg_y, leg_w,
                 int(8 * s) + len(legend_groups) * leg_h)
    for i, (name, col) in enumerate(legend_groups):
        yt = leg_y + int(8 * s) + (i + 1) * leg_h - int(6 * s)
        cv2.line(img, (leg_x + int(6 * s), yt - int(3 * s)),
                  (leg_x + int(24 * s), yt - int(3 * s)),
                  col, max(2, int(2.5 * s)))
        _label(img, name, (leg_x + int(28 * s), yt),
                 (240, 240, 240), fs * 0.85, ft, fsh)
    return img


def render_pnp_3d_mesh(image_path: str, result: dict,
                            lang: str = "tr") -> "np.ndarray | None":
    """03: PnP-fitted 3D mesh + HEAD/TAIL + sol-alt fit paneli (kucuk)."""
    import cv2
    img = cv2.imread(image_path)
    if img is None:
        return None
    h, w = img.shape[:2]
    s, fs, ft, fsh, _ = _setup_font(img)
    pad = int(12 * s)

    # Seg mask outline (zayif)
    seg = result.get("segmentation") or {}
    if "mask_xy" in seg:
        pts = np.asarray(seg["mask_xy"], dtype=np.int32)
        cv2.polylines(img, [pts], True, (0, 200, 0), max(1, int(1.5 * s)),
                       cv2.LINE_AA)

    # Mesh overlay
    if result.get("method", "").startswith("pnp"):
        try:
            img = _render_pnp_mesh(img, result, s)
        except Exception:
            pass

    # HEAD/TAIL arrow (orta vurgulu, kucuk yazi)
    axis = result.get("axis") or {}
    if "head_pixel" in axis and "tail_pixel" in axis:
        hp = tuple(int(v) for v in axis["head_pixel"])
        tp = tuple(int(v) for v in axis["tail_pixel"])
        cv2.arrowedLine(img, tp, hp, (40, 220, 240), max(2, int(2.5 * s)),
                          tipLength=0.06, line_type=cv2.LINE_AA)
        cv2.circle(img, hp, max(3, int(4 * s)), (40, 220, 240), -1)
        cv2.circle(img, tp, max(2, int(3 * s)), (40, 220, 240), -1)
        _label(img, _s(lang, "head"),
                 (hp[0] + int(8 * s), hp[1] - int(6 * s)),
                 (40, 220, 240), fs * 1.0, ft, fsh)
        _label(img, _s(lang, "tail"),
                 (tp[0] + int(8 * s), tp[1] + int(14 * s)),
                 (40, 220, 240), fs * 1.0, ft, fsh)

    pnp = result.get("pnp_fit")
    if pnp:
        morph = result.get("morphology") or {}
        lines = [
            f"{_s(lang, 'fit_lbl')}",
            f"  yaw={pnp['yaw_deg']:+.0f}  "
            f"pitch={pnp['pitch_deg']:+.0f}  "
            f"roll={pnp['roll_deg']:+.0f}",
            f"  {_s(lang, 'scale')}: {pnp['scale_px_per_cm']:.1f} "
            f"{_s(lang, 'scale_unit')}",
            f"  {_s(lang, 'reproj_err')}: {pnp['residual_px']:.1f}px"
            f"   {_s(lang, 'inliers')}: "
            f"{pnp.get('n_inliers', '?')}/{pnp.get('n_keypoints_used', '?')}",
        ]
        if morph:
            lines.append(
                f"  morph: sx={morph.get('sx', 1):.2f} "
                f"sy={morph.get('sy', 1):.2f} "
                f"sz={morph.get('sz', 1):.2f} "
                f"BCS={morph.get('bcs', 0):+.2f}")
        if pnp.get("mirror_warning"):
            lines.append(f"! {_s(lang, 'mirror_warn')}")
        line_h = int(15 * s)
        panel_w = max(cv2.getTextSize(l, cv2.FONT_HERSHEY_SIMPLEX, fs * 0.78,
                                              ft)[0][0] for l in lines) + 2 * pad
        panel_h = int(6 * s) + len(lines) * line_h
        _panel_box(img, pad // 2, h - pad // 2 - panel_h,
                     panel_w + pad, panel_h, alpha=0.55)
        for i, line in enumerate(lines):
            yt = h - pad // 2 - panel_h + (i + 1) * line_h - int(3 * s)
            color = (255, 200, 80) if line.startswith("!") else (240, 240, 240)
            _label(img, line, (pad, yt), color, fs * 0.78, ft, fsh)
    return img


def render_organs_classic(image_path: str, result: dict,
                              target_oid: int | None = None,
                              lang: str = "tr") -> "np.ndarray | None":
    """04: SADECE organ pozisyonlari (panel/baslik yok).

    Klasik tasarim: organ noktalari + renkli isimler + hedef halo.
    """
    import cv2
    img = cv2.imread(image_path)
    if img is None:
        return None
    h, w = img.shape[:2]
    s, fs, ft, fsh, font = _setup_font(img)

    organs = result.get("organs") or {}
    rad = int(5 * s); rad_t = int(9 * s); halo = int(18 * s)

    anchors, labels, sizes, metas = [], [], [], []
    for oid_str, info in sorted(organs.items(), key=lambda kv: int(kv[0])):
        oid = int(oid_str)
        x, y = info["pixel_xy"]
        color = ORGAN_COLORS.get(oid, (255, 255, 255))
        is_target = (target_oid is not None and oid == target_oid)
        text = _organ_name(oid, lang) + ("*" if is_target else "")
        sc = fs * (0.95 if is_target else 0.78)
        (tw, th_), _ = cv2.getTextSize(text, font, sc, ft)
        anchors.append((int(x), int(y)))
        labels.append((text, sc))
        sizes.append((tw, th_))
        metas.append((oid, color, is_target))
    placements = _place_labels_no_overlap(anchors, w, h, sizes,
                                              padding=int(3 * s))

    for (ax, ay), (lx, ly), (oid, color, is_target) in zip(
            anchors, placements, metas):
        if is_target:
            cv2.circle(img, (ax, ay), halo, color, max(1, int(2 * s)),
                        cv2.LINE_AA)
            cv2.circle(img, (ax, ay), rad_t, color, -1, cv2.LINE_AA)
            cv2.circle(img, (ax, ay), rad_t, (255, 255, 255),
                        max(1, int(1.5 * s)), cv2.LINE_AA)
        else:
            cv2.circle(img, (ax, ay), rad, color, -1, cv2.LINE_AA)
            cv2.circle(img, (ax, ay), rad, (0, 0, 0),
                        max(1, int(s)), cv2.LINE_AA)
        cv2.line(img, (ax, ay), (lx, ly), color, max(1, int(s)),
                  cv2.LINE_AA)
    for (lx, ly), (text, sc), (oid, color, is_target) in zip(
            placements, labels, metas):
        _label(img, text, (lx, ly), color, sc, ft, fsh)
    return img


def render_deskewed_with_organs(image_path: str, result: dict,
                                     target_oid: int | None = None,
                                     target_h_px: int = 800,
                                     lang: str = "tr") -> "np.ndarray | None":
    """05: Kedinin gercek lateral side-view'i + organ projeksiyonlari.

    Yaklasim: Canonical cat mesh'i kamera-bagimsiz LATERAL view'dan render
    eder (yaw=90°, pitch=0, roll=0 — kafa sagda, kuyruk solda, sirt yukari).
    Boylece input pozdan bagimsiz olarak her zaman dogru yandan goruntu
    elde edilir. Organlar canonical 3D pozisyonlarinda yerlestirilir.
    Sag-altta kucuk pencere: actual input image deskewed (similarity warp)
    referans icin.
    """
    import cv2
    # Lateral render canvas (koyu gradient arka plan)
    target_w = int(target_h_px * 2.1)
    img = np.zeros((target_h_px, target_w, 3), dtype=np.uint8)
    # Radial gradient: merkeze yakin daha aydinlik, kenarlar koyu
    yy, xx = np.indices((target_h_px, target_w))
    cy_grad = target_h_px / 2.0
    cx_grad = target_w / 2.0
    r_max = float(np.sqrt(cx_grad ** 2 + cy_grad ** 2))
    r_norm = np.sqrt((xx - cx_grad) ** 2 + (yy - cy_grad) ** 2) / r_max
    bg = (1.0 - 0.6 * r_norm)                                     # 0.4..1.0
    img[..., 0] = (bg * 38).astype(np.uint8)
    img[..., 1] = (bg * 42).astype(np.uint8)
    img[..., 2] = (bg * 52).astype(np.uint8)

    # Canonical lateral cat mesh: R=I, kamera +z'den bakar
    mesh = get_canonical_mesh()
    V = mesh["vertices"]                                       # (V, 3) cm
    F = mesh["faces"]
    # Lateral view: cm -> pixel, image y down
    s_target = (target_h_px * 0.7) / 22.0                      # 22 cm dorso-ventral
    cx, cy = target_w / 2, target_h_px / 2
    V_2d = np.column_stack([
        cx + V[:, 0] * s_target,
        cy - V[:, 1] * s_target,
    ]).astype(np.int32)
    V_z = V[:, 2]

    # cm grid (her 5cm) - subtle
    grid_color = (60, 65, 75)
    grid_thick = 1
    for dx_cm in range(-30, 31, 5):
        gx = int(cx + dx_cm * s_target)
        if 0 <= gx < target_w:
            cv2.line(img, (gx, 0), (gx, target_h_px), grid_color,
                      grid_thick, cv2.LINE_AA)
    for dy_cm in range(-15, 16, 5):
        gy = int(cy - dy_cm * s_target)
        if 0 <= gy < target_h_px:
            cv2.line(img, (0, gy), (target_w, gy), grid_color,
                      grid_thick, cv2.LINE_AA)

    # Anatomik bolge zonlari (canonical X kullanilarak boyanir, semi-transparent)
    # Head: X > +9, Thorax/cranial: +9..0, Abdomen: 0..-9, Pelvis/caudal: < -9
    zone_overlay = img.copy()
    zone_alpha = 0.18
    zones = [
        # (x_min_cm, x_max_cm, BGR color, label_key)
        (+9.0, +25.0, (150, 100, 250), _s(lang, "zone_head")),
        (+1.0,  +9.0, (180, 220, 100), _s(lang, "zone_thorax")),
        (-7.0,  +1.0, (255, 220,  80), _s(lang, "zone_abdomen")),
        (-25.0, -7.0, (110, 180, 255), _s(lang, "zone_pelvis")),
    ]
    for x_lo, x_hi, color, _ in zones:
        x1 = int(cx + x_lo * s_target)
        x2 = int(cx + x_hi * s_target)
        # Vurgu: yalniz mesh'in dikey araliginda
        y1 = int(cy - 11.5 * s_target)
        y2 = int(cy + 14.5 * s_target)
        cv2.rectangle(zone_overlay, (x1, y1), (x2, y2), color, -1)
    np.copyto(img, cv2.addWeighted(zone_overlay, zone_alpha,
                                          img, 1 - zone_alpha, 0))

    # Face z-sort + backface culling
    face_z = V_z[F].mean(axis=1)
    face_order = np.argsort(-face_z)
    face_v = V[F]
    e1 = face_v[:, 1] - face_v[:, 0]
    e2 = face_v[:, 2] - face_v[:, 0]
    normals = np.cross(e1, e2)
    visible = normals[:, 2] > 0
    z_min, z_max = float(face_z.min()), float(face_z.max())
    z_range = max(z_max - z_min, 1e-3)

    # Mesh fill: Phong-like shading using normal.z (depth) ve y (yon)
    # Body region renkleri: head/torso/limbs gibi farkli tonlar
    for fi in face_order:
        if not visible[fi]:
            continue
        tri = V_2d[F[fi]]
        d = (face_z[fi] - z_min) / z_range                      # 0..1 (on..arka)
        # Light direction: yukari-on (Y+, Z+)
        n = normals[fi] / max(np.linalg.norm(normals[fi]), 1e-6)
        light = np.array([0.3, 0.6, 0.6])
        light /= np.linalg.norm(light)
        shade = float(np.clip(np.dot(n, light), 0.25, 1.0))
        # Base tone: soft cream/beige
        base = np.array([195, 210, 220])
        c = base * (0.55 + 0.45 * shade) * (1.0 - 0.18 * d)
        c = np.clip(c, 40, 240).astype(int)
        cv2.drawContours(img, [tri], -1, (int(c[0]), int(c[1]),
                                                int(c[2])),
                          thickness=cv2.FILLED, lineType=cv2.LINE_AA)
    # Wireframe outline (cok subtle)
    for fi in np.where(visible)[0]:
        tri = V_2d[F[fi]]
        cv2.polylines(img, [tri], True, (95, 105, 120), 1, cv2.LINE_AA)
    # Disline (silhouette): visible olmayanlar arasinda kenar varsa cizmek
    # icin convex hull yaklasimi
    visible_verts = np.unique(F[visible])
    if len(visible_verts) > 3:
        hull_pts = cv2.convexHull(V_2d[visible_verts])
        cv2.polylines(img, [hull_pts], True, (50, 80, 110),
                       max(2, int(2 * s_target / 30)), cv2.LINE_AA)

    h, w = target_h_px, target_w
    s, fs, ft, fsh, font = _setup_font(img)
    pad = int(12 * s)

    # HEAD/TAIL canonical mesh ucu
    pnp = result.get("pnp_fit") or {}
    K3 = np.array([CANONICAL_CAT_3D[n] for n in KEYPOINT_NAMES],
                    dtype=np.float64)
    pts_canon = np.column_stack([
        cx + K3[:, 0] * s_target,
        cy - K3[:, 1] * s_target,
    ])
    head_kp_idx = KEYPOINT_NAMES.index("nose")
    tail_kp_idx = KEYPOINT_NAMES.index("tail_end")
    hp = tuple(int(v) for v in pts_canon[head_kp_idx])
    tp = tuple(int(v) for v in pts_canon[tail_kp_idx])
    cv2.arrowedLine(img, tp, hp, (40, 200, 240), max(2, int(2 * s)),
                      tipLength=0.05, line_type=cv2.LINE_AA)
    _label(img, _s(lang, "head"), (hp[0] + int(8 * s), hp[1] - int(6 * s)),
             (40, 200, 240), fs * 0.90, ft, fsh)
    _label(img, _s(lang, "tail"), (tp[0] - int(55 * s), tp[1] - int(6 * s)),
             (40, 200, 240), fs * 0.90, ft, fsh)

    # Organlar canonical lateral pozisyonda (kucuk marker'lar)
    organs = result.get("organs") or {}
    anchors, labels, sizes, metas = [], [], [], []
    rad = int(5 * s); rad_t = int(9 * s); halo = int(18 * s)
    # Per-cat scaled atlas (L1+L2)
    per_cat_atlas = get_per_cat_organ_atlas(result)
    # z-stagger: lateral mesh'te (R=I projection drop z), z bileseni
    # yalnizca depth icin kullaniliyor. Bu durumda sol/sag eslesik organlar
    # (akciger_sag z=+3, akciger_sol z=-3) ayni 2D noktaya dusuyor.
    # Z'nin %18 kismini X'e ekleyerek depth illusion + label collision'i azaltan
    # gorsel ayrim saglariz.
    Z_STAGGER = 0.18                                              # 18% z -> x
    for oid, (oname, x3, y3, z3) in per_cat_atlas.items():
        if oid not in organs and str(oid) not in organs:
            continue
        px = cx + (x3 + z3 * Z_STAGGER) * s_target
        py = cy - y3 * s_target
        color = ORGAN_COLORS.get(oid, (255, 255, 255))
        is_target = (target_oid is not None and oid == target_oid)
        text = _organ_name(oid, lang) + ("*" if is_target else "")
        sc = fs * (0.95 if is_target else 0.80)
        (tw, th_), _ = cv2.getTextSize(text, font, sc, ft)
        anchors.append((int(px), int(py)))
        labels.append((text, sc))
        sizes.append((tw, th_))
        metas.append((oid, color, is_target))
    placements = _place_labels_no_overlap(anchors, w, h, sizes,
                                              padding=int(3 * s))
    for (ax, ay), (lx, ly), (oid, color, is_target) in zip(
            anchors, placements, metas):
        if is_target:
            cv2.circle(img, (ax, ay), halo, color, max(1, int(2 * s)),
                        cv2.LINE_AA)
            cv2.circle(img, (ax, ay), rad_t, color, -1, cv2.LINE_AA)
            cv2.circle(img, (ax, ay), rad_t, (255, 255, 255),
                        max(1, int(1.5 * s)), cv2.LINE_AA)
        else:
            cv2.circle(img, (ax, ay), rad, color, -1, cv2.LINE_AA)
            cv2.circle(img, (ax, ay), rad, (0, 0, 0),
                        max(1, int(s)), cv2.LINE_AA)
        cv2.line(img, (ax, ay), (lx, ly), color, max(1, int(s)),
                  cv2.LINE_AA)
    for (lx, ly), (text, sc), (oid, color, is_target) in zip(
            placements, labels, metas):
        _label(img, text, (lx, ly), color, sc, ft, fsh)

    # Inset: actual segmented cat image (kucuk pencere referans)
    seg_cat = _segmented_cat_image(image_path, result, bg_color=(40, 40, 40))
    if seg_cat is not None:
        # Inset boyut: target_h * 0.30
        inset_h = int(target_h_px * 0.32)
        ratio = seg_cat.shape[1] / seg_cat.shape[0]
        inset_w = int(inset_h * ratio)
        if inset_w > target_w * 0.4:
            inset_w = int(target_w * 0.4)
            inset_h = int(inset_w / ratio)
        inset = cv2.resize(seg_cat, (inset_w, inset_h),
                              interpolation=cv2.INTER_AREA)
        # Sag-altta yerlestir
        ix = target_w - inset_w - pad
        iy = target_h_px - inset_h - pad
        cv2.rectangle(img, (ix - 3, iy - 3),
                        (ix + inset_w + 3, iy + inset_h + 3),
                        (180, 180, 200), 2)
        img[iy:iy + inset_h, ix:ix + inset_w] = inset
        _label(img, _s(lang, "camera_view"),
                 (ix + 4, iy - int(6 * s)),
                 (180, 200, 230), fs * 0.80, ft, fsh)

    # Zone label'lari (mesh ALTINA — paw seviyesi)
    for x_lo, x_hi, color, zlabel in zones:
        zx = int(cx + (x_lo + x_hi) / 2 * s_target)
        zy = int(cy + 13.5 * s_target)
        # Etiket arkasi yumusak panel
        (tw, th_), _ = cv2.getTextSize(zlabel, font, fs * 0.85, ft)
        cv2.rectangle(img,
                        (zx - tw // 2 - int(4 * s), zy - th_ - int(4 * s)),
                        (zx + tw // 2 + int(4 * s), zy + int(4 * s)),
                        (25, 30, 40), -1)
        _label(img, zlabel, (zx - tw // 2, zy),
                 color, fs * 0.85, ft, fsh)

    # Scale bar (sol-altta, 10 cm)
    sb_x = pad
    sb_y = target_h_px - int(50 * s)
    sb_len = int(10 * s_target)                                  # 10 cm
    cv2.line(img, (sb_x, sb_y), (sb_x + sb_len, sb_y),
              (240, 240, 240), max(2, int(2 * s)), cv2.LINE_AA)
    cv2.line(img, (sb_x, sb_y - int(6 * s)),
              (sb_x, sb_y + int(6 * s)),
              (240, 240, 240), max(2, int(2 * s)), cv2.LINE_AA)
    cv2.line(img, (sb_x + sb_len, sb_y - int(6 * s)),
              (sb_x + sb_len, sb_y + int(6 * s)),
              (240, 240, 240), max(2, int(2 * s)), cv2.LINE_AA)
    # Tick'ler her 1cm
    for k in range(1, 10):
        kx = sb_x + int(k * s_target)
        cv2.line(img, (kx, sb_y - int(3 * s)),
                  (kx, sb_y + int(3 * s)),
                  (200, 200, 200), 1, cv2.LINE_AA)
    _label(img, _s(lang, "scale_bar"),
             (sb_x + int(sb_len / 2 - 18 * s), sb_y + int(18 * s)),
             (240, 240, 240), fs * 0.80, ft, fsh)

    # Compass (sol-ust altina): cranial/dorsal/lateral okları
    cmp_x = pad + int(34 * s)
    cmp_y = pad + int(70 * s)
    cmp_r = int(25 * s)
    cv2.circle(img, (cmp_x, cmp_y), cmp_r + 4, (40, 50, 65), -1, cv2.LINE_AA)
    cv2.circle(img, (cmp_x, cmp_y), cmp_r + 4, (180, 200, 230),
                max(1, int(1.2 * s)), cv2.LINE_AA)
    # +X cranial: saga
    cv2.arrowedLine(img, (cmp_x, cmp_y), (cmp_x + cmp_r, cmp_y),
                      (100, 230, 240), max(2, int(2 * s)), tipLength=0.3,
                      line_type=cv2.LINE_AA)
    _label(img, _s(lang, "cranial"),
             (cmp_x + cmp_r + int(3 * s), cmp_y + int(4 * s)),
             (100, 230, 240), fs * 0.70, max(1, ft - 1), fsh)
    cv2.arrowedLine(img, (cmp_x, cmp_y), (cmp_x, cmp_y - cmp_r),
                      (120, 220, 120), max(2, int(2 * s)), tipLength=0.3,
                      line_type=cv2.LINE_AA)
    _label(img, _s(lang, "dorsal"),
             (cmp_x - int(32 * s), cmp_y - cmp_r - int(4 * s)),
             (120, 220, 120), fs * 0.70, max(1, ft - 1), fsh)
    return img


def render_3d_view_standalone(result: dict, w_px: int = 900,
                                    h_px: int = 900,
                                    image_path: str | None = None,
                                    target_oid: int | None = None,
                                    lang: str = "tr") -> "np.ndarray | None":
    """06: Buyuk 3D scene + segmented kedi inset + organ labels (lang)."""
    return _make_3d_side_plot(result, w_px, h_px,
                                  image_path=image_path,
                                  target_oid=target_oid,
                                  lang=lang)


def draw_overlay(image_path: str, result: dict, out_path: str,
                  target_oid: int | None = None,
                  lang: str = "tr") -> bool:
    """07: 4 onemli paneli 2x2 grid'de birlestiren ozet."""
    try:
        import cv2
    except ImportError:
        return False

    p1 = render_keypoints(image_path, result, lang=lang)
    p2 = render_organs_classic(image_path, result, target_oid=target_oid,
                                    lang=lang)
    p3 = render_deskewed_with_organs(image_path, result, target_oid=target_oid,
                                          target_h_px=600, lang=lang)
    p4 = _make_3d_side_plot(result, w_px=800, h_px=600,
                                  image_path=image_path,
                                  target_oid=target_oid,
                                  lang=lang)

    panels = [(p, lbl) for p, lbl in
                ((p1, "02"), (p2, "04"), (p3, "05"), (p4, "06"))
                if p is not None]
    if len(panels) < 4:
        # fallback eski yontem: ilk panel veya solid
        cv2.imwrite(out_path, p1 if p1 is not None else
                      cv2.imread(image_path))
        return True

    # Her paneli ayni yukseklige resize et (2x2 grid icin)
    target_h = 600
    rescaled = []
    for p, lbl in panels:
        ph, pw = p.shape[:2]
        new_h = target_h
        new_w = int(pw * target_h / ph)
        rescaled.append((cv2.resize(p, (new_w, new_h),
                                          interpolation=cv2.INTER_AREA), lbl))
    # Iki satir: max genislik
    top_w = rescaled[0][0].shape[1] + rescaled[1][0].shape[1]
    bot_w = rescaled[2][0].shape[1] + rescaled[3][0].shape[1]
    grid_w = max(top_w, bot_w) + 30
    grid_h = target_h * 2 + 30
    grid = np.full((grid_h, grid_w, 3), 18, dtype=np.uint8)
    # Yerlestir
    gap = 10
    x = gap
    grid[gap:gap + target_h, x:x + rescaled[0][0].shape[1]] = rescaled[0][0]
    x += rescaled[0][0].shape[1] + gap
    grid[gap:gap + target_h, x:x + rescaled[1][0].shape[1]] = rescaled[1][0]
    x = gap
    grid[gap + target_h + gap:gap + 2 * target_h + gap,
         x:x + rescaled[2][0].shape[1]] = rescaled[2][0]
    x += rescaled[2][0].shape[1] + gap
    grid[gap + target_h + gap:gap + 2 * target_h + gap,
         x:x + rescaled[3][0].shape[1]] = rescaled[3][0]
    cv2.imwrite(out_path, grid)
    return True


# ============================================================================
# CLI
# ============================================================================
