# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""FAZ 2 KUYRUĞU: FELINE/CT EigenCAM + RNA Integrated Gradients (plan §5/§7).

ÖLÇÜLEN DURUM: retikülosit/CT tespitleri annotated görsel döner ama modelin hangi hücre
kümelerine/bölgelere dayandığı ayrıca görünmez (EigenCAM label-agnostik, GRADIENT'SİZ —
YOLO'da Grad-CAM gürültülü, doc §10.1). RNA ucu KIRC/other olasılığı döner ama HANGİ
GENLERİN kararı sürüklediğini dönmez (Captum IG; CT-XAI Faz-0 karar #4 ile ONAYLI).

DÜZELTME: xai_retikulosit_isi_haritasi + xai_ct_isi_haritasi (PT-YOLO cache + tek-iş
kilidi + bellek-içi base64) ve RNA xai_top_genler (IG internal_batch_size'lı; hasta
başına signed top-N gen; ⚠️ N>25 hastada üretilmez — 60MB CSV'de IG maliyet patlaması).
Router explain=true kablolaması + ai_service paritesi; XAI hatası analizi düşürmez.

CI notu: torch yok + PT'ler gitignore'lu → gerçek-model testleri açık-reason skipif;
kablolama testleri mock'la her ortamda (yerleşik desen).
"""

from __future__ import annotations

import base64
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]

_FELINE_PT = KOK / "release_assets/ai_models/ai_hub/feline_reticulocytes/yolov8s.pt"
_CT_PT = KOK / "release_assets/ai_models/ai_hub/inference_human_kidney_ct/yolov8s.pt"
_RNA_PT = KOK / "ai_hub/inference_human_kidney_rna/mlp_medium_kirc.pt"


def _torch_var() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


yolo_pt_gerekir = pytest.mark.skipif(
    not (_torch_var() and _FELINE_PT.exists() and _CT_PT.exists()),
    reason="torch/YOLO-PT yok (CI) — gerçek EigenCAM testi modelli ortamda",
)
rna_pt_gerekir = pytest.mark.skipif(
    not (_torch_var() and _RNA_PT.exists()),
    reason="torch/mlp PT yok (CI) — gerçek IG testi modelli ortamda",
)


def _b64_gorsel(b64: str) -> np.ndarray:
    import cv2

    img = cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8), cv2.IMREAD_COLOR)
    assert img is not None, "xai_image_base64 geçerli görsel değil"
    return img


# ── 1) EigenCAM — gerçek PT'lerle ────────────────────────────────────────────
@yolo_pt_gerekir
def test_KRITIK_feline_eigencam_URETIR_ve_DETERMINISTIK(tmp_path):
    import cv2

    from ai_hub.feline_reticulocytes.inference_feline_reticulocytes import xai_retikulosit_isi_haritasi

    rng = np.random.default_rng(4)
    img = (rng.random((320, 320, 3)) * 255).astype(np.uint8)
    p = tmp_path / "kan.jpg"
    cv2.imwrite(str(p), img)
    r1 = xai_retikulosit_isi_haritasi(str(p))
    ov = _b64_gorsel(r1["xai_image_base64"])
    assert float(ov.std()) > 1.0 and r1.get("method") == "eigencam"
    r2 = xai_retikulosit_isi_haritasi(str(p))
    assert r1["xai_image_base64"] == r2["xai_image_base64"], "EigenCAM deterministik değil"


@yolo_pt_gerekir
def test_KRITIK_ct_eigencam_URETIR(tmp_path):
    import cv2

    from ai_hub.inference_human_kidney_ct.inference_human_kidney_ct import xai_ct_isi_haritasi

    rng = np.random.default_rng(6)
    img = (rng.random((320, 320, 3)) * 255).astype(np.uint8)
    p = tmp_path / "ct.jpg"
    cv2.imwrite(str(p), img)
    r = xai_ct_isi_haritasi(str(p))
    ov = _b64_gorsel(r["xai_image_base64"])
    assert float(ov.std()) > 1.0 and r.get("method") == "eigencam"


def test_YAPISAL_eigencam_tek_is_kilidi():
    for dosya, fn in [
        ("ai_hub/feline_reticulocytes/inference_feline_reticulocytes.py", "def xai_retikulosit_isi_haritasi"),
        ("ai_hub/inference_human_kidney_ct/inference_human_kidney_ct.py", "def xai_ct_isi_haritasi"),
    ]:
        src = (KOK / dosya).read_text(encoding="utf-8", errors="replace")
        i = src.index(fn)
        govde = src[i : i + 2400]
        kilit = govde.find("_XAI_KILIT")
        explain = govde.find(".explain(")
        assert kilit >= 0 and explain >= 0 and kilit < explain, f"{dosya}: EigenCAM kilitsiz/kilitten önce"


# ── 2) RNA IG — gerçek PT ile ────────────────────────────────────────────────
@rna_pt_gerekir
def test_KRITIK_rna_ig_top_genler_URETIR_ve_DETERMINISTIK():
    import pandas as pd

    from ai_hub.inference_human_kidney_rna.inference_human_kidney_rna import xai_top_genler

    # Sentetik 20531-gen tablosu (2 hasta) — GERÇEK scaler/fs_idx/PT zinciriyle akar.
    rng = np.random.default_rng(12)
    n_gen = 20531
    df = pd.DataFrame(
        rng.random((2, n_gen)).astype(np.float32) * 100.0,
        index=["hasta_A", "hasta_B"],
        columns=[f"gene_{i}" for i in range(n_gen)],
    )
    a = xai_top_genler(df, top_n=8)
    assert len(a) == 2
    for satir in a:
        tg = satir["top_genes"]
        assert len(tg) == 8 and all(t["gene"].startswith("gene_") for t in tg)
        assert sum(abs(t["attribution"]) for t in tg) > 1e-8, "IG katkıları ~0 — zincir kırık"
    b = xai_top_genler(df, top_n=8)
    assert a == b, "aynı CSV'ye farklı gen açıklaması (IG deterministik olmalı)"


# ── 3) Uç kablolamaları (mock — her ortamda) ─────────────────────────────────
_SENT_IMG = {"xai_image_base64": base64.b64encode(b"x").decode(), "method": "eigencam"}


@pytest.fixture()
def istemci(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    return TestClient(apis.app), air


def _jpg_b64() -> str:
    """RENKLİ test görüntüsü — modalite kapısı düz/gri kareyi haklı olarak reddediyor
    (kapı çalışıyor; test kapıdan GEÇEBİLEN kan-yayması-benzeri renkli doku üretir)."""
    import cv2

    rng = np.random.default_rng(3)
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    img[..., 2] = (rng.random((64, 64)) * 120 + 120).astype(np.uint8)  # kırmızı ağırlıklı (BGR)
    img[..., 1] = (rng.random((64, 64)) * 90 + 40).astype(np.uint8)
    img[..., 0] = (rng.random((64, 64)) * 60 + 30).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf.tobytes()).decode()


def test_KRITIK_feline_endpoint_explain_kablolamasi(istemci, monkeypatch):
    client, air = istemci
    import ai_hub.feline_reticulocytes.inference_feline_reticulocytes as ifr

    class _R:  # ultralytics result taklidi (endpoint'in okuduğu alanlar)
        boxes = None
        save_dir = ""

    class _M:
        def predict(self, **k):
            return [_R()]

    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: _M())
    cagri = []
    monkeypatch.setattr(ifr, "xai_retikulosit_isi_haritasi", lambda *a, **k: cagri.append(1) or _SENT_IMG)

    r = client.post("/api/ai/vision/reticulocytes", data={"image_base64": _jpg_b64(), "explain": "true"})
    assert r.status_code == 200, r.text
    assert r.json().get("xai_image_base64") == _SENT_IMG["xai_image_base64"] and cagri

    r2 = client.post("/api/ai/vision/reticulocytes", data={"image_base64": _jpg_b64()})
    assert r2.status_code == 200 and "xai_image_base64" not in r2.json()


def test_KRITIK_rna_endpoint_explain_kablolamasi_ve_N_SINIRI(istemci, monkeypatch):
    import io

    import pandas as pd

    client, air = istemci
    import ai_hub.inference_human_kidney_rna.inference_human_kidney_rna as ihr

    class _P:
        expected_cols = 5
        classes = ["other", "KIRC"]

        def predict(self, df):
            return [{"patient_id": str(i), "prediction": "KIRC", "confidence": 0.9} for i in df.index]

    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: _P())
    sentinel = [{"patient_id": "p0", "top_genes": [{"gene": "gene_1", "attribution": 0.5}]}]
    monkeypatch.setattr(ihr, "xai_top_genler", lambda df, **k: sentinel)

    def _csv(n_hasta):
        df = pd.DataFrame(np.ones((n_hasta, 5)), index=[f"p{i}" for i in range(n_hasta)], columns=list("abcde"))
        buf = io.BytesIO()
        df.to_csv(buf)
        return base64.b64encode(buf.getvalue()).decode()

    r = client.post("/api/ai/rna/kidney", data={"csv_base64": _csv(3), "explain": "true"})
    assert r.status_code == 200, r.text
    assert r.json().get("xai") == sentinel, "explain=true iken RNA yanıtı xai taşımıyor"

    # N sınırı: 26 hasta → IG maliyet patlaması engellenir, analiz YİNE döner.
    r2 = client.post("/api/ai/rna/kidney", data={"csv_base64": _csv(26), "explain": "true"})
    assert r2.status_code == 200
    b2 = r2.json()
    assert "xai" not in b2 and b2.get("xai_error"), "N>25 sınırı uygulanmadı (60MB CSV'de IG patlar)"

    r3 = client.post("/api/ai/rna/kidney", data={"csv_base64": _csv(3)})
    assert r3.status_code == 200 and "xai" not in r3.json() and "xai_error" not in r3.json()


def test_KRITIK_rna_xai_hatasi_analizi_DUSURMEZ(istemci, monkeypatch):
    import io

    import pandas as pd

    client, air = istemci
    import ai_hub.inference_human_kidney_rna.inference_human_kidney_rna as ihr

    class _P:
        expected_cols = 5
        classes = ["other", "KIRC"]

        def predict(self, df):
            return [{"patient_id": "p0", "prediction": "other", "confidence": 0.7}]

    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: _P())

    def _patla(*a, **k):
        raise RuntimeError("captum patladı (test)")

    monkeypatch.setattr(ihr, "xai_top_genler", _patla)
    df = pd.DataFrame(np.ones((1, 5)), index=["p0"], columns=list("abcde"))
    buf = io.BytesIO()
    df.to_csv(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    r = client.post("/api/ai/rna/kidney", data={"csv_base64": b64, "explain": "true"})
    assert r.status_code == 200, f"XAI hatası RNA analizini düşürdü: {r.text}"
    body = r.json()
    assert body.get("predictions") and body.get("xai_error") and "xai" not in body


# ── 3b) ai_service IN-PROCESS smoke (gerçek PT, CPU) ─────────────────────────
# Docker bu makinede yok → cu128 İMAJ smoke'u GPU makinesinde (scripts/ai_service_xai_smoke.ps1).
# Burada imaj-DIŞI ama GERÇEK handler+PT yolu doğrulanır: /infer/thermal explain=true uçtan uca.
@yolo_pt_gerekir
def test_KRITIK_ai_service_inprocess_thermal_explain_SMOKE(tmp_path):
    import cv2

    import ai_service.app as sapp

    sc = TestClient(sapp.app)
    yy, xx = np.mgrid[0:224, 0:224].astype(np.float32)
    sicak = np.exp(-(((yy - 112) ** 2 + (xx - 112) ** 2) / (2 * 40.0**2)))
    img = np.stack([(1 - sicak) * 180, sicak * 120, sicak * 255], axis=-1).astype(np.uint8)  # BGR sıcak-renkli
    ok, buf = cv2.imencode(".jpg", img)
    r = sc.post(
        "/infer/thermal",
        files={"file": ("t.jpg", buf.tobytes(), "image/jpeg")},
        data={"explain": "true"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "success"
    assert body.get("xai_image_base64"), f"servis explain yolu ısı haritası dönmedi: {list(body)}"
    _b64_gorsel(body["xai_image_base64"])


# ── 4) parite ────────────────────────────────────────────────────────────────
def test_YAPISAL_ai_service_kuyruk_XAI_paritesi():
    src = (KOK / "ai_service" / "app.py").read_text(encoding="utf-8")
    for uc, fn in [
        ('post("/infer/reticulocytes")', "xai_retikulosit_isi_haritasi"),
        ('post("/infer/kidney_ct")', "xai_ct_isi_haritasi"),
        ('post("/infer/rna")', "xai_top_genler"),
    ]:
        i = src.index(uc)
        govde = src[i : i + 4500]
        assert fn in govde and "explain" in govde, f":8100 {uc} XAI paritesi yok"
