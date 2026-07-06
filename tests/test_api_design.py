"""API tasarımı (audit B-8.1, B-8.2): tek versiyon kaynağı + /api/v1 alias + X-API-Version header;
/api/patients pagination (geriye-uyumlu) + delete_all kazara-silme koruması (confirm)."""
import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def api():
    from servers import api_server
    return api_server


@pytest.fixture(scope="module")
def client(api):
    return TestClient(api.app)


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
    assert body["status"] == "success"      # eski sözleşme korunur
    assert "data" in body and isinstance(body["data"], list)
    assert "total" in body                   # yeni alan (eski istemci yok sayar)


def test_patients_pagination_limits(client):
    r = client.get("/api/patients?limit=1&offset=0")
    assert r.status_code == 200
    assert len(r.json()["data"]) <= 1


def test_delete_all_requires_confirmation(client):
    # confirm YOK / yanlış → 400 (kazara toplu-silme engellenir)
    assert client.post("/api/patients/delete_all", json={}).status_code == 400
    assert client.post("/api/patients/delete_all", json={"confirm": "yanlis"}).status_code == 400


def test_delete_all_with_confirmation_succeeds(client):
    r = client.post("/api/patients/delete_all", json={"confirm": "DELETE_ALL"})
    assert r.status_code == 200
    assert r.json()["status"] == "success"
