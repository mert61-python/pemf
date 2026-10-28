# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.64 · B-5.18 — histopatoloji KARARSIZLIK haritası mutlak ayrışma büyüklüğünü korur ve yanıt mutlak bir ölçü taşır.

🔴 ÖLÇÜLEN DURUM (HEAD ebf1c3fe): `ai_hub/xai_utils/disagreement.py::ensemble_disagreement_map` piksel std'sini görüntü
başına min-max ile [0, 1]'e geriyordu → üç backbone neredeyse AYNI haritayı verse de (ham std maks ≈ 0,003) en parlak bölge 1,0;
arayüz (`ai.patoloji.kararsizlikNot`) "Parlak bölgelerde üç model AYRIŞIYOR — derece o bölgede daha az güvenilirdir" diyordu.
Uyumlu ve ayrışan durumda gösterilen harita AYNI parlaklıkta; yanıtta mutlak bir ölçü yok. ⚠️ pytorch-grad-cam her CAM'i zaten
kendi içinde min-max'lar — buradaki ölçü normalize haritaların ŞEKİL ayrışması; mutlak ölçek = [0, 1]'deki N değerin kuramsal
en büyük std'si (N=3 → √2/3).
KAPI (planın yöntemi): uyumlu 3 CAM (ham std maks ≈ 0,003) ve ayrışan 3 CAM (a) gerçek `ensemble_disagreement_map`ten ve
(b) ÜRÜNÜN yanıt zincirinden (`xai_histopat_isi_haritasi`; sınıflandırıcı + CAM üreticisi sahte, birleştirme / overlay / yanıt
gerçek) geçirilir. İddia: yanıttaki mutlak ölçü (`xai_disagreement_max`) uyumlu durumda ≥ 10 kat düşük; gösterilen overlay'in
parlaklığı buna orantılı; router ve :8100 ölçüyü yanıta taşır. Sınıflandırma sonucu (grade / olasılık) DEĞİŞMEZ.
"""

from __future__ import annotations

import base64
import math
from pathlib import Path

import capraz
import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
#: N=3 değer [0, 1]'deyken kuramsal en büyük nüfus std'si (pinli — üründen OKUNMAZ)
TAVAN3 = math.sqrt(2) / 3


def _cams(uyumlu: bool) -> list[np.ndarray]:
    """224×224 üç CAM — pytorch-grad-cam gibi her biri KENDİ içinde min-max'lı [0, 1]."""
    y, x = np.mgrid[0:224, 0:224].astype(np.float32)

    def leke(cx, cy, s=28.0):
        return np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * s * s))

    if uyumlu:
        taban = leke(112, 112)
        rng = np.random.default_rng(5)
        ham = [taban + rng.normal(0, 0.002, taban.shape).astype(np.float32) for _ in range(3)]
    else:
        ham = [leke(60, 60), leke(170, 70), leke(110, 175)]
    out = []
    for c in ham:
        c = np.maximum(c, 0)
        out.append(((c - c.min()) / (c.max() - c.min())).astype(np.float32))
    return out


def test_KRITIK_kararsizlik_haritasi_MUTLAK_buyuklugu_korur():
    from ai_hub.xai_utils.disagreement import ensemble_disagreement_map

    u, a = _cams(True), _cams(False)
    ham_u = float(np.stack(u).std(axis=0).max())
    ham_a = float(np.stack(a).std(axis=0).max())
    assert ham_u < 0.01 and ham_a > 0.3, f"kurulum: uyumlu ham std maks {ham_u:.4f}, ayrışan {ham_a:.4f}"
    du, da = ensemble_disagreement_map(u, mode="std"), ensemble_disagreement_map(a, mode="std")
    assert du.shape == da.shape == (224, 224)
    assert float(du.max()) == pytest.approx(ham_u / TAVAN3, rel=1e-3), (
        f"uyumlu CAM'lerde harita maksimumu {du.max():.4f} — mutlak (ham std / √2/3 = {ham_u / TAVAN3:.4f}) değil; "
        "görüntü başına min-max büyüklüğü atıyor"
    )
    assert float(da.max()) == pytest.approx(ham_a / TAVAN3, rel=1e-3), (
        f"ayrışan CAM'lerde harita maksimumu {da.max():.4f} (beklenen {ham_a / TAVAN3:.4f})"
    )
    assert float(da.max()) >= 10 * float(du.max()), (
        f"uyumlu ({du.max():.4f}) ve ayrışan ({da.max():.4f}) harita aynı parlaklıkta — kararsızlık büyüklüğü atılıyor"
    )
    assert float(du.min()) >= 0.0 and float(da.max()) <= 1.0


def _zincir(monkeypatch, tmp_path, uyumlu: bool) -> dict:
    capraz.paket_yoksa_atla("torch")
    capraz.paket_yoksa_atla("pytorch_grad_cam")
    import cv2

    import ai_hub.inference_renal_histopath_kmc.inference_renal_histopath_kmc as irh
    import ai_hub.xai_utils.grad_cam as gc

    cams = _cams(uyumlu)
    sayac = {"i": 0}

    class _SahteExplainer:
        def __init__(self, *a, **k):
            self.i = sayac["i"]
            sayac["i"] += 1

        def explain(self, x, class_idx=None):
            return cams[self.i]

    class _SahteClf:
        classes = ["Grade 0", "Grade 1", "Grade 2", "Grade 3", "Grade 4"]
        device = "cpu"
        model = object()

        def predict(self, p, top_k=1):
            return {"top_1_class": "Grade 2", "top_1_prob": 0.8}

    monkeypatch.setattr(gc, "GradCAMExplainer", _SahteExplainer)
    monkeypatch.setitem(irh._XAI_PT_CACHE, "kmc", _SahteClf())
    monkeypatch.setattr(irh, "_KMC_TRIO_TARGET_LAYERS", {"a": lambda m: None, "b": lambda m: None, "c": lambda m: None})
    p = tmp_path / "siyah.png"
    cv2.imwrite(str(p), np.zeros((224, 224, 3), np.uint8))
    return irh.xai_histopat_isi_haritasi(str(p), pt_path=str(p))


def _parlaklik(b64: str) -> float:
    import cv2

    img = cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8), cv2.IMREAD_COLOR)
    return float(img.astype(np.float32).sum(axis=2).max())


def test_KRITIK_yanit_MUTLAK_olcu_tasir_ve_gosterilen_harita_ORANTILI(monkeypatch, tmp_path):
    ru = _zincir(monkeypatch, tmp_path, uyumlu=True)
    ra = _zincir(monkeypatch, tmp_path, uyumlu=False)
    for r in (ru, ra):
        assert "xai_disagreement_max" in r, f"yanıtta mutlak kararsızlık ölçüsü yok: {sorted(r)}"
        assert 0.0 <= r["xai_disagreement_max"] <= 1.0
    assert ra["xai_disagreement_max"] >= 10 * ru["xai_disagreement_max"], (
        f"yanıttaki ölçü uyumlu {ru['xai_disagreement_max']} / ayrışan {ra['xai_disagreement_max']} — ≥10 kat fark yok"
    )
    pu, pa = _parlaklik(ru["xai_disagreement_base64"]), _parlaklik(ra["xai_disagreement_base64"])
    assert pa >= 10 * max(pu, 1.0), (
        f"gösterilen kararsızlık haritası uyumlu durumda da parlak (uyumlu {pu:.0f} / ayrışan {pa:.0f}, RGB toplamı maks) — "
        "büyüklük görüntü başına normalizasyonla atılıyor"
    )


def test_KRITIK_router_ve_8100_mutlak_olcuyu_YANITA_tasir():
    """Yanıt zinciri: gömülü router ve :8100 aynı alanı (`xai_disagreement_max`) yanıta koyar (parite)."""
    for yol, isaret in (
        (KOK / "apps" / "backend" / "servers" / "ai_router.py", "def analyze_histopath"),
        (KOK / "ai_service" / "app.py", 'post("/infer/histopath")'),
    ):
        src = yol.read_text(encoding="utf-8")
        i = src.index(isaret)
        govde = src[i : i + 5000]
        assert '"xai_disagreement_max"' in govde, f"{yol.name}: histopath yanıtı mutlak kararsızlık ölçüsünü taşımıyor"


# ── TUR 2 kolları (çürütücü, hat D) ─────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("n", [2, 3, 4])
@pytest.mark.parametrize("kip", ["std", "var", "ptp"])
def test_kuramsal_EN_BUYUK_ayrisma_HER_kipte_ve_HER_n_de_1(kip, n):
    """Tur 2 kolu (ikiz kip / tanım değeri): [0, 1]'de en büyük ayrışma (yarısı 0, kalanı 1) mutlak ölçekte HER kipte (std / var /
    ptp) ve her model sayısında TAM 1'e eşlenir — tavanı yanlış bir kipte (ör. var için karesiz) harita en büyük ayrışmayı <1 gösterir."""
    from ai_hub.xai_utils.disagreement import ensemble_disagreement_map

    k = n // 2
    cams = [np.zeros((8, 8), np.float32)] * k + [np.ones((8, 8), np.float32)] * (n - k)
    d = ensemble_disagreement_map(cams, mode=kip)
    assert d.shape == (8, 8)
    assert np.allclose(d, 1.0, atol=1e-5), (
        f"en büyük ayrışma {kip} / n={n} kipinde {float(d.min()):.4f}–{float(d.max()):.4f} (1 bekleniyordu)"
    )
    uyum = ensemble_disagreement_map([np.full((8, 8), 0.4, np.float32)] * n, mode=kip)
    assert np.allclose(uyum, 0.0, atol=1e-6), f"tam uyum {kip} / n={n} kipinde sıfır değil: {float(uyum.max()):.4f}"


def test_TEK_CAM_haritasi_SONLU_ve_SIFIR():
    """Tur 2 kolu (tek öğe): tek CAM'de ayrışma tanımsız değil SIFIRDIR — harita NaN / sonsuz taşımaz (0'a bölme yok)."""
    from ai_hub.xai_utils.disagreement import ensemble_disagreement_map

    d = ensemble_disagreement_map([np.linspace(0, 1, 64, dtype=np.float32).reshape(8, 8)], mode="std")
    assert np.isfinite(d).all(), f"tek CAM'de harita sonlu değil: {d.ravel()[:4]}"
    assert float(np.abs(d).max()) == 0.0, f"tek CAM'de ayrışma sıfır değil: {float(np.abs(d).max())}"


def test_yanit_OLCUSU_haritanin_MAKSIMUMU(monkeypatch, tmp_path):
    """Tur 2 kolu (ikiz çağrı yeri — yanıt alanı): `xai_disagreement_max` gösterilen haritanın MAKSİMUMUDUR (ad + docstring) —
    ham std maksimumu / kuramsal tavan (testte bağımsız hesap); ortalama ya da başka bir istatistik uyumlu/ayrışan oranını korusa da YANLIŞ."""
    for uyumlu in (True, False):
        r = _zincir(monkeypatch, tmp_path, uyumlu=uyumlu)
        beklenen = float(np.stack(_cams(uyumlu)).std(axis=0).max()) / TAVAN3
        assert r["xai_disagreement_max"] == pytest.approx(beklenen, abs=2e-3), (
            f"{'uyumlu' if uyumlu else 'ayrışan'}: yanıt ölçüsü {r['xai_disagreement_max']} ≠ harita maksimumu {beklenen:.4f}"
        )
