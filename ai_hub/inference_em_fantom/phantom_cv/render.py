# Author: mertaygn, cglrgrkn
"""render.py — Fantom + Tumor 7-panel TR+EN overlay (adaptif font).

Adaptif olcekleme:
    - Font scale, thickness, daire yariciap, kenarlik kalinligi
      goruntu kisa kenarina gore otomatik ayarlanir
    - Kucuk goruntu (300px) icin font 0.4
    - Buyuk goruntu (1600px) icin font 1.0

7 panel (yanik kaldirildi):
    01_input.jpg           — orijinal giris
    02_phantom_detect.jpg  — silikon bobrek fantom konturu
    03_phantom_mask.jpg    — fantom maske + bbox + centroid
    04_tumors.jpg          — mavi tumor noktalari
    05_local_coords.jpg    — her tumor icin lokal (X, Y) mm
    06_predictions.jpg     — PhantomPredictor D[7]/E sonuclari
    07_combined.jpg        — 6 panel 3x2 grid
"""
from __future__ import annotations
from pathlib import Path

import cv2
import numpy as np


COLOR_TUMOR    = (0, 0, 255)
COLOR_HEALTHY  = (60, 200, 60)
COLOR_PHANTOM  = (255, 200, 0)
COLOR_ORIGIN   = (255, 255, 0)
COLOR_AXIS_X   = (0, 0, 255)
COLOR_AXIS_Y   = (0, 255, 0)
COLOR_TEXT     = (255, 255, 255)
COLOR_BG       = (40, 40, 40)


LANG = {
    "tr": {
        "input":     "Giris",
        "phantom":   "Fantom Tespiti",
        "mask":      "Fantom Maskesi",
        "tumor":     "Tumor Odaklari",
        "coords":    "Koordinatlar (mm)",
        "predict":   "PEMF Tahminleri",
        "combined":  "Tam Ozet",
        "fantom_lbl":"Fantom A={a}px",
        "origin":    "Merkez",
        "no_phantom":"Fantom bulunamadi",
        "method":    "Yontem: {m}",
        "mm_per_px": "Olcek: {s:.3f} mm/px",
        "n_tumor":   "Tumor: {n}",
        "E_cancer":  "E_kanser",
        "duty":      "D[7]",
    },
    "en": {
        "input":     "Input",
        "phantom":   "Phantom Detection",
        "mask":      "Phantom Mask",
        "tumor":     "Tumor Foci",
        "coords":    "Coordinates (mm)",
        "predict":   "PEMF Predictions",
        "combined":  "Full Summary",
        "fantom_lbl":"Phantom A={a}px",
        "origin":    "Center",
        "no_phantom":"Phantom not found",
        "method":    "Method: {m}",
        "mm_per_px": "Scale: {s:.3f} mm/px",
        "n_tumor":   "Tumor: {n}",
        "E_cancer":  "E_cancer",
        "duty":      "D[7]",
    },
}


class Style:
    """Goruntu boyutuna gore adaptif stil parametreleri."""

    def __init__(self, image_shape: tuple[int, int]):
        h, w = image_shape[:2]
        short = min(h, w)
        # 300px -> scale ~0.35 / 1600px -> scale ~1.0
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


def panel_01_input(img, lang="tr"):
    style = Style(img.shape)
    return _header(img.copy(), f"01 - {LANG[lang]['input']}", style)


def panel_02_phantom(img, phantoms, method, mm_per_px, lang="tr"):
    L = LANG[lang]
    style = Style(img.shape)
    out = img.copy()
    if not phantoms:
        _put_text(out, L["no_phantom"],
                  (style.text_pad, out.shape[0] // 2), style,
                  color=(0, 0, 255), scale=style.font_large,
                  thickness=style.thick_med)
        return _header(out, f"02 - {L['phantom']}", style)

    for i, ph in enumerate(phantoms):
        cv2.drawContours(out, [ph.contour_px], -1, COLOR_PHANTOM,
                         style.thick_thick)
        cx, cy = int(ph.centroid_px[0]), int(ph.centroid_px[1])
        cv2.circle(out, (cx, cy), style.dot_med, COLOR_ORIGIN, -1)
        cv2.circle(out, (cx, cy), style.ring_med, COLOR_ORIGIN,
                   style.thick_thin)
        prefix = f"F{i+1} " if len(phantoms) > 1 else ""
        _put_text(out, prefix + L["fantom_lbl"].format(a=ph.area_px),
                  (cx + style.dot_med + 5, cy - 5), style,
                  color=COLOR_PHANTOM)
    H = out.shape[0]
    _put_text(out, L["method"].format(m=method),
              (style.text_pad, H - 2 * (style.header_h // 2)), style)
    _put_text(out, L["mm_per_px"].format(s=mm_per_px),
              (style.text_pad, H - style.header_h // 2), style)
    return _header(out, f"02 - {L['phantom']}", style)


def panel_03_mask(img, phantoms, lang="tr"):
    L = LANG[lang]
    style = Style(img.shape)
    out = img.copy()
    if phantoms:
        overlay = np.zeros_like(out)
        for ph in phantoms:
            overlay[ph.mask > 0] = COLOR_HEALTHY
        out = cv2.addWeighted(out, 0.55, overlay, 0.45, 0)
        for ph in phantoms:
            cv2.drawContours(out, [ph.contour_px], -1, COLOR_HEALTHY,
                             style.thick_med)
            bx, by, bw, bh = ph.bbox_px
            cv2.rectangle(out, (bx, by), (bx + bw, by + bh),
                          COLOR_HEALTHY, style.thick_med)
    return _header(out, f"03 - {L['mask']}", style)


def panel_04_tumors(img, regions, lang="tr"):
    """Mavi tumor noktalari (yanik kaldirildi)."""
    L = LANG[lang]
    style = Style(img.shape)
    out = img.copy()
    for r in regions.get("tumor", []):
        cv2.drawContours(out, [r.contour_px], -1, COLOR_TUMOR,
                         style.thick_med)
        cx, cy = int(r.centroid_px[0]), int(r.centroid_px[1])
        cv2.circle(out, (cx, cy), style.dot_med, COLOR_TUMOR, -1)
        cv2.circle(out, (cx, cy), style.ring_large, COLOR_TUMOR,
                   style.thick_med)
        _put_text(out, f"T A={r.area_px}",
                  (cx + style.ring_large + 3, cy - 5), style,
                  color=COLOR_TUMOR, scale=style.font_small)
    _put_text(out, L["n_tumor"].format(n=len(regions.get("tumor", []))),
              (style.text_pad, out.shape[0] - style.header_h // 2), style,
              color=COLOR_TUMOR, scale=style.font_large,
              thickness=style.thick_med)
    return _header(out, f"04 - {L['tumor']}", style)


def panel_05_coords(img, phantoms, regions_pred, lang="tr"):
    L = LANG[lang]
    style = Style(img.shape)
    out = img.copy()
    # En buyuk fantom merkez = origin
    phantom = max(phantoms, key=lambda p: p.area_px) if phantoms else None
    if phantom is not None:
        cx, cy = int(phantom.centroid_px[0]), int(phantom.centroid_px[1])
        cv2.circle(out, (cx, cy), style.dot_med, COLOR_ORIGIN, -1)
        arrow_len = max(40, int(min(out.shape[:2]) * 0.12))
        cv2.arrowedLine(out, (cx, cy), (cx + arrow_len, cy), COLOR_AXIS_X,
                        style.thick_med, tipLength=0.2)
        cv2.arrowedLine(out, (cx, cy), (cx, cy - arrow_len), COLOR_AXIS_Y,
                        style.thick_med, tipLength=0.2)
        _put_text(out, "+X", (cx + arrow_len + 3, cy + 6), style,
                  color=COLOR_AXIS_X)
        _put_text(out, "+Y", (cx - 10, cy - arrow_len - 3), style,
                  color=COLOR_AXIS_Y)
    for rp in regions_pred:
        if rp.organ_id != 1:        # sadece tumor
            continue
        col = COLOR_TUMOR
        px = (int(rp.centroid_px[0]), int(rp.centroid_px[1]))
        cv2.circle(out, px, style.dot_med, col, -1)
        x, y, _ = rp.centroid_cabin_mm
        txt = f"({x:+.1f}, {y:+.1f}) mm"
        _put_text(out, txt, (px[0] + style.dot_med + 3, px[1]), style,
                  color=col, scale=style.font_small)
    return _header(out, f"05 - {L['coords']}", style)


def panel_06_predictions(img, regions_pred, lang="tr"):
    L = LANG[lang]
    style = Style(img.shape)
    h, w = img.shape[:2]
    overlay = np.zeros_like(img)
    cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
    out = cv2.addWeighted(img, 0.25, overlay, 0.75, 0)

    tumors = [r for r in regions_pred if r.organ_id == 1]
    if not tumors:
        _put_text(out, L["no_phantom"],
                  (w // 2 - int(w * 0.15), h // 2), style,
                  color=(0, 255, 255), scale=style.font_large,
                  thickness=style.thick_med)
        return _header(out, f"06 - {L['predict']}", style)

    # Her tumor icin alt-blok
    box_h = max(80, (h - 20) // max(len(tumors), 1))
    for i, r in enumerate(tumors[:5]):
        y0 = 10 + i * box_h
        x, y, z = r.centroid_cabin_mm
        head = f"T{i+1} ({x:+.1f},{y:+.1f})mm  {L['E_cancer']}={r.E_cancer:.4f}"
        _put_text(out, head,
                  (style.text_pad, y0 + int(box_h * 0.25)), style,
                  color=COLOR_TUMOR, scale=style.font_normal,
                  thickness=style.thick_med)
        # D[7] bar
        bar_y = y0 + int(box_h * 0.50)
        bar_w = (w - 2 * style.text_pad) // 7
        bar_h_max = int(box_h * 0.35)
        for k, dv in enumerate(r.D):
            bh = max(2, int(bar_h_max * dv))
            bx = style.text_pad + k * bar_w
            cv2.rectangle(out, (bx, bar_y + bar_h_max - bh),
                          (bx + bar_w - 3, bar_y + bar_h_max),
                          (200, 200, 0), -1)
            _put_text(out, f"D{k+1}", (bx, bar_y + bar_h_max + 13), style,
                      color=(180, 180, 180), scale=style.font_small,
                      bg=False)
    return _header(out, f"06 - {L['predict']}", style)


def panel_07_combined(panels, lang="tr"):
    L = LANG[lang]
    style = Style(panels[0].shape)
    if len(panels) < 6:
        return _header(panels[0], f"07 - {L['combined']}", style)
    # Hepsi ayni boyuta
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


def render_all_panels(image_bgr, *, phantoms=None, phantom=None,
                      marker=None, regions=None, regions_pred=None,
                      method="", mm_per_px=1.0, lang="tr"):
    # Geriye uyum: phantom (tekil) verilirse listeye cevir
    if phantoms is None:
        phantoms = [phantom] if phantom is not None else []
    regions = regions or {"tumor": [], "healthy": []}
    regions_pred = regions_pred or []
    p01 = panel_01_input(image_bgr, lang)
    p02 = panel_02_phantom(image_bgr, phantoms, method, mm_per_px, lang)
    p03 = panel_03_mask(image_bgr, phantoms, lang)
    p04 = panel_04_tumors(image_bgr, regions, lang)
    p05 = panel_05_coords(image_bgr, phantoms, regions_pred, lang)
    p06 = panel_06_predictions(image_bgr, regions_pred, lang)
    p07 = panel_07_combined([p01, p02, p03, p04, p05, p06], lang)
    return {
        "01_input":           p01,
        "02_phantom_detect":  p02,
        "03_phantom_mask":    p03,
        "04_tumors":          p04,
        "05_local_coords":    p05,
        "06_predictions":     p06,
        "07_combined":        p07,
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
