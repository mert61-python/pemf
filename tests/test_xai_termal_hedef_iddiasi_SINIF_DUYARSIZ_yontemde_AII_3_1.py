# -*- coding: utf-8 -*-
"""AII-3.1 — termal XAI yanıtı yalnız haritanın GERÇEKTEN ayırabildiği kararı iddia eder.

ÖLÇÜLEN (A3, 2026-10-12, `bca9e544`, gerçek `GhostNetV2.pt`, CPU; `_inceleme/kayit/k1_termal_sonda.json`):
termal uçların izin listesi `gradcam++`, `gradcam`, `eigencam`, `hirescam` (router `/api/ai/vision/thermal`, ai_service
`/infer/thermal`, `scripts/xai_batch_rapor.py --xai-method`). `xai_termal_isi_haritasi` her yöntemde yanıta `hedef`
(Healthy / Sick) koyuyor; arayüz başlığı bunu "modeli “Sağlıklı” kararına götüren bölgeler", toplu CLI kartı
"açıklanan karar: Sağlıklı" diye yazıyor. Ama `eigencam` hedeften BAĞIMSIZ (Sick ve Healthy haritası bayt-aynı, 6/6
görüntü) ve `gradcam++` tek lojitte sınıf-duyarsız (rho 0,83–0,95) → bu yöntemlerde "Sağlıklı kararına götüren" iddiası
YANLIŞ AÇIKLAMA. Kapı: yanıt bir karar iddia ediyorsa, o kararın haritası karşıt kararınkinden AYRIŞMALI (rho < 0,5).
"""

from __future__ import annotations

from pathlib import Path

import capraz
import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
SAGLIKLI = KOK / "tests" / "xai_veri" / "termal_saglikli_03a_224.png"
HASTA = KOK / "tests" / "xai_veri" / "termal_hasta_03b_224.png"
_PT = "ai_hub/cat_thermal/GhostNetV2.pt"
_ONNX = "ai_hub/cat_thermal/GhostNetV2.onnx"
#: Termal uçların kabul ettiği yöntemler (router / ai_service / toplu CLI izin listesi — sözleşme, kaynaktan OKUNMAZ).
_UCUN_KABUL_ETTIGI = ("gradcam++", "gradcam", "eigencam", "hirescam")


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = np.argsort(np.argsort(a.ravel())).astype(np.float64)
    rb = np.argsort(np.argsort(b.ravel())).astype(np.float64)
    if ra.std() == 0 or rb.std() == 0:
        return 1.0
    return float(np.corrcoef(ra, rb)[0, 1])


@pytest.fixture()
def ict():
    capraz.paket_yoksa_atla("torch")
    capraz.paket_yoksa_atla("pytorch_grad_cam")
    from golden.eser import atla, eser_var_mi

    if not eser_var_mi(_PT, _ONNX):
        atla(f"termal ağırlıkları yok ({_PT}, {_ONNX})")
    from ai_hub.cat_thermal import inference_cat_thermal as m

    return m


@pytest.mark.parametrize("goruntu,karar", [(SAGLIKLI, "Healthy"), (HASTA, "Sick")])
@pytest.mark.parametrize("yontem", _UCUN_KABUL_ETTIGI)
def test_KRITIK_yanit_karar_iddia_ediyorsa_harita_o_karari_AYIRIR(ict, yontem, goruntu, karar):
    r = ict.xai_termal_isi_haritasi(str(goruntu), method=yontem, hedef_sinif=karar)
    assert r.get("xai_image_base64"), "harita üretilmedi"
    iddia = r.get("hedef")
    if iddia is None:
        return  # karar iddia edilmiyor → arayüz genel başlığı ("modelin baktığı bölgeler") gösterir: dürüst
    karsit = "Sick" if iddia == "Healthy" else "Healthy"
    _, h_iddia, _ = ict.termal_cam_haritasi(str(goruntu), hedef_sinif=iddia, method=yontem)
    _, h_karsit, _ = ict.termal_cam_haritasi(str(goruntu), hedef_sinif=karsit, method=yontem)
    rho = _spearman(h_iddia, h_karsit)
    assert rho < 0.5, (
        f"yöntem {yontem!r}: yanıt '{iddia}' kararını açıkladığını iddia ediyor (arayüz: “… kararına götüren bölgeler”) "
        f"ama '{iddia}' ve '{karsit}' haritaları ayrışmıyor (Spearman rho {rho:.3f}; aynı={np.array_equal(h_iddia, h_karsit)})"
    )


def test_KARSIT_varsayilan_yontem_karari_IDDIA_EDER(ict):
    """Varsayılan (hirescam) yöntemde karar iddiası KALIR — düzeltme başlığı genel başlığa düşürmemeli."""
    r = ict.xai_termal_isi_haritasi(str(SAGLIKLI), hedef_sinif="Healthy")
    assert r.get("method") == "hirescam" and r.get("hedef") == "Healthy"
