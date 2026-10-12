# -*- coding: utf-8 -*-
"""AII-3.4 — tespit hedefli CAM'in hedef eşiği CANLI tespit eşiğiyle aynı: ekranda gösterilen HER kutu açıklanır.

ÖLÇÜLEN (A3, 2026-10-12, gerçek yolov8s, CPU; `_inceleme/kayit/k2b_zayif_kutu.json`): retikülosit 000045 (= `tests/xai_veri/
retikulosit_04a.jpg`) ekranda 4 kutu, biri güven 0,491 (eritrosit). Ürün eşiği 0,25'te bu kutunun CAM lift'i 15,0; XAI eşiği 0,6'ya
kayarsa **0,0** — ekrandaki tespit açıklamadan düşer. AI-1 kapısı (`test_xai_yolo_TESPIT_hedefli_cam_AI1_X2_X3.py` + `test_xai_faz2_kuyruk.py`)
retikülosit `XAI_TESPIT_CONF = 0.6` ve BT `conf=0.6` mutantlarında 11/11 YEŞİL kaldı (kör). Kapı: (1) gerçek ağırlık — canlı ONNX'in
gösterdiği her kutuda CAM lift ≥ 2; (2) ağırlıksız sözleşme — XAI'nin YoloDetCAM'e verdiği eşik = canlı yolun eşiği (router / dedektör).
"""

from __future__ import annotations

import base64
import inspect
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]
RETIK = KOK / "tests" / "xai_veri" / "retikulosit_04a.jpg"


@pytest.fixture()
def yolo_agirliklari():
    pytest.importorskip("torch")
    pytest.importorskip("ultralytics")
    from golden.eser import atla, eser_var_mi

    pt, onnx = "ai_hub/feline_reticulocytes/yolov8s.pt", "ai_hub/feline_reticulocytes/yolov8s.onnx"
    if not eser_var_mi(pt, onnx):
        atla(f"retikülosit ağırlıkları yok ({pt}, {onnx})")
    from ai_hub.xai_utils.pt_yolu import pt_coz

    return pt_coz(onnx)


def test_KRITIK_retikulosit_EKRANDAKI_her_kutu_haritada_aciklanir(yolo_agirliklari):
    from ultralytics import YOLO

    from ai_hub.feline_reticulocytes import inference_feline_reticulocytes as ifr

    # canlı yolun parametreleriyle (router /api/ai/vision/reticulocytes: conf 0,25 · iou 0,7 · 640) ekrandaki kutular
    r = YOLO(yolo_agirliklari, task="detect").predict(
        source=str(RETIK), conf=0.25, iou=0.7, imgsz=640, device="cpu", verbose=False
    )[0]
    kutular = r.boxes.xyxy.cpu().numpy()
    guven = r.boxes.conf.cpu().numpy()
    assert len(kutular) >= 3 and float(guven.min()) < 0.6, f"senaryo: zayıf (0,25–0,6) kutu yok ({guven})"
    h = ifr.retikulosit_cam_haritasi(str(RETIK))
    H, W = h.shape
    for b, c in zip(kutular, guven):
        x1, y1, x2, y2 = [int(round(v)) for v in b]
        m = np.zeros((H, W), bool)
        m[max(0, y1) : min(H, y2), max(0, x1) : min(W, x2)] = True
        lift = float(h[m].sum() / h.sum()) / float(m.mean())
        assert lift >= 2.0, (
            f"ekrandaki kutu (güven {c:.3f}) haritada açıklanmıyor: lift {lift:.2f} (XAI eşiği canlı eşikten sapmış olabilir)"
        )


# ── 2) ağırlıksız sözleşme: XAI eşiği = canlı eşik ────────────────────────────────────────────────────────────────
class _Kaydedici:
    son: dict = {}

    def __init__(self, yolo, imgsz=640, conf=0.25, method="hirescam", device=None):
        _Kaydedici.son = {"conf": conf, "imgsz": imgsz}

    def explain(self, image, class_id=None):
        return np.zeros((4, 4), np.float32)


@pytest.fixture()
def sahte_cam(monkeypatch):
    import ultralytics

    import ai_hub.xai_utils.yolo_cam as yc

    monkeypatch.setattr(yc, "YoloDetCAM", _Kaydedici)
    monkeypatch.setattr(ultralytics, "YOLO", lambda *a, **k: object())
    _Kaydedici.son = {}
    return _Kaydedici


def test_KRITIK_retikulosit_XAI_esigi_ROUTER_canli_esigiyle_ayni(sahte_cam, monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    from ai_hub.feline_reticulocytes import inference_feline_reticulocytes as ifr

    monkeypatch.setattr(ifr, "_XAI_PT_CACHE", {})
    ifr.retikulosit_cam_haritasi("yok.jpg", pt_path="yok.pt")
    xai_conf = sahte_cam.son["conf"]

    yakalanan: dict = {}

    class _R:
        boxes = None

    class _M:
        def predict(self, **kw):
            yakalanan.update(kw)
            return [_R()]

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: _M())
    # gerçek kan yayması baytları (görüntü alanı kapısı düz gri görüntüyü "gri tıbbi görüntü" diye 422 ile reddeder — ölçüldü)
    yanit = TestClient(apis.app).post(
        "/api/ai/vision/reticulocytes", data={"image_base64": base64.b64encode(RETIK.read_bytes()).decode()}
    )
    assert yanit.status_code == 200, yanit.text
    assert "conf" in yakalanan, f"canlı predict çağrılmadı: {yakalanan}"
    assert float(xai_conf) == float(yakalanan["conf"]), (
        f"XAI hedef eşiği {xai_conf} ≠ canlı tespit eşiği {yakalanan['conf']} — ekrandaki kutular haritada açıklanmayabilir"
    )


def test_KRITIK_bt_XAI_esigi_DEDEKTOR_canli_esigiyle_ayni(sahte_cam, monkeypatch):
    from ai_hub.inference_human_kidney_ct import KidneyCTDetector
    from ai_hub.inference_human_kidney_ct import inference_human_kidney_ct as ikt

    monkeypatch.setattr(ikt, "_XAI_PT_CACHE", {})
    ikt.ct_cam_haritasi("yok.jpg", pt_path="yok.pt")
    canli = inspect.signature(KidneyCTDetector.__init__).parameters["conf"].default  # router bu varsayılanla kurar
    assert float(sahte_cam.son["conf"]) == float(canli), (
        f"BT XAI hedef eşiği {sahte_cam.son['conf']} ≠ canlı dedektör eşiği {canli}"
    )
