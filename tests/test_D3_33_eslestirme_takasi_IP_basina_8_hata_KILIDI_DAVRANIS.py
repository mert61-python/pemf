# Author: mertaygn, cglrgrkn
"""D3.33 (B-10.15) — `/api/auth/exchange` IP başına 8 yanlış kodda 60 sn KİLİT: DAVRANIŞLA.

ÖLÇÜLEN KÖR KAPI: auth testleri kilidi davranışla ölçmüyordu (plan: `_bkt['fails'] += 1` silinince 16 test YEŞİL kalıyordu) —
tünelden erişilen, kimlikten muaf eşleştirme ucunda 6 haneli koda kaba kuvvet açılırdı.
SÖZLEŞME: aynı istemciden 8 yanlış kod 403; 9. istek (DOĞRU kod olsa bile) 429; kilit başka istemciyi etkilemez; doğru kod sayacı
sıfırlar; süre dolunca doğru kod geçer. Sahte yalnız EN ALT katta: eşleştirme kodu (sır deposu) ve cihaz jetonu.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

KOD = "482913"


@pytest.fixture
def uc(monkeypatch):
    import servers.auth as auth
    import utils.secrets_manager as sm
    from servers import api_server
    from servers import auth_router as ar

    monkeypatch.setattr(sm, "get_secret", lambda ad, *a, **k: KOD if ad == "pairing_code" else "")
    monkeypatch.setattr(auth, "get_api_token", lambda *a, **k: "d3-33-sahte-jeton")
    monkeypatch.setattr(ar, "_exchange_throttle", {})

    def _gonder(host: str, kod: str, basliklar: dict | None = None):
        c = TestClient(api_server.app, client=(host, 51333))
        return c.post("/api/auth/exchange", json={"code": kod}, headers=basliklar or {})

    return _gonder, ar


def test_KRITIK_D3_33_sekiz_yanlis_koddan_sonra_DOGRU_kod_da_429(uc):
    gonder, ar = uc
    for i in range(8):
        r = gonder("192.168.1.30", "000000")
        assert r.status_code == 403, f"{i + 1}. yanlış kod {r.status_code}"
    r = gonder("192.168.1.30", KOD)
    assert r.status_code == 429, f"8 hatadan sonra kilit YOK ({r.status_code}) — kaba kuvvet açık"
    assert "d3-33-sahte-jeton" not in r.text


def test_KARSIT_D3_33_kilit_BASKA_istemciyi_etkilemez_ve_sure_dolunca_acilir(uc):
    gonder, ar = uc
    for _ in range(8):
        gonder("192.168.1.30", "000000")
    assert gonder("192.168.1.31", KOD).json().get("token") == "d3-33-sahte-jeton", "kilit başka istemciyi de kilitledi"
    for kova in ar._exchange_throttle.values():
        kova["until"] = 0.0  # 60 sn geçti
    assert gonder("192.168.1.30", KOD).json().get("token") == "d3-33-sahte-jeton"


def test_KARSIT_D3_33_dogru_kod_sayaci_SIFIRLAR(uc):
    gonder, ar = uc
    for _ in range(7):
        assert gonder("192.168.1.30", "000000").status_code == 403
    assert gonder("192.168.1.30", KOD).status_code == 200
    for _ in range(7):
        assert gonder("192.168.1.30", "000000").status_code == 403, "doğru kod sayacı sıfırlamadı"
