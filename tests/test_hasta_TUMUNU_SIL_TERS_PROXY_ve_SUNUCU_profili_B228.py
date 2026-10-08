# -*- coding: utf-8 -*-
"""B2-2.8 (2-B bağımsız inceleme · A2) — A-03 `delete_all`: başlıksız ters-proxy ve `server` profili (loopback'e bağlı + kimlik
kipi) "cihazın kendisi" SAYILMAZ.

ÖLÇÜLEN KÖR NOKTA: D2.11 `cihazin_kendisinden_mi` docstring'i/raporu "`is_loopback_request` (tünel/ters-proxy başlığı ve
loopback-bağlı + kimlik kipi fail-closed kuralı dahil)" diyor; `tests/test_hasta_TUMUNU_SIL_yalniz_cihazdan_D211_A03.py` yalnız
LAN, LAN+token ve tünel BAŞLIKLI kolları ölçüyor. Yardımcıyı düz "soket 127.0.0.1/::1 ve başlık yok" denetimine indirgeyen
mutant (k6e) D2.11 + D2.43 + ayrıcalıklı uçlar + auth + api_design kümesinde 67/67 YEŞİL (ölçüldü, `kayit/k6_mutasyon.txt`) —
o hâlde `deploy/server.env` (PEMF_API_HOST=127.0.0.1 + PEMF_REQUIRE_AUTH=1) kurulumunda X-Forwarded-For EKLEMEYEN bir nginx
arkasından gelen İNTERNET isteği (soket 127.0.0.1, başlıksız) tüm hasta defterini silebilirdi. Bugünkü ürün DOĞRU (HEAD'de yeşil).
"""

from __future__ import annotations

import ipaddress

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
        hdb.add_patient({"name": f"P{i}", "species": "Kedi"})
    try:
        yield type("O", (), {"hdb": hdb, "c": TestClient(api.app, client=("127.0.0.1", 52534))})
    finally:
        tdb.close_connections()


def test_KRITIK_sunucu_profili_basliksiz_ters_proxy_TUMUNU_SILEMEZ(o, monkeypatch):
    """server profili: backend loopback'e bağlı + kimlik kipi → 127.0.0.1'den gelen her istek proxy'dendir."""
    from servers import auth

    monkeypatch.setattr(auth, "_LOOPBACK_BIND", True)
    monkeypatch.setattr(auth, "_require", True)
    r = o.c.post(
        "/api/patients/delete_all", json={"confirm": "DELETE_ALL"}, headers={"X-API-Key": auth.get_api_token()}
    )
    assert (r.status_code, o.hdb.count_patients()) == (403, 2), (
        f"sunucu profilinde ters-proxy isteği tüm defteri sildi: {r.status_code}"
    )


def test_KRITIK_beyanli_ters_proxydan_TUMUNU_SILEMEZ(o, monkeypatch):
    from servers import auth

    monkeypatch.setattr(auth, "_TRUSTED_PROXIES", [ipaddress.ip_network("127.0.0.1/32")])
    r = o.c.post("/api/patients/delete_all", json={"confirm": "DELETE_ALL"})
    assert (r.status_code, o.hdb.count_patients()) == (403, 2), (
        f"PEMF_TRUSTED_PROXIES'teki adresten gelen istek sildi: {r.status_code}"
    )


def test_KARSIT_klinik_profili_cihazin_kendisi_SILER(o, monkeypatch):
    from servers import auth

    monkeypatch.setattr(auth, "_LOOPBACK_BIND", False)
    monkeypatch.setattr(auth, "_TRUSTED_PROXIES", [])
    r = o.c.post("/api/patients/delete_all", json={"confirm": "DELETE_ALL"})
    assert (r.status_code, o.hdb.count_patients()) == (200, 0), r.text[:200]
