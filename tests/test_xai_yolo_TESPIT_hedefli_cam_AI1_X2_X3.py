# -*- coding: utf-8 -*-
"""AI1.X2 / X3 — retikülosit ve böbrek BT ısı haritası TESPİT KUTULARINDA, dolguda / siyah zeminde DEĞİL
(hoca XAI v3: `xai_utils/yolo_cam_v2.py` → guii `ai_hub/xai_utils/yolo_cam.py::YoloDetCAM`).

ÖLÇÜLEN DURUM (2026-10-11, guii `97908b9b`, gerçek yolov8s.pt, CPU; `DUZELTME-AI1.md` X2/X3): `YoloEigenCAM`
  1) LetterBox(scaleup=False) — predict scaleup=True kullanır; 300×300 yayma 640'ın ortasında küçük kaldı,
  2) letterbox geri alınmadan 640×640 harita orijinale gerildi — retikülositte harita enerjisinin %100'ü dolgudaydı,
  3) EigenCAM etiket-bağımsız — CAM kütlesinin tespit kutularındaki payı retikülositte %0–5,8 (tesadüfi ~%3–5), BT'de
     %0,3–26,6; BT'de siyah zemin payı %36–86.
Düzeltme (tespit hedefli HiRes-CAM, P3/P4/P5, predict ile aynı ön işleme, dolgu kırpılır): kutu payı %87,6–99,2 (hocanınkiyle
birebir aynı harita, maks fark 0). Test girdileri: `tests/xai_veri/KAYNAK.md`.
"""

from __future__ import annotations

import base64
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
VERI = KOK / "tests" / "xai_veri"
RETIK = VERI / "retikulosit_04a.jpg"
BT = VERI / "bt_tas_07a.jpg"
_RETIK_PT = "ai_hub/feline_reticulocytes/yolov8s.pt"
_BT_PT = "ai_hub/inference_human_kidney_ct/yolov8s.pt"


@pytest.fixture(scope="module")
def yolo_agirliklari():
    pytest.importorskip("torch")
    pytest.importorskip("pytorch_grad_cam")
    pytest.importorskip("ultralytics")
    from golden.eser import atla, eser_var_mi

    if not eser_var_mi(_RETIK_PT, _BT_PT):
        atla(f"YOLO PT ağırlıkları yok ({_RETIK_PT}, {_BT_PT})")
    from ai_hub.xai_utils.pt_yolu import pt_coz

    return {"retic": pt_coz(_RETIK_PT), "ct": pt_coz(_BT_PT)}


def _kutu_maskesi(pt: str, yol: Path, boyut) -> np.ndarray:
    """Tespit kutuları — XAI'den BAĞIMSIZ bir YOLO örneğiyle, canlı uçla aynı eşiklerde (conf 0.25, iou 0.7, 640)."""
    from ultralytics import YOLO

    r = YOLO(pt).predict(source=str(yol), conf=0.25, iou=0.7, imgsz=640, device="cpu", verbose=False)[0]
    m = np.zeros(boyut, bool)
    for x1, y1, x2, y2 in r.boxes.xyxy.cpu().numpy() if r.boxes is not None else []:
        m[max(0, int(y1)) : int(np.ceil(y2)), max(0, int(x1)) : int(np.ceil(x2))] = True
    return m


def _pay(h: np.ndarray, maske: np.ndarray) -> float:
    return float(h[maske].sum()) / float(h.sum())


def _gri(yol: Path) -> np.ndarray:
    import cv2

    return cv2.cvtColor(cv2.imread(str(yol)), cv2.COLOR_BGR2GRAY)


# ── 1) gerçek ağırlık: CAM kütlesi tespit kutularında ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bicim", ["kare_300x300", "dikdortgen_300x200"])
def test_KRITIK_retikulosit_haritasi_TESPIT_KUTULARINDA_dolguda_degil(yolo_agirliklari, tmp_path, bicim):
    import cv2

    from ai_hub.feline_reticulocytes import inference_feline_reticulocytes as ifr

    yol = RETIK
    if bicim.startswith(
        "dikdortgen"
    ):  # letterbox dolgusu ancak kare OLMAYAN girdide oluşur (hata #2 yalnız burada görünür)
        yol = tmp_path / "retik_300x200.png"
        cv2.imwrite(str(yol), cv2.imread(str(RETIK))[40:240, :, :])
    gri = _gri(yol)
    h = ifr.retikulosit_cam_haritasi(str(yol))
    assert h.shape == gri.shape, f"harita orijinal görüntüye hizalı değil: {h.shape} != {gri.shape}"
    km = _kutu_maskesi(yolo_agirliklari["retic"], yol, gri.shape)
    assert km.any(), "senaryo ayrışmıyor: görüntüde tespit yok"
    kutu, alan = _pay(h, km), float(km.mean())
    assert kutu >= 0.6 and kutu >= 5 * alan, (
        f"CAM kütlesinin kutulardaki payı {kutu:.3f} (kutu alanı {alan:.3f}) — harita tespitleri açıklamıyor"
    )
    siyah = _pay(h, gri < 10)
    assert siyah <= 0.1, f"CAM kütlesinin siyah zemindeki payı {siyah:.3f} — harita görüntü dışında / dolguda"


def test_KRITIK_bt_haritasi_BOBREK_TESPITINDE_siyah_zeminde_degil(yolo_agirliklari):
    from ai_hub.inference_human_kidney_ct import inference_human_kidney_ct as ikt

    gri = _gri(BT)
    h = ikt.ct_cam_haritasi(str(BT))
    assert h.shape == gri.shape
    km = _kutu_maskesi(yolo_agirliklari["ct"], BT, gri.shape)
    assert km.any(), "senaryo ayrışmıyor: BT'de tespit yok"
    kutu, alan = _pay(h, km), float(km.mean())
    assert kutu >= 0.6 and kutu >= 5 * alan, f"BT CAM kutu payı {kutu:.3f} (alan {alan:.3f}) — böbrek tespitinde değil"
    siyah = _pay(h, gri < 10)
    assert siyah <= 0.4, (
        f"BT CAM kütlesinin siyah zemin (dolgu) payı {siyah:.3f} — hocanın bulgusu (omurga + siyah dolgu)"
    )


def test_KRITIK_urun_isi_haritasi_YONTEMI_ve_gorseli(yolo_agirliklari):
    import cv2

    from ai_hub.feline_reticulocytes import inference_feline_reticulocytes as ifr
    from ai_hub.inference_human_kidney_ct import inference_human_kidney_ct as ikt

    for fn, yol in ((ifr.xai_retikulosit_isi_haritasi, RETIK), (ikt.xai_ct_isi_haritasi, BT)):
        r = fn(str(yol))
        assert r.get("method") == "hirescam", f"{fn.__name__}: yöntem etiketi {r.get('method')!r}"
        ov = cv2.imdecode(np.frombuffer(base64.b64decode(r["xai_image_base64"]), np.uint8), cv2.IMREAD_COLOR)
        assert ov is not None and ov.shape[:2] == _gri(yol).shape
        assert float(np.abs(ov.astype(int) - cv2.imread(str(yol)).astype(int)).mean()) > 2.0, (
            "overlay orijinalle aynı (CAM yok)"
        )


# ── 2) ağırlıksız: letterbox geometrisi ve hedef anlamı ─────────────────────────────────────────────────────────────
def test_KRITIK_letterbox_PREDICT_ile_ayni_ve_GERI_ALINIR():
    """Hatalar #1 ve #2: harita predict'in gördüğü girdiyle (scaleup=True) hesaplanmalı ve dolgu KIRPILARAK orijinale
    dönmeli. Kare olmayan sentetik görüntüde beyaz dikdörtgen, ön işleme → geri alma sonrası AYNI yerde çıkmalı."""
    pytest.importorskip("torch")
    pytest.importorskip("ultralytics")
    from ai_hub.xai_utils.yolo_cam import YoloDetCAM

    cam = object.__new__(YoloDetCAM)  # model yüklemeden yalnız geometri
    cam.imgsz = 640
    import torch

    cam.device = torch.device("cpu")
    img = np.zeros((200, 300, 3), np.uint8)
    img[50:80, 100:150] = 255
    x, geo = cam._preprocess(img)
    assert tuple(x.shape) == (1, 3, 640, 640)
    top, left, nh, nw, H0, W0 = geo
    assert (nw, nh, H0, W0) == (640, 427, 200, 300), f"predict ölçeği (scaleup=True, r=640/300) değil: {geo}"
    m640 = x[0, 0].numpy()
    assert float(m640[:top].max(initial=0)) < 0.6, "dolgu bölgesinde içerik var (letterbox geometrisi kaydı)"
    geri = YoloDetCAM._unletterbox(m640, geo)
    assert geri.shape == (200, 300)
    ys, xs = np.where(geri > 0.5)
    assert (
        abs(ys.min() - 50) <= 2 and abs(ys.max() - 79) <= 2 and abs(xs.min() - 100) <= 2 and abs(xs.max() - 149) <= 2
    ), f"geri alınan harita kaydı: y {ys.min()}..{ys.max()} x {xs.min()}..{xs.max()} (beklenen y 50..79 x 100..149)"


def test_KRITIK_tespit_skoru_hedefi_ESIK_sinif_ve_BOS_harita_yok():
    torch = pytest.importorskip("torch")
    from ai_hub.xai_utils.yolo_cam import TespitSkoruHedefi

    out = torch.full((4 + 3, 6), 0.01)
    out[4 + 1, 0] = 0.9  # ankraj 0: sınıf 1 güçlü
    out[4 + 2, 1] = 0.3  # ankraj 1: sınıf 2 eşiğin üstünde
    out[4 + 0, 2] = 0.2  # ankraj 2: eşiğin ALTINDA — hedefe girmez
    assert float(TespitSkoruHedefi(0.25)(out)) == pytest.approx(1.2), "eşiği geçen tespitlerin skor toplamı değil"
    assert float(TespitSkoruHedefi(0.25, class_id=2)(out)) == pytest.approx(0.3), "class_id süzgeci çalışmıyor"
    zayif = torch.full((4 + 3, 6), 0.1)
    assert float(TespitSkoruHedefi(0.25)(zayif)) > 0.0, "tespit yokken hedef SIFIR → harita boş ama 'başarılı' döner"
