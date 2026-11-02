# Author: mertaygn, cglrgrkn
"""KP-1 · apps/backend/servers/api_server.py · sözleşmeler: MQTT bağlanma / ileti işleyicisi (`_on_mqtt_connect_api`,
`_on_mqtt_message_api`) — köprü / ağ geçidi durumu, sayısal olmayan bobin konusu, `frequency` alanı, öz-sınama olayları,
ESP alarmında STOP iş parçacığı açılamaması, bozuk yük.

Sahte EN ALT katta: WS yayını (`_ws_broadcast_sync`) ve bildirim gönderimi (`_push_notification`) kaydedilir; ESP MQTT yayını
(`_mqtt_publish`) ağa çıkmaz; STOP iş parçacığının açılamaması `threading.Thread.start` düzeyinde (gerçek arıza biçimi
`RuntimeError("can't start new thread")`). Bildirim metinleri ürünün kendi kataloğundan (`ceviri.t`).
"""

from __future__ import annotations

import copy
import json
import logging
import threading
from types import SimpleNamespace

import pytest
from topoloji import ESP_BOBIN, esp_yolu_gerekir


@pytest.fixture
def ortam(monkeypatch):
    from servers import api_server as a
    from servers import live_state as ls

    yayin: list = []
    bildirim: list = []

    def _bildirim(mesaj, seviye="info", mesajlar=None):
        bildirim.append((mesaj, seviye, dict(ls._BILDIRIM_MESAJLARI.get() or {})))

    monkeypatch.setattr(a, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(a, "_push_notification", _bildirim)
    monkeypatch.setattr(a._sensor_kaydedici, "kaydet", lambda *x, **k: None)
    monkeypatch.setattr(a, "_mqtt_publish", lambda *x, **k: False)
    with a._live_state_lock:
        once = {k: copy.deepcopy(v) for k, v in a._live_state.items()}
    tel_once = dict(a._coil_last_telemetry)
    try:
        yield SimpleNamespace(api=a, yayin=yayin, bildirim=bildirim)
    finally:
        with a._live_state_lock:
            for k, v in once.items():
                a._live_state[k] = v
        a._coil_last_telemetry.clear()
        a._coil_last_telemetry.update(tel_once)


def _ileti(konu: str, yuk, retain: bool = False):
    ham = yuk if isinstance(yuk, bytes) else (yuk.encode("utf-8") if isinstance(yuk, str) else json.dumps(yuk).encode())
    return SimpleNamespace(topic=konu, payload=ham, retain=retain)


class _SahteIstemci:
    def __init__(self):
        self.abonelik: list = []

    def subscribe(self, konu):
        self.abonelik.append(konu)


def test_baglanti_kodu_sifir_degil_mqtt_HATA_ve_abonelik_YOK(ortam):
    """rc != 0 ile bağlanma geri çağrısı → canlı durumda `mqtt == "error"`, hiçbir konuya abone olunmaz, 'bağlandı' bildirimi yok."""
    ist = _SahteIstemci()
    ortam.api._on_mqtt_connect_api(ist, None, None, 5)
    assert ortam.api._live_state["mqtt"] == "error"
    assert ist.abonelik == []
    assert ortam.bildirim == []


@pytest.mark.parametrize(("ham", "beklenen"), [("connected", "online"), (" 1 ", "online"), ("0", "offline")])
def test_kopru_durumu_GATEWAY_alanina_yazilir_ve_yayinlanir(ortam, ham, beklenen):
    """`pemf/bridge/status` yükü "1"/"true"/"connected" → gateway "online", aksi "offline"; `gateway_status` WS iletisi aynı değer."""
    ortam.api._on_mqtt_message_api(None, None, _ileti("pemf/bridge/status", ham))
    assert ortam.api._live_state["gateway"] == beklenen
    assert ortam.yayin == [{"type": "gateway_status", "data": {"gateway": beklenen}}]


@pytest.mark.parametrize(("yuk", "beklenen"), [({"status": "online"}, "online"), ({}, "offline")])
def test_ag_gecidi_konusu_durum_alanini_yazar_YOKSA_offline(ortam, yuk, beklenen):
    """`pemf/gateway/<x>` JSON yükü → gateway = yük["status"] (yoksa "offline") ve aynı değer WS'ye yayınlanır."""
    ortam.api._on_mqtt_message_api(None, None, _ileti("pemf/gateway/status", yuk))
    assert ortam.api._live_state["gateway"] == beklenen
    assert ortam.yayin == [{"type": "gateway_status", "data": {"gateway": beklenen}}]


def test_bobin_kimligi_SAYI_DEGILSE_hicbir_durum_degismez(ortam):
    """`pemf/coil/abc/status` → bobin durumu, telemetri damgası ve WS yayını DEĞİŞMEZ (ileti yok sayılır)."""
    a = ortam.api
    with a._live_state_lock:
        once = copy.deepcopy(a._live_state["coils"])
    tel = dict(a._coil_last_telemetry)
    a._on_mqtt_message_api(None, None, _ileti("pemf/coil/abc/status", {"status": "running", "frequency": 9}))
    assert a._live_state["coils"] == once
    assert dict(a._coil_last_telemetry) == tel
    assert ortam.yayin == []


def test_status_FREQUENCY_alani_bobin_frekansina_yazilir(ortam):
    """Canlı status yükü `frequency: 7.5` (pwm_frequency yok) → o bobinin `frequencyHz` alanı 7.5; `coil_status` yayını aynı değeri taşır."""
    esp_yolu_gerekir()
    a = ortam.api
    a._on_mqtt_message_api(None, None, _ileti(f"pemf/coil/{ESP_BOBIN}/status", {"frequency": 7.5}))
    assert a._live_state["coils"][ESP_BOBIN - 1]["frequencyHz"] == 7.5
    durum = [m for m in ortam.yayin if m.get("type") == "coil_status"]
    assert durum and durum[-1]["coilId"] == ESP_BOBIN and durum[-1]["data"]["frequencyHz"] == 7.5


def test_ozsinama_BASARISIZ_hata_bildirimi_ve_sonuc_yayini(ortam):
    """`selftest_fail` olayı → "error" düzeyli `bildirim.selfTestBasarisiz` (TR + EN, ayrıntı 160 karakterle kırpılmış) ve
    `selftest_result` WS iletisi {result: selftest_fail, message: kırpılmış ayrıntı}."""
    esp_yolu_gerekir()
    from utils import ceviri

    uzun = "X" * 300
    ortam.api._on_mqtt_message_api(
        None, None, _ileti(f"pemf/coil/{ESP_BOBIN}/events", {"type": "selftest_fail", "message": uzun})
    )
    kirpik = uzun[:160]
    assert len(ortam.bildirim) == 1
    mesaj, seviye, diller = ortam.bildirim[0]
    assert seviye == "error"
    assert mesaj == ceviri.t("bildirim.selfTestBasarisiz", dil="tr", coil=str(ESP_BOBIN), ayrinti=kirpik)
    assert diller["en"] == ceviri.t("bildirim.selfTestBasarisiz", dil="en", coil=str(ESP_BOBIN), ayrinti=kirpik)
    assert ortam.yayin[-1] == {
        "type": "selftest_result",
        "coilId": ESP_BOBIN,
        "data": {"result": "selftest_fail", "message": kirpik},
    }


@pytest.mark.parametrize(
    ("olay", "anahtar", "seviye"),
    [("selftest_ok", "bildirim.selfTestGecti", "success"), ("selftest_skipped", "bildirim.selfTestAtlandi", "info")],
)
def test_ozsinama_GECTI_ve_ATLANDI_kendi_duzeyinde_bildirilir(ortam, olay, anahtar, seviye):
    """`selftest_ok` → "success" + selfTestGecti; `selftest_skipped` → "info" + selfTestAtlandi; ayrıntı `detail`ten okunur ve yayına girer."""
    esp_yolu_gerekir()
    from utils import ceviri

    ortam.api._on_mqtt_message_api(None, None, _ileti(f"pemf/coil/{ESP_BOBIN}/events", {"type": olay, "detail": "d1"}))
    assert [(m, s) for m, s, _ in ortam.bildirim] == [(ceviri.t(anahtar, dil="tr", coil=str(ESP_BOBIN)), seviye)]
    assert ortam.yayin[-1]["data"] == {"result": olay, "message": "d1"}


def test_ESP_alarmi_STOP_is_parcacigi_ACILAMAZSA_isleyici_cokmez_alarm_bildirilir(ortam, monkeypatch, caplog):
    """Canlı (retain'siz) aşırı-akım alarmı + STOP iş parçacığı açılamıyor (`RuntimeError`) → işleyici istisna sızdırmaz,
    `bildirim.bobinAlarm` "error" bildirimi yine gider ve hata "ESP alarm STOP failed" olarak günlüğe yazılır."""
    esp_yolu_gerekir()
    from utils import ceviri

    gercek = threading.Thread

    class _AcilmayanThread(gercek):
        def start(self):
            if str(self.name).startswith("estop-"):
                raise RuntimeError("can't start new thread")
            return super().start()

    monkeypatch.setattr(threading, "Thread", _AcilmayanThread)
    caplog.set_level(logging.ERROR)
    ortam.api._on_mqtt_message_api(None, None, _ileti(f"pemf/coil/{ESP_BOBIN}/alarm", {"type": "overcurrent"}))
    assert (ceviri.t("bildirim.bobinAlarm", dil="tr", coil=str(ESP_BOBIN), atype="overcurrent"), "error") in [
        (m, s) for m, s, _ in ortam.bildirim
    ]
    assert any("ESP alarm STOP failed" in r.getMessage() for r in caplog.records)


def test_BOZUK_json_yuku_uyari_gunlugu_ile_yutulur(ortam, caplog):
    """Bobin konusunda JSON olmayan yük → istisna sızmaz; "MQTT on_message islenemedi (topic=…)" uyarısı konu adıyla yazılır,
    canlı durum ve yayın değişmez."""
    esp_yolu_gerekir()
    caplog.set_level(logging.WARNING)
    konu = f"pemf/coil/{ESP_BOBIN}/sensors"
    ortam.api._on_mqtt_message_api(None, None, _ileti(konu, b"{bozuk"))
    uyari = [r.getMessage() for r in caplog.records if "MQTT on_message islenemedi" in r.getMessage()]
    assert uyari and f"topic={konu}" in uyari[0]
    assert ortam.yayin == []
