# -*- coding: utf-8 -*-
"""AI1.X4 — CKD tek hasta açıklaması SIFIRA çökmez: Kernel SHAP arka planı = EĞİTİM verisi özeti (ağırlıklı)
(hoca XAI v3: `inference_human_kidney_disease/xai_kidney_disease_v2.py` + `xai_train_ref_v2.npz`).

ÖLÇÜLEN DURUM (2026-10-11, gerçek ExtraTrees ONNX + preprocessor, hocanın 40 hastası; `DUZELTME-AI1.md` X4):
  * gelen (ata) kod: arka plan = hastanın kendisi → 40/40 TAM SIFIR (hocanın K1 bulgusu). guii bunu Faz 1'de (`30636b6e`,
    "ortalama hasta") kapattı; ama o taban modelce %99 CKD → CKD hastalarında kütle ort. 0,026. Denetim #04 (`3aaf3513`)
    klinik-normal referansa geçti → bu kez SAĞLIKLI hastalarda kütle ort. 0,026: "kararı sürükleyenler" gürültü; tek referans
    hastayla aynı olan özellikler TAM SIFIR (CKD hastasında 24'ün 13'ü).
  * eğitim arka planı (30 k-means merkezi + küme payları): taban 0,643 (ağırlıklı eğitim ortalaması), CKD kütlesi ort. 0,34,
    sağlıklı 0,62, verimlilik hatası 0. Hocanın kodu `shap.common` yoksa payları düşürüyordu (taban 0,82) — burada AĞIRLIKLI.
"""

from __future__ import annotations

import numpy as np
import pytest

# hocanın test girdisi `xai_test_girdileri/kidney_disease.csv` satır 1 (ckd, kreatinin 24) ve satır 39 (notckd)
_HASTA_CKD = {
    "age": 68.0,
    "bp": 70.0,
    "sg": 1.01,
    "al": 0.0,
    "su": 0.0,
    "rbc": None,
    "pc": "normal",
    "pcc": "notpresent",
    "ba": "notpresent",
    "bgr": 100.0,
    "bu": 54.0,
    "sc": 24.0,
    "sod": 104.0,
    "pot": 4.0,
    "hemo": 12.4,
    "pcv": 36.0,
    "wc": None,
    "rc": None,
    "htn": "no",
    "dm": "no",
    "cad": "no",
    "appet": "good",
    "pe": "no",
    "ane": "no",
}
_HASTA_SAGLIKLI = {
    "age": 48.0,
    "bp": 80.0,
    "sg": 1.025,
    "al": 0.0,
    "su": 0.0,
    "rbc": "normal",
    "pc": "normal",
    "pcc": "notpresent",
    "ba": "notpresent",
    "bgr": 75.0,
    "bu": 22.0,
    "sc": 0.8,
    "sod": 137.0,
    "pot": 5.0,
    "hemo": 16.8,
    "pcv": 51.0,
    "wc": 6000.0,
    "rc": 6.5,
    "htn": "no",
    "dm": "no",
    "cad": "no",
    "appet": "good",
    "pe": "no",
    "ane": "no",
}


@pytest.fixture(scope="module")
def ckd():
    pytest.importorskip("shap")
    pytest.importorskip("onnxruntime")
    from golden.eser import atla, ckd_eserleri, eser_var_mi

    if not eser_var_mi(*ckd_eserleri()):
        atla(f"CKD model eserleri yok ({ckd_eserleri()})")
    from ai_hub.inference_human_kidney_disease import inference_human_kidney_disease as m

    return m


def _kutle(r) -> float:
    return sum(abs(t["attribution"]) for t in r["top_features"])


def test_KRITIK_SAGLIKLI_hastanin_aciklamasi_SIFIRA_cokmez(ckd):
    r = ckd.xai_top_features(_HASTA_SAGLIKLI, top_n=24)
    assert r["prob_ckd"] < 0.1, f"senaryo ayrışmıyor: sağlıklı kayıt artık sağlıklı tahmin edilmiyor ({r['prob_ckd']})"
    assert _kutle(r) > 0.2, (
        f"sağlıklı hastada açıklama kütlesi {_kutle(r):.4f} — referans hastaya çok yakın, 'kararı sürükleyenler' gürültü "
        "(ölçülen bozuk hâl: klinik-normal referansta 0,026)"
    )
    ilk5 = {t["feature"] for t in r["top_features"][:5]}
    assert ilk5 & {"sg", "htn", "dm", "al", "hemo"}, f"klinik çekirdek ilk-5'te yok: {ilk5}"
    assert r["baseline"] == "egitim_verisi_ozeti"


def test_KRITIK_CKD_hastasinin_aciklamasi_SIFIRA_cokmez(ckd):
    r = ckd.xai_top_features(_HASTA_CKD, top_n=24)
    assert r["prob_ckd"] > 0.9, f"senaryo ayrışmıyor: CKD kaydı artık CKD tahmin edilmiyor ({r['prob_ckd']})"
    assert _kutle(r) > 0.1, f"CKD hastasında açıklama kütlesi {_kutle(r):.4f} (Faz 1 'ortalama hasta'sında 0,01)"
    sifir = sum(1 for t in r["top_features"] if t["attribution"] == 0.0)
    assert sifir < 10, (
        f"24 özelliğin {sifir}'i TAM SIFIR — özellik susturuluyor (l1_reg, Denetim #04) ya da tek referansla aynı (ölçülen 13)"
    )


def test_KRITIK_taban_AGIRLIKLI_egitim_ortalamasi_ve_VERIMLILIK(ckd):
    """Katkılar toplamı = f(x) − E_w[f(merkez)] (SHAP verimliliği). Taban AĞIRLIKLI eğitim ortalaması olmalı: ağırlıklar
    düşerse (hocanın kodundaki sessiz düşüş) taban 0,82 olur; arka plan hastanın kendisi ya da tek referans hasta olursa
    toplam bambaşka çıkar."""
    pre, sess, inp = ckd.load_model(None)
    merkez, agirlik = ckd.xai_egitim_arka_plani(len(ckd._preprocessor_feature_names(pre)))
    taban = float(np.dot(agirlik, ckd._predict_onnx(sess, inp, merkez)))
    assert 0.55 < taban < 0.72, f"ağırlıklı eğitim ortalaması beklenmedik: {taban:.4f} (ölçülen 0,643)"
    for kayit in (_HASTA_CKD, _HASTA_SAGLIKLI):
        r = ckd.xai_top_features(kayit, top_n=24)
        toplam = sum(t["attribution"] for t in r["top_features"])
        assert toplam == pytest.approx(r["prob_ckd"] - taban, abs=2e-3), (
            f"katkı toplamı {toplam:.4f} ≠ f(x) − taban {r['prob_ckd'] - taban:.4f} — arka plan ağırlıklı eğitim özeti DEĞİL"
        )


def test_KRITIK_referans_YOKSA_ya_da_BOZUKSA_aciklama_URETILMEZ(monkeypatch, tmp_path):
    """Başka bir referansa SESSİZ düşüş yok (açıklamanın anlamı değişirdi) — açık hata; router onu 'Açıklama üretilemedi'ye
    çevirir (`test_ckd_xai.py::test_KRITIK_xai_hatasi_analizi_DUSURMEZ`). Ağırlıksız: model yüklenmeden."""
    from ai_hub.inference_human_kidney_disease import inference_human_kidney_disease as m

    merkez, agirlik = m.xai_egitim_arka_plani(24)
    assert merkez.shape == (30, 24) and agirlik.shape == (30,) and abs(float(agirlik.sum()) - 1.0) < 1e-9
    monkeypatch.setattr(m, "XAI_EGITIM_REFERANSI", tmp_path / "yok.npz")
    with pytest.raises(FileNotFoundError):
        m.xai_egitim_arka_plani(24)
    bozuk = tmp_path / "bozuk.npz"
    np.savez(bozuk, background=merkez[:, :20], weights=agirlik)
    monkeypatch.setattr(m, "XAI_EGITIM_REFERANSI", bozuk)
    with pytest.raises(ValueError):
        m.xai_egitim_arka_plani(24)
    np.savez(bozuk, background=merkez, weights=agirlik * 2.0)
    with pytest.raises(ValueError):
        m.xai_egitim_arka_plani(24)


def test_KRITIK_hazirlik_probu_CKD_referansini_OLCER(monkeypatch, tmp_path):
    """`/api/ai/hazirlik` XAI zinciri: referans yoksa 'eksik' + hazır DEĞİL (spec'te yok → üretimde sessiz ölü sınıfı)."""
    import servers.ai_router as air

    from ai_hub.inference_human_kidney_disease import inference_human_kidney_disease as m

    d1 = air._xai_zinciri_durumu()
    assert d1.get("ckd_xai_referansi") == "ok", d1
    monkeypatch.setattr(m, "XAI_EGITIM_REFERANSI", tmp_path / "yok.npz")
    d2 = air._xai_zinciri_durumu()
    assert d2.get("ckd_xai_referansi") == "eksik" and d2.get("hazir") is False, d2
    assert "yok.npz" in d2.get("ckd_xai_referansi_sebep", ""), "sebep zinciri kayboldu"
