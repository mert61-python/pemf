# -*- coding: utf-8 -*-
"""AI1.X10 — `scripts/xai_batch_rapor.py` (guii'nin TEK toplu XAI CLI'ı) düzeltilmiş yöntemleri kullanır; hocanın `xai_run.py`'si guii'ye
ikinci CLI olarak GİRMEZ.

ÖLÇÜLEN DURUM (2026-10-11; `DUZELTME-AI1.md` X10): `--xai-method` varsayılanı `gradcam++` termale (tek lojitte sınıf-duyarsız — X1) ve sese
(bazı örneklerde boş harita — X7) ZORLANIYORDU; EM toplu yolu (`_run_xai_em` → `batch_xai`) eski duyarlılığı (ileri fark, organ kesirli,
öğrenilmemiş/alan işareti yok) ve `nsamples=60` SHAP'ı kullanıyordu — 6 özellikte 62 koalisyonun altında rastgele örnekleme: aynı noktanın
SHAP'ı tek başına ve yığın sonunda FARKLI (ölçüldü: x katkısı 0,000187 ↔ 0,000059; 200'de birebir).
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import capraz
import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
F = ["x", "y", "z", "organ_id", "achieved_B", "duty_sum"]


@pytest.fixture(scope="module")
def cli():
    spec = importlib.util.spec_from_file_location("xai_batch_rapor_ai1", KOK / "scripts" / "xai_batch_rapor.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["xai_batch_rapor_ai1"] = m
    spec.loader.exec_module(m)
    return m


def test_KRITIK_cli_xai_method_VARSAYILANI_zorlamaz():
    agac = ast.parse((KOK / "scripts" / "xai_batch_rapor.py").read_text(encoding="utf-8"))
    cagri = next(
        c
        for c in ast.walk(agac)
        if isinstance(c, ast.Call)
        and getattr(c.func, "attr", "") == "add_argument"
        and c.args
        and getattr(c.args[0], "value", None) == "--xai-method"
    )
    varsayilan = next(k.value for k in cagri.keywords if k.arg == "default")
    assert isinstance(varsayilan, ast.Constant) and varsayilan.value is None, "toplu CLI termal/ses yöntemini ZORLUYOR"


def test_KRITIK_termal_ve_ses_MODUL_varsayilanina_devreder(cli, monkeypatch, tmp_path):
    import subprocess

    import utils.ses_kalitesi as sk

    import ai_hub.cat_thermal.inference_cat_thermal as ict
    import ai_hub.inference_cat_sound.inference_cat_sound as ics

    cagri = []
    monkeypatch.setattr(ict, "xai_termal_isi_haritasi", lambda *a, **k: cagri.append(("termal", a, k)) or {})
    monkeypatch.setattr(ics, "xai_ses_isi_haritasi", lambda *a, **k: cagri.append(("ses", a, k)) or {})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stderr=b""))
    monkeypatch.setattr(sk, "wav_rms_dbfs", lambda yol: -12.0)
    monkeypatch.setattr(sk, "sessiz_mi", lambda rms: False)
    cli._gorsel_explain_fn("termal", None)(tmp_path / "t.jpg")
    cli._ses_kapili_explain(tmp_path / "s.mp3", None)
    for ad, a, k in cagri:
        assert "method" not in k and len(a) <= 2, f"{ad}: yöntem verilmediği halde zorlandı: {a} {k}"
    cagri.clear()
    cli._gorsel_explain_fn("termal", "gradcam")(tmp_path / "t.jpg")
    cli._ses_kapili_explain(tmp_path / "s.mp3", "hirescam")
    assert [(a[2] if len(a) > 2 else k.get("method")) for _, a, k in cagri] == ["gradcam", "hirescam"], (
        "açık yöntem seçimi geçmedi"
    )


def _sahte_tahminci():
    W = np.linspace(-1.0, 1.0, 6 * 9).reshape(6, 9)
    W[5, :7] = 3.0

    def _onnx(X):
        Z = np.asarray(X, np.float64) / np.array([100, 100, 100, 3, 0.001, 1.0])
        return np.tanh(Z @ W) + 0.3 * (Z[:, :1] ** 2)

    p = SimpleNamespace(sy=SimpleNamespace(inverse_transform=lambda y: np.asarray(y, np.float64)))
    p._build_input = lambda x, y, z, o, B, d: np.column_stack([np.atleast_1d(v) for v in (x, y, z, o, B, d)]).astype(
        np.float64
    )
    p._run_onnx = _onnx
    return p


_REF = {
    "min": np.array([-100, -100, -100, 0, 0.0009, 1.0]),
    "max": np.array([100, 100, 100, 0, 0.0011, 3.0]),
    "std": np.array([40.0, 40.0, 40.0, 0.0, 5e-5, 0.4]),
    "mean": np.zeros(6),
}
_REF_STATS = {
    "std": _REF["std"],
    "background": np.random.default_rng(7).uniform(_REF["min"], _REF["max"], size=(12, 6)),
}


def test_KRITIK_EM_toplu_yol_ALAN_ogrenilmemis_ve_YIGINDAN_bagimsiz(tmp_path):
    pd = capraz.paket_yoksa_atla("pandas")
    capraz.paket_yoksa_atla("shap")
    capraz.paket_yoksa_atla("matplotlib")
    from ai_hub.xai_tabular.em_runtime import batch_xai

    p = _sahte_tahminci()
    nokta = np.array([[20.0, -30.0, 10.0, 0.0, 0.001, 2.0]])
    digerleri = np.array(
        [[90.0, 5.0, -70.0, 0.0, 0.00095, 1.5], [-40.0, 60.0, 150.0, 0.0, 0.00105, 2.7]]
    )  # ikincisi z dışı
    tek = batch_xai(p, _REF_STATS, nokta, tmp_path / "tek", egitim_ref=_REF, sample_ids=["p0"])
    yigin = batch_xai(
        p, _REF_STATS, np.vstack([digerleri, nokta]), tmp_path / "yigin", egitim_ref=_REF, sample_ids=["d1", "d2", "p0"]
    )
    dc = pd.read_csv(tmp_path / "yigin" / "domain_check.csv")
    assert dc["egitim_araliginda"].tolist() == [True, False, True] and "z=150" in dc["aralik_disi"][1], dc.to_dict()
    sens = pd.read_csv(tmp_path / "yigin" / "sensitivity.csv").set_index("feature")["mean_abs_delta"]
    assert np.isnan(sens["organ_id"]) and (sens.drop("organ_id") > 0).all(), f"öğrenilmemiş organ_id NaN değil: {sens}"
    s_tek = pd.read_csv(tmp_path / "tek" / "sensitivity_ornek.csv", index_col=0).loc["p0"].to_numpy(float)
    s_yig = pd.read_csv(tmp_path / "yigin" / "sensitivity_ornek.csv", index_col=0).loc["p0"].to_numpy(float)
    assert np.allclose(s_tek, s_yig, equal_nan=True), "aynı noktanın duyarlılığı yığına bağlı"
    sh_tek = pd.read_csv(tmp_path / "tek" / "shap_values.csv", index_col=0).loc["p0"].to_numpy(float)
    sh_yig = pd.read_csv(tmp_path / "yigin" / "shap_values.csv", index_col=0).loc["p0"].to_numpy(float)
    assert np.isnan(sh_tek[3]) and np.isnan(sh_yig[3]), "öğrenilmemiş organ_id SHAP'ı NaN değil"
    assert np.allclose(sh_tek, sh_yig, rtol=1e-9, atol=1e-12, equal_nan=True), (
        f"aynı noktanın SHAP'ı tek başına {sh_tek} ↔ yığında {sh_yig} — koalisyon örneklemesi yığına bağlı"
    )
    assert tek["alan_disi"] == [[]] and len(yigin["alan_disi"][1]) == 1


@pytest.mark.parametrize(
    "modul",
    [
        "ai_hub.em_kedi.inference_em_kedi",
        "ai_hub.inference_em_fantom.inference_em_fantom",
        "ai_hub.inference_em_petri.inference_em_petri",
    ],
)
def test_KRITIK_modul_toplu_yolu_EGITIM_REFERANSINI_gecirir(monkeypatch, modul):
    import importlib

    import ai_hub.xai_tabular.em_runtime as rt

    m = importlib.import_module(modul)
    yakalanan = {}
    monkeypatch.setattr(rt, "batch_xai", lambda pred, ref, X, out, **kw: yakalanan.update(kw) or {})
    m._run_xai_em(object(), np.zeros((1, 6)), "cikti")
    er = yakalanan.get("egitim_ref")
    assert er is not None and set(er) >= {"min", "max", "std"}, f"{modul}: toplu yol eğitim referansını geçirmiyor"


def test_KRITIK_EM_toplu_SHAP_ALTI_ozellik_degisirken_YIGINDAN_bagimsiz(tmp_path):
    """6 özelliğin HEPSİ arka plana göre değişirken (organ_id öğrenilmiş) KernelExplainer 2^6-2 = 62 koalisyon ister: 60 örnekte rastgele
    örnekleme → aynı noktanın SHAP'ı yığındaki konumuna bağlı (gerçek em_kedi'de ölçüldü); 200'de tam sayım → birebir aynı.
    (Önceki senaryoda organ_id arka planda sabit → 5 değişken → 30 koalisyon: 60 bile tam sayımdı, kapı bu kusuru görmüyordu.)"""
    pd = capraz.paket_yoksa_atla("pandas")
    capraz.paket_yoksa_atla("shap")
    capraz.paket_yoksa_atla("matplotlib")
    from ai_hub.xai_tabular.em_runtime import batch_xai

    ref = {
        "min": np.array([-100, -100, -100, 0, 0.0009, 1.0]),
        "max": np.array([100, 100, 100, 6, 0.0011, 3.0]),
        "std": np.array([40.0, 40.0, 40.0, 1.9, 5e-5, 0.4]),
        "mean": np.zeros(6),
    }
    rng = np.random.default_rng(11)
    bg = rng.uniform(ref["min"], ref["max"], size=(12, 6))
    bg[:, 3] = rng.integers(0, 7, size=12)
    rs = {"std": ref["std"], "background": bg}
    p = _sahte_tahminci()
    nokta = np.array([[20.0, -30.0, 10.0, 3.0, 0.001, 2.0]])
    digerleri = rng.uniform(ref["min"], ref["max"], size=(4, 6))
    digerleri[:, 3] = [1, 2, 5, 6]
    batch_xai(p, rs, nokta, tmp_path / "tek", egitim_ref=ref, sample_ids=["p0"])
    batch_xai(
        p, rs, np.vstack([digerleri, nokta]), tmp_path / "yigin", egitim_ref=ref, sample_ids=["a", "b", "c", "d", "p0"]
    )
    sh_tek = pd.read_csv(tmp_path / "tek" / "shap_values.csv", index_col=0).loc["p0"].to_numpy(float)
    sh_yig = pd.read_csv(tmp_path / "yigin" / "shap_values.csv", index_col=0).loc["p0"].to_numpy(float)
    assert not np.isnan(sh_tek).any(), "öğrenilmiş özellikte NaN"
    assert np.allclose(sh_tek, sh_yig, rtol=1e-9, atol=1e-12), f"SHAP yığına bağlı: tek {sh_tek} ↔ yığın {sh_yig}"
