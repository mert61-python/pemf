# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.95 · B-1.13 · B-1.16 — taşan START parametresi bobin durumunu/deadline'ı DEĞİŞTİRMEZ; uçlar 422 döner.

ÖLÇÜLEN KUSUR (plan d01t21, probe_pack_overflow): `update_coil` süre (`float(duration_seconds)`) ve paket
(`struct.pack`) dönüşümlerini durum YAZILDIKTAN SONRA yapıyordu:
  · `duration_seconds=10**309` → `is_running=True` yazıldı, deadline None kaldı (keep-alive bobini SÜRESİZ
    enerjili tutar — 10 pakette ölçüldü), API 500;
  · duty 4e40 (%) → durum yazıldı; sonraki HER paket — başka bobinin STOP'u ve keep-alive dahil — `OverflowError`
    ile düştü (hayalet 'completed' seans).
Duty ÜST sınırı EKLENMEZ (Ö.4-Y9): yalnız paketin float32 alanına SIĞMAYAN değer reddedilir — karşıt kol pinler.

Kapı GERÇEK `HardwareController` (`kayitci_donanim.gercek_hc`, paketler firmware aynasıyla çözülür) ve GERÇEK uçlarla.
"""

from __future__ import annotations

import pytest
from topoloji import TUM_STM

_B1, _B2 = sorted(TUM_STM)[:2]
_COK_UZUN_SN = 10**309  # float'a çevrilemez (OverflowError)
_TASAN_DUTY = 4e40  # % → oran 4e38 > float32 azamisi (~3,4e38)


def _paketler(hc):
    return list(hc.core._hw_send_queue.paketler)


def _coz(p):
    from kayitci_donanim import paket_coz

    return paket_coz(p)


@pytest.fixture
def hc_ortam(monkeypatch):
    from kayitci_donanim import gercek_hc
    from servers import api_server as api

    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    monkeypatch.setattr(api, "_begin_coil_run", lambda *a, **k: None)
    monkeypatch.setattr(api, "_finish_coil_run", lambda *a, **k: None)
    monkeypatch.setitem(api._active_session, "is_active", False)
    with gercek_hc() as hc:
        monkeypatch.setattr(api.state, "hardware", hc)
        monkeypatch.setattr(api.state, "core", hc.core)
        assert hc.update_coil(_B1, 100.0, 30.0, 0.0, 1, start=True) is True  # önceden sürülen, TUTARLI durum
        yield api, hc


@pytest.mark.parametrize(
    "tasma",
    [
        {"duty": 50.0, "duration_seconds": _COK_UZUN_SN},
        {"duty": _TASAN_DUTY, "duration_seconds": None},
    ],
    ids=["sure_10e309", "duty_4e40"],
)
def test_KRITIK_tasan_parametre_durumu_ve_deadlinei_DEGISTIRMEZ_sonraki_STOP_gider(hc_ortam, tasma):
    _api, hc = hc_ortam
    with hc._state_lock:
        once_durum = {i: dict(s) for i, s in hc.coils_state.items()}
        once_deadline = dict(hc._coil_deadline)
    paket_once = len(_paketler(hc))
    sonuc = hc.update_coil(_B2, 100.0, tasma["duty"], 0.0, 5, start=True, duration_seconds=tasma["duration_seconds"])
    assert sonuc is False, "tasan parametre 'kabul' edildi"
    with hc._state_lock:
        assert {i: dict(s) for i, s in hc.coils_state.items()} == once_durum, "tasan parametre bobin DURUMUNU yazdi"
        assert dict(hc._coil_deadline) == once_deadline, "tasan parametre deadline'i degistirdi (sure kapagi kayboldu)"
    assert len(_paketler(hc)) == paket_once, "tasan parametre donanim kuyruguna paket koydu"
    # Sonraki STOP (BAŞKA bobin) paketlenebilmeli — eskiden her paket OverflowError ile düşüyordu.
    assert hc.update_coil(_B2, 0, 0, 0, 0, start=False) is True
    duty = _coz(_paketler(hc)[-1])[0]
    assert duty[_B2 - 1] == 0.0 and duty[_B1 - 1] == pytest.approx(0.30), f"sonraki paket bozuk: {duty}"
    assert hc.stop_all_coils() is True and all(d == 0.0 for d in _coz(_paketler(hc)[-1])[0])


def test_KRITIK_start_all_tasan_duty_HICBIR_bobini_yazmaz(hc_ortam):
    _api, hc = hc_ortam
    with hc._state_lock:
        once = {i: dict(s) for i, s in hc.coils_state.items()}
    assert hc.start_all_coils(100.0, _TASAN_DUTY, 0.0, 5) is False
    with hc._state_lock:
        assert {i: dict(s) for i, s in hc.coils_state.items()} == once, "start_all tasan duty'de durumu yazdi"
    assert hc.stop_all_coils() is True, "start_all tasmasindan sonra STOP paketlenemedi"


@pytest.mark.parametrize(
    "uc,govde",
    [
        ("tekil", {"start": True, "freq": 100, "duty": _TASAN_DUTY, "phase": 0, "duration": 60}),
        ("tekil", {"start": True, "freq": 100, "duty": 30, "phase": 0, "duration": _COK_UZUN_SN}),
        ("batch", {"start": True, "freq": 100, "duty": _TASAN_DUTY, "phase": 0, "duration": 60}),
        ("seans", {"frequency": 100, "duty": _TASAN_DUTY, "phase": 0, "duration_minutes": 5}),
    ],
    ids=["tekil_duty", "tekil_sure", "batch_duty", "seans_duty"],
)
def test_KRITIK_uclar_tasan_girdiyi_422_ile_reddeder_ve_hicbir_sey_SURULMEZ(hc_ortam, uc, govde):
    from fastapi.testclient import TestClient

    api, hc = hc_ortam
    paket_once = len(_paketler(hc))
    c = TestClient(api.app, raise_server_exceptions=False)
    if uc == "tekil":
        r = c.post(f"/api/coil/{_B2}/control", json=govde)
    elif uc == "batch":
        r = c.post("/api/coil/batch", json={"coil_ids": [_B2], **govde})
    else:
        r = c.post("/api/session/start", json={"mode": "Manuel", "coil_ids": [_B2], "patient_name": "Pamuk", **govde})
    assert r.status_code == 422, f"{uc}: tasan girdi {r.status_code} dondu (422 beklenir): {r.text[:200]}"
    assert "1e+40" not in r.text and "4e+40" not in r.text and "0" * 50 not in r.text, "422 zarfi ham girdiyi tasiyor"
    assert len(_paketler(hc)) == paket_once, f"{uc}: tasan girdide donanima paket gitti"
    assert hc.coils_state[_B2]["is_running"] is False
    with api._session_lock:
        assert api._active_session.get("is_active") is not True, f"{uc}: tasan girdide seans acildi"


def test_KARSIT_duty_UST_SINIRI_EKLENMEDI_float32ye_sigan_deger_SURULUR_Y9(hc_ortam):
    """Ö.4-Y9 / Y20: backend'e duty tavanı EKLENMEZ — %300 ve float32'ye sığan 3e40 % kabul edilir ve pakete gider."""
    _api, hc = hc_ortam
    assert hc.update_coil(_B2, 100.0, 300.0, 0.0, 1, start=True) is True
    assert _coz(_paketler(hc)[-1])[0][_B2 - 1] == pytest.approx(3.0), "duty %300 kirpildi (Y9: tavan YOK)"
    assert hc.update_coil(_B2, 100.0, 3e40, 0.0, 1, start=True) is True, "float32'ye SIGAN duty reddedildi"
    assert hc.update_coil(_B2, 0, 0, 0, 0, start=False) is True
