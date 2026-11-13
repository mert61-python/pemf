# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODK5 (istem 45 · sahip 12 Kasım gece): KEDİ AI Pro ÖNERİ / ONAY hesabı ODAK'tan — KEDI_TV (Tüm Vücut) / KEDI_ORGAN. Kedi SÜRÜŞÜ
Y142 gereği KAPALI KALIR (onay 409, başlatma 409, sürüş katı — `test_ai_pro_KEDI_surus_KAPALI_varsayilan_Y142.py`).
SÖZLEŞME: gövde merkezi + yönü AYNI karedeki organlardan (kranial: kalp / akciğerler / karaciğer → kaudal: mesane / bağırsak; güven ≥ 0,3,
kabin içi, eksen ≥ 40 mm) · bulunamazsa SÜRMEZ, engel `kediGovdeYok` eylem söyler (TR + EN) · θ kuralı `oneri.kip_girdisi` gövde ızgarasıyla
AYNI (ızgaranın uzun ekseni organ eksenine paralel) · mühürde ODAK ayarı varsa kedi `predict`i ODAK'tan (hoca modeli sürüş kaynağı değil).
EN ALT sahte: ODAK modeli (fizikle tutan) ve cat_organ'ın organ sözlüğü; alan tablosu + kalibrasyon GERÇEK."""

from __future__ import annotations

import json
import os

import ai_pro_aparati as ap
import numpy as np
import pytest
from test_ODK_ai_pro_odak_entegrasyon import _DogruModel, _kok_kur

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORNEK = os.path.join(KOK, "tests", "veri", "odak_kalibrasyon_ornek.json")
# Çapraz duran kedi (backend mm): göğüs önde-solda, karın arkada-sağda → θ ≠ 0, ±90 (işaret hatası yakalanır).
GOGUS = {7: (60.0, -150.0, 40.0), 9: (50.0, -150.0, 55.0), 10: (70.0, -150.0, 25.0), 3: (35.0, -150.0, 20.0)}
KARIN = {4: (-60.0, -150.0, -45.0), 6: (-40.0, -150.0, -25.0)}
BOBREK = (0.0, -150.0, 0.0)


def _org(P, rel=0.9):
    return {"coord_cabin_cm": [v / 10.0 for v in P], "reliability": rel}


def _organlar(**ek):
    d = {k: _org(P) for k, P in {**GOGUS, **KARIN}.items()}
    d[2] = _org(BOBREK)
    d.update(ek)
    return d


@pytest.fixture(scope="module")
def A():
    from ai_hub.odak.alan import AlanModeli

    with open(ORNEK, encoding="utf-8") as fh:
        return AlanModeli(json.load(fh))


def test_KRITIK_govde_geometrisi_MERKEZ_ve_YON_kip_girdisi_IZGARASIYLA_ayni(A):
    from servers.ai_pro_hedef import kedi_govde_geometrisi

    from ai_hub.odak import oneri
    from ai_hub.odak.alan import backend_to_olcum

    g = kedi_govde_geometrisi(_organlar())
    on, arka = np.mean(list(GOGUS.values()), axis=0), np.mean(list(KARIN.values()), axis=0)
    assert g is not None and g["organ_sayisi"] == 6
    assert np.allclose(g["merkez_P"], (on + arka) / 2.0)
    # ürünün KEDI_TV gövde ızgarasının uzun ekseni (ölçüm çerçevesi x–z) organ eksenine PARALEL
    T = oneri.kip_girdisi("KEDI_TV", A, hedef_P=g["merkez_P"], kedi={"merkez_P": g["merkez_P"], "theta": g["theta"]})[
        "T"
    ]
    Tm = backend_to_olcum(np.asarray(T))[:, [0, 2]]
    w, v = np.linalg.eigh(np.cov((Tm - Tm.mean(0)).T))
    ana = v[:, np.argmax(w)]
    a = (backend_to_olcum(arka) - backend_to_olcum(on))[[0, 2]]
    assert abs(float(ana @ a) / np.linalg.norm(a)) > 0.99, (ana, a, g["theta"])
    assert np.allclose(Tm.mean(0), backend_to_olcum(np.asarray(g["merkez_P"]))[[0, 2]], atol=1.0)


@pytest.mark.parametrize(
    "bozma",
    [
        "yalniz_gogus",
        "yalniz_karin",
        "dusuk_guven",
        "kabin_disi",
        "kisa_eksen",
        "bos",
    ],
)
def test_KARSIT_govde_geometrisi_YOKSA_None(bozma):
    from servers.ai_pro_hedef import kedi_govde_geometrisi

    d = _organlar()
    if bozma == "yalniz_gogus":
        d = {k: v for k, v in d.items() if k not in KARIN}
    elif bozma == "yalniz_karin":
        d = {k: v for k, v in d.items() if k not in GOGUS}
    elif bozma == "dusuk_guven":
        d = {k: (_org(GOGUS[k], 0.29) if k in GOGUS else v) for k, v in d.items()}
    elif bozma == "kabin_disi":
        d = {k: (_org((900.0, -150.0, 0.0)) if k in KARIN else v) for k, v in d.items()}
    elif bozma == "kisa_eksen":
        d = {**{k: _org((10.0, -150.0, 5.0)) for k in GOGUS}, **{k: _org((-10.0, -150.0, -5.0)) for k in KARIN}}
    else:
        d = {}
    assert kedi_govde_geometrisi(d) is None


def test_KRITIK_localize_AYNI_karenin_organlarindan_meta_odak_kedi_BAYAT_KALMAZ(monkeypatch):
    from servers import ai_pro_hedef as hedef
    from servers import ai_router as air

    kutu = {"org": _organlar()}
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(air, "_localize_organ_cpu", lambda f, oid: air._extract_organ_target(kutu["org"], oid, None))
    sag = hedef.KediSaglayici()
    sonuc = sag.localize(np.zeros((4, 4, 3), np.uint8), 2)
    assert sonuc[0] is True and sag.odak_kedi_girdisi()["organ_sayisi"] == 6
    assert set(sag.son_lokalizasyon_meta()) <= {"ood"}, "gövde geometrisi veteriner meta'sına sızdı"
    kutu["org"] = {k: v for k, v in _organlar().items() if k not in KARIN}
    sag.localize(np.zeros((4, 4, 3), np.uint8), 2)
    assert sag.odak_kedi_girdisi() is None, "önceki karenin gövdesi bayat kaldı"


class _Kedi:
    ad = "kedi"

    def __init__(self, geo):
        self.geo = geo

    def son_lokalizasyon_meta(self):
        return {"ood": False}

    def odak_kedi_girdisi(self):
        return self.geo


def _plan_kur(monkeypatch, A, tmp_path, kip, geo):
    from servers import ai_pro_hedef as hedef

    from ai_hub.odak import oneri

    kok = _kok_kur(str(tmp_path / "veri_koku"))
    monkeypatch.setattr(hedef, "duzlem_veri_koku", lambda: kok)
    T = oneri.kip_girdisi(
        kip,
        A,
        hedef_P=(geo["merkez_P"] if kip == "KEDI_TV" else list(BOBREK)),
        kedi={"merkez_P": geo["merkez_P"], "theta": geo["theta"]},
    )["T"]
    monkeypatch.setattr(oneri, "model_al", lambda k, **_k: _DogruModel(A, T))


@pytest.mark.parametrize("hedef_id,kip", [(0, "KEDI_TV"), (2, "KEDI_ORGAN")])
def test_KRITIK_kedi_ODAK_plani_doz_TUTAR_ve_kip_dogru(monkeypatch, A, tmp_path, hedef_id, kip):
    from servers import ai_pro_hedef as hedef
    from servers.ai_pro_hedef import kedi_govde_geometrisi

    geo = kedi_govde_geometrisi(_organlar())
    _plan_kur(monkeypatch, A, tmp_path, kip, geo)
    konum = {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0} if hedef_id == 0 else dict(zip(("x_mm", "y_mm", "z_mm"), BOBREK))
    tv = hedef.odak_plani(_Kedi(geo), konum, hedef_id, None)  # doz yok → tavanın %80'i
    assert tv["engel"] is None, tv
    plan = hedef.odak_plani(_Kedi(geo), konum, hedef_id, round(0.5 * tv["tavan_mT"], 2))
    assert plan["engel"] is None and plan["kip"] == kip, plan
    assert plan["beklenen_mT"] == pytest.approx(plan["doz_mT"], rel=0.02)
    assert max(plan["duty"]) <= 0.5 and any(d > 0 for d in plan["duty"])
    assert (plan["cevre_mT"] is None) == (kip == "KEDI_TV")


def test_KRITIK_govde_YOKSA_SURMEZ_engel_kediGovdeYok_EYLEM_iki_dilde(monkeypatch, A, tmp_path):
    from servers import ai_pro_hedef as hedef
    from utils import ceviri

    monkeypatch.setattr(hedef, "duzlem_veri_koku", lambda: _kok_kur(str(tmp_path / "veri_koku")))
    plan = hedef.odak_plani(_Kedi(None), {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0}, 0, 0.3)
    assert plan["engel"] == "kediGovdeYok" and plan["duty"] == [0.0] * 7 and plan["kip"] == "KEDI_TV"
    tr, en = (ceviri.t("ai.pro.odak.engel.kediGovdeYok", dil=d) for d in ("tr", "en"))
    assert "yeniden hesaplayın" in tr and "recalculate" in en and "ai.pro" not in tr + en


def test_KRITIK_kedi_predict_MUHURDE_ODAK_varsa_ODAK_yoksa_eski_yol(monkeypatch):
    from servers import ai_pro_hedef as hedef
    from servers import ai_router as air

    sag = hedef.KediSaglayici()
    cagri = []
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(air, "_predict_and_drive_cpu", lambda *a: cagri.append("hoca") or ([0.4] * 7, [0.0] * 7, 1.0))
    plan = {"engel": None, "duty": [0.1, 0.2, 0.0, 0.0, 0.3, 0.0, 0.25], "faz": [0.0, 36.0, 0.0, 0.0, 180.0, 0.0, 18.0]}
    monkeypatch.setattr(hedef, "odak_plani", lambda *a, **k: cagri.append("odak") or dict(plan))
    hedef.odak_ayarla(sag, {"doz_mT": 0.4, "kip": "KEDI_TV"}, "Tüm Vücut")
    D, P, _ = sag.predict(0.0, 0.0, 0.0, 0)
    assert D == plan["duty"] and P == plan["faz"] and cagri == ["odak"], "mühürlü kedi seansı hoca modeliyle sürdü"
    hedef.odak_ayarla(sag, None)
    D, P, _ = sag.predict(0.0, 0.0, 0.0, 0)
    assert cagri == ["odak", "hoca"] and D == [0.4] * 7


@pytest.fixture
def o(monkeypatch, tmp_path, A):
    from servers import ai_pro_hedef as hedef

    from ai_hub.odak import oneri

    ns = ap.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(ns.air, "ai_service_enabled", lambda: False)
    ns.org = {"v": _organlar()}
    monkeypatch.setattr(
        ns.air, "_localize_organ_cpu", lambda f, oid: ns.air._extract_organ_target(ns.org["v"], oid, None)
    )
    monkeypatch.setattr(ns.air, "_localize_organ", lambda f, oid: hedef.SAGLAYICILAR["kedi"].localize(f, oid))
    monkeypatch.setattr(ns.air, "_ORGAN_LOCALIZE_INTERVAL_S", 0.0)
    kok = _kok_kur(str(tmp_path / "veri_koku"))
    monkeypatch.setattr(hedef, "duzlem_veri_koku", lambda: kok)
    geo = hedef.kedi_govde_geometrisi(_organlar())
    T = oneri.kip_girdisi(
        "KEDI_TV", A, hedef_P=geo["merkez_P"], kedi={"merkez_P": geo["merkez_P"], "theta": geo["theta"]}
    )["T"]
    monkeypatch.setattr(oneri, "model_al", lambda k, **_k: _DogruModel(A, T))
    monkeypatch.setattr(ns.air, "_ai_hedef_modeli", "kedi")
    monkeypatch.setattr(ns.air, "_ai_organ_id", 0)
    monkeypatch.delenv("PEMF_KEDI_AIPRO_SURUS", raising=False)
    from kayitci_donanim import gercek_hc

    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.c.post("/api/ai/pro/stop")
        if getattr(ns, "hc", None) is not None:
            ns.hc.stop_all_coils()
        ns.geri()


def _oner(o, **ek):
    o.air._ai_relocalize = True
    j = ap.kare(o).json()
    assert j.get("detected") is True, j
    return o.c.post("/api/ai/pro/propose", json={"organ_id": 0, "duration_minutes": 5, "model": "kedi", **ek})


def test_KRITIK_kedi_ONERI_ODAK_ONAY_EKRANI_alanlari_SURUS_KAPALI_soyler(o):
    r = _oner(o, doz_mT=0.2)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    od = j["specs"]["odak"]
    assert (
        od["kip"] == "KEDI_TV"
        and od["doz_mT"] == pytest.approx(0.2)
        and od["beklenen_mT"] == pytest.approx(0.2, rel=0.02)
    )
    assert od["tavan_mT"] > 0.2 and od.get("cevre_mT") is None and 0 < od["oran"] <= 1.0
    assert max(j["specs"]["D"]) <= 0.5 and any(d > 0 for d in j["specs"]["D"])
    assert "xaiSensitivity" not in j["meta"], "ODAK önerisinde hoca XAI'si gösterildi"
    assert j["surusAcik"] is False and j["surusKapaliNedeni"], "Y142: onay ekranı sürüşün kapalı olduğunu söylemiyor"
    a = o.c.post("/api/ai/pro/approve", json={"proposal_id": j["proposalId"], "operator_email": "hekim@test.local"})
    assert a.status_code == 409, "Y142: kedi ODAK önerisi onaylanabildi (sürüş kapalıyken)"


def test_KRITIK_kedi_ONERI_govde_YOKSA_409_kediGovdeYok(o):
    o.org["v"] = {k: v for k, v in _organlar().items() if k not in KARIN}
    r = _oner(o, doz_mT=0.2)
    assert r.status_code == 409 and "yeniden hesaplayın" in r.json()["detail"], r.text[:300]
