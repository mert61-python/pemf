# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.63 · B-5.17 — tespit hedefli CAM ısı haritası ÜRÜNÜN `explain` yolunda letterbox dolgusu kırpılıp orijinale geri
ölçeklenir; harita orijinal görüntüde DOĞRU yere düşer (retikülosit + böbrek BT aynı `YoloDetCAM.explain`i kullanır).

🔴 ÖLÇÜLEN DURUM (HEAD ebf1c3fe, D67): ürün `ade28e5f` (AI1.X2-X3) ile `YoloDetCAM`e geçti — `explain` `_unletterbox` çağırıyor.
AMA kapı KÖR: `explain` içinde geri eşlemeyi kaldıran mutant (`h = cv2.resize(heat, (W0, H0))`, dolgu dahil germe) mevcut
kapıların HEPSİNDE yeşil kaldı — ağırlıksız 19 passed / 8 skipped, GERÇEK ağırlıklı (M67_MODELLER=1) 27 passed: geometri
testi `_preprocess` + `_unletterbox`u DOĞRUDAN çağırıyor (explain'i değil), gerçek ağırlıklı kutu payı testleri kare (300×300,
512×512 BT → dolgu yok) ya da gevşek eşikli. `explain` içinde haritayı ters çeviren mutant ağırlıksız kipte (CI) yeşil.
KAPI (planın yöntemi): bilinen konumda parlak "hücre" (beyaz disk) siyah tuvale yapıştırılır; CAM, letterbox'lı girdiyi
yansıtan bir sahteyle değiştirilir (harita = modele giden 640×640 tensörün R kanalı — dolgu 114/255 gri); ÜRÜNÜN `explain`i
(ön işleme + geri eşleme + normalizasyon) kullanılır. İddia: ısı ağırlık merkezi gerçek konumdan köşegenin %1'inden az uzak,
harita orijinal boyutta. Tuval: 1280×720 (üst/alt dolgu), 720×1280 (sol/sağ dolgu), 300×300 (640'tan küçük, scaleup).
Ağırlık / pytorch-grad-cam GEREKMEZ (torch + ultralytics LetterBox yeter).
"""

from __future__ import annotations

import capraz
import numpy as np
import pytest

#: (tuval genişliği, yüksekliği, disk merkezi x, y, yarıçap) — merkezler bilerek MERKEZ DIŞI (ters çevirme / kayma görünsün).
TUVALLER = {
    "yatay_1280x720": (1280, 720, 300, 500, 40),
    "dikey_720x1280": (720, 1280, 500, 300, 40),
    "kucuk_kare_300x300": (300, 300, 70, 210, 15),
}


class _SahteCAM:
    """pytorch-grad-cam yerine: harita = letterbox'lı girdi tensörünün R kanalı (modelin gördüğü 640×640 düzlem)."""

    class _Model:
        @staticmethod
        def parameters():
            return []

    model = _Model()

    def __call__(self, input_tensor, targets):
        return [input_tensor[0, 0].detach().cpu().numpy().astype(np.float32)]


def _aciklayici():
    capraz.paket_yoksa_atla("torch")
    capraz.paket_yoksa_atla("ultralytics")
    import torch

    from ai_hub.xai_utils.yolo_cam import YoloDetCAM

    cam = object.__new__(YoloDetCAM)  # model yüklemeden: ürünün explain / ön işleme / geri eşleme kodu
    cam.imgsz, cam.conf, cam.method = 640, 0.25, "hirescam"
    cam.device = torch.device("cpu")
    cam._cam = _SahteCAM()
    return cam


@pytest.mark.parametrize("ad", list(TUVALLER))
def test_KRITIK_explain_haritasi_ORIJINAL_konuma_esler(ad):
    import cv2

    W, H, cx, cy, r = TUVALLER[ad]
    tuval = np.zeros((H, W, 3), np.uint8)
    cv2.circle(tuval, (cx, cy), r, (255, 255, 255), -1)
    cam = _aciklayici()

    h = cam.explain(tuval)

    assert h.shape == (H, W), f"{ad}: harita orijinal boyutta değil: {h.shape} (beklenen {(H, W)})"
    assert float(h.max()) == pytest.approx(1.0, abs=1e-6), f"{ad}: harita [0,1]'e normalize değil (maks {h.max()})"
    ys, xs = np.mgrid[0:H, 0:W]
    kutle = float(h.sum())
    my, mx = float((h * ys).sum()) / kutle, float((h * xs).sum()) / kutle
    sapma = float(np.hypot(mx - cx, my - cy))
    kosegen = float(np.hypot(W, H))
    assert sapma < 0.01 * kosegen, (
        f"{ad}: ısı ağırlık merkezi ({mx:.1f}, {my:.1f}) gerçek konumdan ({cx}, {cy}) {sapma:.1f} px uzak "
        f"(sınır köşegenin %1'i = {0.01 * kosegen:.1f} px) — letterbox dolgusu kırpılmıyor / ölçek geri alınmıyor"
    )
    kenar = max(float(h[:3].max()), float(h[-3:].max()), float(h[:, :3].max()), float(h[:, -3:].max()))
    assert kenar < 0.1, (
        f"{ad}: siyah tuvalin kenar bandında ısı {kenar:.3f} (dolgu gri düzeyi 114/255 ≈ 0,45) — dolgu sızıyor"
    )
