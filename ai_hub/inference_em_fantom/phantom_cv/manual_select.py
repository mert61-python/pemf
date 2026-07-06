"""manual_select.py — OpenCV window'da kullanici tikla -> fantom seed.

Kullanim:
    from phantom_cv.manual_select import select_seed_interactive
    seed_xy = select_seed_interactive(image_bgr, window_title="Fantom merkezi tikla")
    # -> (x, y) veya None (ESC)
"""
from __future__ import annotations
import cv2
import numpy as np


def _resize_for_display(image_bgr: np.ndarray,
                        max_dim: int = 1000) -> tuple[np.ndarray, float]:
    """Goruntu cok buyukse display icin kucult. Scale donder (orijinale geri)."""
    h, w = image_bgr.shape[:2]
    short = max(h, w)
    if short <= max_dim:
        return image_bgr.copy(), 1.0
    scale = max_dim / short
    new_w, new_h = int(w * scale), int(h * scale)
    return cv2.resize(image_bgr, (new_w, new_h)), scale


def select_seed_interactive(
    image_bgr: np.ndarray,
    *,
    window_title: str = "Fantom merkezi tikla (ESC=iptal, ENTER=onayla)",
    instruction: str = "Sentetik bobrek fantom MERKEZINI tikla, ENTER ile onayla",
) -> tuple[int, int] | None:
    """OpenCV window ac, kullanicinin tiklamasini bekle.

    Args:
        image_bgr: BGR goruntu
        window_title: Pencere basligi
        instruction: Goruntu uzerine yazilan talimat

    Returns:
        (x, y) orijinal koordinat veya None (ESC).
    """
    disp, scale = _resize_for_display(image_bgr, max_dim=1000)

    state = {"click": None, "preview": None}

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            state["click"] = (x, y)
            state["preview"] = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and state["click"]:
            state["preview"] = (x, y)

    cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_title, on_mouse)

    while True:
        show = disp.copy()
        # Talimat ust banner
        cv2.rectangle(show, (0, 0), (show.shape[1], 36), (0, 0, 0), -1)
        cv2.putText(show, instruction, (10, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1,
                    cv2.LINE_AA)
        # Mevcut click
        if state["click"]:
            cx, cy = state["click"]
            cv2.circle(show, (cx, cy), 10, (0, 255, 255), 2)
            cv2.circle(show, (cx, cy), 3, (0, 255, 255), -1)
            cv2.line(show, (cx - 15, cy), (cx + 15, cy), (0, 255, 255), 1)
            cv2.line(show, (cx, cy - 15), (cx, cy + 15), (0, 255, 255), 1)
            cv2.putText(show, f"({cx}, {cy})  ENTER=onayla, R=reset",
                        (cx + 12, cy - 12), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (0, 255, 255), 1, cv2.LINE_AA)

        cv2.imshow(window_title, show)
        key = cv2.waitKey(30) & 0xFF
        if key == 27:           # ESC
            cv2.destroyWindow(window_title)
            return None
        elif key in (13, 10):   # ENTER
            if state["click"]:
                cv2.destroyWindow(window_title)
                cx, cy = state["click"]
                return (int(cx / scale), int(cy / scale))
        elif key in (ord("r"), ord("R")):
            state["click"] = None
            state["preview"] = None


def headless_check() -> bool:
    """Headless ortam mi? (DISPLAY yok, cv2.imshow calismaz)"""
    import os
    return not (os.environ.get("DISPLAY") or
                os.environ.get("WAYLAND_DISPLAY"))
