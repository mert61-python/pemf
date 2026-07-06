"""Characterization: sistem/durum GET uçlarının RESPONSE SHAPE'i (anahtar kümesi).

Route-contract PATH'i korur; bu test RESPONSE gövdesinin anahtar-kümesini dondurur →
extraction sırasında bir handler'ın çıktı-şekli (ör. transkripsiyon hatası, eksik alan)
değişirse KIRILIR. Özellikle `/api/health` kurulum-doğrulaması (`atRestEncrypted`,
`status`) için kritik.

Baseline: 2026-07-06. Client kurulumu test_api_safety ile aynı (PEMF_SIMULATE kapalı).
"""
import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient

GOLDEN_SHAPES = {
    "/api/health": {
        "atRestEncrypted", "core_initialized", "deviceId", "localIp", "pairingCode",
        "service", "services", "status", "stmConnected", "tunnelUrl",
    },
    "/api/discovery": {"capabilities", "localIp", "port", "service", "tunnelUrl", "version"},
    "/api/system/info": {
        "deviceId", "hardwareVersion", "pairingCode", "softwareVersion",
        "stmConnected", "timestamp", "tunnelUrl",
    },
    "/api/gateway/status": {
        "bridgeConnected", "brokerRunning", "gatewayState", "hotspotActive", "mosquitto",
        "mqttConnected", "network", "networkOnline", "stmConnected",
    },
    "/api/kpi/summary": {
        "avgDurationMin", "coilUsage", "completedSessions", "last7Days",
        "modeDistribution", "stoppedSessions", "totalSessions",
    },
}


@pytest.fixture(scope="module")
def client():
    from servers import api_server

    return TestClient(api_server.app)


@pytest.mark.parametrize("path,expected_keys", sorted(GOLDEN_SHAPES.items()))
def test_status_endpoint_shape(client, path, expected_keys):
    r = client.get(path)
    assert r.status_code == 200, f"{path} -> HTTP {r.status_code}"
    assert set(r.json().keys()) == expected_keys, f"{path} response anahtar-kümesi DEĞİŞTİ"
