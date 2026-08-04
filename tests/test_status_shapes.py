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
        # DENETIM P2 (BILINCLI sekil degisikligi): bulut cihaz-registry durumu. 'secret_mismatch'
        # KALICI bir hatadir (TOFU muhru — yeniden kurulum sonrasi device_secret degisti) ve
        # eskiden yalnizca log'a dusuyordu; operator uzaktan erisimin neden sessizce
        # guncellenmedigini goremiyordu. Bu test tam da sekil degisikliklerini yakalamak icin
        # var → altin kume kasitli olarak genisletildi.
        "cloudRegistry",
        # DENETIM 2026-08-04 P2 #13 (BILINCLI sekil degisikligi): launcher'in "bu porttaki
        # GERCEKTEN benim baslattigim backend mi?" dogrulamasi. find_free_port portu bind edip
        # hemen birakiyor; o pencerede portu kapan yerel bir surec HTTP 200 dondugu icin "hazir"
        # saniliyordu → kapanistaki E-stop POST'u ONA gidiyor, gercek bobinler hastanin uzerinde
        # kaliyordu. Deger YALNIZ loopback'e verilir (tunele/LAN'a sizarsa dogrulama anlamsiz);
        # `PEMF_HEALTH_NONCE` verilmemisse None doner. Bkz. launcher/core/src/backend.rs.
        "launcherNonce",
        # DENETIM 2026-08-04 (BILINCLI sekil degisikligi): launcher oto-guncellemesi acilista
        # SESSIZCE `/S` kurulum yapar; NSIS yukseltme kancasi PEMF_Backend.exe'yi oldurur →
        # HASTA UZERINDE SUREN seans yarida kesilirdi. Launcher artik guncellemeden ONCE bunu
        # okuyup seans varsa ERTELIYOR. launcherNonce ile ayni gerekcede YALNIZ loopback'e verilir
        # (auth-muaf + tunelden erisilebilir bir uc; "su an tedavi suruyor" disari sizmamali).
        "sessionActive",
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
