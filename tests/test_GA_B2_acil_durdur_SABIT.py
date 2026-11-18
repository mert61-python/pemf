# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) B2 — Y257: ACİL DURDUR'a modül yayılımı eklenmeden ÖNCE mevcut davranışı SABİTLEYEN test (değişiklikten önce ve sonra
AYNI yeşil). Modül hiç kullanılmamışken `_emergency_stop_all`:
  - STM `stop_all_coils` TAM BİR kez; dönüş anahtarları ve durumları aynı; WS yayın sırası (8 bobin durumu → emergency_stop →
    estop_mandali) aynı; ek iş parçacığı / alt süreç YOK; süre kısa.
"""

from __future__ import annotations

import threading
import time

import pytest


@pytest.fixture
def api(monkeypatch):
    from servers import api_server as _api

    olaylar: list[str] = []

    class _HW:
        def stop_all_coils(self):
            olaylar.append("stm_stop")
            return True

    yayinlar: list[str] = []
    monkeypatch.setattr(_api.state, "hardware", _HW())
    monkeypatch.setattr(_api, "_ws_broadcast_sync", lambda m, **k: yayinlar.append(m.get("type")))
    monkeypatch.setattr(_api, "_stm_stop_yazildi_mi", lambda ok, *a: ok)
    monkeypatch.setattr(_api, "_stm_stop_kart_yaniti", lambda *a: "onay")
    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    yield _api, olaylar, yayinlar
    from ai_pro_aparati import istemci, mandali_sifirla

    mandali_sifirla(istemci(_api.app))


def test_KRITIK_GA_B2_SABIT_acil_durdur_modulsuz_DAVRANIS_AYNI(api):
    _api, olaylar, yayinlar = api
    once = {t.name for t in threading.enumerate()}
    t0 = time.monotonic()
    r = _api._emergency_stop_all(reason="ga-sabit", kalici=False)
    sure = time.monotonic() - t0
    assert olaylar == ["stm_stop"]
    assert isinstance(r, dict)
    assert {"status", "stmStopped"} <= set(r)
    assert r["stmStopped"] is True
    assert yayinlar[:8] == ["coil_status"] * 8
    assert yayinlar[8:10] == ["emergency_stop", "estop_mandali"]
    assert sure < 2.0, sure
    yeni = {t.name for t in threading.enumerate()} - once
    assert not any(n.startswith(("estop-moduller", "modul-")) for n in yeni), yeni
