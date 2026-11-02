# Author: mertaygn, cglrgrkn
"""KP-1 · apps/backend/servers/api_server.py · sözleşmeler: `/api/session/start` — DB açılış nedeni (göç) 503 ayrıntısında;
güncelleme sürerken 409, güncelleme yöneticisi sorgusu patlarsa başlatma sürer; başlangıç kaydının yan yazımları (hasta
dokunuşu, hasta özeti, hasta aynası, seans meta, sahip e-postası, denetim ref'i) patlasa da seans 200 başlar ve DB satırı
açılır; önceki seanstan kalan açık koşu kapatılamasa da başlar; canlı E bağlamı ve seans alan kaydı açılamasa da başlar;
hasta kaydı beklenmedik biçimdeyse canlı hasta özeti adla kurulur.

Aparat: `ai_pro_aparati.kur` (gerçek `TreatmentHistoryDB` tmp'de, MQTT yayını kaydedici) + `kayitci_donanim.gercek_hc`
(gerçek HardwareController, kayıtçı seri kuyruk). Sahte EN ALT katta: hasta DB'si (`get_patient_database`, arıza
`sqlite3.OperationalError`), tedavi DB'sinin tek tek yöntemleri (aynı arıza), güncelleme yöneticisi sorgusu, kayıt kuyruğu.
"""

from __future__ import annotations

import logging
import sqlite3
import types

import ai_pro_aparati as ap
import pytest
from topoloji import STM_BOBIN

GOVDE = {"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 20, "coil_ids": [STM_BOBIN]}


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc
    from servers import api_server as _api0

    gercek_hazir = _api0._kayit_db_hazir  # aparat "hep hazır" yamasından ÖNCE
    ns = ap.kur(monkeypatch, tmp_path)
    ns.gercek_hazir = gercek_hazir
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            try:
                yield ns
            finally:
                if ns.api._active_session.get("is_active"):
                    ns.c.post("/api/session/stop")
                ns.c.close()
    finally:
        ns.geri()


def _patlayan(hata):
    def _f(*_a, **_k):
        raise hata

    return _f


def _log(caplog):
    return [r.getMessage() for r in caplog.records]


def _t(anahtar, **k):
    from utils import ceviri

    return ceviri.t(anahtar, dil="tr", **k)


def _seans_satiri(o, sid):
    with o.db._get_connection() as conn:
        return conn.execute("SELECT session_status FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()


def test_DB_hazir_degil_ACILIS_nedeni_ayrintida_503(o, monkeypatch):
    """Tedavi DB'si açılışta göç nedeniyle açılamadı → 503, ayrıntı = `seans.hata.kayitDbAcilamadi` + `seans.hata.kayitDbNeden`
    (neden metniyle); bobin sürülmez, seans açılmaz."""
    monkeypatch.setattr(o.api, "_kayit_db_hazir", o.gercek_hazir)
    monkeypatch.setattr(
        o.api.state, "core", types.SimpleNamespace(stm_uyumlu=None, db_acilis_hatalari={"tedavi": "göç bekliyor"})
    )
    r = o.c.post("/api/session/start", json=GOVDE)
    assert r.status_code == 503
    assert r.json()["detail"] == _t("seans.hata.kayitDbAcilamadi") + _t("seans.hata.kayitDbNeden", sebep="göç bekliyor")
    assert o.api._active_session.get("is_active") is not True


def test_GUNCELLEME_suruyorken_409_sorgu_PATLARSA_baslar(o, monkeypatch):
    """Güncelleme uygulanıyor → 409 `seans.hata.guncellemeSuruyor`; güncelleme durumu sorgusu istisna → kapı yok sayılır, seans 200."""
    from servers import update_manager

    monkeypatch.setattr(update_manager, "is_update_in_progress", lambda: True)
    r = o.c.post("/api/session/start", json=GOVDE)
    assert r.status_code == 409 and r.json()["detail"] == _t("seans.hata.guncellemeSuruyor")
    monkeypatch.setattr(update_manager, "is_update_in_progress", _patlayan(OSError("kilit dosyası okunamadı")))
    r = o.c.post("/api/session/start", json=GOVDE)
    assert r.status_code == 200 and r.json()["status"] == "success"


class _HastaDb:
    """Hasta DB'si yerine: `touch_last_treatment` kilitli; `get_patient` ilk çağrıda (sahip e-postası) kayıt, sonra `ikinci`."""

    def __init__(self, ikinci):
        self.sayi = 0
        self.ikinci = ikinci

    def touch_last_treatment(self, _u):
        raise sqlite3.OperationalError("database is locked")

    def get_patient(self, _u):
        self.sayi += 1
        if self.sayi == 1:
            return {"owner_email": "sahip@ornek.com", "name": "Pamuk"}
        if isinstance(self.ikinci, Exception):
            raise self.ikinci
        return self.ikinci


def test_BASLANGIC_yan_yazimlari_PATLASA_da_seans_baslar_satir_acilir(o, monkeypatch, caplog):
    """Hasta dokunuşu / hasta özeti / hasta aynası (upsert) / seans meta / sahip e-postası ve denetim ref parametresi yazımı
    OperationalError → 200 success, seans aktif, DB satırı "active" açılır; her hata kendi debug metniyle yazılır."""
    a = o.api
    hdb = _HastaDb(sqlite3.OperationalError("kilitli"))
    monkeypatch.setattr(a, "get_patient_database", lambda *x, **k: hdb)
    monkeypatch.setattr(o.db, "upsert_patient", _patlayan(sqlite3.OperationalError("disk I/O error")))
    gercek_meta = o.db.set_session_meta

    def _meta(sid, **k):
        if "started_epoch" in k and "patient_id" in k:
            raise sqlite3.OperationalError("disk I/O error")
        return gercek_meta(sid, **k)

    monkeypatch.setattr(o.db, "set_session_meta", _meta)
    monkeypatch.setattr(o.db, "set_session_parameter", _patlayan(sqlite3.OperationalError("disk I/O error")))
    caplog.set_level(logging.DEBUG)
    r = o.c.post("/api/session/start", json={**GOVDE, "patient_id": "u-kp1", "patient_name": "Pamuk"})
    assert r.status_code == 200 and r.json()["status"] == "success", r.text[:300]
    sid = a._active_session.get("db_session_id")
    assert a._active_session.get("is_active") is True and sid
    assert _seans_satiri(o, sid)[0] == "active"
    log = _log(caplog)
    for parca in (
        "touch_last_treatment hatasi",
        "Hasta Özeti snapshot lookup hatasi",
        "upsert_patient hatasi",
        "set_session_meta(start) hatasi",
        "set_session_parameter(owner_email) hatasi",
        "set_session_parameter(audit_ref) hatasi",
    ):
        assert parca in log, parca


def test_BEKLENMEDIK_hasta_kaydi_bicimi_canli_ozet_ADLA_kurulur(o, monkeypatch, caplog):
    """Hasta özeti sorgusu sözlük olmayan kayıt döndürüyor → canlı hasta özeti istekteki adla {"name": "Pamuk", species/breed/owner
    boş}, seans 200; hata "Hasta Özeti snapshot lookup hatasi" ile yutulur."""
    a = o.api
    hdb = _HastaDb(["beklenmedik", "satir"])
    monkeypatch.setattr(a, "get_patient_database", lambda *x, **k: hdb)
    caplog.set_level(logging.DEBUG)
    r = o.c.post("/api/session/start", json={**GOVDE, "patient_id": "u-kp2", "patient_name": "Pamuk"})
    assert r.status_code == 200
    hasta = a._live_state["activeTreatment"].get("patient") or a._live_state.get("patient")
    assert hasta == {"name": "Pamuk", "species": "", "breed": "", "owner": ""}
    assert _log(caplog).count("Hasta Özeti snapshot lookup hatasi") >= 1


def test_ARTIK_kosu_kapatilamasa_da_ve_E_baglami_alan_kaydi_ACILAMASA_da_baslar(o, monkeypatch, caplog):
    """Önceki seanstan açık koşu kaydı + koşu kapatma kuyruğu kapalı + canlı E bağlamı ve seans alan kaydı açılış istisnası →
    seans 200; "artik kosu kapatilamadi (bobin N)", "canlı E bağlamı temizlenemedi", "seans alan kaydı açılamadı" yazılır."""
    from servers import efield_live
    from utils import dongu_disi_yazim

    a = o.api
    gercek = dongu_disi_yazim.calistir

    def _kuyruk(fn, *x, ad="kayit", **k):
        if str(ad).startswith("bobin kosu kaydi bitir"):
            raise RuntimeError("cannot schedule new futures after shutdown")
        return gercek(fn, *x, ad=ad, **k)

    monkeypatch.setattr(dongu_disi_yazim, "calistir", _kuyruk)
    monkeypatch.setattr(efield_live, "seans_basladi", _patlayan(RuntimeError("E bağlamı kilitli")))
    monkeypatch.setattr(
        a,
        "_seans_alan",
        types.SimpleNamespace(seans_basladi=_patlayan(OSError("masaüstü yazılamaz")), seans_bitti=lambda *x, **k: None),
    )
    artik = max(STM_BOBIN + 1, 2)
    with a._active_coil_runs_lock:
        a._active_coil_runs[artik] = 123456
    caplog.set_level(logging.WARNING)
    r = o.c.post("/api/session/start", json=GOVDE)
    assert r.status_code == 200 and r.json()["status"] == "success", r.text[:300]
    log = _log(caplog)
    assert f"artik kosu kapatilamadi (bobin {artik})" in log
    assert "canlı E bağlamı temizlenemedi (seans akışı etkilenmez)" in log
    assert "seans alan kaydı açılamadı (seans akışı etkilenmez)" in log
