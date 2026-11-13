# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODK10 (istem 45 · sahip 13 Kasım 2026: "petri kabı koy simülasyona petri için simülasyon yap … alt camın üstündeymiş gibi"):
PETRİ E'si KUYU SIVISI İÇİNDE. Havada (ortamsız) CST E kuyu içindekinin ~190 katıydı — petri seansında E çubuğu artık kuyu sıvısındaki
E'yi gösterir; kedi (ortam benzetimi yok) havada kalır ve etiketi bunu söyler.
FİZİK: yarı-durağan iletken kuyu + yalıtkan duvar → E = −∂(A + ∇ψ)/∂t, n·(A + ∇ψ) = 0; σ / ε kuyu İÇİNDEKİ E'yi değiştirmez.
ÇAPA: CST LF petri benzetimi (13-11, plaka camın üstünde, 24 kuyu sıvısı εr 1e6 / σ 0,15 S/m, 100 Hz) — dört kuyu (eksenel B payı %3 / %15 /
%41 / %91), kuyu ortalama B (karmaşık) + CST iç (duvar / yüzeyden ≥ 2 mm) |E| ortalaması; CST nokta ızgarası aynen kurulur.
EN ALT sahte: ODAK modeli (`_DogruModel`, fizikle tutan); alan tablosu + E tablosu + kalibrasyon + plan GERÇEK."""

from __future__ import annotations

import json
import os

import numpy as np
import pytest
from test_ODK_odak_alan_ve_oneri import _DogruModel, _plaka

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORNEK = os.path.join(KOK, "tests", "veri", "odak_kalibrasyon_ornek.json")
W100 = 2 * np.pi * 100.0

#: (B gerçel, B sanal (T, CST eksenleri: X yükseklik), CST |E| ort (V/m), CST ızgara kayması (v, w) mm, nokta sayısı)
CST_CAPA = (
    (
        (5.914075e-06, 0.0001707526, 2.092933e-05),
        (3.173642e-06, -0.0001913603, -1.876013e-05),
        0.0001938783,
        (0.35, 0.65),
        530,
    ),  # %3 eksenel
    (
        (1.05944e-05, -4.585377e-06, -3.510676e-06),
        (-1.04302e-05, 3.297734e-06, 1.883059e-06),
        1.873763e-05,
        (0.65, 0.35),
        530,
    ),  # %91
    (
        (6.718846e-06, -2.463976e-06, -2.202493e-05),
        (-1.209809e-05, 5.656738e-06, 2.089e-05),
        2.826602e-05,
        (0.75, 0.05),
        520,
    ),  # %41
    (
        (-1.108419e-05, -0.0001241672, -3.605815e-06),
        (2.600546e-05, 0.0001419416, 3.628106e-06),
        0.0001443374,
        (0.25, 0.95),
        520,
    ),  # %15
)


@pytest.fixture(scope="module")
def A():
    from ai_hub.odak.alan import AlanModeli

    with open(ORNEK, encoding="utf-8") as fh:
        return AlanModeli(json.load(fh))


def _hucre(P, Q, h):
    """Q noktalarını içeren şekil hücresinin P'deki sırası (hücre sınırları h'nin katlarında)."""
    sozluk = {tuple(k): i for i, k in enumerate(np.floor(P / h + 1e-9).astype(np.int64))}
    return np.array([sozluk[tuple(k)] for k in np.floor(Q / h + 1e-9).astype(np.int64)])


@pytest.mark.parametrize("capa", CST_CAPA, ids=["yanal_3", "eksenel_91", "karisik_41", "yanal_15"])
def test_KRITIK_CST_CAPASI_kuyu_ici_E_model_ile_UYUSUR(capa):
    from ai_hub.odak import kuyu_e

    b_re, b_im, e_cst, (kv, kw), n = capa
    B = np.array(b_re) + 1j * np.array(b_im)
    P, G = kuyu_e.sekil(kuyu_e.KUYU_YARICAP_MM, 10.0, 0.5, 1)
    u, v, w = np.meshgrid(np.arange(-2.0, 3.0), np.arange(-7.0, 8.0) + kv, np.arange(-7.0, 8.0) + kw, indexing="ij")
    Q = np.stack((u.ravel(), v.ravel(), w.ravel()), 1)
    Q = Q[np.hypot(Q[:, 1], Q[:, 2]) < kuyu_e.KUYU_YARICAP_MM - 2.0]
    assert len(Q) == n, "CST nokta ızgarası kurulamadı"
    j = _hucre(P, Q, 0.5)
    E = -1j * W100 * np.einsum("k,kpc->pc", B, G[:, j, :]) * 1e-3
    e_model = float(np.linalg.norm(np.abs(E), axis=1).mean())
    assert e_model == pytest.approx(e_cst, rel=0.04), (e_model, e_cst)


def test_KRITIK_SEKIL_eksenel_B_analitik_yarim_omega_B_r():
    """Eksenel düzgün B'de tam çözüm ψ = 0: E = ω/2 · B · r (azimutal) — iç noktalarda."""
    from ai_hub.odak import kuyu_e

    P, G = kuyu_e.sekil(7.8, 10.0, 0.5, 1)
    r = np.hypot(P[:, 1], P[:, 2])
    ic = (r > 1.0) & (r < 6.0) & (np.abs(P[:, 0]) < 4.0)
    beklenen = np.stack((np.zeros(ic.sum()), -0.5 * P[ic, 2], 0.5 * P[ic, 1]), 1)
    assert np.abs(G[0, ic] - beklenen).max() < 0.03 * (0.5 * 6.0)


def test_KRITIK_SEKIL_YALITKAN_DUVAR_ince_kuyuda_yanal_B_dilim_cozumu():
    """Duvar koşulu (akım sızmaz) gerçekten çözülüyor mu: ince geniş kuyuda (H ≪ R) yanal B için tam dilim çözümü G = −u · (û × ê)
    (|G| = |u|); ψ'siz ½ ê × r ise merkezden uzakta |G| ~ r/2 olurdu."""
    from ai_hub.odak import kuyu_e

    P, G = kuyu_e.sekil(10.0, 1.0, 0.25, 1)
    r = np.hypot(P[:, 1], P[:, 2])
    ic = r < 4.0
    beklenen = np.stack((np.zeros(ic.sum()), np.zeros(ic.sum()), -P[ic, 0]), 1)  # ê = v̂ → û × v̂ = ŵ
    assert np.abs(G[1, ic] - beklenen).max() < 0.05 * 0.5
    assert np.abs(np.linalg.norm(G[1, ic], axis=1) - np.abs(P[ic, 0])).max() < 0.05 * 0.5


def test_KRITIK_KUYU_E_TEPE_faraday_birimleri_ve_zaman_turevi(A):
    """Tek bobin: tepe |E| = ortalama_p max_t |G·M_c| · |W_c′(t)| (bağımsız türev: np.gradient), V/m (mm · mT → 1e-6)."""
    from ai_hub.odak import kuyu_e

    T = np.array([[20.0, -160.0, 10.0]])
    _P, G = kuyu_e.sekil(kuyu_e.KUYU_YARICAP_MM, 10.0)
    M = A.alan(T)[0]
    for c, d in ((0, 0.3), (6, 0.4)):
        sd = np.zeros(7)
        sd[c] = d
        Wc = A._td_dalga(sd)[c]
        Nt = Wc.size
        g = np.gradient(np.tile(Wc, 3), 1.0 / (A.f_hz * Nt))[Nt : 2 * Nt]
        Gm = np.einsum("kpc,k->pc", G, M[:, c])  # (p, 3) mm · mT
        beklenen = float((np.linalg.norm(Gm, axis=1) * np.abs(g).max()).mean() * 1e-6)
        assert float(kuyu_e.kuyu_e_tepe(A, T, sd, 10.0)[0]) == pytest.approx(beklenen, rel=0.03)


def _sd(plan):
    """Plandan işaretli duty (Y280: faz = (d_maks − d)·360 + 180 negatifse, mod 360). ⚠️ duty 4, faz 2 basamağa yuvarlı → artık açı 0
    yerine 359,98° çıkabilir (ODK12 kazançlarında ölçüldü: `> 90` testi pozitif bobini NEGATİF sayıyordu) → negatif = (90°, 270°)."""
    d = np.asarray(plan["duty"])
    artik = np.mod(np.asarray(plan["faz"]) - (d.max() - d) * 360, 360)
    return d * np.where((artik > 90) & (artik < 270), -1, 1)


def test_KRITIK_PLAN_KUYUCUK_E_kuyu_SIVISINDA_havadakinden_COK_KUCUK(A):
    from ai_hub.odak import kuyu_e, oneri

    kuyular = _plaka()
    hedef = next(k for k in kuyular if k["etiket"] == "B3")
    tv = oneri.hedef_tavani("KUYUCUK", A, kuyular=kuyular, hedef_etiket="B3")
    plan = oneri.oner(
        "KUYUCUK", A, 0.6 * tv["tavan_mT"], model=_DogruModel(A, [hedef["P"]]), kuyular=kuyular, hedef_etiket="B3"
    )
    assert plan["engel"] is None and plan["e_ortam"] == "kuyu", plan
    g = oneri.kip_girdisi("KUYUCUK", A, kuyular=kuyular, hedef_etiket="B3")
    sd = _sd(plan)
    H = 2.0 * float(oneri.numune()["plaka"]["sivi_orta_mm"])
    assert plan["e_hedef_Vm"] == pytest.approx(float(kuyu_e.kuyu_e_tepe(A, g["T"], sd, H).mean()), rel=0.05)
    assert plan["e_cevre_Vm"] == pytest.approx(float(kuyu_e.kuyu_e_tepe(A, g["C"], sd, H).mean()), rel=0.05)
    hava = float(A.td_e_tepe(A.e_alan(g["T"]), sd).mean())
    assert 0 < plan["e_hedef_Vm"] < hava / 20.0, (plan["e_hedef_Vm"], hava)


def test_KRITIK_PLAN_TUM_PETRI_E_kuyu_cevre_YOK(A):
    from ai_hub.odak import oneri

    kuyular = _plaka(px=False)
    tv = oneri.hedef_tavani("TUM_PETRI", A, kuyular=kuyular)
    plan = oneri.oner(
        "TUM_PETRI", A, 0.5 * tv["tavan_mT"], model=_DogruModel(A, [k["P"] for k in kuyular]), kuyular=kuyular
    )
    assert (
        plan["engel"] is None and plan["e_ortam"] == "kuyu" and plan["e_hedef_Vm"] > 0 and plan["e_cevre_Vm"] is None
    ), plan


@pytest.mark.parametrize("kip", ["KEDI_TV", "KEDI_ORGAN"])
def test_KARSIT_KEDI_E_HAVADA_ortam_hava(A, kip):
    from ai_hub.odak import oneri

    T = [0.0, -150.0, 0.0]
    kedi = {"merkez_P": [0.0, -175.0, 0.0], "theta": 0.2}
    g = oneri.kip_girdisi(kip, A, hedef_P=T, kedi=kedi)
    plan = oneri.oner(kip, A, 0.3, model=_DogruModel(A, list(g["T"])), hedef_P=T, kedi=kedi)
    if plan["engel"] is None:
        assert plan["e_ortam"] == "hava"
        assert plan["e_hedef_Vm"] == pytest.approx(float(A.td_e_tepe(A.e_alan(g["T"]), _sd(plan)).mean()), rel=0.05)


def test_KRITIK_kuyu_E_HESAPLANAMAZSA_havaya_DUSMEZ_plan_SURULUR(A, monkeypatch):
    from ai_hub.odak import kuyu_e, oneri

    def patla(*a, **k):
        raise RuntimeError("deneme")

    monkeypatch.setattr(kuyu_e, "kuyu_e_tepe", patla)
    kuyular = _plaka()
    hedef = next(k for k in kuyular if k["etiket"] == "C4")
    tv = oneri.hedef_tavani("KUYUCUK", A, kuyular=kuyular, hedef_etiket="C4")
    plan = oneri.oner(
        "KUYUCUK", A, 0.5 * tv["tavan_mT"], model=_DogruModel(A, [hedef["P"]]), kuyular=kuyular, hedef_etiket="C4"
    )
    assert plan["engel"] is None and any(d > 0 for d in plan["duty"])
    assert plan["e_hedef_Vm"] is None and plan["e_cevre_Vm"] is None and plan["e_ortam"] == "kuyu", plan


def test_KRITIK_efield_live_ORTAM_tasinir_gecersiz_None():
    from servers import efield_live as ef

    ef.set_context([{"centroid_cabin_mm": [0.0, 0.0, 0.0]}], 1, "petri")
    try:
        calisan = [{"running": True, "dutyCycle": 30.0, "magneticMt": 0.8, "measuredFields": ["magneticMt"]}]
        ef.odak_guncelle({"cancer": 0.0012, "healthy": 0.0004, "ortam": "kuyu"})
        v = ef.compute(calisan)
        assert v["kaynak"] == "cst" and v["ortam"] == "kuyu" and v["cancer"] == 0.0012
        assert ef.compute([{"running": False}])["ortam"] == "kuyu"
        ef.odak_guncelle({"cancer": 0.05, "healthy": None, "ortam": "hava"})
        assert ef.compute(calisan)["ortam"] == "hava"
        ef.odak_guncelle({"cancer": 0.05, "healthy": None, "ortam": "<script>"})
        assert ef.compute(calisan)["ortam"] is None
    finally:
        ef.set_context([])


def test_KRITIK_saglayici_E_ORTAMINI_tasir(monkeypatch):
    from servers import ai_pro_hedef as hedef

    p = hedef.PetriSaglayici()
    hedef.odak_ayarla(p, {"doz_mT": 0.4, "kip": "KUYUCUK"}, "B3")
    plan = {
        "engel": None,
        "duty": [0.2] * 7,
        "faz": [0.0] * 7,
        "e_hedef_Vm": 0.0012,
        "e_cevre_Vm": 0.0003,
        "e_ortam": "kuyu",
    }
    monkeypatch.setattr(hedef, "odak_plani", lambda *a, **k: dict(plan))
    p.predict(0.0, -160.0, 0.0, 1)
    assert p.son_odak_e == {"cancer": 0.0012, "healthy": 0.0003, "ortam": "kuyu"}
