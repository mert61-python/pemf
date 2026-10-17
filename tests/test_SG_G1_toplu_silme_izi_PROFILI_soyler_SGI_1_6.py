# Author: mertaygn, cglrgrkn
"""SGI-1.6 (bağımsız inceleme) — profil süzgeciyle DARALTILMIŞ toplu silmenin denetim izi (KVKK "sildim" kanıtı) PROFİLİ söyler.

Ölçülen (549ce2b0): SG.G1/G2 "Tümünü Sil"i profile daralttı (araştırmada yalnız araştırma kayıtları) ama ekleme-only denetim izi ve KVKK günlük
satırı bunu BİLMİYOR — AI için `scope="TUM_KLINIK"`, hasta için `scope="TUM_HASTALAR"`, `detail`de profil YOK. İz, veteriner kayıtları
dururken "kliniğin tüm AI geçmişi / tüm hastalar silindi" der; bir silme talebine iz kanıt gösterilirse yanlış kanıttır.
GERÇEK TreatmentHistoryDB (iz tablosu) + GERÇEK PatientDatabase + TestClient uçları (`/api/ai/log/delete_all`, `/api/patients/delete_all`).
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

VET, ARS = "veterinarian", "researcher"
_H = "X-PEMF-Profil"


def _h(p):
    return {_H: p} if p else {}


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server, patient_router

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    tdb = TreatmentHistoryDB(tmp_path / "g")
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: tdb)
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: pdb)
    c = TestClient(api_server.app, client=("127.0.0.1", 52693))
    try:
        yield c, tdb
    finally:
        tdb.close_connections()


def _iz(tdb, tur):
    for _ in range(40):  # iz döngü dışı FIFO işçide yazılabilir (audit_log.yaz) — kısa bekleme
        iz = tdb.denetim_oku(20, tur)
        if iz:
            return iz
        time.sleep(0.05)
    return []


def _ai_tohum(tdb):
    tdb.add_ai_analysis(mode=VET, module_id="landmark", result_summary="vet")
    tdb.add_ai_analysis(mode=ARS, module_id="em_fantom", result_summary="ars")


def test_KRITIK_AI_toplu_silme_PROFILE_daraltildiysa_iz_PROFILI_soyler(ortam):
    c, tdb = ortam
    _ai_tohum(tdb)
    r = c.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "all_operators": True}, headers=_h(ARS))
    assert r.status_code == 200 and r.json()["deleted"] == 1, r.text[:200]
    iz = _iz(tdb, "ai_log.delete_all")
    assert iz and iz[0]["outcome"] == "ok", iz
    d = json.loads(iz[0]["detail"] or "{}")
    assert d.get("profil") == ARS, f"daraltılmış silmenin izi profili söylemiyor (kapsam '{iz[0]['scope']}'): {d}"


def test_KRITIK_hasta_toplu_silme_PROFILE_daraltildiysa_iz_PROFILI_soyler(ortam):
    c, tdb = ortam
    for ad, p in (("Vet-Mia", VET), ("Ars-1", ARS)):
        assert c.post("/api/patients", json={"name": ad}, headers=_h(p)).json()["status"] == "success"
    r = c.post("/api/patients/delete_all", json={"confirm": "DELETE_ALL"}, headers=_h(ARS))
    assert r.status_code == 200 and r.json()["deleted"] == 1, r.text[:200]
    iz = _iz(tdb, "patient.delete_all")
    assert iz and iz[0]["outcome"] == "ok", iz
    d = json.loads(iz[0]["detail"] or "{}")
    assert d.get("profil") == ARS, (
        f"daraltılmış hasta silmesinin izi profili söylemiyor (kapsam '{iz[0]['scope']}'): {d}"
    )


def test_KARSIT_basliksiz_eski_istemci_toplu_silme_izi_profil_TASIMAZ(ortam):
    c, tdb = ortam
    _ai_tohum(tdb)
    r = c.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "all_operators": True})
    assert r.status_code == 200 and r.json()["deleted"] == 2, r.text[:200]
    iz = _iz(tdb, "ai_log.delete_all")
    d = json.loads(iz[0]["detail"] or "{}")
    assert not d.get("profil"), d
    assert d.get("all_operators") is True
