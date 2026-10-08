# -*- coding: utf-8 -*-
"""D2.22 (B-3.85) — AI analizlerinde ad→kimlik geri doldurması KALICI tek seferliktir (DB'de işaret).

ÖLÇÜLEN KUSUR: `_ai_hasta_kimliklerini_tasi_bir_kez` "bir kez"i yalnız SÜREÇ bayrağıyla (`_ai_kimlik_tasindi`) tutuyordu →
her backend açılışında yeniden koşuyordu. İlk koşuda aynı adlı iki hayvan yüzünden BİLEREK kimliksiz bırakılan eski bir analiz,
sonradan hayvanlardan biri silinip ad TEKİLLEŞİNCE bir sonraki açılışta kalan hayvanın kimliğine bağlanıyordu — belirsiz bir ad
eşleşmesi geri alınamaz bir kimliğe dönüşüyor, kimlikli süzgeçler kaydı o hayvanınmış gibi sayıyordu. 1.9.50'de YOK (taşıma
`ac9ea3c`, 09-15); HEAD tabanlı ilk derlemeyle sahaya girerdi.
Kapı GERÇEK taşımayı, GERÇEK hasta defterini (`PatientDatabase` + `delete_patient`) ve GERÇEK tedavi DB'sini kullanır; yeniden
başlatma = süreç bayrağının sıfırlanması (DB aynı). Satırın kimliği SQL ile okunur.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from servers import api_server

    kok = tmp_path / "gecmis"
    kok.mkdir()
    d = TreatmentHistoryDB(kok)
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: d)
    monkeypatch.setattr(api_server, "_app_data_dir", lambda: kok)
    monkeypatch.setattr("database.patient_database.get_patient_database", lambda: pdb)
    monkeypatch.setattr(api_server, "_ai_kimlik_tasindi", False)
    c = TestClient(api_server.app, client=("127.0.0.1", 50222))
    return api_server, d, pdb, c


def _kimlik(d, ozet: str) -> str:
    with d._get_connection() as c:
        return c.execute(
            "SELECT COALESCE(patient_uuid,'') FROM ai_analyses WHERE result_summary = ?", (ozet,)
        ).fetchone()[0]


def _yeniden_baslat(api_server):
    api_server._ai_kimlik_tasindi = False  # süreç bayrağı sıfırlanır; DB aynı (açılış benzetimi)


def test_KRITIK_ilk_kosuda_BELIRSIZ_birakilan_analiz_ad_tekillesince_yeniden_acilista_BAGLANMAZ(o):
    api, d, pdb, _c = o
    mia_a = pdb.add_patient({"name": "Mia", "species": "Kedi"})
    mia_b = pdb.add_patient({"name": "Mia", "species": "Köpek"})
    d.add_ai_analysis(module_id="landmark", patient_name="Mia", result_summary="ESKI-MIA")
    api._ai_hasta_kimliklerini_tasi_bir_kez(d)
    assert _kimlik(d, "ESKI-MIA") == "", "ön koşul: aynı adlı iki hayvanda belirsiz analiz kimliksiz kalmalı"
    assert pdb.delete_patient(mia_b), "ön koşul: ikinci Mia silinmeli (ad tekilleşir)"
    _yeniden_baslat(api)
    api._ai_hasta_kimliklerini_tasi_bir_kez(d)
    assert _kimlik(d, "ESKI-MIA") == "", (
        f"belirsiz eski analiz yeniden açılışta kalan hayvana ({mia_a}) BAĞLANDI — taşıma tek seferlik değil"
    )


def test_KRITIK_GERCEK_uc_yolu_yeniden_acilista_tasimayi_TEKRARLAMAZ(o):
    """Aynı senaryo, taşımayı tetikleyen GERÇEK yazma yoluyla (`POST /api/ai/log`)."""
    api, d, pdb, c = o
    pdb.add_patient({"name": "Mia", "species": "Kedi"})
    mia_b = pdb.add_patient({"name": "Mia", "species": "Köpek"})
    d.add_ai_analysis(module_id="landmark", patient_name="Mia", result_summary="ESKI-MIA")
    assert (
        c.post("/api/ai/log", json={"module": "m", "summary": "yeni-1", "patient_name": "X"}).json()["status"]
        == "success"
    )
    pdb.delete_patient(mia_b)
    _yeniden_baslat(api)
    assert (
        c.post("/api/ai/log", json={"module": "m", "summary": "yeni-2", "patient_name": "X"}).json()["status"]
        == "success"
    )
    assert _kimlik(d, "ESKI-MIA") == ""


def test_KARSIT_ilk_ve_tek_kosuda_TEKIL_ad_yine_baglanir(o):
    api, d, pdb, _c = o
    pamuk = pdb.add_patient({"name": "Pamuk", "species": "Kedi"})
    d.add_ai_analysis(module_id="landmark", patient_name="Pamuk", result_summary="ESKI-PAMUK")
    api._ai_hasta_kimliklerini_tasi_bir_kez(d)
    assert _kimlik(d, "ESKI-PAMUK") == pamuk


def test_KARSIT_tasima_DUSERSE_isaret_konmaz_sonraki_acilista_yeniden_denenir(o, monkeypatch):
    api, d, pdb, _c = o
    pamuk = pdb.add_patient({"name": "Pamuk", "species": "Kedi"})
    d.add_ai_analysis(module_id="landmark", patient_name="Pamuk", result_summary="ESKI-PAMUK")
    with monkeypatch.context() as m:
        m.setattr(d, "ai_analiz_kimliklerini_doldur", lambda harita: (_ for _ in ()).throw(RuntimeError("disk")))
        api._ai_hasta_kimliklerini_tasi_bir_kez(d)
    assert _kimlik(d, "ESKI-PAMUK") == ""
    _yeniden_baslat(api)
    api._ai_hasta_kimliklerini_tasi_bir_kez(d)
    assert _kimlik(d, "ESKI-PAMUK") == pamuk, "düşen taşıma işaret koyup kalıcı olarak atlandı"
