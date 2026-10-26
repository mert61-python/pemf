# -*- coding: utf-8 -*-
"""DALGA-1 §7 "Dalga 2 (veri)" (1-B §9 #3 — D3 devri → D5): DB'siz kipte (hasta DB'si AÇILIŞTA açılamadı, D1.37 / Y43) `GET /api/patients`
500 değil 503 + eylem söyleyen katalog iletisi (`hasta.hata.listeOkunamadi`: "bu 'hasta yok' demek değil, yeni kart açmayın").

Ölçülen önce (HEAD `5bc99be1`): `get_patient_database()` açılış kilidinde `RuntimeError` atar; liste ucu bunu `try` DIŞINDA çağırdığı için
yanıt 500 ("Internal Server Error") — arayüz bunu genel sunucu hatası sanar. Arıza EN ALT katta, ürünün kendi açılış kilidiyle kurulur
(`acilis_hatasini_kilitle` — backend açılışının yaptığı)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def db_siz(monkeypatch):
    from database import patient_database as pdb
    from servers import api_server
    from utils.path_utils import get_app_data_directory

    kok = get_app_data_directory()
    monkeypatch.setattr(pdb, "_patient_db", None)
    monkeypatch.setattr(pdb, "_acilis_kilidi", {})
    pdb.acilis_hatasini_kilitle(kok, RuntimeError("test: hasta DB'si açılışta açılamadı"))
    with pytest.raises(RuntimeError):
        pdb.get_patient_database()  # aparat: DB'siz kip GERÇEKTEN kurulu
    return TestClient(api_server.app, client=("127.0.0.1", 50000), raise_server_exceptions=False)


@pytest.mark.parametrize("dil, parca", [("tr", "yeni kart açmayın"), ("en", "do not create new cards")])
def test_KRITIK_DB_siz_kipte_hasta_listesi_503_ve_EYLEM_iletisi(db_siz, dil, parca):
    r = db_siz.get("/api/patients", headers={"X-PEMF-Dil": dil})
    assert r.status_code == 503, (
        f"DB'siz kipte hasta listesi {r.status_code} (500 = genel sunucu hatası sanılır): {r.text[:200]}"
    )
    assert parca in r.json().get("detail", ""), r.json()


def test_KARSIT_DB_varken_liste_200(monkeypatch):
    from database import patient_database as pdb
    from servers import api_server

    monkeypatch.setattr(pdb, "_acilis_kilidi", {})
    r = TestClient(api_server.app, client=("127.0.0.1", 50000)).get("/api/patients")
    assert r.status_code == 200, r.text[:200]
