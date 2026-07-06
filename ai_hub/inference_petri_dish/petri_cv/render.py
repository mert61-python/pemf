"""render.py — Multi-Well 7-panel TR+EN overlay (adaptif font).

Kedi (inference_cat_organ) 10 organ render paterniyle uyumlu:
    - Her kuyucuk numarali (W1, W2, ...)
    - Cabin frame mm koordinati
    - Kanser/saglikli renk kodlu (kirmizi/yesil)

7 panel:
    01_input.jpg          — orijinal giris
    02_yolo_dets.jpg      — YOLO bbox + kontur + conf
    03_yolo_masks.jpg     — YOLO mask + bbox
    04_classify.jpg       — kuyucuk sinif (kanser/saglikli)
    05_local_coords.jpg   — her kuyucuk mm koord + well_id
    06_predictions.jpg    — D[7] bar + E_kanser
    07_combined.jpg       — 6 panel 3x2 grid
"""
from __future__ import annotations
from pathlib import Path

import cv2
import numpy as np


COLOR_CANCER   = (0, 0, 255)         # kirmizi
COLOR_HEALTHY  = (60, 200, 60)       # yesil
COLOR_DETECT   = (255, 200, 0)       # acik mavi
COLOR_ORIGIN   = (255, 255, 0)       # cyan
COLOR_AXIS_X   = (0, 0, 255)
COLOR_AXIS_Y   = (0, 255, 0)
COLOR_TEXT     = (255, 255, 255)
COLOR_BG       = (40, 40, 40)


LANG = {
    "tr": {
        "input":     "Giris",
        "yolo":      "YOLO Kuyucuk Tespiti",
        "masks":     "YOLO Mask + BBox",
        "classify":  "Siniflandirma",
        "coords":    "Cabin Koordinatlari (mm)",
        "predict":   "PEMF Tahminleri",
        "combined":  "Tam Ozet",
        "well_lbl":  "{wid} A={a}px",
        "origin":    "Origin",
        "no_well":   "Kuyucuk bulunamadi",
        "method":    "Yontem: {m}",
        "mm_per_px": "Olcek: {s:.3f} mm/px",
        "n_wells":   "Kuyucuk: {n}",
        "n_cancer":  "Kanser: {n}",
        "n_healthy": "Saglikli: {n}",
        "cancer":    "KANSER",
        "healthy":   "SAGLIKLI",
        "E_cancer":  "E_kanser",
        "duty":      "D[7]",
    },
    "en": {
        "input":     "Input",
        "yolo":      "YOLO Well Detection",
        "masks":     "YOLO Mask + BBox",
        "classify":  "Classification",
        "coords":    "Cabin Coordinates (mm)",
        "predict":   "PEMF Predictions",
        "combined":  "Full Summary",
        "well_lbl":  "{wid} A={a}px",
        "origin":    "Origin",
        "no_well":   "No well found",
        "method":    "Method: {m}",
        "mm_per_px": "Scale: {s:.3f} mm/px",
        "n_wells":   "Wells: {n}",
        "n_cancer":  "Cancer: {n}",
        "n_healthy": "Healthy: {n}",
        "cancer":    "CANCER",
        "healthy":   "HEALTHY",
        "E_cancer":  "E_cancer",
        "duty":      "D[7]",
    },
}


class Style:
    """Goruntu boyutuna gore adaptif stil parametreleri."""
    def __init__(self, image_shape: tuple[int, int]):
        h, w = image_shape[:2]
        short = min(h, w)
        s = max(0.30, min(1.0, short / 1000))
        self.font_small  = max(0.30, s * 0.45)
        self.font_normal = max(0.35, s * 0.55)
        self.font_large  = max(0.45, s * 0.75)
        self.font_title  = max(0.50, s * 0.85)
        self.thick_thin  = max(1, int(s * 1.5))
        self.thick_med   = max(1, int(s * 2.5))
        self.thick_thick = max(2, int(s * 3.5))
        self.dot_small   = max(2, int(s * 4))
        self.dot_med     = max(3, int(s * 6))
        self.dot_large   = max(5, int(s * 10))
        self.ring_med    = max(6, int(s * 12))
        self.ring_large  = max(10, int(s * 18))
        self.header_h    = max(28, int(s * 40))
        self.text_pad    = max(5, int(s * 10))


def _put_text(img, text, org, style: Style, *,
              color=COLOR_TEXT, scale=None, thickness=None, bg=True):
    scale = scale if scale is not None else style.font_normal
    thickness = thickness if thickness is not None else style.thick_thin
    if bg:
        (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX,
                                    scale, thickness)
        x, y = org
        pad = max(2, int(scale * 4))
        cv2.rectangle(img, (x - pad, y - h - pad),
                      (x + w + pad, y + pad), (0, 0, 0), -1)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX,
                scale, color, thickness, cv2.LINE_AA)


def _header(img, title, style: Style):
    h, w = img.shape[:2]
    band = np.full((style.header_h, w, 3), COLOR_BG, dtype=np.uint8)
    (tw, th), _ = cv2.getTextSize(title, cv2.FONT_HERSHEY_DUPLEX,
                                  style.font_title, style.thick_med)
    yy = (style.header_h + th) // 2
    cv2.putText(band, title, (style.text_pad, yy), cv2.FONT_HERSHEY_DUPLEX,
                style.font_title, (255, 255, 255),
                style.thick_med, cv2.LINE_AA)
    return np.vstack([band, img])


def _well_color(organ_id: int) -> tuple[int, int, int]:
    return COLOR_CANCER if organ_id == 1 else COLOR_HEALTHY


def panel_01_input(img, lang="tr"):
    style = Style(img.shape)
    return _header(img.copy(), f"01 - {LANG[lang]['input']}", style)


def panel_02_yolo(img, detections, wells, method, mm_per_px, lang="tr"):
    """YOLO bbox + kontur + conf + well_id."""
    L = LANG[lang]
    style = Style(img.shape)
    out = img.copy()
    if not detections:
        _put_text(out, L["no_well"], (style.text_pad, out.shape[0] // 2),
                  style, color=(0, 0, 255), scale=style.font_large,
                  thickness=style.thick_med)
        return _header(out, f"02 - {L['yolo']}", style)

    # Detections ve wells ayni siralamada
    for i, (det, well) in enumerate(zip(detections, wells), 1):
        col = _well_color(well.organ_id)
        cv2.drawContours(out, [det.contour], -1, col, style.thick_med)
        x1, y1, x2, y2 = (int(v) for v in det.bbox_xyxy)
        cv2.rectangle(out, (x1, y1), (x2, y2), col, style.thick_thin)
        cx, cy = int(det.centroid_px[0]), int(det.centroid_px[1])
        cv2.circle(out, (cx, cy), style.dot_med, col, -1)
        # well_id + conf
        _put_text(out, f"{well.well_id} {det.conf:.2f}",
                  (x1 + 3, y1 - 3), style,
                  color=col, scale=style.font_small)

    H = out.shape[0]
    _put_text(out, L["method"].format(m=method),
              (style.text_pad, H - 2 * (style.header_h // 2)), style)
    _put_text(out, L["mm_per_px"].format(s=mm_per_px),
              (style.text_pad, H - style.header_h // 2), style)
    return _header(out, f"02 - {L['yolo']}", style)


def panel_03_masks(img, detections, wells, lang="tr"):
    """YOLO mask overlay + bbox + well_id."""
    L = LANG[lang]
    style = Style(img.shape)
    out = img.copy()
    if detections:
        overlay = np.zeros_like(out)
        for det, well in zip(detections, wells):
            col = _well_color(well.organ_id)
            overlay[det.mask > 0] = col
        out = cv2.addWeighted(out, 0.55, overlay, 0.45, 0)
        for det, well in zip(detections, wells):
            col = _well_color(well.organ_id)
            cv2.drawContours(out, [det.contour], -1, col, style.thick_med)
            x1, y1, x2, y2 = (int(v) for v in det.bbox_xyxy)
            cv2.rectangle(out, (x1, y1), (x2, y2), col, style.thick_thin)
    return _header(out, f"03 - {L['masks']}", style)


def panel_04_classify(img, wells, lang="tr"):
    """Kanser/saglikli siniflandirma — kuyucuk basina label + sayilar."""
    L = LANG[lang]
    style = Style(img.shape)
    out = img.copy()
    for well in wells:
        col = _well_color(well.organ_id)
        cx, cy = int(well.centroid_px[0]), int(well.centroid_px[1])
        cv2.circle(out, (cx, cy), style.ring_large, col, style.thick_thick)
        label = L["cancer"] if well.organ_id == 1 else L["healthy"]
        _put_text(out, f"{well.well_id}: {label}",
                  (cx - style.ring_large, cy - style.ring_large - 3),
                  style, color=col, scale=style.font_small,
                  thickness=style.thick_thin)
    H = out.shape[0]
    n_cancer = sum(1 for w in wells if w.organ_id == 1)
    n_healthy = sum(1 for w in wells if w.organ_id == 0)
    _put_text(out, L["n_wells"].format(n=len(wells)),
              (style.text_pad, H - 3 * (style.header_h // 2)), style,
              color=COLOR_TEXT, scale=style.font_normal,
              thickness=style.thick_med)
    _put_text(out, L["n_cancer"].format(n=n_cancer),
              (style.text_pad, H - 2 * (style.header_h // 2)), style,
              color=COLOR_CANCER, scale=style.font_normal,
              thickness=style.thick_med)
    _put_text(out, L["n_healthy"].format(n=n_healthy),
              (style.text_pad, H - style.header_h // 2), style,
              color=COLOR_HEALTHY, scale=style.font_normal,
              thickness=style.thick_med)
    return _header(out, f"04 - {L['classify']}", style)


def panel_05_coords(img, wells, lang="tr"):
    """Her kuyucuk mm koordinat (kedi'deki organ koord gibi)."""
    L = LANG[lang]
    style = Style(img.shape)
    out = img.copy()
    if wells:
        # Origin: en buyuk kuyucuk merkezi (varsayim — pipeline'da ref_cx,cy)
        primary = max(wells, key=lambda w: w.area_px)
        cx, cy = int(primary.centroid_px[0]), int(primary.centroid_px[1])
        arrow_len = max(40, int(min(out.shape[:2]) * 0.08))
        cv2.circle(out, (cx, cy), style.dot_med, COLOR_ORIGIN, -1)
        cv2.arrowedLine(out, (cx, cy), (cx + arrow_len, cy), COLOR_AXIS_X,
                        style.thick_med, tipLength=0.2)
        cv2.arrowedLine(out, (cx, cy), (cx, cy - arrow_len), COLOR_AXIS_Y,
                        style.thick_med, tipLength=0.2)
        _put_text(out, "+X", (cx + arrow_len + 3, cy + 6), style,
                  color=COLOR_AXIS_X)
        _put_text(out, "+Y", (cx - 10, cy - arrow_len - 3), style,
                  color=COLOR_AXIS_Y)

    for well in wells:
        col = _well_color(well.organ_id)
        px = (int(well.centroid_px[0]), int(well.centroid_px[1]))
        cv2.circle(out, px, style.dot_med, col, -1)
        x, y, _z = well.centroid_cabin_mm
        txt = f"{well.well_id} ({x:+.1f},{y:+.1f})mm"
        _put_text(out, txt, (px[0] + style.dot_med + 3, px[1]), style,
                  color=col, scale=style.font_small)
    return _header(out, f"05 - {L['coords']}", style)


def panel_06_predictions(img, wells, lang="tr"):
    """Her kuyucuk icin D[7] bar + E_kanser ozeti."""
    L = LANG[lang]
    style = Style(img.shape)
    h, w = img.shape[:2]
    overlay = np.zeros_like(img)
    cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
    out = cv2.addWeighted(img, 0.20, overlay, 0.80, 0)

    if not wells:
        _put_text(out, L["no_well"], (w // 2 - int(w * 0.15), h // 2), style,
                  color=(0, 255, 255), scale=style.font_large,
                  thickness=style.thick_med)
        return _header(out, f"06 - {L['predict']}", style)

    # Her kuyucuk icin satir
    n_show = min(8, len(wells))
    row_h = max(60, (h - 20) // n_show)
    for i, well in enumerate(wells[:n_show]):
        y0 = 10 + i * row_h
        col = _well_color(well.organ_id)
        x, y, _z = well.centroid_cabin_mm
        head = (f"{well.well_id} {well.label[:1].upper()} "
                f"({x:+.1f},{y:+.1f})mm E={well.E_cancer:.3f}")
        _put_text(out, head, (style.text_pad, y0 + int(row_h * 0.30)),
                  style, color=col,
                  scale=style.font_small, thickness=style.thick_thin)
        # D[7] mini bar
        bar_y = y0 + int(row_h * 0.55)
        bar_w = max(3, (w - 2 * style.text_pad) // 7)
        bar_h_max = max(8, int(row_h * 0.30))
        for k, dv in enumerate(well.D):
            bh = max(2, int(bar_h_max * dv))
            bx = style.text_pad + k * bar_w
            cv2.rectangle(out, (bx, bar_y + bar_h_max - bh),
                          (bx + bar_w - 2, bar_y + bar_h_max),
                          (200, 200, 0), -1)
    if len(wells) > n_show:
        _put_text(out, f"... +{len(wells) - n_show}",
                  (style.text_pad, h - style.header_h // 2), style,
                  color=COLOR_TEXT, scale=style.font_small)
    return _header(out, f"06 - {L['predict']}", style)


def panel_07_combined(panels, lang="tr"):
    L = LANG[lang]
    style = Style(panels[0].shape)
    if len(panels) < 6:
        return _header(panels[0], f"07 - {L['combined']}", style)
    h_target = max(280, panels[0].shape[0])
    resized = []
    for p in panels[:6]:
        rh, rw = p.shape[:2]
        sc = h_target / rh
        rw_new = int(rw * sc)
        resized.append(cv2.resize(p, (rw_new, h_target)))
    rows = []
    for i in range(0, 6, 2):
        a, b = resized[i], resized[i + 1]
        tw = max(a.shape[1], b.shape[1])
        if a.shape[1] != tw:
            a = cv2.resize(a, (tw, h_target))
        if b.shape[1] != tw:
            b = cv2.resize(b, (tw, h_target))
        rows.append(np.hstack([a, b]))
    max_w = max(r.shape[1] for r in rows)
    aligned = [cv2.copyMakeBorder(r, 0, 0, 0, max_w - r.shape[1],
                                   cv2.BORDER_CONSTANT, value=COLOR_BG)
               for r in rows]
    combined = np.vstack(aligned)
    return _header(combined, f"07 - {L['combined']}", Style(combined.shape))


def render_all_panels(image_bgr, *, detections=None, marker=None,
                      wells=None, method="", mm_per_px=1.0, lang="tr"):
    """Multi-well 7-panel render.

    Args:
        detections: list[PetriDetection] — YOLO sonuclari (siralı)
        wells: list[WellPrediction] — pipeline tahminleri (siralı, detections ile ayni)
    """
    detections = detections or []
    wells = wells or []
    p01 = panel_01_input(image_bgr, lang)
    p02 = panel_02_yolo(image_bgr, detections, wells, method, mm_per_px, lang)
    p03 = panel_03_masks(image_bgr, detections, wells, lang)
    p04 = panel_04_classify(image_bgr, wells, lang)
    p05 = panel_05_coords(image_bgr, wells, lang)
    p06 = panel_06_predictions(image_bgr, wells, lang)
    p07 = panel_07_combined([p01, p02, p03, p04, p05, p06], lang)
    return {
        "01_input":         p01,
        "02_yolo_dets":     p02,
        "03_yolo_masks":    p03,
        "04_classify":      p04,
        "05_local_coords":  p05,
        "06_predictions":   p06,
        "07_combined":      p07,
    }


def save_all_panels(panels, out_dir, *, fmt="jpg", quality=90):
    out_dir.mkdir(parents=True, exist_ok=True)
    params = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)] \
        if fmt.lower() in ("jpg", "jpeg") else []
    paths = []
    for name, img in panels.items():
        p = out_dir / f"{name}.{fmt}"
        cv2.imwrite(str(p), img, params)
        paths.append(p)
    return paths
