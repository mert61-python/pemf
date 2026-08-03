"""Kritik yol: bobin transport yönlendirmesi (STM 1-5 → HardwareController, ESP 6-8 → MQTT) +
geçersiz bobin reddi + toplu (batch) yönlendirme + durdurma mekanizması. Donanım/broker mock'lanır."""
import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def api():
    from servers import api_server
    return api_server


@pytest.fixture(scope="module")
def client(api):
    return TestClient(api.app)


@pytest.fixture()
def mocked_hw(api, monkeypatch):
    """state.hardware (STM) + _mqtt_publish (ESP) çağrılarını yakalar."""
    calls = {"stm": [], "mqtt": []}

    class FakeHW:
        # İmza GERÇEK HardwareController.update_coil ile aynı olmalı; duration_seconds
        # (DENETIM P3: dakikaya yuvarlanmış süre yerine hassas saniye) kaydedilir ki
        # aşağıdaki test onun GERÇEKTEN iletildiğini doğrulayabilsin.
        def update_coil(self, coil_id, freq, duty, phase, duration, start=True,
                        duration_seconds=None):
            calls["stm"].append({"coil": coil_id, "start": start,
                                 "duration_min": duration, "duration_seconds": duration_seconds})
            return True

        def stop_all_coils(self):
            calls["stm"].append({"stop_all": True})
            return True

    monkeypatch.setattr(api.state, "hardware", FakeHW())
    monkeypatch.setattr(api.state, "core", object())  # /api/hardware/command core+hardware ister
    monkeypatch.setattr(api, "_mqtt_publish",
                        lambda topic, payload: (calls["mqtt"].append(topic) or True))
    # Aktif seans kalıntısını temizle (coil-run DB yan-etkisi olmasın).
    with api._session_lock:
        api._active_session.clear()
    return calls


def test_stm_coil_routes_to_hardware(client, mocked_hw):
    r = client.post("/api/coil/3/control", json={"freq": 50, "duty": 25, "start": True})
    assert r.status_code == 200
    assert r.json()["transport"] == "stm32"
    assert any(c.get("coil") == 3 for c in mocked_hw["stm"])
    assert not mocked_hw["mqtt"]  # STM bobini MQTT'ye GİTMEZ


def test_esp_coil_routes_to_mqtt(client, mocked_hw):
    r = client.post("/api/coil/7/control", json={"freq": 50, "duty": 25, "start": True})
    assert r.status_code == 200
    assert r.json()["transport"] == "mqtt"
    assert any("coil/7" in t for t in mocked_hw["mqtt"])  # ESP bobini MQTT'ye gitti


def test_invalid_coil_rejected(client, mocked_hw):
    assert client.post("/api/coil/9/control", json={"start": True}).status_code == 400
    assert client.post("/api/coil/0/control", json={"start": True}).status_code == 400


def test_batch_splits_stm_and_esp(client, mocked_hw):
    r = client.post("/api/coil/batch", json={"coil_ids": [2, 6], "freq": 50, "duty": 25, "start": True})
    assert r.status_code == 200
    results = {x["coilId"]: x["transport"] for x in r.json()["results"]}
    assert results[2] == "stm32"
    assert results[6] == "mqtt"


def test_stop_all_uses_hardware(client, mocked_hw):
    r = client.post("/api/hardware/command", json={"command": "stop_all_coils"})
    # HardwareController.stop_all_coils çağrılmalı (STM güvenli durdurma).
    assert r.status_code == 200
    assert any(c.get("stop_all") for c in mocked_hw["stm"])


def test_serial_write_failure_closes_port_and_drops_stale_payload():
    """DENETIM P2 regresyonu: seri yazım hatası portu KAPATMALI + bayat paketi düşürmeli.

    (1) Yazım hatasında yalnız 'bağlantı koptu' bayrağı düşürülüyordu; reconnect koşulu
        `not serial_conn or not serial_conn.is_open` olduğu için yeniden bağlanma HİÇ
        tetiklenmiyordu → USB yarım-kopmasında port sonsuza dek açık ama ölü kalıyor,
        bobin komutları sessizce kayboluyordu.
    (2) STM_NACK sonrası son ham paket koşulsuz yeniden kuyruğa konuyordu; NACK bir STOP
        kuyruğa girdikten SONRA işlenirse bobinler acil-durdurmadan sonra tekrar
        enerjilenebiliyordu. Artık yaş sınırı var.
    """
    import inspect

    import headless_core

    src = inspect.getsource(headless_core.HeadlessCore._hw_sender_worker)

    # (1) yazım hatası dalında port kapatılmalı (dal = [STM32 SEND] logundan UDP bloğuna kadar)
    _after_send_err = src.split("[STM32 SEND]")[1].split("if udp_sock")[0]
    assert "close_serial(serial_conn)" in _after_send_err, \
        "yazım hatasında port kapatılmalı (yoksa reconnect tetiklenmez)"
    assert "last_payload[0] = None" in _after_send_err, \
        "kopuk bağlantıda bayat paket düşürülmeli (re-fire önlemi)"

    # (2) retry yaş sınırına tabi olmalı
    assert "_RETRY_MAX_AGE_S" in src, "NACK tekrar-oynatması yaş sınırlı olmalı"
    assert 0 < headless_core._RETRY_MAX_AGE_S <= 2.0, "yaş sınırı keep-alive turuna yakın olmalı"


def test_precise_duration_seconds_forwarded_to_deadline(client, mocked_hw):
    """DENETIM P3 regresyonu: hassas saniye donanım katmanına İLETİLMELİ.

    STM firmware süresi DAKİKA granülerliğinde olduğundan saniye→dakika dönüşümü YUKARI
    yuvarlanır: 30 sn'lik komut firmware'e 1 dk gider (2x fazla tedavi). Firmware için bu doğru
    (tedaviyi yarıda kesmez), ama yazılım deadline'ı monotonik SANİYE tuttuğu için gerçek süreyi
    tam uygulayabilir → çağrı hassas saniyeyi de geçmeli.
    """
    mocked_hw["stm"].clear()
    r = client.post("/api/coil/1/control",
                    json={"freq": 50, "duty": 25, "phase": 0, "duration": 30, "start": True})
    assert r.status_code == 200
    rec = next(c for c in mocked_hw["stm"] if c.get("coil") == 1)
    assert rec["duration_min"] == 1, "firmware'e yukarı yuvarlanmış dakika gider (yarıda kesmesin)"
    assert rec["duration_seconds"] == 30, "yazılım deadline'ı GERÇEK saniyeyi almalı"
