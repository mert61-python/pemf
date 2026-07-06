"""Kritik GÜVENLİK yolu (audit B-3.1 #1): seans süre-watchdog'u — süresi dolan seansı DONANIM
düzeyinde otomatik durdurur (firmware keep-alive tek başına auto-stop OLMAZ). `with TestClient`
lifespan'i tetikler → watchdog thread'i başlar; süresi geçmiş seans kurulur, tick beklenir."""
import os
import time

os.environ.pop("PEMF_SIMULATE", None)

from fastapi.testclient import TestClient


def test_watchdog_auto_stops_expired_session(monkeypatch):
    from servers import api_server
    # ESP publish'i mock'la (broker yok); STM yok → yalnız watchdog mantığı sınanır.
    monkeypatch.setattr(api_server, "_mqtt_publish", lambda *a, **k: True)

    with TestClient(api_server.app):  # lifespan → _start_background_threads → session-watchdog
        # Süresi DOLMUŞ seans: start_time 2 dk önce, süre 1 dk → total 60s < geçen 120s.
        with api_server._session_lock:
            api_server._active_session.clear()
            api_server._active_session.update({
                "is_active": True,
                "session_id": "wd_test",
                "coil_ids": [6, 7, 8],
                "duration_minutes": 1,
                "start_time": time.time() - 120,
            })
        # Watchdog her 1sn'de kontrol eder → ~3sn içinde is_active=False yapmalı.
        stopped = False
        for _ in range(40):
            time.sleep(0.1)
            with api_server._session_lock:
                if not api_server._active_session.get("is_active"):
                    stopped = True
                    break
        assert stopped, "süre-watchdog süresi dolan seansı durdurmadı (GÜVENLİK regresyonu)"


def test_watchdog_keeps_active_unexpired_session(monkeypatch):
    from servers import api_server
    monkeypatch.setattr(api_server, "_mqtt_publish", lambda *a, **k: True)
    with TestClient(api_server.app):
        with api_server._session_lock:
            api_server._active_session.clear()
            api_server._active_session.update({
                "is_active": True,
                "session_id": "wd_active",
                "coil_ids": [6, 7, 8],
                "duration_minutes": 60,          # 1 saat
                "start_time": time.time(),        # yeni başladı → süre DOLMADI
            })
        time.sleep(1.5)  # watchdog birkaç tick attı
        with api_server._session_lock:
            assert api_server._active_session.get("is_active"), "watchdog süresi dolmamış seansı erken durdurdu"
        # temizle
        with api_server._session_lock:
            api_server._active_session["is_active"] = False
