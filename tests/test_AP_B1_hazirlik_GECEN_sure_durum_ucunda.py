# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AP · B1 (S-AP.1, sahip 13 Kasım 2026 "Seans sürsün"): sekme / rota değişiminde web önizlemesi SÜRER; panel yeniden açılınca hazırlık
saatini sunucudaki önizlemenin GEÇEN süresinden sürdürür (`hazirlikGecenSn`, yalnız-ek) — iki 120 sn tavanı aynı anda biter."""

import time

from fastapi.testclient import TestClient


def test_durum_ucu_ONIZLEMENIN_gecen_suresini_verir():
    import servers.ai_router as air
    import servers.api_server as apis

    eski = (air._ai_hazirlik_active, air._ai_hazirlik_started_at)
    try:
        air._ai_hazirlik_active = True
        air._ai_hazirlik_started_at = time.monotonic() - 30.0
        j = TestClient(apis.app).get("/api/ai/pro/status").json()
        assert 29 <= j["hazirlikGecenSn"] <= 32
        air._ai_hazirlik_active = False
        assert TestClient(apis.app).get("/api/ai/pro/status").json()["hazirlikGecenSn"] == 0
    finally:
        air._ai_hazirlik_active, air._ai_hazirlik_started_at = eski
