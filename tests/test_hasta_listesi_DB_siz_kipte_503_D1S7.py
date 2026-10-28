# -*- coding: utf-8 -*-
"""DALGA-1 §7 "Dalga 2 (veri)" (1-B §9 #3 — D3 devri → D5): DB'siz kipte (hasta DB'si AÇILIŞTA açılamadı, D1.37 / Y43) `GET /api/patients`
500 değil 503 + eylem söyleyen katalog iletisi (`hasta.hata.listeOkunamadi`: "bu 'hasta yok' demek değil, yeni kart açmayın").

Ölçülen önce (HEAD `5bc99be1`): `get_patient_database()` açılış kilidinde `RuntimeError` atar; liste ucu bunu `try` DIŞINDA çağırdığı için
yanıt 500 ("Internal Server Error") — arayüz bunu genel sunucu hatası sanar. Arıza EN ALT katta, ürünün kendi açılış kilidiyle kurulur
(`acilis_hatasini_kilitle` — backend açılışının yaptığı)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _ucun_db_modulu():
    """Liste ucunun GERÇEKTEN çağırdığı `get_patient_database`'in modül durumu (işlevin kendi globals'ı).

    D5 kapanış süiti (ölçüldü): `test_anahtar_uyusmazligi_karantina.py` `database.patient_database`'i sys.modules'tan silip yeniden
    içe aktarıyor; `servers.patient_router` ise işlevi içe aktarma anında bağladığı için ESKİ modülü kullanmaya devam ediyor. Aparat
    sys.modules'taki YENİ modülü yamalarsa uç eski modülün canlı DB'sini açar (200) — kapı ürünü değil aparatı ölçer. Bu yüzden durum,
    ucun kullandığı işlevin modülünde kurulur."""
    from servers import patient_router

    return patient_router.get_patient_database.__globals__


@pytest.fixture
def db_siz(monkeypatch):
    from servers import api_server, patient_router
    from utils.path_utils import get_app_data_directory

    g = _ucun_db_modulu()
    kok = get_app_data_directory()
    monkeypatch.setitem(g, "_patient_db", None)
    monkeypatch.setitem(g, "_acilis_kilidi", {})
    g["acilis_hatasini_kilitle"](kok, RuntimeError("test: hasta DB'si açılışta açılamadı"))
    with pytest.raises(RuntimeError):
        patient_router.get_patient_database()  # aparat: DB'siz kip ucun KENDİ erişimcisinde GERÇEKTEN kurulu
    return TestClient(api_server.app, client=("127.0.0.1", 50000), raise_server_exceptions=False)


@pytest.mark.parametrize("dil, parca", [("tr", "yeni kart açmayın"), ("en", "do not create new cards")])
def test_KRITIK_DB_siz_kipte_hasta_listesi_503_ve_EYLEM_iletisi(db_siz, dil, parca):
    r = db_siz.get("/api/patients", headers={"X-PEMF-Dil": dil})
    assert r.status_code == 503, (
        f"DB'siz kipte hasta listesi {r.status_code} (500 = genel sunucu hatası sanılır): {r.text[:200]}"
    )
    assert parca in r.json().get("detail", ""), r.json()


def test_KARSIT_DB_varken_liste_200(monkeypatch):
    from servers import api_server

    monkeypatch.setitem(_ucun_db_modulu(), "_acilis_kilidi", {})
    r = TestClient(api_server.app, client=("127.0.0.1", 50000)).get("/api/patients")
    assert r.status_code == 200, r.text[:200]
