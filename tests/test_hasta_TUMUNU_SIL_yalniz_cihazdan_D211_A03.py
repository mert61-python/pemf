# -*- coding: utf-8 -*-
"""D2.11 · B-2.9 · A-03 — `/api/patients/delete_all` YALNIZ cihazın kendi ekranından (loopback).

ÖLÇÜLEN KUSUR (DENETIM-02 B-2.9): uç yalnız `_enforce_patient_auth` çağırıyordu ve o `PEMF_REQUIRE_PATIENT_AUTH`
varsayılanı "0" ile no-op → klinik Wi-Fi'ındaki HERHANGİ bir cihaz token'sız tek istekle tüm hasta defterini VACUUM'lu
siliyordu (eşi `/api/ai/log/delete_all` aynı gerekçeyle ayrıcalıklı).

KURAL (sahip kararı A-03 — plandan üstün): kliniğin TAMAMINI silme yalnız cihazın KENDİSİNDEN (127.0.0.1 / ::1, tünel ve
ters-proxy loopback SAYILMAZ). Telefon ya da ağdaki başka cihaz — geçerli cihaz token'ıyla da — silemez (ayrıcalıklı
kapıdan DAHA sıkı: `is_privileged_request` LAN + token'ı kabul eder). Red izde `reddedildi`.
GERÇEK: uç (TestClient soket IP'si), hasta DB'si (geçici), denetim izi (geçici tedavi DB'si). Ölçüt ham satır sayısı.
"""

import pytest
from fastapi.testclient import TestClient


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


def _sil(o, ip, headers=None):
    return TestClient(o.api.app, client=(ip, 51734)).post(
        "/api/patients/delete_all", json={"confirm": "DELETE_ALL"}, headers=headers or {}
    )


def test_KRITIK_LAN_tokensiz_TUM_hastalari_SILEMEZ(o):
    """Planın kapısı. MUTASYON: eklenen cihaz denetimini silmek → KIRMIZI."""
    r = _sil(o, "192.168.1.50")
    assert r.status_code == 403, f"LAN token'sız tüm hastaları sildi: {r.status_code} {r.text[:200]}"
    assert _sayi(o) == 2


def test_KRITIK_LAN_GECERLI_token_ile_de_SILEMEZ_A03(o, monkeypatch):
    """A-03: 'Telefon ya da ağdaki başka cihaz silemez' — ayrıcalıklı kapı (loopback VEYA token) burada YETMEZ.
    MUTASYON: denetimi `is_privileged_request`e gevşetmek → KIRMIZI."""
    from servers import auth

    monkeypatch.setattr(auth, "check_token", lambda t: t == "DOGRU-TOKEN")
    r = _sil(o, "192.168.1.50", {"X-API-Key": "DOGRU-TOKEN"})
    assert r.status_code == 403, r.text[:200]
    assert _sayi(o) == 2


def test_KRITIK_TUNEL_istegi_loopback_SAYILMAZ(o):
    """cloudflared 127.0.0.1'den bağlanır — başlıklı istek cihazın kendisi DEĞİLDİR."""
    r = _sil(o, "127.0.0.1", {"cf-ray": "8a1b2c3d4e5f-IST", "cf-connecting-ip": "203.0.113.9"})
    assert r.status_code in (401, 403), r.text[:200]
    assert _sayi(o) == 2


def test_KRITIK_red_IZDE_reddedildi(o):
    _sil(o, "192.168.1.50")
    iz = o.tdb.denetim_oku(50, "patient.delete_all")
    assert [(s["outcome"], s["item_count"]) for s in iz] == [("reddedildi", 0)], iz


def test_KARSIT_cihazin_KENDISI_tumunu_siler(o):
    r = _sil(o, "127.0.0.1")
    assert r.status_code == 200 and r.json().get("deleted") == 2, r.text[:200]
    assert _sayi(o) == 0


def test_KARSIT_onay_dizesi_kapisi_KORUNUR(o):
    r = TestClient(o.api.app, client=("127.0.0.1", 51735)).post("/api/patients/delete_all", json={})
    assert r.status_code == 400 and _sayi(o) == 2, r.text[:200]
