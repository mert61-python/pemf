# Author: mertaygn, cglrgrkn
"""ESP LAST-WILL (LWT) simetrisi — donanım-uyum denetimi D-4 (2026-08-19).

NEDEN VAR: S3 bağlanırken LWT (last-will) ayarlıyordu, 8266 AYARLAMIYORDU (connect will'siz).
Bobin 8 ani koparsa yalnız ~30 sn staleness watchdog'uyla geç fark ediliyordu (S3 ~keepalive'da).
Bu turda 8266 connect'ine S3-eşdeğeri LWT eklendi; backend'e de retained-events koruması eklendi.

16. parti (sahip onayı 2026-08-20): willRetain artık FALSE — kapsamlı tarama (2026-08-20) tek
MQTT abonesinin backend olduğunu ve HER retained girdiyi elediğini/kapıladığını, yerel broker'da
`persistence false` olduğunu, bulut broker'da hiçbir abone olmadığını ölçtü. retain=true hiçbir
tüketiciye fayda sağlamıyor, yalnız bayat-retained riski üretiyordu (HiveMQ'da süresiz kalan
offline + D-4'ün bilinen 'reconnect'te temizlenmeyen retained offline churn'ü). MQTT-3.3.1-9:
canlı LWT teslimi retain bayrağından BAĞIMSIZ — kopma tespiti değişmez (aşağıdaki davranış
testleri bunun kanıtı: hepsi bayraktan bağımsız yeşil).
"""

from __future__ import annotations

import inspect
from pathlib import Path

from c_soyucu import c_soy

import servers.api_server as api

KOK = Path(__file__).resolve().parents[1]


def _8266_nm() -> str:
    # 17. parti (adversaryal test-gaming bulgusu): HAM metin aranıyordu — LWT'li connect satırı
    # YORUMA alınıp yerine will'siz connect yazıldığında aranan string yorumda yaşadığı için test
    # yeşil kalıyordu (ampirik kanıtlandı; deponun kendi dersi: "kusuru anlatan yorum düzeltme
    # sanılmasın"). Artık YORUM-SOYULMUŞ kaynak aranır.
    return c_soy(
        (KOK / "firmware" / "esp8266_pemf_coil" / "NetworkManager.cpp").read_text(encoding="utf-8", errors="replace")
    )


def test_KRITIK_8266_iki_broker_da_LWT_ile_baglanir():
    """Local + Cloud connect'lerinin İKİSİ de will parametreli olmalı (S3 birebir) —
    16. parti sonrası willRetain=FALSE (gerekçe modül başlığında)."""
    s = _8266_nm()
    # will'li connect: connect(clientId, ..., lwtTopic, 1, false, lwtMsg)
    assert s.count("lwtTopic") >= 2, "8266 iki broker'da LWT topic'i kurmuyor"
    assert 'connect(clientId, lwtTopic, 1, false, lwtMsg)' in s, (
        "local broker LWT'siz ya da retain=true bağlanıyor (16. parti: willRetain=false)"
    )
    assert 'connect(clientId, _mqttUser, _mqttPass, lwtTopic, 1, false, lwtMsg)' in s, (
        "cloud broker LWT'siz ya da retain=true bağlanıyor"
    )
    # LWT topiği + payload backend'in beklediği offline event ile uyumlu
    assert 'pemf/coil/%d/events' in s, "LWT topiği events değil"
    assert '\\"event_type\\":\\"offline\\"' in s, "LWT payload'ı backend'in beklediği offline formatı değil"


def test_KRITIK_S3_LWT_willRetain_FALSE():
    """S3'ün üç connect'i de (local kimlikli/kimliksiz + cloud) will'li ve retain=FALSE olmalı.
    17. parti: yorum-soyulmuş kaynakta (8266 ile aynı gaming koruması) + connect'e ÇAPALI sayım."""
    import re

    s = c_soy(
        (KOK / "firmware" / "esps3_pemf_coil" / "NetworkManager.cpp").read_text(encoding="utf-8", errors="replace")
    )
    assert s.count("lwtTopic") >= 2, "S3 LWT topic'i kurmuyor"
    assert not re.search(r"connect\([^;]*?,\s*1,\s*true,", s, re.S), (
        "S3 connect'lerinde willRetain=true kalmış (16. parti: false — bayat-retained riski)"
    )
    assert len(re.findall(r"connect\([^;]*?,\s*1,\s*false,", s, re.S)) >= 3, (
        "S3 üç connect'in hepsi will parametreli+retain'siz olmalı"
    )


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
