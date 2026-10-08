# Author: mertaygn, cglrgrkn
"""API tasarımı (audit B-8.1, B-8.2): tek versiyon kaynağı + /api/v1 alias + X-API-Version header;
/api/patients pagination (geriye-uyumlu) + delete_all kazara-silme koruması (confirm)."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def api():
    from servers import api_server

    return api_server


@pytest.fixture(scope="module")
def client(api):
    return TestClient(api.app)


@pytest.fixture(scope="module")
def cihaz(api):
    """Cihazın KENDİSİ (loopback). ⚠️ D2.11 · A-03: `delete_all` yalnız buradan; erişim kapısı
    tests/test_hasta_TUMUNU_SIL_yalniz_cihazdan_D211_A03.py'de — bu dosya onay İŞLEVİNİ test eder."""
    return TestClient(api.app, client=("127.0.0.1", 51236))


# ── B-8.1: versiyon tutarlılığı + versiyonlama ────────────────────────────────
def test_version_single_source_consistent(client, api):
    from utils.path_utils import get_app_version

    v = get_app_version()
    assert api.app.version == v
    assert client.get("/api/discovery").json()["version"] == v
    assert client.get("/api/system/info").json()["softwareVersion"] == v


def test_x_api_version_header(client, api):
    from utils.path_utils import get_app_version

    r = client.get("/api/health")
    assert r.headers.get("X-API-Version") == get_app_version()


def test_api_v1_alias_routes_to_handler(client):
    # /api/v1/* → /api/* handler (route çoğaltmadan; eski /api de çalışır)
    assert client.get("/api/v1/health").json()["status"] == "online"
    assert client.get("/api/health").json()["status"] == "online"


# ── B-8.2: pagination + delete_all guard ──────────────────────────────────────
def test_patients_pagination_backward_compatible(client):
    r = client.get("/api/patients")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"  # eski sözleşme korunur
    assert "data" in body and isinstance(body["data"], list)
    assert "total" in body  # yeni alan (eski istemci yok sayar)


def test_patients_pagination_limits(client):
    """⚠️ D1.36 (B-10.110): eskiden `len(data) <= 1` hasta YOKKEN de doğruydu (0 ≤ 1) — sayfalama
    hiç ölçülmüyordu (`limit` yok sayılsa YEŞİL). Artık ≥2 hasta oluşturulur; limit=1 TAM 1 kayıt,
    limit=2 TAM 2 kayıt (her şeyi 1'e kesen mutanta karşı), offset bir sonraki kaydı verir."""
    eklenen = []
    try:
        for ad in ("SayfaA", "SayfaB"):
            r = client.post("/api/patients", json={"name": ad, "species": "kedi"})
            assert r.status_code == 200 and r.json()["status"] == "success", r.text[:200]
            eklenen.append(r.json()["patient_id"])
        r1 = client.get("/api/patients?limit=1&offset=0")
        assert r1.status_code == 200
        assert r1.json()["total"] >= 2
        assert len(r1.json()["data"]) == 1, f"limit=1 → {len(r1.json()['data'])} kayıt"
        r2 = client.get("/api/patients?limit=2&offset=0").json()["data"]
        assert len(r2) == 2, f"limit=2 → {len(r2)} kayıt"
        r3 = client.get("/api/patients?limit=1&offset=1").json()["data"]
        assert len(r3) == 1 and r3[0]["id"] != r1.json()["data"][0]["id"], "offset sonraki kaydı vermiyor"
    finally:
        for pid in eklenen:
            client.delete(f"/api/patients/{pid}")


def test_delete_all_requires_confirmation(cihaz):
    # confirm YOK / yanlış → 400 (kazara toplu-silme engellenir)
    assert cihaz.post("/api/patients/delete_all", json={}).status_code == 400
    assert cihaz.post("/api/patients/delete_all", json={"confirm": "yanlis"}).status_code == 400


def test_delete_all_with_confirmation_succeeds(cihaz):
    r = cihaz.post("/api/patients/delete_all", json={"confirm": "DELETE_ALL"})
    assert r.status_code == 200
    assert r.json()["status"] == "success"
