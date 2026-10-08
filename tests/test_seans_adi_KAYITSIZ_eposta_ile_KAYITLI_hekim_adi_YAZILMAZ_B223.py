# -*- coding: utf-8 -*-
"""B2-2.3 (2-B bağımsız inceleme · A2) — kayıtlı operatörlü cihazda DOĞRULANMAMIŞ ad seans kaydına yazılmaz (D2.41 · B-2.19).

ÖLÇÜLEN KUSUR: D2.41 `cozumlenmis_operator_adi` "kanıtsız beyan bir hekimin adını taşıyamaz" diyor ve e-posta boşken (c3) bunu
uyguluyor; ama jetonsuz istek KAYITSIZ bir e-posta (eski APK'nın paylaşılan giriş e-postası, uydurma adres) ile birlikte KAYITLI
bir hekimin görünen adını ("Dr. Ayşe") gönderince ad aynen kabul ediliyor → seans satırı, `session_started` izi ve seans alan
CSV'si "Dr. Ayşe" taşıyor (sonda `_inceleme/B2-2.2/sonda_kayitsiz_beyan.py`: satır ('Dr. Ayşe', klinik@ortak-giris.com),
iz aynı, CSV başlığı ['Dr. Ayşe']). Kayıtlı operatörlü cihazda bir AD ancak jetondan (kayıtlı görünen ad) gelir.
KARŞIT: Kural 2 (operatörsüz klinik) beyan adı korunur; jetonlu istekte kayıtlı görünen ad yazılır.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
ORTAK = "klinik@ortak-giris.com"
TEK = "tek@klinik.com"
LAN = ("192.168.1.81", 51635)


def _operatorleri_sil(c):
    for op in c.get("/api/operators").json().get("data", []):
        c.post("/api/operators/remove", json={"email": op["email"]})


class _AlanKaydedici:
    def __init__(self):
        self.basliklar = []

    def seans_basladi(self, sid, bilgi):
        self.basliklar.append(dict(bilgi))
        return None

    def seans_bitti(self, *a, **k):
        return None


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as apa
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens

    o = apa.kur(monkeypatch, tmp_path)
    o.alan = _AlanKaydedici()
    monkeypatch.setattr(o.api, "_seans_alan", o.alan)
    secenek = dict(apa.ISTEMCI_SECENEKLERI)
    o.yerel = TestClient(o.api.app, client=("127.0.0.1", 51634), backend_options=secenek)
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


def _iki_hekim(o):
    j = {}
    for e, ad in ((AYSE, "Dr. Ayşe"), (MEHMET, "Dr. Mehmet")):
        r = o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": ad, "pin": "123456"})
        assert r.status_code == 200, r.text[:200]
        j[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return j


def _seans(o, eposta, ad, jeton=""):
    r = o.lan.post(
        "/api/session/start",
        json={
            "coil_ids": [1],
            "frequency": 100,
            "duty": 40,
            "phase": 0,
            "duration_minutes": 5,
            "mode": "Manuel",
            "operator_email": eposta,
            "operator_name": ad,
        },
        headers={"X-PEMF-Operator": jeton} if jeton else {},
    )
    assert r.status_code == 200, r.text[:300]
    satir = o.db.get_session_history(limit=5)[0]
    with o.db._get_connection() as c:
        olay = c.execute(
            "SELECT payload FROM session_events WHERE event_type='session_started' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    o.lan.post("/api/session/stop")
    yuk = json.loads(olay[0]) if olay else {}
    return (
        satir.get("operator_name") or "",
        yuk.get("operator_name") or "",
        (o.alan.basliklar[-1].get("operator_name") or ""),
    )


@pytest.mark.parametrize("ad", ["Dr. Ayşe", "Dr. Mehmet", "Dr Ayse"])
def test_KRITIK_jetonsuz_KAYITSIZ_eposta_ile_KAYITLI_hekim_ADI_seansa_izine_CSVye_GECMEZ(o, ad):
    """MUTASYON: kayıtsız e-postada beyan adını kabul etmek (bugünkü hâl) → KIRMIZI."""
    _iki_hekim(o)
    satir, iz, csv = _seans(o, ORTAK, ad)
    assert (satir, iz, csv) == ("", "", ""), (
        f"kayıtlı operatörlü cihazda jetonsuz istek kayıtlı hekimin adını ({ad!r}) mühürledi: satır={satir!r} iz={iz!r} CSV={csv!r}"
    )


def test_KARSIT_jetonlu_istekte_KAYITLI_gorunen_ad(o):
    j = _iki_hekim(o)
    assert _seans(o, ORTAK, "Dr. Ayşe", j[MEHMET]) == ("Dr. Mehmet", "Dr. Mehmet", "Dr. Mehmet")


@pytest.mark.parametrize("eposta", [TEK, ""], ids=["beyanli", "yalniz_ad_eski_istemci"])
def test_KARSIT_KURAL2_operatorsuz_klinikte_beyan_ADI_korunur(o, eposta):
    assert _seans(o, eposta, "Dr Tek") == ("Dr Tek", "Dr Tek", "Dr Tek")
