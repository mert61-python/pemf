# Author: mertaygn, cglrgrkn
"""D3.01 (B-10.17) — uzak (tünel) istemciye `pairingCode` / `tunnelUrl` / `deviceId` SIZDIRILMAZ: DAVRANIŞLA, üç uçta.

ÖLÇÜLEN KÖR KAPI: `test_kalan_davranissal::test_system_info_UZAK_istemciye_tunel_ve_eslestirme_SIZDIRMAZ` yalnız `system_router`
KAYNAK METNİNDE alan satırında `_local` geçiyor mu diye bakıyordu (ilk eşleşme = `system_info`); `/api/health` ve `/api/discovery`
hiç ölçülmüyordu ve `_local`'in NASIL hesaplandığı (proxy başlığı) görünmüyordu. `_local` düşerse K1 zinciri (health → kod →
`/api/auth/exchange` → token) tünelden yeniden açılır.
SÖZLEŞME: tünel başlığı (cf-connecting-ip / cf-ray / x-forwarded-for) taşıyan ya da LAN dışı kaynaklı istek UZAKTIR → üç alan `None`
(yanıt gövdesinde değerler HİÇ geçmez); loopback ve LAN (A-01: LAN güvenilir ağ) yereldir → değerler gelir. Sahte yalnız EN ALT
katta: kod / tünel / cihaz kimliği üreticileri.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

KOD = "739215"
TUNEL = "https://d3-01-ornek-tunel.trycloudflare.com"
CIHAZ = "PEMF-D301-SAHTE"
UCLAR = ("/api/health", "/api/discovery", "/api/system/info")
# Uçların hangi alanı taşıdığı (discovery yalnız tunnelUrl taşır).
ALANLAR = {
    "/api/health": ("pairingCode", "tunnelUrl", "deviceId"),
    "/api/discovery": ("tunnelUrl",),
    "/api/system/info": ("pairingCode", "tunnelUrl", "deviceId"),
}
DEGER = {"pairingCode": KOD, "tunnelUrl": TUNEL, "deviceId": CIHAZ}


@pytest.fixture
def istemci(monkeypatch):
    import servers.tunnel_manager as tm
    import utils.path_utils as pu
    from servers import api_server

    monkeypatch.setattr(pu, "get_pairing_code", lambda *a, **k: KOD)
    monkeypatch.setattr(pu, "get_unique_device_id", lambda *a, **k: CIHAZ)
    monkeypatch.setattr(tm, "get_tunnel_url", lambda *a, **k: TUNEL)

    def _yap(host: str):
        return TestClient(api_server.app, client=(host, 51301))

    return _yap


UZAK = [
    pytest.param("127.0.0.1", {"cf-connecting-ip": "203.0.113.9"}, id="tunel-cf-connecting-ip"),
    pytest.param("127.0.0.1", {"cf-ray": "8a1b2c3d4e5f-IST"}, id="tunel-cf-ray"),
    pytest.param("192.168.1.20", {"x-forwarded-for": "203.0.113.9"}, id="lan-ustunden-proxy"),
    pytest.param("203.0.113.9", {}, id="lan-disi-kaynak"),
]


@pytest.mark.parametrize("uc", UCLAR)
@pytest.mark.parametrize(("host", "basliklar"), UZAK)
def test_KRITIK_D3_01_uzak_istemciye_kod_tunel_cihaz_kimligi_SIZMAZ(istemci, uc, host, basliklar):
    r = istemci(host).get(uc, headers=basliklar)
    for deger in (KOD, TUNEL, CIHAZ):
        assert deger not in r.text, f"{uc} uzak istemciye {deger!r} sızdırdı ({host}, {basliklar}): {r.text[:300]}"
    if r.status_code == 200:
        govde = r.json()
        for alan in ALANLAR[uc]:
            assert alan in govde and govde[alan] is None, f"{uc} {alan} uzakta None değil: {govde.get(alan)!r}"


@pytest.mark.parametrize("uc", UCLAR)
@pytest.mark.parametrize("host", ["127.0.0.1", "192.168.1.20"], ids=["loopback", "lan-A01"])
def test_KARSIT_D3_01_yerel_ve_LAN_istemci_degerleri_ALIR(istemci, uc, host):
    r = istemci(host).get(uc)
    assert r.status_code == 200, f"{uc} yerelde {r.status_code}"
    govde = r.json()
    for alan in ALANLAR[uc]:
        assert govde.get(alan) == DEGER[alan], f"{uc} {alan} yerelde gelmedi (kapı kör olurdu): {govde.get(alan)!r}"
