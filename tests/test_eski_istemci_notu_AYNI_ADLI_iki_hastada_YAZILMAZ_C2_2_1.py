# -*- coding: utf-8 -*-
"""C2-2.1 (2-C inceleme A2) — seans kimliği GÖNDERMEYEN eski istemcinin (APK 2.3.34) gözlem notu, AYNI ADLI iki farklı hastanın
yakın tarihli bitmiş seansı varken BAŞKA hastanın (ve başka hekimin) seansına YAZILMAZ.

ÖLÇÜLEN (HEAD 1cd770c, `_inceleme/kayit/sonda_y116.txt` [S1iii]): Ayşe'nin Pamuk'u (kedi, `uuid-pamuk-A`) ve Mehmet'in Pamuk'u
(köpek, `uuid-pamuk-B`) aynı gün tedavi edildi; eski istemci Ayşe'nin Pamuk'u için `{"notes", "patient_name": "Pamuk"}` gönderdi →
200 `hedef: hasta`, not MEHMET'in Pamuk'unun satırına (`patient_id` B, `operator_email` dr.mehmet) yazıldı; iz sahipsiz.
Kök: `_not_hedefi` kimliksiz dalı (bellek dalı da) yalnız AD eşler (`son_biten_seans_kimligi`: `patient_name = ?`, en son başlayan).
İlke (A-62 · D2.21 · D2.22): ad belirsizse BAĞLANMAZ. Düzeltme: aday seanslar (aynı ad, 12 sa, bitmiş) birden çok hastaya aitse 409 —
not istemcide kalır, hiçbir satır değişmez. Tek hastalı (bugünkü) eski akış ve `session_id`'li yeni istemci DEĞİŞMEZ.
GERÇEK: `/api/session/start` (gercek_hc), `/api/session/stop`, `/api/session/notes`, tedavi DB'si; satırlar ham SQL.
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
            ns.c.post("/api/session/stop")
    finally:
        ns.geri()


def _seans(o, hasta_kimligi, ad="Pamuk"):
    r = o.c.post(
        "/api/session/start",
        json={
            "mode": "Manuel",
            "frequency": 100,
            "duty": 40,
            "phase": 0,
            "intensity": 0,
            "duration_minutes": 20,
            "coil_ids": [1],
            "patient_name": ad,
            "patient_id": hasta_kimligi,
        },
    )
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:300]
    sid = r.json()["session"]["db_session_id"]
    assert o.c.post("/api/session/stop").status_code == 200
    return sid


def _yas(o, sid, saniye):
    import time

    with o.db._get_connection() as c:
        c.execute("UPDATE treatment_sessions SET started_epoch = ? WHERE id = ?", (time.time() - saniye, sid))
        c.commit()


def _satir(o, sid):
    with o.db._get_connection() as c:
        c.row_factory = None
        return c.execute(
            "SELECT s.patient_name, p.patient_uuid, COALESCE(s.patient_notes, '') FROM treatment_sessions s "
            "LEFT JOIN patients p ON p.id = s.patient_id WHERE s.id = ?",
            (sid,),
        ).fetchone()


def _eski_not(o, ad="Pamuk", metin="A icin gozlem"):
    # APK 2.3.34 gövdesi: session_id YOK, patient_id alanı YOK.
    return o.c.post(
        "/api/session/notes",
        json={
            "notes": metin,
            "patient_name": ad,
            "mode": "Manuel",
            "frequency": 100,
            "intensity": 0,
            "duration_minutes": 20,
        },
    )


def _bellegi_sil(o):
    with o.api._session_lock:
        o.api._active_session.clear()


def test_KRITIK_ayni_adli_IKI_hasta_eski_istemci_notu_BASKA_hastanin_seansina_YAZILMAZ(o):
    a = _seans(o, "uuid-pamuk-A")
    b = _seans(o, "uuid-pamuk-B")
    _yas(o, a, 3600)
    _yas(o, b, 600)
    _bellegi_sil(o)  # hasta dalı (yeniden başlatma sonrası / başka istemci)
    r = _eski_not(o)
    assert _satir(o, b)[2] == "", (
        f"A'nın notu BAŞKA hastanın (uuid-pamuk-B) seansına yazıldı: {_satir(o, b)} · {r.text[:200]}"
    )
    assert _satir(o, a)[2] == "" and r.status_code == 409, (r.status_code, r.text[:200], _satir(o, a))


def test_KRITIK_ayni_adli_IKI_hasta_BELLEK_dali_da_baskasinin_seansina_YAZMAZ(o):
    a = _seans(o, "uuid-pamuk-A")
    b = _seans(o, "uuid-pamuk-B")  # bellekte B (bitmiş) — eski istemci A için not gönderir
    _yas(o, a, 3600)
    _yas(o, b, 600)
    r = _eski_not(o)
    assert _satir(o, b)[2] == "", f"bellek dalı A'nın notunu B'nin seansına yazdı: {_satir(o, b)} · {r.text[:200]}"
    assert r.status_code == 409, (r.status_code, r.text[:200])


def test_KARSIT_tek_hasta_eski_istemci_notu_EN_SON_seansina_yazilir(o):
    a1 = _seans(o, "uuid-pamuk-A")
    a2 = _seans(o, "uuid-pamuk-A")
    _yas(o, a1, 3600)
    _yas(o, a2, 600)
    _bellegi_sil(o)
    r = _eski_not(o, metin="tek hasta notu")
    assert r.status_code == 200 and r.json().get("session_id") == a2, r.text[:200]
    assert _satir(o, a2)[2] == "tek hasta notu" and _satir(o, a1)[2] == ""


def test_KARSIT_yeni_istemci_session_id_ile_ayni_adli_hastada_DOGRU_seansa_yazar(o):
    a = _seans(o, "uuid-pamuk-A")
    b = _seans(o, "uuid-pamuk-B")
    r = o.c.post("/api/session/notes", json={"session_id": a, "notes": "kimlikli not", "patient_name": "Pamuk"})
    assert r.status_code == 200 and r.json().get("session_id") == a, r.text[:200]
    assert _satir(o, a)[2] == "kimlikli not" and _satir(o, b)[2] == ""


def test_KRITIK_belirsizlik_OKUMASI_DUSERSE_not_YAZILMAZ_fail_closed(o, monkeypatch):
    """Orkestratör eki (2-C incelemesi): belirsizlik sorgusu DB hatasıyla düşerse not hiçbir satıra YAZILMAZ (409) — ad
    eşlemesi doğrulanamadan kayda bağlanmaz. Arıza EN ALT katta: yalnız bu sorguda `OperationalError` veren bağlantı vekili."""
    import sqlite3
    from contextlib import contextmanager

    a = _seans(o, "uuid-pamuk-A")
    _bellegi_sil(o)
    orj = o.db._get_connection

    class _Vekil:
        def __init__(self, c):
            self._c = c

        def __getattr__(self, ad):
            return getattr(self._c, ad)

        def execute(self, sql, *a, **k):
            if "COUNT(DISTINCT patient_id)" in sql:
                raise sqlite3.OperationalError("database is locked")
            return self._c.execute(sql, *a, **k)

    @contextmanager
    def _bozuk():
        with orj() as c:
            yield _Vekil(c)

    monkeypatch.setattr(o.db, "_get_connection", _bozuk)
    r = _eski_not(o, metin="dogrulanamayan not")
    monkeypatch.setattr(o.db, "_get_connection", orj)
    assert r.status_code == 409, (r.status_code, r.text[:200])
    assert _satir(o, a)[2] == "", f"belirsizlik okunamadan not yazıldı: {_satir(o, a)}"
