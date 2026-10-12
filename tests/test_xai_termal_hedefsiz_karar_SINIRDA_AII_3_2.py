# -*- coding: utf-8 -*-
"""AII-3.2 — hedefsiz termal XAI çağrısının kararı karar SINIRINA yakın görüntüde de ONNX tahminiyle AYNI.

`termal_cam_haritasi(hedef_sinif=None)` kararı PT lojitinden verir ("lojit >= 0 <=> predict eşiği 0,5"). Bu yolu
`scripts/xai_batch_rapor.py --modul termal` kullanır (kart: "açıklanan karar: …"). AI-1 kapısı hedefsiz yolu yalnız
lojiti sınırdan UZAK 03a'da ölçüyor → eşik `>= 0.0` → `>= 0.5` mutantı (A3 K1_MA) 8/8 YEŞİL kaldı (kör kapı).
Bu kapı 03a ↔ 03b karışımından sınıra yakın iki görüntü kurar (ONNX olasılığı 0,5–0,61 ve 0,39–0,5) ve hedefsiz
kararın ürünün ONNX `predict` kararıyla aynı olduğunu ölçer. (ONNX↔PT lojit farkı ölçüldü: maks 1,2e-4 / 186 görüntü.)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
SAGLIKLI = KOK / "tests" / "xai_veri" / "termal_saglikli_03a_224.png"
HASTA = KOK / "tests" / "xai_veri" / "termal_hasta_03b_224.png"
_PT = "ai_hub/cat_thermal/GhostNetV2.pt"
_ONNX = "ai_hub/cat_thermal/GhostNetV2.onnx"


@pytest.fixture()
def gercek():
    pytest.importorskip("torch")
    pytest.importorskip("pytorch_grad_cam")
    from golden.eser import atla, eser_var_mi

    if not eser_var_mi(_PT, _ONNX):
        atla(f"termal ağırlıkları yok ({_PT}, {_ONNX})")
    from ai_hub.cat_thermal import inference_cat_thermal as ict

    return ict, ict.CatThermalPredictor(model_name="GhostNetV2")


#: Sınıra yakınlık penceresi (lojit). Orkestratör (AI inceleme) ölçtü: ±0,45'te karar eşiğinin AŞAĞI kayması (lojit −0,3 ≈ olasılık
#: 0,43) ve yukarı kayması (> 0,1 — ±0,15 penceresinde de) YEŞİL kalıyordu; ±0,06 her iki yönde ≥ 0,06 lojitlik (≈ 0,015 olasılık) kaymayı yakalar.
#: Alt sınır 0,02, ONNX↔PT lojit farkının (≤ 1,2e-4) çok üstünde.
PENCERE = 0.06


def _sinira_yakin(tahminci, tmp_path: Path) -> dict:
    """03a↔03b karışımında ONNX lojiti ∈ [0,02; PENCERE] (Sick) ve ∈ [−PENCERE; −0,02] (Healthy) olan birer görüntü."""
    from PIL import Image

    a = Image.open(SAGLIKLI).convert("RGB")
    b = Image.open(HASTA).convert("RGB")

    def lojit(t: float) -> tuple[float, Path]:
        p = tmp_path / f"k_{t:.6f}.png"
        Image.blend(a, b, float(t)).save(p)
        prob = tahminci.predict(str(p), threshold=0.5)["probability_sick"]
        prob = min(max(prob, 1e-6), 1 - 1e-6)
        return float(np.log(prob / (1 - prob))), p

    lo, hi = 0.0, 1.0
    l_lo, _ = lojit(lo)
    assert l_lo < 0 < lojit(hi)[0], "senaryo kurulamadı: uç görüntüler sınırın iki yanında değil"
    bulunan: dict = {}
    for _ in range(40):
        m = (lo + hi) / 2
        lm, pm = lojit(m)
        if 0.02 <= lm <= PENCERE:
            bulunan.setdefault("Sick", pm)
        if -PENCERE <= lm <= -0.02:
            bulunan.setdefault("Healthy", pm)
        if lm < 0:
            lo = m
        else:
            hi = m
        if len(bulunan) == 2:
            break
    # ikili arama tek tarafı bulamadıysa sınır çevresinde ince tarama
    for t in np.linspace(lo - 0.003, hi + 0.003, 121):
        if len(bulunan) == 2:
            break
        lt, pt_ = lojit(float(t))
        if 0.02 <= lt <= PENCERE:
            bulunan.setdefault("Sick", pt_)
        if -PENCERE <= lt <= -0.02:
            bulunan.setdefault("Healthy", pt_)
    assert len(bulunan) == 2, f"senaryo kurulamadı: sınıra yakın görüntü bulunamadı ({sorted(bulunan)})"
    return bulunan


def test_KRITIK_hedefsiz_karar_SINIRA_yakin_goruntude_ONNX_tahminiyle_ayni(gercek, tmp_path):
    ict, tahminci = gercek
    for beklenen, yol in _sinira_yakin(tahminci, tmp_path).items():
        onnx = tahminci.predict(str(yol), threshold=0.5)
        assert onnx["label"] == beklenen, f"senaryo: {onnx}"
        _, _, aciklanan = ict.termal_cam_haritasi(str(yol))
        assert aciklanan == onnx["label"], (
            f"hedefsiz XAI '{aciklanan}' kararını açıklıyor, ürünün tahmini '{onnx['label']}' "
            f"(olasılık {onnx['probability_sick']}) — toplu CLI kartı yanlış kararı yazar"
        )
        r = ict.xai_termal_isi_haritasi(str(yol))
        assert r.get("hedef") == onnx["label"], f"yanıt hedefi {r.get('hedef')!r} ≠ tahmin {onnx['label']!r}"
