# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODK6 (istem 45 · sahip 12 Kasım gece): CANLI E ÇUBUĞU → CST E. ODAK seansında E, sürülen planın CST E'sidir (ODAK fizik denetimiyle AYNI
hesap): CST `bobin1..7_ekutu.txt` (LF 100 Hz) B tablosuyla aynı küresel faz + Eylül işaretiyle gerçelleştirilmiş; E'nin SANAL (indüklenen)
kısmı — 12-11 ölçüldü: gerçel kısım enerjinin < %0,2'si (saf Faraday). E(t) = Σ_c Ê_c · i_c′(t) / ω_CST; i_c(t) B ile AYNI genlik (ölçülen B
kalibrasyonu) / RL dalga biçimi / Y280 hizası. E DOĞRUDAN ÖLÇÜLMEDİ → arayüz "hesaplanan" der. Analiz bağlamında (ODAK dışı) vekil yol AYNEN
("yaklaşık"). E tablosu yoksa yalnız gösterim eksik kalır — sürüş ENGELLENMEZ (doz denetimi B ile).
Tablo AI MODEL KATMANINDA (Y282: `release_assets/ai_models/ai_hub/odak/veri/e_tablosu.npz`, açık depoda YOK, takipli manifestte)."""

from __future__ import annotations

import json
import os

import numpy as np
import pytest
from test_ODK_ai_pro_odak_entegrasyon import _DogruModel

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORNEK = os.path.join(KOK, "tests", "veri", "odak_kalibrasyon_ornek.json")


def _K():
    with open(ORNEK, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def A():
    from ai_hub.odak.alan import AlanModeli

    return AlanModeli(_K())


def test_YAPISAL_E_tablosu_AI_MODEL_KATMANINDA_izgara_B_ile_AYNI_manifestte():
    from utils import model_downloader as md

    from ai_hub.odak.alan import E_TABLOSU, VERI_DIZINI, alan_tablosu, e_tablosu, model_katmani_yolu

    yol = model_katmani_yolu(E_TABLOSU)
    assert not os.path.exists(os.path.join(VERI_DIZINI, E_TABLOSU)), "E tablosu depodaki veri dizininde (Y282)"
    et, bt = e_tablosu(), alan_tablosu()
    assert np.allclose(et["kok"], bt["kok"]) and et["adim"] == bt["adim"] and np.array_equal(et["boyut"], bt["boyut"])
    assert et["f_cst_hz"] == 100.0 and et["E"].shape == bt["B"].shape
    man = json.load(open(os.path.join(KOK, "release_assets", "ai_models_sha256.json"), encoding="utf-8"))["dosyalar"]
    rel = f"ai_hub/odak/veri/{E_TABLOSU}"
    assert rel in man and md._dosya_ozeti(md.Path(yol)) == man[rel]["sha256"]


def test_KRITIK_E_FARADAY_akim_TUREVI_ve_omega_CST(A):
    """Tek bobin, tek nokta: tepe |E| = |Ê| · max|i′(t)| / (2π · 100 Hz) — i(t) B'nin dalgasıyla AYNI (bağımsız türev: np.gradient)."""
    P = np.array([[20.0, -120.0, 10.0]])
    ME = A.e_alan(P)
    for c, d in ((0, 0.3), (5, 0.4)):  # bipolar 1 · tek yönlü 6
        sd = np.zeros(7)
        sd[c] = d
        W = A._td_dalga(sd)[c]
        Nt = W.size
        g = np.gradient(np.tile(W, 3), 1.0 / (A.f_hz * Nt))[Nt : 2 * Nt]
        beklenen = np.linalg.norm(ME[0, :, c]) * np.abs(g).max() / (2 * np.pi * 100.0)
        assert A.td_e_tepe(ME, sd)[0] == pytest.approx(beklenen, rel=0.02), c
        # B ile aynı genlik: duty yarıya inince E'nin TÜREV tepesi dalga biçimine göre değişir ama sıfır olmaz; duty 0 → E 0
        assert A.td_e_tepe(ME, np.zeros(7))[0] == 0.0
    # E (V/m) mertebesi: 1 mT civarı tepe alanda CST ölçeğinde 0,001–1 V/m
    sd = A.isaretli_duty(np.full(7, 0.6))
    e = A.td_e_tepe(ME, sd)[0]
    assert 1e-3 < e < 1.0, e


def test_KRITIK_E_kalibrasyon_KAZANCIYLA_olceklenir(A):
    """E ölçeği B kalibrasyonundan (aynı bobin akımı): kazanç 2× → E 2×."""
    from ai_hub.odak.alan import AlanModeli

    K2 = _K()
    K2["kazanc"] = [2.0 * float(v) for v in K2["kazanc"]]
    A2 = AlanModeli(K2)
    P = np.array([[0.0, -150.0, 0.0]])
    sd = A.isaretli_duty(np.array([0.5, -0.3, 0.2, 0.0, 0.4, 0.1, -0.2]))
    assert A2.td_e_tepe(A2.e_alan(P), sd)[0] == pytest.approx(2.0 * A.td_e_tepe(A.e_alan(P), sd)[0], rel=1e-6)


def test_KRITIK_PLAN_hedef_ve_cevre_E_ODAK_fizik_denetimiyle_AYNI(A):
    from ai_hub.odak import oneri

    T = [20.0, -155.0, 10.0]
    fan = {"merkez_P": [0.0, -150.0, 0.0], "theta": 0.4}
    plan = oneri.oner("FANTOM", A, 0.5, model=_DogruModel(A, [T]), hedef_P=T, fantom=fan)
    assert plan["engel"] is None and plan["e_hedef_Vm"] > 0 and plan["e_cevre_Vm"] > 0, plan
    g = oneri.kip_girdisi("FANTOM", A, hedef_P=T, fantom=fan)
    sd = np.asarray(plan["duty"]) * np.where(
        np.mod(np.asarray(plan["faz"]) - (max(plan["duty"]) - np.asarray(plan["duty"])) * 360, 360) > 90, -1, 1
    )
    assert plan["e_hedef_Vm"] == pytest.approx(float(A.td_e_tepe(A.e_alan(g["T"]), sd).mean()), rel=0.05)


def test_KARSIT_E_tablosu_YOKSA_plan_SURULUR_E_None(monkeypatch):
    from ai_hub.odak import alan, oneri

    gercek = alan.model_katmani_yolu

    def secici(ad):
        if ad == alan.E_TABLOSU:
            raise FileNotFoundError(ad)
        return gercek(ad)

    monkeypatch.setattr(alan, "model_katmani_yolu", secici)
    alan.e_tablosu.cache_clear()
    try:
        A = alan.AlanModeli(_K())
        T = [20.0, -155.0, 10.0]
        plan = oneri.oner(
            "FANTOM",
            A,
            0.5,
            model=_DogruModel(A, [T]),
            hedef_P=T,
            fantom={"merkez_P": [0.0, -150.0, 0.0], "theta": 0.4},
        )
    finally:
        alan.e_tablosu.cache_clear()
    assert plan["engel"] is None and any(d > 0 for d in plan["duty"])
    assert plan["e_hedef_Vm"] is None and plan["e_cevre_Vm"] is None


_CALISAN = [
    {"running": True, "dutyCycle": 30.0, "magneticMt": 0.8, "measuredFields": ["magneticMt"]},
    {"running": False},
]


def test_KRITIK_efield_live_ODAK_kaynagi_VEKILIN_ONUNDE_ve_TEMIZLENIR(monkeypatch):
    from servers import efield_live as ef

    def patla(*a, **k):
        raise AssertionError("ODAK seansında vekil model çağrıldı")

    monkeypatch.setattr(ef, "_predictor", patla)
    ef.set_context([{"centroid_cabin_mm": [0.0, 0.0, 0.0]}], 1, "fantom")
    try:
        ef.odak_guncelle({"cancer": 0.05, "healthy": 0.01})
        v = ef.compute(_CALISAN)
        assert v["kaynak"] == "cst" and v["cancer"] == 0.05 and v["healthy"] == 0.01 and v["activeCoils"] == 1
        assert v["avg"] == pytest.approx(0.03) and v["achievedB_T"] == pytest.approx(0.0008)
        v0 = ef.compute([{"running": False}])
        assert v0["kaynak"] == "cst" and v0["cancer"] == 0.0 and v0["activeCoils"] == 0, (
            "bobinler dururken E sürüyor görünüyor"
        )
        ef.odak_guncelle({"cancer": 0.05, "healthy": None})
        v = ef.compute(_CALISAN)
        assert v["healthy"] is None and v["avg"] == pytest.approx(0.05)  # çevre yok (tüm vücut / tüm petri) → '—'
        ef.seans_basladi("ai_pro", "fantom")
        assert ef.odak_degeri() is None, "önceki seansın ODAK E'si yeni seansa sızdı"
        ef.odak_guncelle({"cancer": 0.05, "healthy": 0.01})
        ef.seans_bitti()
        assert ef.odak_degeri() is None and ef.get_context() is None
    finally:
        ef.set_context([])


def test_KRITIK_saglayici_SURULEN_planin_E_sini_tutar_ENGELDE_None(monkeypatch):
    from servers import ai_pro_hedef as hedef

    f = hedef.FantomSaglayici()
    hedef.odak_ayarla(f, {"doz_mT": 0.4, "kip": "FANTOM"}, "Tümör 1")
    plan = {"engel": None, "duty": [0.2] * 7, "faz": [0.0] * 7, "e_hedef_Vm": 0.04, "e_cevre_Vm": 0.02}
    monkeypatch.setattr(hedef, "odak_plani", lambda *a, **k: dict(plan))
    f.predict(0.0, -150.0, 0.0, 1)
    assert f.son_odak_e == {"cancer": 0.04, "healthy": 0.02, "ortam": None}  # ODK10: plan e_ortam vermedi
    monkeypatch.setattr(
        hedef, "odak_plani", lambda *a, **k: {"engel": "dozSapmasi", "duty": [0.0] * 7, "faz": [0.0] * 7}
    )
    f.predict(0.0, -150.0, 0.0, 1)
    assert f.son_odak_e is None
