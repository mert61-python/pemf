# -*- coding: utf-8 -*-
"""AII-3.6 — hücre CAM'i İSTİSNA yolunda da (explain içinde hata) cache'li CPN'in requires_grad bayraklarını ve .grad artıklarını geri alır.

`hucre_cam_haritasi` bayrakları try/finally ile geri alıyor (DÜŞMAN-DOĞRULAMA dersi: geri alınmazsa sonraki HER normal analiz
grad-etkin koşar, .grad tensörleri ~355 MB kalır). AI-1 kapısı `test_KRITIK_BOS_harita_basarili_DONMEZ_ve_bayraklar_geri_alinir`
"hata yolunda da" diyor ama hatası try bloğu BİTTİKTEN sonra (boş harita denetimi) atılıyor → ÖLÇÜLDÜ (A3): geri yüklemeyi yalnız başarı
yoluna taşıyan mutant (X5_MD) ve `.grad = None`'ı silen mutant (X5_MB) AI-1 kapısında 6/6 YEŞİL. Bu kapı explain İÇİNDE hata (ör. CUDA OOM)
ve backward artığı bırakan explain ile ölçer. Ağırlıksız.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest


def _sahte(torch):
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
    return cek, sahte


@pytest.fixture()
def ortam():
    torch = pytest.importorskip("torch")
    pytest.importorskip("pytorch_grad_cam")
    pytest.importorskip("celldetection")
    import ai_hub.xai_utils.grad_cam as gcm
    from ai_hub.inference_paper_dilek_hoca import inference_paper_dilek_hoca as m

    return torch, gcm, m


def test_KRITIK_explain_ICINDE_hata_bayraklar_ve_grad_geri_alinir(ortam, monkeypatch):
    torch, gcm, m = ortam
    cek, sahte = _sahte(torch)

    def _oom(self, *a, **k):
        for p in cek.parameters():
            p.grad = torch.ones_like(p)  # backward yarıda kaldı: artık var
        raise RuntimeError("CUDA out of memory (benzetim)")

    monkeypatch.setattr(gcm.GradCAMExplainer, "explain", _oom)
    with pytest.raises(RuntimeError, match="out of memory"):
        m.hucre_cam_haritasi(sahte, "x.png")
    assert not any(p.requires_grad for p in cek.parameters()), (
        "explain içinde hata: requires_grad bayrakları geri alınmadı"
    )
    assert all(p.grad is None for p in cek.parameters()), "explain içinde hata: .grad artığı cache'li modelde kaldı"


def test_KRITIK_basarili_yolda_grad_artigi_birakilmaz(ortam, monkeypatch):
    torch, gcm, m = ortam
    cek, sahte = _sahte(torch)

    def _dolu(self, *a, **k):
        for p in cek.parameters():
            p.grad = torch.ones_like(p)
        h = np.zeros((64, 64), np.float32)
        h[20:40, 20:40] = 1.0
        return h

    monkeypatch.setattr(gcm.GradCAMExplainer, "explain", _dolu)
    h = m.hucre_cam_haritasi(sahte, "x.png")
    assert float(h.max()) > 0
    assert not any(p.requires_grad for p in cek.parameters())
    assert all(p.grad is None for p in cek.parameters()), "başarılı yolda .grad artığı cache'li modelde kaldı"
