# Author: mertaygn, cglrgrkn
"""D3.06 (B-2.8) — `/api/v1/*` yeniden yazımı rate-limit'ten ÖNCE: sağlık / keşif muafiyeti takma adda da geçerli; ACİL DURDUR aynen.

ÖLÇÜLEN (HEAD): yeniden yazım yalnız auth katmanının içindeydi; rate-limit auth'tan SONRA eklendiği için (Starlette'te son eklenen en
dışta koşar) yeniden-yazılMAMIŞ yolu görüyordu → uzak istemci, limit=3: `/api/v1/health` ×5 = [200, 200, 200, 429, 429]; aynısı
`/api/v1/discovery`. `/api/v1/hardware/emergency_stop` alt dize denetimiyle zaten muaftı (Y8 kolu — korunur).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def uzak(monkeypatch):
    from servers import api_server as api

    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 3)
    api._rl_hits.clear()
    yield TestClient(api.app, client=("203.0.113.61", 51306)), api
    api._rl_hits.clear()


@pytest.mark.parametrize("yol", ["/api/v1/health", "/api/v1/discovery"])
def test_KRITIK_D3_06_v1_saglik_ve_kesif_RATE_LIMIT_disi(uzak, yol):
    c, _ = uzak
    kodlar = [c.get(yol).status_code for _ in range(5)]
    assert 429 not in kodlar, f"{yol} takma adda sınırlandı: {kodlar}"


def test_KRITIK_D3_06_v1_ACIL_DURDUR_sinirlanmaz_Y8(uzak, monkeypatch):
    c, api = uzak
    kodlar = [c.post("/api/v1/hardware/emergency_stop").status_code for _ in range(5)]
    assert 429 not in kodlar, f"ACİL DURDUR takma adda sınırlandı: {kodlar}"


def test_KARSIT_D3_06_v1_korumali_uc_YINE_sinirlanir(uzak):
    c, _ = uzak
    kodlar = [c.get("/api/v1/system/info").status_code for _ in range(5)]
    assert 429 in kodlar, f"takma ad rate-limit'i TAMAMEN atlattı: {kodlar}"


def test_YAPISAL_D3_06_takma_ad_katmani_rate_limitin_DISINDA():
    from servers import api_server as api

    sinif = [m.cls.__name__ if hasattr(m, "cls") else str(m) for m in api.app.user_middleware]
    assert "_ApiV1TakmaAdi" in sinif, sinif
    i_takma = sinif.index("_ApiV1TakmaAdi")
    http_katmanlari = [i for i, ad in enumerate(sinif) if ad == "BaseHTTPMiddleware"]
    assert http_katmanlari and all(i_takma < i for i in http_katmanlari), (
        f"takma ad katmanı bir @app.middleware('http') katmanının İÇİNDE (user_middleware[0] en dıştır): {sinif}"
    )
