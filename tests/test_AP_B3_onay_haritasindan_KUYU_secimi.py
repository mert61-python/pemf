# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AP · B3 + AP-20 (istem 48, tezgâh 13 Kasım 2026): onay penceresinde (KUYUCUK) kuyu haritasından hedef seçilebilir.
  · `/ai/pro/propose` `kuyu` ("C6"): AYNI lokalizasyonun adaylarından plan; mühür o kuyunun KALICI kimliği + etiketi + konumu (görülen =
    sürülen); otomatik seçim işareti YOK.
  · kamerada sıvı görülmeyen (boş) kuyu aday değildir → 409 `kuyuYok` (ODK11: boş kuyu hedef OLAMAZ).
  · AP-20: yeniden hesap önizlemenin lokalize ettiği hedefle (otomatikte 0) istenir → tazelik geçer (mühürdeki kimlikle 409 veriyordu).
ODAK planı sahtelenir (bu dosyanın konusu hedef / mühür; fizik `test_ODK_*`)."""

import time

import pytest
from fastapi.testclient import TestClient

C2 = {"id": 7, "label": "Kuyu C2", "x": 10.0, "y": -150.0, "z": 20.0, "reliability": 0.95, "pxn": [0.3, 0.5]}
C6 = {"id": 11, "label": "Kuyu C6", "x": 60.0, "y": -150.0, "z": 25.0, "reliability": 0.9, "pxn": [0.6, 0.5]}


@pytest.fixture()
def o(monkeypatch):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air
    import servers.api_server as apis

    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    monkeypatch.setattr(hedef, "duzlem_surus_engeli", lambda _s: None)
    planlar = []

    def _plan(sag, konum, hedef_id, doz, kip="", frek=None):
        planlar.append({"hedef_id": hedef_id, "etiket": konum.get("target_label"), "kip": kip})
        return {
            "kip": kip or "KUYUCUK",
            "doz_mT": 0.6,
            "tavan_mT": 1.2,
            "duty": [0.2] * 7,
            "faz": [0.0] * 7,
            "frek_hz": 100.0,
        }

    monkeypatch.setattr(hedef, "odak_plani", _plan)
    snap = dict(air._ai_organ_cache)
    air._ai_organ_cache.update(
        {
            "localized": True,
            "organ_id": 0,  # önizleme OTOMATİK hedefle lokalize etti
            "model": "petri",
            "at": time.time(),
            "x_mm": C2["x"],
            "y_mm": C2["y"],
            "z_mm": C2["z"],
            "reliability": 0.95,
            "kosulsuz": False,
            "targets": [C2, C6],
            "secili_id": 7,
            "target_label": "Kuyu C2",
        }
    )
    yield TestClient(apis.app), planlar
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap)


def _oner(c, **ek):
    return c.post("/api/ai/pro/propose", json={"organ_id": 0, "model": "petri", "duration_minutes": 5, **ek})


def test_KRITIK_B3_haritadan_secilen_kuyu_MUHURE_kimligi_etiketi_konumuyla_yazilir(o):
    c, planlar = o
    r = _oner(c, kuyu="c6", odak_kip="KUYUCUK", doz_mT=0.6)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["specs"]["organ_id"] == 11 and j["specs"]["target_label"] == "Kuyu C6"
    assert (j["meta"]["x_mm"], j["meta"]["z_mm"]) == (60.0, 25.0)
    assert not j["meta"].get("otomatik_secim")
    assert planlar[-1]["etiket"] == "Kuyu C6"


def test_KRITIK_B3_bos_ya_da_gorulmeyen_kuyu_hedef_OLAMAZ_409_kuyuYok(o):
    c, _ = o
    r = _oner(c, kuyu="B1", odak_kip="KUYUCUK")
    assert r.status_code == 409
    assert "B1" in r.json()["detail"]


def test_AP20_otomatik_onerinin_YENIDEN_HESABI_ayni_hedefle_TAZE(o):
    c, _ = o
    ilk = _oner(c)
    assert ilk.status_code == 200 and ilk.json()["specs"]["organ_id"] == 7 and ilk.json()["meta"].get("otomatik_secim")
    assert _oner(c, doz_mT=0.5).status_code == 200  # panel artık önizlemenin hedefiyle (0) ister
    # Mühürdeki kimlikle (eski panel davranışı) istemek tazelik denetiminde 409 — panel bunu göndermemeli.
    eski = c.post("/api/ai/pro/propose", json={"organ_id": 7, "model": "petri", "doz_mT": 0.5})
    assert eski.status_code == 409


def test_kuyu_alani_PETRI_DISINDA_yok_sayilir(o, monkeypatch):
    import servers.ai_router as air

    c, _ = o
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO_FANTOM", "1")  # ODAK planı sahte — Y283 engeli bu dosyanın konusu değil
    air._ai_organ_cache["model"] = "fantom"
    air._ai_organ_cache["targets"] = [{"id": 3, "label": "Tümör T1", "x": 1.0, "y": -150.0, "z": 2.0}]
    air._ai_organ_cache["secili_id"] = 3
    r = c.post("/api/ai/pro/propose", json={"organ_id": 0, "model": "fantom", "kuyu": "C6"})
    assert r.status_code == 200, r.text
    assert r.json()["specs"]["organ_id"] == 3
