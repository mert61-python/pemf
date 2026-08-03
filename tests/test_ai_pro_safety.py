"""Audit P1 (test-boşluğu): AI Pro OTONOM tedavi güvenlik kapakları (süre-clamp, organ-doğrulama)
davranışsal test edilmiyordu — yalnız route-varlığı. Uçlar kasıtlı auth-muaf olduğundan bu kapaklar
tek koruma; süre-clamp bir refactorda düşerse {duration_minutes:999999} gözetimsiz sürüş açar.
_ai_pro_loop no-op'lanır → kamera/donanım gerekmez."""
import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from servers import api_server
    return TestClient(api_server.app)


def test_ai_pro_duration_capped_to_clinical_max(client, monkeypatch):
    import servers.ai_router as air
    monkeypatch.setattr(air, "_ai_pro_loop", lambda: None)  # loop no-op → kamera/donanım yok
    try:
        r = client.post("/api/ai/pro/start", json={"organ_id": 0, "duration_minutes": 999999})
        assert r.status_code == 200
        # Audit P1: {duration_minutes:999999} klinik üst sınıra (120 dk) KAPANMALI
        assert r.json()["durationMin"] == air._AI_PRO_MAX_DURATION_MIN == 120
    finally:
        client.post("/api/ai/pro/stop")


def test_ai_pro_rejects_unsupported_organ(client):
    # Audit P2: em_kedi yalnız organ 0-6 tedavi eder; 7-10 sessiz-sıfır + yanlış 'aktif' göstergesi
    r = client.post("/api/ai/pro/start", json={"organ_id": 8, "duration_minutes": 20})
    assert r.status_code == 422
    r2 = client.post("/api/ai/pro/organ", json={"organ_id": 9, "duration_minutes": 20})
    assert r2.status_code == 422


def test_ai_pro_double_start_is_idempotent(client, monkeypatch):
    import servers.ai_router as air
    monkeypatch.setattr(air, "_ai_pro_loop", lambda: None)
    try:
        r1 = client.post("/api/ai/pro/start", json={"organ_id": 0, "duration_minutes": 20})
        assert r1.status_code == 200
        r2 = client.post("/api/ai/pro/start", json={"organ_id": 0, "duration_minutes": 20})
        assert r2.status_code == 200
        assert "running" in r2.json().get("message", "").lower()  # ikinci start yeni loop AÇMAZ
    finally:
        client.post("/api/ai/pro/stop")


def test_stop_ai_pro_stops_coil_8_too(client, monkeypatch):
    """DENETIM P1 regresyonu: /api/ai/pro/stop TÜM 8 bobine STOP göndermeli.

    Hata: kapsam range(1,8) idi → bobin 8 atlanıyordu. "AI (Auto)" landmark yolu 8 bobinli
    seans açıp ESP 6,7,8'e duration=1800 publish ediyor ve /ai/pro/start'ı hiç çağırmadığı için
    loop-teardown da yok → açık STOP komutundan sonra bobin 8 ESP'de 30 dk enerjili kalıyordu.
    """
    import servers.api_server as api

    published = []

    class _HW:
        def update_coil(self, *a, **kw):
            return True

        def stop_all_coils(self):
            return True

    monkeypatch.setattr(api.state, "hardware", _HW())
    monkeypatch.setattr(api, "_mqtt_publish",
                        lambda topic, payload: published.append((topic, payload.get("command"))) or True)

    r = client.post("/api/ai/pro/stop")
    assert r.status_code == 200

    stopped_esp = {t.split("/")[2] for t, cmd in published if cmd == "stop" and t.startswith("pemf/coil/")}
    assert {"6", "7", "8"} <= stopped_esp, f"ESP 6-8'in hepsi durdurulmalıydı, gelen: {stopped_esp}"


class _FakeCap:
    """cv2.VideoCapture yerine: her read() geçerli bir kare döndürür."""
    def __init__(self, *a, **kw):
        self.released = False

    def isOpened(self):
        return True

    def read(self):
        import numpy as np
        return True, np.zeros((8, 8, 3), dtype="uint8")

    def release(self):
        self.released = True


def test_external_stop_runs_teardown_and_stops_coils(client, monkeypatch):
    """DENETIM P0 regresyonu: DIŞ durdurma (E-stop / süre-watchdog / /session/stop) algılandığında
    loop, bobinleri durduran teardown'ı ÇALIŞTIRMALI.

    Hata: :623'teki break `_ai_loop_active`'i temizlemiyordu → teardown guard'ı (:730
    `if _ai_loop_active: return`) bunu 'yeni loop başladı' sanıp STOP'u ATLIYORDU. Sürüş
    penceresine denk gelen bir E-stop'tan sonra bobinler keep-alive ile enerjili kalıyordu.
    Bu test kamerasız/donanımsız çalışır: loop ilk iterasyonda seansı pasif görüp çıkar.
    """
    import servers.ai_router as air
    import servers.api_server as api

    monkeypatch.setattr(air.cv2, "VideoCapture", _FakeCap)
    monkeypatch.setattr(air, "_get_or_load_kedi", lambda: None)
    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: None)

    stopped = {"stm": 0, "esp": []}

    class _HW:
        def stop_all_coils(self):
            stopped["stm"] += 1
            return True

    monkeypatch.setattr(api.state, "hardware", _HW())
    monkeypatch.setattr(api, "_mqtt_publish",
                        lambda topic, payload: stopped["esp"].append(topic) or True)

    # Seans DIŞARIDAN durdurulmuş durumda (E-stop / watchdog bunu yapar)
    with api._session_lock:
        api._active_session["is_active"] = False

    air._ai_loop_active = True
    air._ai_pro_loop()          # senkron: ilk iterasyonda dış-stop görüp çıkmalı

    assert air._ai_loop_active is False, "dış durdurma bayrağı temizlemeli (yoksa teardown atlanır)"
    assert stopped["stm"] == 1, "teardown STM bobinlerini durdurmalıydı (guard yanlış atladı)"
    assert any("/6/" in t or "/7/" in t or "/8/" in t for t in stopped["esp"]), \
        "teardown ESP 6-8'e STOP publish etmeliydi"
