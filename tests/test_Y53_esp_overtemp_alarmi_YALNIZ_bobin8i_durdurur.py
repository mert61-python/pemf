# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y53 (sahip, 1-D inceleme i2-F-10) — ESP'den gelen "aşırı sıcaklık" (overtemp) alarmı YALNIZ kendi kartının bobinini (8)
durdurur ve uyarı verir; bobin 1–7 çalışmaya DEVAM eder; genel ACİL DURDUR ve mandal KURULMAZ.

ÖLÇÜLEN KUSUR: `_on_mqtt_message_api` alarm dalı türü ne olursa olsun `_emergency_stop_async` çağırıyordu → kartın kendi
aşırı-sıcaklık alarmı bütün bobinleri (STM 1–7 dahil) durdurup Y4 mandalını kuruyordu. A-47 (bobin 1–7'de termal durdurma
yok) ile çelişir; Y40: kartın kendi 100 °C kesmesi kalır. Bugün ÖLÜ YOL (alarm yayınlayan firmware yok, ESP kapalı) — kod
silinmez (Ö.4-Y7); kapı yolu ESP AÇIK kipte gerçek MQTT ileti işleyicisinden koşar.

Ö.4-Y8: ACİL DURDUR'un kendisi hiçbir koşulda kapılanmaz — diğer alarm türleri (overcurrent / safety_violation) eskisi
gibi TAM acil durdurma (KARŞIT kol); bobin 8'in STOP'u kapısız gider.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from topoloji import ESP_BOBIN, TUM_STM

_B = min(TUM_STM)


@pytest.fixture
def ortam(monkeypatch):
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from utils import estop_mandali

    yayin: list = []
    estoplar: list = []
    bildirim: list = []
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: yayin.append((topic, payload)) or True)
    monkeypatch.setattr(api, "_emergency_stop_async", lambda reason="manual", mode="": estoplar.append(reason))
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info": bildirim.append((m, t)))
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    with api._session_lock:
        api._active_session.clear()
    with gercek_hc() as hc:
        monkeypatch.setattr(api.state, "hardware", hc)
        assert hc.update_coil(_B, 100.0, 40.0, 0.0, 5, start=True) is True, "aparat: STM bobini baslamadi"
        yield SimpleNamespace(api=api, hc=hc, mandal=estop_mandali, yayin=yayin, estoplar=estoplar, bildirim=bildirim)


def _alarm(o, tur: str, retain: bool = False) -> None:
    msg = SimpleNamespace(
        topic=f"pemf/coil/{ESP_BOBIN}/alarm", payload=json.dumps({"type": tur, "temp": 101.5}).encode(), retain=retain
    )
    o.api._on_mqtt_message_api(None, None, msg)


def test_KRITIK_overtemp_alarmi_yalniz_bobin8i_durdurur_STM_bobinleri_SURER_mandal_YOK(ortam):
    o = ortam
    _alarm(o, "overtemp")
    assert o.estoplar == [], f"overtemp alarmi GENEL acil durdurma tetikledi: {o.estoplar}"
    assert o.mandal.mandalli_mi() is False, "overtemp alarmi mandal kurdu (Y53: kurmamali)"
    assert o.hc.coils_state[_B]["is_running"] is True, "overtemp alarmi STM bobinini durdurdu (A-47/Y53)"
    stoplar = [p for t, p in o.yayin if t == f"pemf/coil/{ESP_BOBIN}/control" and p.get("command") == "stop"]
    assert stoplar, "bobin 8'e STOP gitmedi"
    assert any(str(ESP_BOBIN) in m and t in ("warning", "error") for m, t in o.bildirim), f"uyari yok: {o.bildirim}"


def test_KARSIT_diger_alarm_turleri_TAM_acil_durdurma_ve_retained_yok_sayilir(ortam):
    o = ortam
    _alarm(o, "overtemp", retain=True)
    assert o.estoplar == [] and not o.yayin, "retained alarm islendi"
    _alarm(o, "overcurrent")
    assert o.estoplar and o.estoplar[-1].startswith(f"esp_alarm_{ESP_BOBIN}_overcurrent"), (
        f"overcurrent alarmi tam acil durdurma YAPMADI (O.4-Y8): {o.estoplar}"
    )


@pytest.mark.parametrize(
    "tur", ["overtemp", "over_temperature", "OverTemp", "overtemp_kesme", "sicaklik_asimi", "AŞIRI_SICAKLIK"]
)
def test_KRITIK_asiri_sicaklik_adlari_YALNIZ_bobin8i_durdurur(ortam, tur):
    o = ortam
    _alarm(o, tur)
    assert o.estoplar == [], f"'{tur}' asiri sicaklik alarmi GENEL acil durdurma tetikledi"
    assert o.hc.coils_state[_B]["is_running"] is True


@pytest.mark.parametrize(
    "tur",
    ["attempt_failed", "overcurrent_temp", "overtemp_overcurrent", "temp_sensor_fault", "contempt", "safety_violation"],
)
def test_KARSIT_asiri_sicaklik_OLMAYAN_tur_TAM_acil_durdurma(ortam, tur):
    """1-E incelemesi (i-11.1): sınıflama "temp" ALT DİZESİNE bakıyordu → bu türler (ölçüldü) TAM acil durdurma yerine yalnız
    bobin 8'i durduruyordu. Y53 yalnız aşırı sıcaklığı daraltır; şüphede durdurma DARALMAZ (Ö.4-Y8)."""
    o = ortam
    _alarm(o, tur)
    assert o.estoplar and o.estoplar[-1].startswith(f"esp_alarm_{ESP_BOBIN}_"), (
        f"'{tur}' alarmi TAM acil durdurma YAPMADI (yalniz bobin {ESP_BOBIN} yoluna dustu): {o.estoplar}"
    )
