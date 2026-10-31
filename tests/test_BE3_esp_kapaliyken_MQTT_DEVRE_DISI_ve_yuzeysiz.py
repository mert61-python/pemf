# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""BE 3 · Y230 — ESP KAPALIYKEN (`PEMF_ESP_ENABLED` ≠ 1, bugünkü saha) "ESP / MQTT" ve bütün MQTT yüzeyleri arayüzden GİZLİ.

Sahip (31.10): "esp mqtt yeşil yanıyor tamamen gizlenmeli esp ile ilgili şeyler". ÖLÇÜLEN KÖK (canlı): `api_server.py` `network.status`
işleyicisi yerel broker erişilebilir olunca (`mqtt_broker_reachable`, mosquitto ESP'den bağımsız koşar) `mqtt`'yi ESP kapısı OLMADAN
"online" yazıyordu → Ana Ekran "ESP / MQTT" rozeti yeşil; `mqtt.broker.status` işleyicisi ise doğru "devre_disi" diyordu (iki işleyici
çelişiyordu). Ayrıca broker bulunamayınca `mqtt.broker.error` bildirimi ("Mosquitto executable …") ESP kapalıyken de ekrana düşüyordu.

SÖZLEŞME (iki kip):
  · ESP kapalı: hangi ağ olayı gelirse gelsin `mqtt == "devre_disi"` (yayın dahil); anlık görüntü `espEtkin: false` taşır (arayüzün TEK kaynağı);
    `mqtt.broker.error` ekrana bildirim DÜŞÜRMEZ (günlükte kalır).
  · ESP açık (`PEMF_ESP_ENABLED=1`): broker erişilebilir → "online", hata → bildirim (eski davranışın TAMAMI geri gelir), `espEtkin: true`.
Kod SİLİNMEZ (Ö.4-Y7); güvenlik aynen (ACİL DURDUR ESP STOP'larını yine gönderir — A-63, `test_internetsiz_ve_esp_kapali.py`).
"""

from __future__ import annotations

import pytest


def _olay(tur: str, veri: dict):
    return type("O", (), {"event_type": tur, "data": veri})()


@pytest.fixture
def ortam(monkeypatch):
    from servers import api_server, live_state

    yayinlar: list = []
    bildirimler: list = []
    monkeypatch.setattr(api_server, "_ws_broadcast_sync", lambda m: yayinlar.append(m))
    monkeypatch.setattr(api_server, "_push_notification", lambda *a, **k: bildirimler.append(a))
    with live_state._live_state_lock:
        eski = {k: live_state._live_state[k] for k in ("gateway", "mqtt", "internet")}
    yield api_server, live_state, yayinlar, bildirimler
    with live_state._live_state_lock:
        live_state._live_state.update(eski)


def _ag(erisilebilir: bool):
    return _olay(
        "network.status",
        {
            "gateway_mode": "offline",
            "hotspot_active": True,
            "internet_connected": False,
            "mqtt_broker_reachable": erisilebilir,
        },
    )


def test_KRITIK_ESP_KAPALI_broker_ERISILEBILIR_olsa_da_mqtt_DEVRE_DISI_yayin_dahil(ortam, monkeypatch):
    api, ls, yayinlar, _ = ortam
    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    api._handle_backend_event(_olay("mqtt.broker.status", {"port_open": True, "running": True}))
    assert ls._live_state["mqtt"] == "devre_disi"
    api._handle_backend_event(_ag(True))
    assert ls._live_state["mqtt"] == "devre_disi", (
        "network.status ESP kapısız 'online' yazdı — ESP / MQTT rozeti YEŞİL yanar"
    )
    son = [m for m in yayinlar if m.get("type") == "gateway_status"][-1]
    assert son["data"]["mqtt"] == "devre_disi", son


def test_KRITIK_ESP_KAPALI_onceki_bayat_online_degeri_de_DUZELIR(ortam, monkeypatch):
    api, ls, _, _ = ortam
    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    with ls._live_state_lock:
        ls._live_state["mqtt"] = "online"  # eski sürümün bıraktığı / yarıştan kalan değer
    api._handle_backend_event(_ag(False))
    assert ls._live_state["mqtt"] == "devre_disi"


def test_ESP_ACIK_broker_erisilebilir_ONLINE_eski_davranis_geri(ortam, monkeypatch):
    api, ls, _, _ = ortam
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    with ls._live_state_lock:
        ls._live_state["mqtt"] = "warning"
    api._handle_backend_event(_ag(True))
    assert ls._live_state["mqtt"] == "online"


@pytest.mark.parametrize(("bayrak", "beklenen"), [(None, False), ("0", False), ("1", True)])
def test_KRITIK_anlik_goruntu_espEtkin_TEK_KAYNAK(ortam, monkeypatch, bayrak, beklenen):
    _, ls, _, _ = ortam
    if bayrak is None:
        monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    else:
        monkeypatch.setenv("PEMF_ESP_ENABLED", bayrak)
    anlik = ls._build_ws_snapshot()
    assert anlik.get("espEtkin") is beklenen, f"anlık görüntü espEtkin={anlik.get('espEtkin')!r} (beklenen {beklenen})"


@pytest.mark.parametrize(("bayrak", "bildirim_var"), [(None, False), ("1", True)])
def test_KRITIK_broker_HATASI_bildirimi_yalniz_ESP_ACIKKEN(ortam, monkeypatch, bayrak, bildirim_var):
    api, _, _, bildirimler = ortam
    if bayrak is None:
        monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    else:
        monkeypatch.setenv("PEMF_ESP_ENABLED", bayrak)
    api._handle_backend_event(_olay("mqtt.broker.error", {"message": "Mosquitto executable or service was not found."}))
    assert bool(bildirimler) is bildirim_var, bildirimler
    api._handle_backend_event(_olay("discovery.error", {"message": "kesif hatasi"}))
    assert bildirimler, "keşif hatası bildirimi (ESP'den bağımsız) KAYBOLDU"
