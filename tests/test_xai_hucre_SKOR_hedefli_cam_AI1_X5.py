# -*- coding: utf-8 -*-
"""AI1.X5 — hücre segmentasyonu (CPN) ısı haritası BOŞ değil, hücrelerde; kenara değen hücreler "en etkili hücre" değil
(hoca XAI v3: `inference_paper_dilek_hoca/xai_dilek_v2.py`, `xai_v3/image_xai.py::CellSegXAI`).

ÖLÇÜLEN DURUM (2026-10-11, gerçek CPN ResNeXt-101 UNet, 12a/12b = atadaki test_data; `DUZELTME-AI1.md` X5): `_xai_cpn_bellekte`
hedefi backbone son katmanı GAP'inin 0. kanalıydı → izin listesindeki Grad-CAM ve Grad-CAM++ TAMAMEN BOŞ harita (std 0, maks 0)
üretip "başarılı" dönüyordu; varsayılan EigenCAM boş değildi ama hücrelerde değildi (lift 0,99 / 1,15). Hedef = tespit edilen hücre
skorları toplamı @ `core.score_fuse` + HiRes-CAM: lift 2,73 / 1,40 (hocanınkiyle birebir). Sınırsız ilk-10 "en etkili hücre"nin
8/10 ve 10/10'u kenara değen hücre (ağ kenar dolgusu yapay etkisi) → sıralama dışı. Girdi: `tests/xai_veri/KAYNAK.md`.
"""

from __future__ import annotations

import ast
import base64
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
KESIT = KOK / "tests" / "xai_veri" / "yara_0H_kesit_640x600.png"
MODUL = KOK / "ai_hub" / "inference_paper_dilek_hoca" / "inference_paper_dilek_hoca.py"
_PT = "ai_hub/inference_paper_dilek_hoca/ginoro_CpnResNeXt101UNet-fbe875f1a3e5ce2c.pt"


def _kenar_bandi(shape, oran=0.02):
    H, W = shape
    mrg = int(oran * max(H, W))
    k = np.zeros((H, W), bool)
    k[:mrg] = k[-mrg:] = True
    k[:, :mrg] = k[:, -mrg:] = True
    return k, mrg


@pytest.fixture(scope="module")
def cpn():
    pytest.importorskip("torch")
    pytest.importorskip("pytorch_grad_cam")
    pytest.importorskip("celldetection")
    from golden.eser import atla, eser_var_mi

    if not eser_var_mi(_PT):
        atla(f"CPN ağırlığı yok ({_PT})")
    from ai_hub.inference_paper_dilek_hoca import inference_paper_dilek_hoca as m

    pred = m.CellSegmentationPredictor(device="cpu")
    res = pred.predict(str(KESIT), compute_closure=False)
    return m, pred, res["_labels"]


# ── 1) gerçek ağırlık ───────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("yontem", ["hirescam", "gradcam"])
def test_KRITIK_harita_BOS_DEGIL_ve_HUCRELERDE(cpn, yontem):
    m, pred, labels = cpn
    assert int(labels.max()) >= 20, f"senaryo ayrışmıyor: kesitte yalnız {int(labels.max())} hücre"
    h = m.hucre_cam_haritasi(pred, str(KESIT), method=yontem)
    assert h.shape == labels.shape
    assert float(h.max()) > 0.0 and float(h.std()) > 0.01, f"{yontem}: harita boş/düz (std {float(h.std()):.4f})"
    lift = float(h[labels > 0].mean()) / float(h.mean())
    assert lift >= 1.2, (
        f"{yontem}: hücre içi / genel ortalama {lift:.3f} — harita hücreleri açıklamıyor (eski EigenCAM 0,99)"
    )


def test_KRITIK_en_etkili_hucreler_KENARA_DEGMEZ_ve_varsayilan_HIRESCAM(cpn):
    m, pred, labels = cpn
    r = m._xai_cpn_bellekte(pred, str(KESIT), labels=labels)
    assert r["xai_method"] == "hirescam", f"varsayılan yöntem {r['xai_method']!r}"
    sira = r.get("xai_en_etkili_hucreler") or []
    assert 1 <= len(sira) <= 10, f"en etkili hücre listesi {len(sira)}"
    kenar, mrg = _kenar_bandi(labels.shape)
    degen = set(int(i) for i in np.unique(labels[kenar & (labels > 0)]))
    assert degen and r.get("xai_kenara_degen_hucre") == len(degen), "kenara değen hücre sayısı yanlış / senaryo yok"
    assert not [s for s in sira if s["hucre"] in degen], (
        f"kenara değen hücre sıralamada: {[s for s in sira if s['hucre'] in degen]}"
    )
    # KARŞIT: süzgeçsiz ilk-10'da kenar hücresi VAR (kenar dolgusu yapay etkisi gerçekten burada) — yoksa kapı vakum
    h = m.hucre_cam_haritasi(pred, str(KESIT))
    n = int(labels.max())
    ort = np.bincount(labels.ravel(), weights=h.ravel(), minlength=n + 1) / np.maximum(
        np.bincount(labels.ravel(), minlength=n + 1), 1
    )
    ilk10 = [int(i) for i in np.argsort(-ort[1:])[:10] + 1]
    assert set(ilk10) & degen, "süzgeçsiz ilk-10'da kenar hücresi yok — senaryo kenar etkisini sınamıyor"
    assert [s["sira"] for s in sira] == list(range(1, len(sira) + 1))
    assert all(sira[i]["katki"] >= sira[i + 1]["katki"] for i in range(len(sira) - 1)), "sıralama katkıya göre değil"
    import cv2

    ov = cv2.imdecode(np.frombuffer(base64.b64decode(r["xai_image_base64"]), np.uint8), cv2.IMREAD_COLOR)
    assert ov is not None and r.get("xai_side_by_side_base64")


# ── 2) ağırlıksız ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_hucre_katkilari_KENAR_hucresini_siralamaya_ALMAZ():
    from ai_hub.inference_paper_dilek_hoca.inference_paper_dilek_hoca import hucre_katkilari

    labels = np.zeros((100, 100), np.int32)
    labels[0:6, 40:50] = 1  # kenara değen, EN parlak
    labels[40:50, 40:50] = 2  # iç, parlak
    labels[70:80, 20:30] = 3  # iç, sönük
    h = np.zeros((100, 100), np.float32)
    h[labels == 1] = 1.0
    h[labels == 2] = 0.6
    h[labels == 3] = 0.2
    sira, degen = hucre_katkilari(h, labels)
    assert degen == 1 and [s["hucre"] for s in sira] == [2, 3], f"sıralama {sira}, kenara değen {degen}"
    assert sira[0]["kutu"] == [40, 40, 49, 49]
    assert len(hucre_katkilari(h, labels, ilk_n=1)[0]) == 1


def test_KRITIK_BOS_harita_basarili_DONMEZ_ve_bayraklar_geri_alinir(monkeypatch):
    """Eski hedefte Grad-CAM boş harita üretip 'başarılı' dönüyordu (ölçüldü). Boş harita → RuntimeError (scratch_analiz bunu
    'Açıklama üretilemedi'ye çevirir) ve cache'li modelin requires_grad bayrakları hata yolunda da geri alınır."""
    torch = pytest.importorskip("torch")
    pytest.importorskip("pytorch_grad_cam")
    pytest.importorskip("celldetection")
    import ai_hub.xai_utils.grad_cam as gcm
    from ai_hub.inference_paper_dilek_hoca import inference_paper_dilek_hoca as m

    class _Cekirdek(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.core = torch.nn.Module()
            self.core.score_fuse = torch.nn.Conv2d(3, 1, 1)

        def forward(self, x):
            return {"scores": [self.core.score_fuse(x).mean().reshape(1)]}

    cek = _Cekirdek()
    for p in cek.parameters():
        p.requires_grad_(False)
    sahte = SimpleNamespace(
        cpn=SimpleNamespace(model=SimpleNamespace(model=cek)),
        device="cpu",
        _read_image=lambda yol: np.full((64, 64, 3), 120, np.uint8),
    )
    monkeypatch.setattr(gcm.GradCAMExplainer, "explain", lambda self, *a, **k: np.zeros((64, 64), np.float32))
    with pytest.raises(RuntimeError, match="BOS"):
        m.hucre_cam_haritasi(sahte, "x.png")
    assert not any(p.requires_grad for p in cek.parameters()), "hata yolunda requires_grad bayrakları geri alınmadı"


def test_YAPISAL_scratch_analiz_ETIKETLERI_XAI_ye_gecirir():
    """Hücre sıralaması scratch_analiz'in CPN etiketlerine dayanır: çağrı `labels=` anahtarını taşımalı (AST — yorum değil)."""
    agac = ast.parse(MODUL.read_text(encoding="utf-8"))
    fn = next(d for d in agac.body if isinstance(d, ast.FunctionDef) and d.name == "scratch_analiz")
    cagrilar = [c for c in ast.walk(fn) if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "_xai_cpn_bellekte"]
    assert cagrilar, "scratch_analiz _xai_cpn_bellekte'yi çağırmıyor"
    assert all(any(k.arg == "labels" for k in c.keywords) for c in cagrilar), "etiketler XAI'ye geçmiyor"
