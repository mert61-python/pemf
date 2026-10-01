# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.99 · B-1.9 · S-1.2 · S-1.6 — kart, koşu kaydı ve değişiklik kaydı donanıma GİDEN (normalize) değeri yazar;
API float alanları NaN/Infinity'yi 422 ile reddeder.

ÖLÇÜLEN KUSUR (plan tv-F6_3, tv-F5_4, v-A26): 30000 Hz istenip 25000 sürülüyor, kayıt 30000 diyordu; 0,5 Hz → 1 Hz
sürülüp kayıt 0,5; duty −50 → uygulanan 0, kayıt −50. `{"freq": Infinity}` 200 alıp koşu kaydına inf yazıyor
(detay ucu kalıcı 500), NaN seans boyunca WS'i bozuyordu. Kaydedilen ≠ uygulanan doz.
Protokol sınırı (`normalize_*`) TAŞIYICIDIR ve KALIR (Ö.4-Y9): kapı kayıt ile TELDEKİ paketin eşitliğini ölçer.

Kapı GERÇEK `HardwareController` (`kayitci_donanim.gercek_hc`; paket firmware aynasıyla çözülür) + GERÇEK uçlar +
tmp `TreatmentHistoryDB` (koşu kaydı GERÇEK `coil_run_tracker` ile yazılır). Ölçüt: çözülen paketteki freq/duty ==
`session_coil_runs` satırı == `activeTreatment.frequencyHz` == `degisiklik_frekans_hz`.
"""

from __future__ import annotations

import json

import pytest
from topoloji import TUM_STM

_B1, _B2 = sorted(TUM_STM)[:2]


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import coil_run_tracker

    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(coil_run_tracker, "_treatment_db_getter", lambda: db)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    import database.treatment_history_db as thdb

    monkeypatch.setattr(thdb, "get_treatment_db", lambda *_a, **_k: db)  # parametre_guncelle aynı DB'ye yazsın
    with api._session_lock:
        eski = dict(api._active_session)
    with gercek_hc() as hc:
        monkeypatch.setattr(api.state, "hardware", hc)
        monkeypatch.setattr(api.state, "core", hc.core)
        c = TestClient(api.app)
        try:
            yield api, hc, db, c
        finally:
            c.post("/api/session/stop")
            with api._session_lock:
                api._active_session.clear()
                api._active_session.update(eski)


def _paket(hc):
    from kayitci_donanim import paket_coz

    duty, _faz, freq, *_ = paket_coz(hc.core._hw_send_queue.paketler[-1])
    return duty, freq


def _kosular(db, sid):
    with db._get_connection() as conn:
        return conn.execute(
            "SELECT coil_id, frequency_hz, duty_percent FROM session_coil_runs WHERE session_id=? ORDER BY id", (sid,)
        ).fetchall()


def _seans(c, frekans, duty):
    r = c.post(
        "/api/session/start",
        json={
            "mode": "Manuel",
            "frequency": frekans,
            "duty": duty,
            "phase": 0,
            "duration_minutes": 5,
            "coil_ids": [_B1],
            "patient_name": "Pamuk",
        },
    )
    assert r.status_code == 200, f"seans baslamadi: {r.status_code} {r.text[:200]}"


def test_KRITIK_seans_kosu_kaydi_ve_KART_teldeki_degeri_yazar(ortam):
    api, hc, db, c = ortam
    _seans(c, 30000, -50)
    duty, freq = _paket(hc)
    with api._session_lock:
        sid = api._active_session.get("db_session_id")
    kosu = [k for k in _kosular(db, sid) if k[0] == _B1]
    assert kosu, "aparat: seans kosu kaydi acmadi"
    assert freq[_B1 - 1] == pytest.approx(25000.0), f"aparat: protokol siniri (Y9) beklenmedik: {freq[_B1 - 1]}"
    assert kosu[-1][1] == pytest.approx(freq[_B1 - 1]), f"kosu kaydi {kosu[-1][1]} Hz, telde {freq[_B1 - 1]} Hz"
    assert kosu[-1][2] == pytest.approx(duty[_B1 - 1] * 100.0), f"kosu kaydi duty {kosu[-1][2]}, telde {duty[_B1 - 1]}"
    with api._live_state_lock:
        kart = api._live_state["activeTreatment"]["frequencyHz"]
    assert kart == pytest.approx(freq[_B1 - 1]), f"seans karti {kart} Hz, telde {freq[_B1 - 1]} Hz"


@pytest.mark.parametrize("uc", ["tekil", "batch"])
def test_KRITIK_tekil_ve_batch_kosu_kaydi_teldeki_degeri_yazar(ortam, uc):
    api, hc, db, c = ortam
    _seans(c, 100, 30)
    with api._session_lock:
        sid = api._active_session.get("db_session_id")
    govde = {"start": True, "freq": 0.5 if uc == "tekil" else 30000, "duty": -50, "phase": 0, "duration": 60}
    if uc == "tekil":
        r = c.post(f"/api/coil/{_B2}/control", json=govde)
    else:
        r = c.post("/api/coil/batch", json={"coil_ids": [_B2], **govde})
    assert r.status_code == 200, r.text[:200]
    duty, freq = _paket(hc)
    kosu = [k for k in _kosular(db, sid) if k[0] == _B2]
    assert kosu, f"aparat: {uc} kosu kaydi acmadi"
    assert kosu[-1][1] == pytest.approx(freq[_B2 - 1]), f"{uc}: kayit {kosu[-1][1]} Hz, telde {freq[_B2 - 1]} Hz"
    assert kosu[-1][2] == pytest.approx(duty[_B2 - 1] * 100.0), f"{uc}: kayit duty {kosu[-1][2]}, telde {duty[_B2 - 1]}"


def test_KRITIK_parametre_guncelle_KART_ve_DEGISIKLIK_kaydi_teldeki_degeri_yazar(ortam):
    api, hc, db, c = ortam
    _seans(c, 100, 30)
    with api._session_lock:
        sid = api._active_session.get("db_session_id")
    # Arayüz yeni parametreyi bobinlere batch ile, kayda parametre_guncelle ile gönderir.
    assert (
        c.post("/api/coil/batch", json={"coil_ids": [_B1], "start": True, "freq": 30000, "duty": -50}).status_code
        == 200
    )
    duty, freq = _paket(hc)
    r = c.post("/api/session/parametre_guncelle", json={"frequency": 30000, "duty": -50, "coil_ids": [_B1]})
    assert r.status_code == 200 and r.json().get("kayda_yazildi") is True, r.text[:200]
    with api._live_state_lock:
        kart = api._live_state["activeTreatment"]["frequencyHz"]
    assert kart == pytest.approx(freq[_B1 - 1]), f"kart {kart} Hz, telde {freq[_B1 - 1]} Hz"
    with db._get_connection() as conn:
        satirlar = dict(
            conn.execute(
                "SELECT parameter_name, parameter_value FROM session_parameters WHERE session_id=? AND parameter_name LIKE 'degisiklik_%'",
                (sid,),
            ).fetchall()
        )
    f_kayit = [float(v) for k, v in satirlar.items() if k.startswith("degisiklik_frekans_hz@")]
    d_kayit = [float(v) for k, v in satirlar.items() if k.startswith("degisiklik_duty_yuzde@")]
    assert f_kayit and f_kayit[-1] == pytest.approx(freq[_B1 - 1]), (
        f"degisiklik_frekans {f_kayit}, telde {freq[_B1 - 1]}"
    )
    assert d_kayit and d_kayit[-1] == pytest.approx(duty[_B1 - 1] * 100.0), f"degisiklik_duty {d_kayit}, telde {duty}"


@pytest.mark.parametrize("deger", [float("inf"), float("-inf"), float("nan")], ids=["Infinity", "-Infinity", "NaN"])
@pytest.mark.parametrize("uc", ["tekil", "batch", "seans", "parametre_guncelle"])
def test_KRITIK_sonlu_olmayan_float_422_ve_WS_bozulmaz(ortam, uc, deger):
    api, hc, _db, c = ortam
    if uc == "parametre_guncelle":
        _seans(c, 100, 30)
    paket_once = len(hc.core._hw_send_queue.paketler)

    def _ham(yol, govde):
        # ⚠️ `json=` KULLANILMAZ: httpx sonlu olmayan sayıyı İSTEMCİDE reddeder (istek sunucuya hiç gitmez — ilk
        # taslakta 12 sahte kırmızı). Ham gövde Python `json.dumps`'un `Infinity`/`NaN` belirteçlerini taşır;
        # Starlette `json.loads` onları float'a çevirir — sahada bozuk bir istemcinin göndereceği gövdenin AYNISI.
        return c.post(yol, content=json.dumps(govde).encode(), headers={"Content-Type": "application/json"})

    if uc == "tekil":
        r = _ham(f"/api/coil/{_B2}/control", {"start": True, "freq": deger, "duty": 30})
    elif uc == "batch":
        r = _ham("/api/coil/batch", {"coil_ids": [_B2], "start": True, "freq": 100, "duty": deger})
    elif uc == "seans":
        r = _ham("/api/session/start", {"mode": "Manuel", "frequency": deger, "coil_ids": [_B2], "patient_name": "P"})
    else:
        r = _ham("/api/session/parametre_guncelle", {"frequency": deger})
    assert r.status_code == 422, f"{uc}: {deger} {r.status_code} dondu (422 beklenir): {r.text[:200]}"
    if uc != "parametre_guncelle":
        assert len(hc.core._hw_send_queue.paketler) == paket_once, f"{uc}: sonlu olmayan girdide paket gitti"
    from servers import live_state

    json.dumps(live_state._build_ws_snapshot(), allow_nan=False)  # NaN/inf WS anlık görüntüsüne SIZMADI
