# Author: mertaygn, cglrgrkn
"""ESP LAST-WILL (LWT) simetrisi — donanım-uyum denetimi D-4 (2026-08-19).

NEDEN VAR: S3 bağlanırken LWT (last-will) ayarlıyordu, 8266 AYARLAMIYORDU (connect will'siz).
Bobin 8 ani koparsa yalnız ~30 sn staleness watchdog'uyla geç fark ediliyordu (S3 ~keepalive'da).
Bu turda 8266 connect'ine S3-eşdeğeri LWT eklendi; backend'e de retained-events koruması eklendi
(LWT retain=true olduğundan, reconnect'te bayat offline'ı canlı sanmasın).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import servers.api_server as api

KOK = Path(__file__).resolve().parents[1]


def _8266_nm() -> str:
    return (KOK / "firmware" / "esp8266_pemf_coil" / "NetworkManager.cpp").read_text(encoding="utf-8", errors="replace")


def test_KRITIK_8266_iki_broker_da_LWT_ile_baglanir():
    """Local + Cloud connect'lerinin İKİSİ de will parametreli olmalı (S3 birebir)."""
    s = _8266_nm()
    # will'li connect: connect(clientId, ..., lwtTopic, 1, true, lwtMsg)
    assert s.count("lwtTopic") >= 2, "8266 iki broker'da LWT topic'i kurmuyor"
    assert 'connect(clientId, lwtTopic, 1, true, lwtMsg)' in s, "local broker LWT'siz bağlanıyor"
    assert 'connect(clientId, _mqttUser, _mqttPass, lwtTopic, 1, true, lwtMsg)' in s, "cloud broker LWT'siz bağlanıyor"
    # LWT topiği + payload backend'in beklediği offline event ile uyumlu
    assert 'pemf/coil/%d/events' in s, "LWT topiği events değil"
    assert '\\"event_type\\":\\"offline\\"' in s, "LWT payload'ı backend'in beklediği offline formatı değil"


def test_KRITIK_backend_RETAINED_offline_bobini_KOPARMAZ():
    """LWT retain=true; backend reconnect'te bayat retained 'offline' canlı bobini offline yapmamalı."""
    idx = 7  # bobin 8
    with api._live_state_lock:
        api._live_state["coils"][idx]["connected"] = True
        api._live_state["coils"][idx]["running"] = True

    class _RetOffline:
        topic = "pemf/coil/8/events"
        retain = True  # broker'da kalmış bayat LWT
        payload = b'{"event_type":"offline","coil_id":8}'

    api._on_mqtt_message_api(None, None, _RetOffline())
    with api._live_state_lock:
        assert api._live_state["coils"][idx]["connected"] is True, (
            "retained bayat offline canlı bobini kopardı → yanlış 'bağlantı kesildi'"
        )


def test_KRITIK_backend_CANLI_offline_bobini_KOPARIR():
    """Karşıt-kanıt: canlı (retain=0) offline event GERÇEKTEN bobini offline yapar."""
    idx = 7
    with api._live_state_lock:
        api._live_state["coils"][idx]["connected"] = True
        api._live_state["coils"][idx]["running"] = True

    class _CanliOffline:
        topic = "pemf/coil/8/events"
        retain = False  # canlı LWT / gerçek kopma
        payload = b'{"event_type":"offline","coil_id":8}'

    api._on_mqtt_message_api(None, None, _CanliOffline())
    with api._live_state_lock:
        assert api._live_state["coils"][idx]["connected"] is False, (
            "canlı offline event işlenmedi → gerçek kopma görünmez"
        )
        assert api._live_state["coils"][idx]["running"] is False


def test_KARSIT_KANIT_events_retained_korumasi_KODDA():
    src = inspect.getsource(api)
    # events dalında is_retained koruması var
    assert 'elif msg_type == "events":' in src
    idx = src.index('elif msg_type == "events":')
    blok = src[idx : idx + 600]
    assert "if is_retained:" in blok, "events dalına retained koruması düşmüş"
