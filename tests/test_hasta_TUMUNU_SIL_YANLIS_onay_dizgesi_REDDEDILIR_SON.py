# -*- coding: utf-8 -*-
"""SON-A1.9 (22-SON A1a · C27 / D5.19 ikiz uç) — `/api/patients/delete_all` YANLIŞ dolu onay dizgesiyle TÜM hastaları SİLMEZ.

ÖLÇÜLEN KÖRLÜK (uç 8b002fc0): D5.19 (C27) `delete_bulk` uçlarına YANLIŞ dolu onay kolunu ekledi (`!= "DELETE_SELECTED"` yerine
`not payload.confirm` mutantı KIRMIZI). İkiz uç `/api/patients/delete_all` (`patient_router.py:259` `!= "DELETE_ALL"`) yalnız BOŞ onayla
sınanıyor (`test_hasta_TUMUNU_SIL_yalniz_cihazdan_D211_A03.py::test_KARSIT_onay_dizesi_kapisi_KORUNUR` `json={}`): `if not payload.confirm:`
mutantı (her dolu dizge TÜM hastaları siler) DELETE_ALL'u anan 27 test dosyasında YEŞİL. Bu uç geri alınamaz tam silmedir.
GERÇEK: uç (cihazın kendisi — loopback soket), hasta DB'si (geçici), denetim izi (geçici tedavi DB'si). Ölçüt ham satır sayısı.
"""

import pytest
from fastapi.testclient import TestClient

#: YANLIŞ dolu onaylar: öteki ucun dizgesi, küçük harf, boşluklu, ön-ek, başka dil, doğruluk değeri.
_YANLIS = ["DELETE_SELECTED", "delete_all", " DELETE_ALL", "DELETE_ALL ", "DELETE", "EVET", "true"]


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import patient_router

    hdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: hdb)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    for i in range(2):
        hdb.add_patient({"name": f"Hasta{i}", "species": "Kedi", "operator_email": ""})
    try:
        yield type("O", (), {"hdb": hdb, "tdb": tdb, "api": api})
    finally:
        tdb.close_connections()


def _sayi(o):
    with o.hdb._get_connection() as c:
        return c.execute("SELECT COUNT(*) FROM patients").fetchone()[0]


@pytest.mark.parametrize("yanlis", _YANLIS)
def test_KRITIK_YANLIS_onay_dizgesiyle_TUM_hastalar_SILINMEZ(o, yanlis):
    assert _sayi(o) == 2, "aparat: hasta yazılmadı"
    r = TestClient(o.api.app, client=("127.0.0.1", 51736)).post("/api/patients/delete_all", json={"confirm": yanlis})
    assert r.status_code == 400, (
        f"yanlış onay {yanlis!r} ile TÜM hasta silme 400 dönmedi: {r.status_code} {r.text[:160]}"
    )
    assert _sayi(o) == 2, f"yanlış onay {yanlis!r} ile TÜM hastalar SİLİNDİ"


def test_KARSIT_dogru_onay_cihazin_kendisinden_SILER(o):
    r = TestClient(o.api.app, client=("127.0.0.1", 51737)).post(
        "/api/patients/delete_all", json={"confirm": "DELETE_ALL"}
    )
    assert r.status_code == 200 and _sayi(o) == 0, r.text[:200]
