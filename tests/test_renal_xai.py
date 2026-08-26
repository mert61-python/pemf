# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""RENAL HİSTOPATOLOJİ HiRes-CAM — Faz 4 (xai-entegrasyon-plani.md §7; sahip seçimi 'a').

ÖLÇÜLEN DURUM: histopat ucu top-k grade döner ama 3-backbone ensemble'ın (VGG19+WRN50+
DenseNet201) kesitin NERESİNE dayandığı görünmez. XAI = backbone başına HiRes-CAM +
ensemble ORTALAMA + **std DISAGREEMENT haritası** (üç modelin AYRIŞTIĞI bölgeler — klinik
"model kararsızlığı" göstergesi; tek skalar güvenin gösteremediği şey).

DÜZELTME: xai_histopat_isi_haritasi — PT ikizi (858MB, research.zip'e girer; download_model_sync
YEREL çözer) ayrı instance + tek-iş kilidi + bellek-içi base64 (mean overlay + disagreement);
Audit P3 (sys.exit→RuntimeError) korunur. Router /vision/histopath explain=true + ai_service
paritesi; XAI hatası analizi düşürmez.

CI: torch yok + PT gitignore'lu → gerçek-model testi açık-reason skipif; kablolama mock'la.
⚠️ Gerçek-model testi CPU'da 3-backbone backward — DAKİKA mertebesi sürebilir (tek koşum).
"""

from __future__ import annotations

import base64
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]
_PT = KOK / "release_assets/ai_models/ai_hub/inference_renal_histopath_kmc/v22_kmc_classictrio_kmc.pt"


def _torch_var() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


gercek_pt_gerekir = pytest.mark.skipif(
    not (_torch_var() and _PT.exists()),
    reason="torch/858MB renal PT yok (CI) — gerçek HiRes-CAM testi modelli ortamda",
)


def _b64_gorsel(b64: str) -> np.ndarray:
    import cv2

    img = cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8), cv2.IMREAD_COLOR)
    assert img is not None
    return img


def _hne_benzeri_goruntu(tmp_path: Path) -> str:
    """H&E-benzeri pembe-mor doku dokusu (modalite kapısından geçebilen sınıfta)."""
    import cv2

    rng = np.random.default_rng(21)
    img = np.zeros((224, 224, 3), dtype=np.uint8)
    img[..., 2] = (rng.random((224, 224)) * 90 + 150).astype(np.uint8)  # R yüksek
    img[..., 0] = (rng.random((224, 224)) * 90 + 120).astype(np.uint8)  # B orta (mor ton)
    img[..., 1] = (rng.random((224, 224)) * 70 + 60).astype(np.uint8)  # G düşük
    p = tmp_path / "kesit.jpg"
    cv2.imwrite(str(p), img)
    return str(p)


# ── 1) Gerçek PT ile ─────────────────────────────────────────────────────────
@gercek_pt_gerekir
def test_KRITIK_renal_hirescam_ENSEMBLE_ve_DISAGREEMENT_uretir(tmp_path):
    from ai_hub.inference_renal_histopath_kmc.inference_renal_histopath_kmc import xai_histopat_isi_haritasi

    p = _hne_benzeri_goruntu(tmp_path)
    r1 = xai_histopat_isi_haritasi(p)
    assert set(r1) >= {"xai_image_base64", "xai_disagreement_base64", "method"}, f"eksik: {set(r1)}"
    ov = _b64_gorsel(r1["xai_image_base64"])
    dis = _b64_gorsel(r1["xai_disagreement_base64"])
    assert float(ov.std()) > 1.0, "ensemble-mean overlay tekdüze"
    assert float(dis.std()) > 1.0, "disagreement overlay tekdüze — 3 backbone hiç ayrışmıyor olamaz"
    r2 = xai_histopat_isi_haritasi(p)
    assert r1["xai_image_base64"] == r2["xai_image_base64"], "HiRes-CAM deterministik değil"


def test_YAPISAL_renal_kilit_ve_P3():
    src = (KOK / "ai_hub/inference_renal_histopath_kmc/inference_renal_histopath_kmc.py").read_text(encoding="utf-8")
    i = src.index("def xai_histopat_isi_haritasi")
    govde = src[i : i + 3600]
    kilit = govde.find("_XAI_KILIT")
    explain = govde.find(".explain(")
    assert kilit >= 0 and explain >= 0 and kilit < explain, "HiRes-CAM tek-iş kilitsiz (858MB model + hook yarışı)"
    # Audit P3: XAI/kütüphane yolunda sys.exit OLMAMALI (CLI main()'deki meşru kullanım hariç)
    assert "sys.exit(" not in govde, "XAI gövdesinde sys.exit (Audit P3 regresyonu)"


# ── 2) Uç kablolaması (mock — her ortamda) ───────────────────────────────────
_SENT = {
    "xai_image_base64": base64.b64encode(b"m").decode(),
    "xai_disagreement_base64": base64.b64encode(b"d").decode(),
    "method": "hirescam-ensemble",
}


@pytest.fixture()
def istemci(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)

    class _Clf:
        classes = ["Grade 0", "Grade 1", "Grade 2", "Grade 3", "Grade 4"]

        def predict(self, image_path, top_k=3):
            return {
                "top_1_class": "Grade 2",
                "top_1_prob": 0.8,
                "top_k": [{"class": "Grade 2", "prob": 0.8}],
                "probabilities": {"Grade 2": 0.8},
            }

    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: _Clf())
    return TestClient(apis.app), air


def test_KRITIK_histopat_endpoint_explain_kablolamasi(istemci, monkeypatch, tmp_path):
    client, air = istemci
    import ai_hub.inference_renal_histopath_kmc.inference_renal_histopath_kmc as irh

    cagri = []
    monkeypatch.setattr(irh, "xai_histopat_isi_haritasi", lambda *a, **k: cagri.append(1) or _SENT)

    p = _hne_benzeri_goruntu(tmp_path)
    b64 = base64.b64encode(Path(p).read_bytes()).decode()
    r = client.post("/api/ai/vision/histopath", data={"image_base64": b64, "explain": "true"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("xai_image_base64") == _SENT["xai_image_base64"] and cagri
    assert body.get("xai_disagreement_base64") == _SENT["xai_disagreement_base64"], (
        "disagreement haritası yanıtta yok — 'model kararsızlığı' göstergesi kayboldu"
    )

    r2 = client.post("/api/ai/vision/histopath", data={"image_base64": b64})
    assert r2.status_code == 200 and "xai_image_base64" not in r2.json() and "xai_error" not in r2.json()


def test_KRITIK_histopat_xai_hatasi_analizi_DUSURMEZ(istemci, monkeypatch, tmp_path):
    client, air = istemci
    import ai_hub.inference_renal_histopath_kmc.inference_renal_histopath_kmc as irh

    def _patla(*a, **k):
        raise RuntimeError("hirescam patladı (test)")

    monkeypatch.setattr(irh, "xai_histopat_isi_haritasi", _patla)
    p = _hne_benzeri_goruntu(tmp_path)
    b64 = base64.b64encode(Path(p).read_bytes()).decode()
    r = client.post("/api/ai/vision/histopath", data={"image_base64": b64, "explain": "true"})
    assert r.status_code == 200, f"XAI hatası analizi düşürdü: {r.text}"
    body = r.json()
    assert body.get("xai_error") and "xai_image_base64" not in body


# ── 3) parite + paket ────────────────────────────────────────────────────────
def test_YAPISAL_ai_service_histopat_XAI_paritesi():
    src = (KOK / "ai_service" / "app.py").read_text(encoding="utf-8")
    i = src.index('post("/infer/histopath")')
    govde = src[i : i + 4500]
    assert "xai_histopat_isi_haritasi" in govde and "explain" in govde, ":8100 histopath XAI paritesi yok"


def test_YAPISAL_renal_pt_research_paketinde():
    """Karar #5: 858MB PT klinik makinelere research.zip ile iner (downloader YEREL çözer)."""
    src = (KOK / "build_tools" / "make_model_zip.py").read_text(encoding="utf-8")
    i = src.index('"research": (')
    govde = src[i : src.index('}', i)]
    assert "v22_kmc_classictrio_kmc.pt" in govde, "renal PT research profil listesinde değil — sahaya inemez"
