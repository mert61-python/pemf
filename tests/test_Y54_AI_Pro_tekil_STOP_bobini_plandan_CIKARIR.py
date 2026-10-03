# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y54 (sahip, İNCELEME-2 i1-F-2) — AI Pro sürerken tek bir bobine verilen STOP, o bobini SEANS SONUNA KADAR AI Pro planından
çıkarır; AI Pro onu bir sonraki karede yeniden çalıştıramaz; ekranda "Bobin X AI Pro planından çıkarıldı" yazar. STOP'un
kendisi kapılanmaz (Ö.4-Y8); bu karar yalnız otomasyonun yeniden START'ını engeller.

ÖLÇÜLEN KUSUR (İNCELEME-2 S5): AI Pro sürerken `/api/coil/{id}/control start:false` bir sonraki AI Pro karesinde (≤ 1 sn)
geri alınıyordu — bobin yeniden enerjileniyordu (bobin 2'de önceden var, 6-7'ye D1.83 ile genişledi).

Kapı: GERÇEK onay akışı (öner → hekim onayı → `/api/ai/pro/start`) + GERÇEK `/api/ai/ai_pro/frame` + GERÇEK
`HardwareController` (kayıtçı kuyruk, firmware aynası); sahte olan: görüntü, lokalizasyon, doz modeli (aparat).
"""

from __future__ import annotations

import ai_pro_aparati as ap
import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.c.post("/api/ai/pro/stop")
        if ns.hc is not None:
            ns.hc.stop_all_coils()
        ns.geri()


def _ai_pro_suruyor(o) -> None:
    _pid, r = ap.onayli_baslat(o, sure_dk=5)
    assert r.status_code == 200, f"aparat: AI Pro baslamadi {r.status_code} {r.text[:200]}"
    k = ap.kare(o)
    assert k.status_code == 200, k.text[:200]
    assert sorted(ap.calisan(o)) == [1, 2, 3, 4, 5, 6, 7], f"aparat: AI Pro 7 bobini surmuyor {ap.calisan(o)}"


@pytest.mark.parametrize("bobin", [2, 6])
def test_KRITIK_tekil_STOP_bobini_AI_Pro_planindan_cikarir_sonraki_kare_SURMEZ(o, bobin):
    _ai_pro_suruyor(o)
    r = o.c.post(f"/api/coil/{bobin}/control", json={"freq": 0, "duty": 0, "phase": 0, "duration": 0, "start": False})
    assert r.status_code == 200 and r.json().get("status") == "success", f"tekil STOP reddedildi/kapilandi: {r.text}"
    assert bobin not in ap.calisan(o), "aparat: tekil STOP bobini durdurmadi"
    for _ in range(3):
        k = ap.kare(o)
        assert k.status_code == 200
    assert bobin not in ap.calisan(o), f"AI Pro tekil STOP'u sonraki karede GERI ALDI (bobin {bobin} yeniden suruluyor)"
    diger = [b for b in range(1, 8) if b != bobin]
    assert sorted(ap.calisan(o)) == diger, f"diger bobinler surmeye devam etmeli: {ap.calisan(o)}"
    per = {c["id"]: c for c in k.json().get("perCoil", [])}
    assert per.get(bobin, {}).get("planDisi") is True and per[bobin].get("suruldu") is False, per.get(bobin)
    assert any(f"Bobin {bobin} AI Pro planından çıkarıldı" in m for m, _t in o.bildirim), o.bildirim


def test_KRITIK_komut_ucu_stop_coil_da_plandan_cikarir(o):
    _ai_pro_suruyor(o)
    o.c.post("/api/hardware/command", json={"command": "stop_coil", "params": {"coil_id": 3}})
    ap.kare(o)
    assert 3 not in ap.calisan(o), "legacy stop_coil sonrasi AI Pro bobini yeniden surdu"


def test_KARSIT_yeni_AI_Pro_seansi_plandisi_listesini_TASIMAZ(o):
    _ai_pro_suruyor(o)
    o.c.post("/api/coil/4/control", json={"freq": 0, "duty": 0, "phase": 0, "duration": 0, "start": False})
    assert o.c.post("/api/ai/pro/stop").status_code == 200
    ap.mandali_sifirla(o.c)
    _ai_pro_suruyor(o)  # yeni seans: 7 bobin yine sürülür
    assert 4 in ap.calisan(o)
    # Yeni seansta BAŞKA bir bobin durdurulunca önceki seansın plan dışı bobini (4) TAŞINMAZ (küme onaya bağlı).
    o.c.post("/api/coil/5/control", json={"freq": 0, "duty": 0, "phase": 0, "duration": 0, "start": False})
    per = {c["id"]: c for c in ap.kare(o).json().get("perCoil", [])}
    # `calisan` yetmez: dışlanan bobin önceki komutla telde çalışmaya devam eder — BU karede sürülüp sürülmediğine bakılır.
    assert per[4].get("planDisi") is not True and per[4].get("suruldu") is True, (
        f"onceki seansin plan disi bobini tasindi: {per[4]}"
    )
    assert per[5].get("planDisi") is True and 5 not in ap.calisan(o)


def test_KARSIT_AI_Pro_YOKKEN_tekil_STOP_hicbir_seyi_plandan_cikarmaz(o):
    r = o.c.post("/api/coil/2/control", json={"freq": 0, "duty": 0, "phase": 0, "duration": 0, "start": False})
    assert r.status_code == 200
    assert not o.air._ai_pro_plan_disi_bobinler(), "AI Pro yokken plan disi listesi doldu"
