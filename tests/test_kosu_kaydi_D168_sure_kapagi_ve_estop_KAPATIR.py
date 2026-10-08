# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.68 · B-1.6 — bobin koşu kaydı (doz kaydı) fiziksel sürüşle aynı anda kapanmalı.

ÖLÇÜLEN KUSURLAR (f870777):
  * Yazılım süre kapağı (`HardwareController._tick`) bobini durdurduğunda koşu kaydı AÇIK kalıyordu; seans sonunda
    (ör. 20. dk) kapanıyordu → 60 sn sürülen bobin kayıtta seans boyu "sürüldü" (kaydedilen ≠ uygulanan).
  * Acil durdurma yalnız SEANSIN bobin listesindeki koşuları kapatıyordu; `stop_all_coils` ise TÜM bobinleri durdurur →
    seans sırasında tekil başlatılmış kapsam dışı bobinin koşusu `ended_epoch=NULL` kalıcı kalıyordu.
  * Yeni seans başlatma koşu haritasını `end_coil_run` ÇAĞIRMADAN siliyordu → önceki seanstan açık kalan koşu NULL kalıcı.

KAPI: GERÇEK `HardwareController` (kayıtçı kuyruk) + GERÇEK `coil_run_tracker` + geçici `TreatmentHistoryDB` + GERÇEK
API uçları. Saat yalnız `hardware_controller` ve `coil_run_tracker` modüllerinde ileri alınır (süreç geneli saat değişmez).
⚠️ Kanca keep-alive iş parçacığını BEKLETMEMELİ (DB yavaşsa firmware ölü-adamı 1,5 sn'de keser): ayrı kol ölçer.
"""

from __future__ import annotations

import threading
import time
import types

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
        ns.geri()


def _seans(o, bobinler, sure_dk=20):
    r = o.c.post(
        "/api/session/start",
        json={
            "mode": "Manuel",
            "frequency": 100,
            "duty": 40,
            "phase": 0,
            "duration_minutes": sure_dk,
            "coil_ids": bobinler,
        },
    )
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:300]
    sid = o.api._active_session.get("db_session_id")
    assert sid, "aparat: seans DB satırı açılmadı"
    return sid


def _tekil(o, bobin, sure_s):
    r = o.c.post(
        f"/api/coil/{bobin}/control", json={"start": True, "freq": 100, "duty": 40, "phase": 0, "duration": sure_s}
    )
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:300]


def _kosu(o, sid, bobin):
    kosular = [k for k in o.db.get_session_coil_runs(sid) if int(k["coil_id"]) == bobin]
    assert kosular, f"aparat: bobin {bobin} için koşu kaydı açılmadı"
    return kosular[-1]


def _saati_ilerlet(monkeypatch, saniye):
    from controllers import hardware_controller as hcm
    from servers import coil_run_tracker as crt

    gercek = time
    monkeypatch.setattr(
        hcm,
        "time",
        types.SimpleNamespace(monotonic=lambda: gercek.monotonic() + saniye, sleep=gercek.sleep, time=gercek.time),
    )
    # D2.40 (B-1.31): koşu süresi artık MONOTONİK saatten — benzetilen ilerleme iki saati de ilerletir (yalnız duvar saati
    # ilerletilirse koşucu `time.monotonic`ı bulamaz ve bitiş best-effort yutulurdu).
    monkeypatch.setattr(
        crt,
        "time",
        types.SimpleNamespace(time=lambda: gercek.time() + saniye, monotonic=lambda: gercek.monotonic() + saniye),
    )


def test_KRITIK_sure_kapagi_bobini_durdurunca_KOSU_KAYDI_da_kapanir_sure_UYGULANANDIR(o, monkeypatch):
    sid = _seans(o, [1])
    _tekil(o, 2, 60)
    assert o.hc.coils_state[2]["is_running"], "aparat: bobin 2 sürülmedi"
    _saati_ilerlet(monkeypatch, 61)
    o.hc._tick()
    assert not o.hc.coils_state[2]["is_running"], "aparat: süre kapağı bobini durdurmadı"
    ap.bekle(lambda: _kosu(o, sid, 2)["ended_epoch"] is not None, 5)
    k = _kosu(o, sid, 2)
    assert k["ended_epoch"] is not None, (
        "süre kapağı bobini DURDURDU ama koşu kaydı AÇIK — kayıt seans sonuna dek 'sürüldü' der (kaydedilen ≠ uygulanan)"
    )
    assert abs(float(k["duration_seconds"]) - 60.0) <= 3.0, f"koşu süresi {k['duration_seconds']} sn (uygulanan 60 sn)"
    assert _kosu(o, sid, 1)["ended_epoch"] is None, "süresi dolmayan seans bobininin koşusu da kapandı"


def test_KRITIK_sure_kapagi_kancasi_KEEPALIVE_is_parcacigini_BEKLETMEZ(o, monkeypatch):
    """Kayıt kapatma yavaşsa (DB kilidi, VACUUM 2–2,6 sn ölçülmüş) `_tick` onu beklememeli: keep-alive paketleri
    gecikirse firmware ölü-adamı (1,5 sn) seansın DİĞER bobinlerini de keser."""
    from servers import coil_run_tracker as crt

    _seans(o, [1])
    _tekil(o, 2, 60)
    serbest = threading.Event()
    gercek_bitir = crt._finish_coil_run

    def _yavas(*a, **kw):
        serbest.wait(10)
        return gercek_bitir(*a, **kw)

    monkeypatch.setattr(crt, "_finish_coil_run", _yavas)
    for mod in (o.api,):
        if hasattr(mod, "_finish_coil_run"):
            monkeypatch.setattr(mod, "_finish_coil_run", _yavas)
    _saati_ilerlet(monkeypatch, 61)
    t0 = time.monotonic()
    try:
        o.hc._tick()
        gecen = time.monotonic() - t0
    finally:
        serbest.set()
    assert gecen < 0.5, f"süre kapağı kancası keep-alive turunu {gecen:.2f} sn BEKLETTİ (ölü-adam 1,5 sn)"


def test_KRITIK_sure_kancasi_GECIKSE_de_araya_giren_YENI_kosuyu_KAPATMAZ(o, monkeypatch):
    """Yarış ZORLANIR: süre kapağı kancasının kayıt iş parçacığı bekletilir, bu arada aynı bobine yeni START (yeni koşu)
    girer; kanca sonra koşunca YALNIZ süresi dolan (eski) koşuyu kapatmalı — yeni koşu açık kalır."""
    sid = _seans(o, [1])
    _tekil(o, 2, 60)
    eski = _kosu(o, sid, 2)["id"]
    girdi, serbest, bitti = threading.Event(), threading.Event(), threading.Event()
    gercek = o.api._finish_coil_run

    def _geciken(*a, **kw):
        girdi.set()
        serbest.wait(10)
        try:
            return gercek(*a, **kw)
        finally:
            bitti.set()

    monkeypatch.setattr(o.api, "_finish_coil_run", _geciken)
    _saati_ilerlet(monkeypatch, 61)
    o.hc._tick()
    assert girdi.wait(5), "aparat: süre kapağı kancası kayıt kapatmayı denemedi"
    _tekil(o, 2, 600)  # aynı bobine YENİ başlatma → yeni koşu
    yeni = _kosu(o, sid, 2)["id"]
    assert yeni != eski
    serbest.set()
    assert bitti.wait(5)
    kosular = {k["id"]: k for k in o.db.get_session_coil_runs(sid)}
    assert kosular[eski]["ended_epoch"] is not None, "süresi dolan koşu kapanmadı"
    assert kosular[yeni]["ended_epoch"] is None, (
        "geciken süre kapağı kancası araya giren YENİ koşuyu kapattı — sürülen bobin kayıtta 'durdu'"
    )


def test_KRITIK_ACIL_DURDUR_seans_DISI_tekil_bobinin_kosusunu_da_KAPATIR(o):
    sid = _seans(o, [1])
    _tekil(o, 3, 600)
    assert _kosu(o, sid, 3)["ended_epoch"] is None
    r = o.c.post("/api/hardware/emergency_stop")
    assert r.status_code == 200
    assert not any(s["is_running"] for s in o.hc.coils_state.values()), "aparat: E-stop bobinleri durdurmadı"
    k = _kosu(o, sid, 3)
    assert k["ended_epoch"] is not None, (
        "ACİL DURDUR tüm bobinleri durdurdu ama seans DIŞI bobin 3'ün koşusu AÇIK kaldı (ended_epoch NULL kalıcı)"
    )


def test_KRITIK_yeni_seans_ONCEKI_acik_kosuyu_KAPATMADAN_silmez(o):
    sid_a = _seans(o, [1])
    _tekil(o, 3, 600)
    assert o.c.post("/api/session/stop").status_code == 200
    _seans(o, [2])
    k = _kosu(o, sid_a, 3)
    assert k["ended_epoch"] is not None, (
        "yeni seans önceki seansın açık koşusunu end_coil_run ÇAĞIRMADAN haritadan sildi — ended_epoch NULL kalıcı"
    )
