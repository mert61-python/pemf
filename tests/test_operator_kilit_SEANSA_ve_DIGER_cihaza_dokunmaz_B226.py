# -*- coding: utf-8 -*-
"""B2-2.6 (2-B bağımsız inceleme · A2) — `POST /api/operators/lock` (D2.E14) YALNIZ gönderilen jetonu düşürür; süren seansa,
STOP'a ve ACİL DURDUR'a DOKUNMAZ (Ö.4-Y8 · Y89).

ÖLÇÜLEN KÖR NOKTA: uç docstring'i "yalnız gönderilen jeton düşer … ACİL DURDUR/STOP'a DOKUNMAZ" diyor; `tests/test_operator_kilit_ucu_E14.py`
yalnız "başka HEKİMİN jetonu" ve "jetonsuz kilit" kollarını ölçüyor. İki mutant 2-B kapısında (E14 + route sözleşmesi + D2.72,
22 test) YEŞİL kaldı (ölçüldü, `kayit/k4_mutasyon.txt`):
  e1 kilit, AYNI hekimin TÜM cihazlarındaki jetonları düşürür (`iptal_email`) — ikinci cihazda süren seansın sonraki yazmaları
     sahipsize düşer (Y89 "seans sürerken jeton ölmesin");
  e4 kilit süren seansı pasifleştirir — tedavi kaydı/akışı operatör kilidine bağlanır (Ö.4-Y8).
Bugünkü ürün DOĞRU (HEAD'de bu kapı yeşil); kapı, iddiayı ölçülebilir kılar.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
LAN = ("192.168.1.87", 52235)


def _operatorleri_sil(c):
    for op in c.get("/api/operators").json().get("data", []):
        c.post("/api/operators/remove", json={"email": op["email"]})


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as apa
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens

    o = apa.kur(monkeypatch, tmp_path)
    secenek = dict(apa.ISTEMCI_SECENEKLERI)
    o.yerel = TestClient(o.api.app, client=("127.0.0.1", 52234), backend_options=secenek)
    o.lan = TestClient(o.api.app, client=LAN, backend_options=secenek)
    operator_tokens.temizle_hepsi()
    _operatorleri_sil(o.yerel)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            yield o
            o.lan.post("/api/session/stop")
    finally:
        operator_tokens.temizle_hepsi()
        _operatorleri_sil(o.yerel)
        o.geri()


def _jeton(o, ilk=False):
    if ilk:
        r = o.yerel.post("/api/operators/enroll", json={"email": AYSE, "display_name": "Dr. Ayşe", "pin": "123456"})
        assert r.status_code == 200, r.text[:200]
    return o.yerel.post("/api/operators/verify", json={"email": AYSE, "pin": "123456"}).json()["operator_token"]


def _b(j):
    return {"X-PEMF-Operator": j}


def _seans(o, j):
    r = o.lan.post(
        "/api/session/start",
        json={"coil_ids": [1], "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 5, "mode": "Manuel"},
        headers=_b(j),
    )
    assert r.status_code == 200, r.text[:300]
    return o.db.get_session_history(limit=5)[0]["id"]


def _aktif(o):
    with o.api._session_lock:
        return bool(o.api._active_session.get("is_active"))


def test_KRITIK_kilit_AYNI_hekimin_DIGER_cihazindaki_jetonu_DUSURMEZ(o):
    """Masaüstünde 'Kilitle' — Ayşe'nin tabletindeki seans jetonu yaşar. MUTASYON: `iptal_email` → KIRMIZI."""
    from servers import operator_tokens

    j_masaustu = _jeton(o, ilk=True)
    j_tablet = _jeton(o)
    assert o.lan.post("/api/operators/lock", headers=_b(j_masaustu)).json() == {"ok": True, "iptal": True}
    assert operator_tokens.cozumle(j_masaustu) == ""
    assert operator_tokens.cozumle(j_tablet) == AYSE, "kilit hekimin DİĞER cihazındaki jetonu da düşürdü"


def test_KRITIK_kilit_SUREN_seansa_dokunmaz_STOP_calisir_sahip_korunur(o):
    """MUTASYON: kilit seansı pasifleştirsin → KIRMIZI."""
    j = _jeton(o, ilk=True)
    sid = _seans(o, j)
    assert _aktif(o), "ön koşul: seans aktif"
    assert o.lan.post("/api/operators/lock", headers=_b(j)).json()["iptal"] is True
    assert _aktif(o), "operatör kilidi süren tedaviyi durdurdu/pasifleştirdi"
    r = o.lan.post("/api/session/stop", headers=_b(j))
    s = next(x for x in o.db.get_session_history(limit=10) if x["id"] == sid)
    assert r.status_code == 200 and not _aktif(o), r.text[:200]
    assert (s.get("operator_email"), s.get("operator_name")) == (AYSE, "Dr. Ayşe"), s


def test_KRITIK_kilit_sonrasi_ACIL_DURDUR_calisir(o):
    j = _jeton(o, ilk=True)
    sid = _seans(o, j)
    o.lan.post("/api/operators/lock", headers=_b(j))
    r = o.lan.post("/api/hardware/emergency_stop", headers=_b(j))
    s = next(x for x in o.db.get_session_history(limit=10) if x["id"] == sid)
    assert r.status_code == 200 and not _aktif(o), r.text[:200]
    assert s.get("operator_email") == AYSE, s
