# -*- coding: utf-8 -*-
# Author: mertaygn
"""ESP kopunca/dönünce `coil_status` WS YAYINI — sahada arayüz "Hazır"da ASILI kalıyordu.

BELİRTİ (sahip bildirimi 2026-09-10, ölçüldü):
    Kontrol sekmesinde hotspot kapatılıyor. Bildirim merkezine
    "⚠️ Bobin N bağlantısı kesildi" DÜŞÜYOR, ama bobin kartı hâlâ **"Hazır"** gösteriyor;
    "Offline"a hiç dönmüyor.

KÖK NEDEN: `_on_mqtt_message_api` içindeki `("wifi_disconnected", "offline")` dalı
`_live_state`i güncelliyor ve `_push_notification` çağırıyordu — ama `coil_status`
**WS yayını YAPMIYORDU**. İstemci `connected` alanını YALNIZCA WS anlık görüntüsünden
ya da `coil_status` olayından öğrenir; "Hazır" etiketi doğrudan o alandan geliyor:

    pf/src/components/domain/CoilParameterPanel.tsx  ve  CoilCard.tsx
        running ? "Aktif" : connected ? "Hazır" : "Offline"

⚠️ NEDEN BEKÇİ KURTARMIYOR: `_esp_telemetry_watchdog` demote koşulu
`coil.get("connected")` — ve bu dal onu ZATEN False yapmış oluyor. Bekçi bobini
ATLIYOR, dolayısıyla onun yaptığı `coil_status` yayını da hiç gitmiyor. İki mekanizma
birbirini kilitliyordu: LWT dalı durumu düşürüyor ama istemciye söylemiyor; bekçi
söyleyecek ama tam bu yüzden devre dışı kalıyor. Arayüz ancak TAM yeniden bağlanmada
(yeni snapshot) kendini düzeltiyordu.

BU KAPI DAVRANIŞ ÖLÇER (varlık değil): gerçek `_on_mqtt_message_api` gerçek bir LWT
yüküyle sürülür ve yayın kuyruğu okunur. AYNA yol (`wifi_connected`) da ölçülür —
yayın olmadan bobin geri geldiğinde kart "Offline"da asılı kalırdı.
"""

from __future__ import annotations

import json
import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from topoloji import ESP_BOBIN, TUM_ESP  # faz 4: literal bobin numarasi YASAK


class _SahteMesaj:
    """paho `MQTTMessage` yerine minimum yüzey: topic + payload + retain."""

    def __init__(self, topic: str, yuk: dict, retain: bool = False):
        self.topic = topic
        self.payload = json.dumps(yuk).encode("utf-8")
        self.retain = retain


@pytest.fixture()
def kur(monkeypatch):
    """Yayınları yakala, bildirimi sustur, ESP bobini'yı BAĞLI başlat."""
    from servers import api_server as api

    yayinlar: list[dict] = []
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: yayinlar.append(m))
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)

    with api._live_state_lock:
        api._live_state["coils"][ESP_BOBIN - 1]["connected"] = True
        api._live_state["coils"][ESP_BOBIN - 1]["running"] = True
    return api, yayinlar


def _coil_status(yayinlar: list[dict], coil_id: int) -> dict | None:
    for m in yayinlar:
        if m.get("type") == "coil_status" and m.get("coilId") == coil_id:
            return m
    return None


def test_KRITIK_offline_olayi_coil_status_YAYINLAR(kur):
    """LWT/`offline` → `coil_status` yayını GİTMELİ ve `connected` False olmalı.

    MUTASYON: `("wifi_disconnected", "offline")` dalındaki `_ws_broadcast_sync(...)`
    çağrısını sil → bu test KIRMIZI olur (sahadaki tam davranış: bildirim var, kart "Hazır").
    """
    api, yayinlar = kur
    api._on_mqtt_message_api(
        None, None, _SahteMesaj(f"pemf/coil/{ESP_BOBIN}/events", {"event_type": "offline", "coil_id": ESP_BOBIN})
    )

    m = _coil_status(yayinlar, ESP_BOBIN)
    assert m is not None, (
        "offline olayinda `coil_status` WS yayini GITMEDI → istemci `connected`i asla "
        'ogrenmez ve bobin karti "Hazır"da asili kalir (sahada olculen ariza). '
        f"Giden yayinlar: {[y.get('type') for y in yayinlar]}"
    )
    assert m["data"]["connected"] is False, f"yayin connected=False tasimiyor: {m['data']}"
    assert m["data"]["running"] is False, "kopan bobin `running` da False olmali"


def test_KRITIK_wifi_connected_olayi_da_YAYINLAR(kur):
    """AYNA yol: bobin dönünce de yayın gitmeli, yoksa kart "Offline"da asılı kalır."""
    api, yayinlar = kur
    with api._live_state_lock:
        api._live_state["coils"][ESP_BOBIN - 1]["connected"] = False

    api._on_mqtt_message_api(
        None, None, _SahteMesaj(f"pemf/coil/{ESP_BOBIN}/events", {"event_type": "wifi_connected", "coil_id": ESP_BOBIN})
    )

    m = _coil_status(yayinlar, ESP_BOBIN)
    assert m is not None, (
        "wifi_connected olayinda `coil_status` yayini GITMEDI → bobin geri geldiginde kart \"Offline\"da asili kalir"
    )
    assert m["data"]["connected"] is True, f"yayin connected=True tasimiyor: {m['data']}"


def test_sunucu_durumu_da_gercekten_dusuyor(kur):
    """Yayının yanında `_live_state` de düşmeli (yeni snapshot doğru olsun)."""
    api, _ = kur
    api._on_mqtt_message_api(
        None,
        None,
        _SahteMesaj(f"pemf/coil/{ESP_BOBIN}/events", {"event_type": "wifi_disconnected", "coil_id": ESP_BOBIN}),
    )
    with api._live_state_lock:
        c = dict(api._live_state["coils"][ESP_BOBIN - 1])
    assert c["connected"] is False and c["running"] is False, c


def test_KARSIT_KANIT_kapi_gercekten_olcuyor(kur):
    """Öz-test: yakalayıcı çalışıyor ve `coil_status` filtresi ayırt ediyor.

    Kapının kendisi bozuksa (ör. yayınlar hiç yakalanmıyorsa) yukarıdaki testler
    SESSİZCE yeşil kalabilirdi. Burada bilinen bir yayın enjekte edilip filtrenin
    onu bulduğu, ALAKASIZ tipin ise bulunmadığı gösterilir.
    """
    _api, yayinlar = kur
    assert _coil_status(yayinlar, ESP_BOBIN) is None, "kurulum yayin uretmemeliydi"
    yayinlar.append({"type": "gateway_status", "data": {}})
    assert _coil_status(yayinlar, ESP_BOBIN) is None, "filtre ALAKASIZ tipi coil_status sandi"
    yayinlar.append({"type": "coil_status", "coilId": ESP_BOBIN, "data": {"connected": False}})
    assert _coil_status(yayinlar, ESP_BOBIN) is not None, "filtre GERCEK coil_status'u bulamadi"
