# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""I18NI-O.1 (14-I18N-INCELEME, orkestratör kapsamı (i) — Ö.4-Y8): bildirim METNİ, arkasından gelen STOP tetikleyicisini KAPILAYAMAZ.

ÖLÇÜLEN KUSUR (göç P1-10b / 10f): arka plan güvenlik yollarında (STM bağlantı kaybı, STM firmware watchdog'u, ESP güvenlik alarmı,
seansta STM komut reddi) bildirim `_push_notification("<düz Türkçe f-string>")` iken `live_state._bildir(lambda d: ceviri.t(…, dil=d))`
oldu ve `_emergency_stop_async(...)` çağrısından ÖNCE, AYNI try gövdesinde koşuyor. `_bildir` üreticinin istisnasını YAKALAMIYORDU →
çeviri alt sistemi atarsa (katalog yaprağı dize değil → `TypeError`; test / `PEMF_I18N_KATI` kipinde eksik anahtar → `KeyError`;
üreticinin çağırdığı metin yardımcısı) STOP tetikleyicisi HİÇ çağrılmıyordu. Göç öncesinde bu yollarda STOP'tan önce yalnız atmayan
f-string vardı (`stop_once_ceviri.py` taraması: uçta 4 yol, `c1e098ef`'te yok). `estop_mandali._metin` aynı ilkeyi zaten söyler:
"ACİL DURDUR kapısı ASLA metin yüzünden düşmez".

Kural: `_bildir` HİÇBİR koşulda fırlatmaz; bir dilin metni üretilemezse öteki dilinki kullanılır, ikisi de üretilemezse bildirim
günlüğe yazılıp atlanır — STOP her durumda tetiklenir. Normal yolda `message` Türkçe bayt bayt (KARŞIT kol).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from topoloji import ESP_BOBIN, TUM_STM

_B = min(TUM_STM)


def _patlayan_t(*_a, **_k):
    raise TypeError("sahte: katalog yaprağı dize değil")


@pytest.fixture
def ortam(monkeypatch):
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import live_state
    from utils import ceviri

    estoplar: list = []
    bildirim: list = []
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: True)
    monkeypatch.setattr(api, "_emergency_stop_async", lambda reason="manual", mode="": estoplar.append(reason))
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info": bildirim.append((m, t)))
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    with gercek_hc() as hc:
        monkeypatch.setattr(api.state, "hardware", hc)
        try:
            yield SimpleNamespace(
                api=api,
                live_state=live_state,
                ceviri=ceviri,
                hc=hc,
                estoplar=estoplar,
                bildirim=bildirim,
                mp=monkeypatch,
            )
        finally:
            # `_emergency_stop_async` sahte → seansı o kapatmaz; aparat kendi açtığı seansı kapatır (D1.41 nöbeti).
            with api._session_lock:
                api._active_session.clear()


def _stm_seansi_ac(o) -> None:
    with o.api._session_lock:
        o.api._active_session.update(is_active=True, coil_ids=[_B])


def _ceviriyi_boz(o) -> None:
    o.mp.setattr(o.ceviri, "t", _patlayan_t)


def test_KRITIK_bildir_ureticisi_atsa_da_FIRLATMAZ():
    from servers import live_state

    giden: list = []
    live_state._bildir(lambda d: (_ for _ in ()).throw(TypeError("sahte")), "error", lambda m, t: giden.append((m, t)))
    # iki dilde de üretilemedi → bildirim atlanır (günlük), istisna YOK
    assert giden == []
    live_state._bildir(
        lambda d: "TR metin" if d == "tr" else (_ for _ in ()).throw(KeyError(d)),
        "error",
        lambda m, t: giden.append((m, t)),
    )
    assert giden == [("TR metin", "error")]
    live_state._bildir(
        lambda d: "EN text" if d == "en" else (_ for _ in ()).throw(KeyError(d)),
        "error",
        lambda m, t: giden.append((m, t)),
    )
    assert giden[-1] == ("EN text", "error"), "Türkçe üretilemeyince öteki dilin metni gitmeli"


def test_KRITIK_STM_kopmasi_ceviri_bozukken_STOP_TETIKLENIR(ortam):
    o = ortam
    _stm_seansi_ac(o)
    _ceviriyi_boz(o)
    o.api._handle_backend_event(SimpleNamespace(event_type="hardware.stm.disconnected", data={}))
    assert o.estoplar == ["stm_disconnected"], f"çeviri atınca STM kopması STOP'u tetiklenmedi: {o.estoplar}"


def test_KRITIK_STM_watchdog_ceviri_bozukken_STOP_TETIKLENIR(ortam):
    o = ortam
    _stm_seansi_ac(o)
    _ceviriyi_boz(o)
    o.api._handle_backend_event(SimpleNamespace(event_type="hardware.stm.watchdog_timeout", data={}))
    assert o.estoplar == ["stm_watchdog_timeout"], f"çeviri atınca watchdog STOP'u tetiklenmedi: {o.estoplar}"


def test_KRITIK_ESP_alarmi_ceviri_bozukken_STOP_TETIKLENIR(ortam):
    o = ortam
    _ceviriyi_boz(o)
    msg = SimpleNamespace(
        topic=f"pemf/coil/{ESP_BOBIN}/alarm", payload=json.dumps({"type": "overcurrent"}).encode(), retain=False
    )
    o.api._on_mqtt_message_api(None, None, msg)
    assert o.estoplar and o.estoplar[-1].startswith(f"esp_alarm_{ESP_BOBIN}_overcurrent"), (
        f"çeviri atınca ESP alarmı STOP'u tetiklenmedi: {o.estoplar}"
    )


def test_KRITIK_seansta_STM_komut_reddi_ceviri_bozukken_STOP_TETIKLENIR(ortam):
    o = ortam
    _stm_seansi_ac(o)
    _ceviriyi_boz(o)
    assert o.api._stm_red_aktif_seansi_durdur("STM_NACK crc") is True
    assert o.estoplar == ["stm_komut_reddi"], f"çeviri atınca komut reddi STOP'u tetiklenmedi: {o.estoplar}"


def test_KARSIT_normal_yolda_bildirim_TURKCE_bayt_bayt_ve_iki_dilli(ortam):
    o = ortam
    _stm_seansi_ac(o)
    o.api._handle_backend_event(SimpleNamespace(event_type="hardware.stm.disconnected", data={}))
    assert o.estoplar == ["stm_disconnected"]
    beklenen = o.ceviri.t("bildirim.stmKoptuSeansDurdu", dil="tr")
    assert (beklenen, "error") in o.bildirim, f"Türkçe bildirim değişti: {o.bildirim}"
    assert beklenen != o.ceviri.t("bildirim.stmKoptuSeansDurdu", dil="en")
