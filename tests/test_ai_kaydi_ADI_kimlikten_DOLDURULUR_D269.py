# -*- coding: utf-8 -*-
"""D2.69 (B-6.29) arka uç yarısı — AI kaydı hasta KİMLİĞİYLE gelip adı BOŞSA ad hasta defterinden doldurulur.

ÖLÇÜLEN KUSUR: ev sahibi ekranı `/api/ai/log`'a `patient_name: ""` + seçili hastanın `patient_id`'sini gönderiyordu (arayüz yarısı
`aiHubEvSahibiHastaAdi.D269.web.test.tsx`); uç adı kimlikten doldurmadığı için satır `patient_name ''` ile yazılıyordu → ev sahibi
geçmişinde hayvan ayrımı ve ada dayalı görünümler (eski kayıtlarla birlikte gösterim) oluşmuyordu.
Satır SQL ile okunur (ürün okuyucusu değil). Karşıtlar: verilen ad EZİLMEZ; bilinmeyen kimlikte ad UYDURULMAZ; kimliksiz eski
istemci aynen çalışır.
"""

from __future__ import annotations

import pytest

MIA = "u-mia-0001"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from servers import api_server

    kok = tmp_path / "gecmis"
    kok.mkdir()
    d = TreatmentHistoryDB(kok)
    hdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: d)
    monkeypatch.setattr(api_server, "_app_data_dir", lambda: kok)
    monkeypatch.setattr("database.patient_database.get_patient_database", lambda: hdb)
    monkeypatch.setattr(api_server, "_ai_kimlik_tasindi", True)  # tek seferlik taşıma bu kapının konusu değil
    pid = hdb.add_patient({"name": "Mia", "species": "Kedi", "id": MIA})
    c = TestClient(api_server.app, client=("127.0.0.1", 50123))
    return d, c, pid


def _satirlar(d):
    with d._get_connection() as c:
        return [
            tuple(r) for r in c.execute("SELECT patient_uuid, patient_name FROM ai_analyses ORDER BY id").fetchall()
        ]


def test_KRITIK_ad_BOS_kimlik_DOLU_gelen_kayit_hastanin_ADIYLA_yazilir(o):
    d, c, pid = o
    r = c.post(
        "/api/ai/log",
        json={"patient_name": "", "patient_id": pid, "module": "FGS", "summary": "s", "module_id": "landmark"},
    )
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    assert _satirlar(d) == [(pid, "Mia")], "ad kimlikten doldurulmadı (ev sahibi geçmişinde hayvan ayrımı oluşmaz)"


def test_KARSIT_verilen_ad_EZILMEZ(o):
    d, c, pid = o
    c.post("/api/ai/log", json={"patient_name": "Mia (eski ad)", "patient_id": pid, "module": "m", "summary": "s"})
    assert _satirlar(d) == [(pid, "Mia (eski ad)")]


def test_KARSIT_bilinmeyen_kimlikte_ad_UYDURULMAZ_kayit_DUSMEZ(o):
    d, c, _pid = o
    r = c.post("/api/ai/log", json={"patient_name": "", "patient_id": "yok-kimlik", "module": "m", "summary": "s"})
    assert r.json().get("status") == "success"
    assert _satirlar(d) == [("yok-kimlik", "")]


def test_KARSIT_kimliksiz_eski_istemci_AYNEN(o):
    d, c, _pid = o
    c.post("/api/ai/log", json={"patient_name": "Pamuk", "module": "m", "summary": "s"})
    assert _satirlar(d) == [("", "Pamuk")]


def test_KARSIT_A01_LAN_istemcisi_de_ayni_kurala_tabi(o):
    """A-01 (LAN güvenilir ağ): telefon/LAN istemcisinin kaydı da kimlikten adlanır; erişim sınıfı değişmez."""
    from fastapi.testclient import TestClient
    from servers import api_server

    d, _c, pid = o
    lan = TestClient(api_server.app, client=("192.168.1.77", 50124))
    r = lan.post("/api/ai/log", json={"patient_name": "", "patient_id": pid, "module": "m", "summary": "s"})
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    assert _satirlar(d) == [(pid, "Mia")]
