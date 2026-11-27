# -*- coding: utf-8 -*-
"""I18NI-A3.2 — GPU AI profili (`ai_service` mikroservisi) panel adlarını çeviremez → backend panel adlarını İSTEK dilinde kurar.

Y344 (sahip 27-11, istem 66 CT2 f3): Docker dağıtımı emekli — imaj (`docker/Dockerfile.ai`) COPY listesine dayanan iki kol
(imajdaki `utils` modüllerinin geçişli bağımlılıkları + yalıtılmış alt süreçte içe aktarma) dosyayla birlikte kaldırıldı (git geçmişinde).
Kalan kol ÜRÜNÜ ölçer: backend GPU profiline devrederken (`ai_service_enabled`) panel adlarını istek dilinde kurar.
"""

from __future__ import annotations

# ── (3) GPU profili: servis katalog taşımaz → backend panel adlarını İSTEK dilinde kurmalı ───────────────────────────────────────


def _gpu_yaniti():
    # Servis (düzeltme sonrası) çeviri yapamaz → `ad` = ham panel anahtarı; eski servis Türkçe göndermiş olabilir (ikisi de çevrilmeli).
    return {
        "status": "success",
        "image_base64": "",
        "paneller": [
            {"k": "01_input", "ad": "01_input", "image_base64": "", "image_w": 1, "image_h": 1},
            {"k": "07_combined", "ad": "Birleşik", "image_base64": "", "image_w": 1, "image_h": 1},
            {"k": "zz_bilinmeyen", "ad": "zz_bilinmeyen", "image_base64": "", "image_w": 1, "image_h": 1},
        ],
    }


import pytest  # noqa: E402


@pytest.mark.parametrize("uc,tablo", [("em_fantom", "PANEL_ADLARI"), ("em_petri", "PETRI_PANEL_ADLARI")])
@pytest.mark.parametrize("dil", ["tr", "en"])
def test_gpu_profili_panel_adlari_istek_dilinde(monkeypatch, uc, tablo, dil):
    import i18n_yardimci as iy
    from fastapi.testclient import TestClient
    from servers import ai_router, api_server
    from utils import panel_yayin

    async def _sahte_devret(name, label=None, **kw):
        return _gpu_yaniti()

    monkeypatch.setattr(ai_router, "ai_service_enabled", lambda: True)
    monkeypatch.setattr(ai_router, "_kapili_devret", _sahte_devret)
    c = TestClient(api_server.app, client=("127.0.0.1", 51241))
    r = c.post(f"/api/ai/vision/{uc}", files={"file": ("t.jpg", b"x", "image/jpeg")}, headers={"X-PEMF-Dil": dil})
    assert r.status_code == 200, r.text[:300]
    adlar = getattr(panel_yayin, tablo)
    kat = iy.katalog("sunucu", dil)
    got = {p["k"]: p["ad"] for p in r.json()["paneller"]}
    assert got["01_input"] == kat[adlar["01_input"]], got
    assert got["07_combined"] == kat[adlar["07_combined"]], got
    assert got["zz_bilinmeyen"] == "zz_bilinmeyen", got
