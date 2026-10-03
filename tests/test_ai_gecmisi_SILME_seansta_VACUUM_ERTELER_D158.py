# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.58 · B-3.88 (+ B-3.87 "uyandırır" notu) — AI geçmişi toplu silmesi AKTİF SEANS sürerken tüm-DB VACUUM'u
çalıştırmaz; VACUUM seans bitimine / bakıma ERTELENİR (KVKK kalıntı temizliği KAYBOLMAZ).

ÖLÇÜLEN KUSUR (b5c74e6+): `/api/ai/log/delete_all` → `clear_ai_analyses` DELETE'ten sonra KOŞULSUZ `VACUUM` çalıştırıyordu.
VACUUM tüm dosyayı yeniden yazar ve yazım kilidi tutar (ölçülmüş 2–2,6 sn; büyük DB'de daha uzun) → tedavi sırasında
sensör/koşu (DOZ) yazımları düşebilir. Bakım döngüsü aynı riski bilerek atlıyordu, bu uç atlamıyordu.
B-3.87 (aynı işlev): VACUUM düşerse DELETE kalıcı olduğu hâlde -1 ("temizlenemedi") dönüyordu → erteleme yoluna taşındı.

KAPI: GERÇEK uç + GERÇEK `TreatmentHistoryDB`; VACUUM, gerçek bağlantılarda `set_trace_callback` ile yakalanır.
"""

from __future__ import annotations

import contextlib
import sqlite3
import time

import ai_pro_aparati as ap
import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    ns.c = TestClient(ns.api.app, client=("127.0.0.1", 51235))  # yıkıcı uç: loopback (enforce_privileged)
    izler: list = []
    gercek = ns.db._get_connection

    @contextlib.contextmanager
    def _izli():
        with gercek() as conn:
            conn.set_trace_callback(izler.append)
            try:
                yield conn
            finally:
                conn.set_trace_callback(None)

    monkeypatch.setattr(ns.db, "_get_connection", _izli)
    ns.vacuum = lambda: [s for s in izler if s.strip().upper().startswith("VACUUM")]
    ns.izler = izler
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _analizler(o, n=20):
    for i in range(n):
        o.db.add_ai_analysis(module_id="m", patient_name=f"Hasta{i}", result_summary="X" * 400, operator_email="")


def _sil(o):
    return o.c.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "all_operators": True})


def _seans(o):
    r = o.c.post(
        "/api/session/start",
        json={"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 20, "coil_ids": [1]},
    )
    assert r.status_code == 200, r.text[:200]


def _bekleyen(o):
    return o.db._get_system_setting("kvkk_vacuum_bekliyor")


def test_KRITIK_aktif_seansta_toplu_silme_VACUUM_CALISTIRMAZ_seans_bitince_CALISIR(o):
    _analizler(o)
    _seans(o)
    o.izler.clear()
    r = _sil(o)
    assert r.status_code == 200 and r.json().get("deleted") == 20, r.text[:200]
    assert o.db.get_ai_analyses(limit=50) == [], "aparat: kayıtlar silinmedi"
    assert not o.vacuum(), "AKTİF SEANS sürerken tüm-DB VACUUM çalıştı (yazım kilidi — tedavi kaydı düşebilir)"
    assert _bekleyen(o) == "1", "ertelenen KVKK VACUUM'u kalıcı olarak işaretlenmedi (yeniden başlatmada kaybolur)"
    assert o.c.post("/api/session/stop").status_code == 200
    assert ap.bekle(lambda: bool(o.vacuum()), 5), (
        "seans bitti ama ertelenen VACUUM ÇALIŞMADI (silinen PII dosyada kalır)"
    )
    assert ap.bekle(lambda: _bekleyen(o) == "0", 5), "VACUUM sonrası bekleme işareti kalkmadı"


def test_KARSIT_seans_yokken_toplu_silme_VACUUM_HEMEN(o):
    _analizler(o)
    o.izler.clear()
    r = _sil(o)
    assert r.status_code == 200 and r.json().get("deleted") == 20
    assert o.vacuum(), "seans yokken VACUUM hemen çalışmadı (KVKK temizliği gecikti)"
    assert _bekleyen(o) in (None, "0")


def test_KRITIK_B387_VACUUM_dusse_de_silme_BASARILI_sayilir_ve_ERTELENIR(o, monkeypatch):
    """DELETE kalıcıyken VACUUM düşerse uç eskiden 500 "temizlenemedi" diyordu (kayıtlar gitmişti, yeniden deneme 0
    siler). Artık silinen sayı döner, VACUUM ertelenir (bakım/seans sonu koşar)."""
    _analizler(o)
    gercek = o.db._get_connection

    class _Vekil:
        def __init__(self, c):
            self._c = c

        def cursor(self):
            cur = self._c.cursor()

            class _Cur:
                def execute(self, sql, *a):
                    if sql.strip().upper().startswith("VACUUM"):
                        raise sqlite3.OperationalError("database is locked")
                    return cur.execute(sql, *a)

                def __getattr__(self, ad):
                    return getattr(cur, ad)

            return _Cur()

        def execute(self, sql, *a):
            if sql.strip().upper().startswith("VACUUM"):
                raise sqlite3.OperationalError("database is locked")
            return self._c.execute(sql, *a)

        def __getattr__(self, ad):
            return getattr(self._c, ad)

    @contextlib.contextmanager
    def _kilitli():
        with gercek() as c:
            yield _Vekil(c)

    monkeypatch.setattr(o.db, "_get_connection", _kilitli)
    r = _sil(o)
    monkeypatch.setattr(o.db, "_get_connection", gercek)
    assert r.status_code == 200 and r.json().get("deleted") == 20, f"VACUUM düşünce: {r.status_code} {r.text[:200]}"
    assert _bekleyen(o) == "1", "düşen VACUUM ertelenmedi (KVKK temizliği sessizce kayboldu)"


def _bakim_turu(api):
    """GERÇEK `_daily_maintenance_loop`un İLK turu: açılış uykusu (60 sn) atlanır, tur sonundaki uykuda durulur.
    Uyku yaması YALNIZ döngünün iş parçacığında etkilidir (`tests/dongu_tek_tur.py` ile aynı ilke)."""
    import threading

    class _Bitti(BaseException):
        pass

    orj = time.sleep
    durum = {"ident": None, "uyku": 0}

    def _uyku(s):
        if threading.get_ident() == durum["ident"]:
            durum["uyku"] += 1
            if durum["uyku"] >= 2:
                raise _Bitti()
            return None
        return orj(s)

    hatalar: list = []

    def _kos():
        durum["ident"] = threading.get_ident()
        try:
            api._daily_maintenance_loop()
        except _Bitti:
            pass
        except BaseException as e:  # noqa: BLE001
            hatalar.append(e)

    time.sleep = _uyku
    try:
        t = threading.Thread(target=_kos, daemon=True)
        t.start()
        t.join(30)
    finally:
        time.sleep = orj
    assert not t.is_alive() and not hatalar and durum["uyku"] == 2, f"aparat: bakım turu {durum} {hatalar}"


def test_KRITIK_yeniden_baslatma_sonrasi_BEKLEYEN_vacuum_BAKIMDA_calisir(o, monkeypatch):
    """Silme seans sürerken yapıldı, VACUUM beklerken süreç yeniden başladı (seans sonu kancası koşmadı): işaret
    KALICI olduğu için bakım döngüsünün ilk turu (seans yokken) VACUUM'u koşar."""
    monkeypatch.setattr(o.db, "purge_old_sensor_samples", lambda *a, **k: 0)
    monkeypatch.setattr(o.db, "purge_old_session_events", lambda *a, **k: 0)
    _analizler(o)
    assert o.db.clear_ai_analyses(None, True) == 20
    assert _bekleyen(o) == "1"
    o.izler.clear()
    _bakim_turu(o.api)
    assert o.vacuum(), "bakım döngüsü bekleyen KVKK VACUUM'unu koşmadı (silinen PII dosyada kalır)"
    assert _bekleyen(o) == "0"
