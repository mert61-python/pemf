# Author: mertaygn, cglrgrkn
"""ESP KOMUT ONAYI (ACK ROUND-TRIP) — donanım-uyum denetimi HG-4 (2026-08-19).

NEDEN VAR: ESP bobinleri (6-8) her komuta `pemf/coil/{id}/ack`e {command_id, success} yayınlar,
ama backend bu konuyu DİNLEMİYORDU. `_mqtt_publish` yalnız broker PUBACK'ini okur → "broker aldı"
≠ "ESP aldı". WiFi'siz ESP'ye E-stop yayınlanınca broker PUBACK döner, çağıran "success" sayar,
operatöre "durduruldu" gösterir — ama ESP mesajı hiç almaz, bobin fiziksel enerjili kalır.

Bu kapı, backend'in ack'i GERÇEKTEN command_id ile eşlediğini + onay gelmeyince (WiFi partition)
operatörü UYARDIĞINI + E-stop'un ack beklerken BLOKLANMADIĞINI kilitler.
"""

from __future__ import annotations

import inspect
import threading
import time

import pytest

import servers.api_server as api


@pytest.fixture(autouse=True)
def _temiz_pending():
    """Her testten önce/sonra pending-ack tablosunu temizle (test izolasyonu)."""
    with api._pending_acks_lock:
        api._pending_acks.clear()
    yield
    with api._pending_acks_lock:
        api._pending_acks.clear()


def test_KRITIK_ack_command_id_ile_eslesir():
    """register → resolve → wait zinciri onayı doğru döndürür (True/False)."""
    api._register_ack("estop_6_111")
    api._resolve_ack("estop_6_111", True)
    assert api._wait_ack("estop_6_111", timeout=0.2) is True

    api._register_ack("estop_7_222")
    api._resolve_ack("estop_7_222", False)
    assert api._wait_ack("estop_7_222", timeout=0.2) is False


def test_KRITIK_onay_GELMEZSE_timeout_None_doner():
    """ESP hiç ack yollamazsa (WiFi partition) → wait None (=onay yok), sonsuz beklemez."""
    api._register_ack("estop_8_333")
    t0 = time.monotonic()
    sonuc = api._wait_ack("estop_8_333", timeout=0.3)
    assert sonuc is None
    assert time.monotonic() - t0 < 1.0, "timeout'a uyulmadı — E-stop yolu bloklanabilir"


def test_KRITIK_bilinmeyen_command_id_NO_OP():
    """Retained/bayat ack veya STM seri yolu bilinmeyen id → resolve çökmeR, wait None."""
    api._resolve_ack("hic_kayitli_olmayan", True)  # çökmemeli
    assert api._wait_ack("hic_kayitli_olmayan", timeout=0.05) is None


def test_KRITIK_ack_gec_gelirse_bekleyen_uyanir():
    """Gerçek yarış: wait sürerken başka thread'den ack gelir → hemen uyanır (polling değil)."""
    api._register_ack("estop_6_444")

    def _gec_ack():
        time.sleep(0.1)
        api._resolve_ack("estop_6_444", True)

    threading.Thread(target=_gec_ack, daemon=True).start()
    t0 = time.monotonic()
    assert api._wait_ack("estop_6_444", timeout=2.0) is True
    assert time.monotonic() - t0 < 0.5, "ack geldi ama wait erken uyanmadı (Event kullanılmıyor?)"


def test_KRITIK_handler_ack_dalini_ISLER(monkeypatch):
    """MQTT ack mesajı `_on_mqtt_message_api`'den geçince pending çözülür."""
    api._register_ack("estop_7_555")

    class _Msg:
        topic = "pemf/coil/7/ack"
        retain = False
        payload = b'{"coil_id":7,"command_id":"estop_7_555","success":true,"timestamp":1}'

    api._on_mqtt_message_api(None, None, _Msg())
    assert api._wait_ack("estop_7_555", timeout=0.2) is True


def test_KRITIK_retain_bayragi_ACK_cozumunu_ENGELLEMEZ():
    """Firmware ack'i retain=true yayınlar (S3:782 / 8266:767). is_retained ile ack'i elemek
    fix'i öldürürdü. Kayıtlı id → retain bayrağı ne olursa olsun çözülmeli."""
    api._register_ack("estop_8_666")

    class _RetMsg:
        topic = "pemf/coil/8/ack"
        retain = True  # firmware bayrağı; MQTT-3.3.1-9 gereği canlı teslimde broker 0'lar ama
        # bayat reconnect'te 1 kalır — her iki durumda da kayıtlı id çözülmeli
        payload = b'{"coil_id":8,"command_id":"estop_8_666","success":true,"timestamp":1}'

    api._on_mqtt_message_api(None, None, _RetMsg())
    assert api._wait_ack("estop_8_666", timeout=0.15) is True, (
        "retained ack yok sayıldı → fix ölü (her E-stop 'onay gelmedi' der)"
    )


def test_KRITIK_RETAINED_mesaj_watchdog_damgasini_TAZELEMEZ():
    """HG-4 denetimi: retained mesaj (broker'da kalmış) OFFLINE bobinin telemetri damgasını
    tazelememeli — yoksa stale-STOP tespiti 30 sn gecikir."""
    idx = 5  # bobin 6
    api._coil_last_telemetry[idx] = 0.0  # "uzun süredir sessiz" durumu

    class _RetStatus:
        topic = "pemf/coil/6/status"
        retain = True  # broker'da kalmış bayat status
        payload = b'{"coil_id":6,"pwm_active":false,"status":"online"}'

    api._on_mqtt_message_api(None, None, _RetStatus())
    assert api._coil_last_telemetry[idx] == 0.0, (
        "retained mesaj damgayı tazeledi → offline bobin 30 sn 'canlı' sanılır (watchdog geciker)"
    )

    # karşıt-kanıt: CANLI (retain=0) status damgayı GERÇEKTEN tazeler
    class _CanliStatus:
        topic = "pemf/coil/6/status"
        retain = False
        payload = b'{"coil_id":6,"pwm_active":false,"status":"online"}'

    api._on_mqtt_message_api(None, None, _CanliStatus())
    assert api._coil_last_telemetry[idx] > 0.0, "canlı mesaj damgayı tazelemiyor — watchdog kör"


def test_KRITIK_BAYAT_retained_ack_aktif_bekleyeni_BOZMAZ():
    """Bayat retained ack'e karşı koruma command_id BENZERSİZLİĞİ: eski id pending'de yok → no-op.
    Aktif bir E-stop'u sahte-çözmez."""
    api._register_ack("estop_6_YENI")  # aktif E-stop bekliyor

    class _BayatMsg:
        topic = "pemf/coil/6/ack"
        retain = True
        payload = b'{"coil_id":6,"command_id":"estop_6_ESKI","success":true,"timestamp":1}'

    api._on_mqtt_message_api(None, None, _BayatMsg())  # eski id
    # aktif bekleyen (YENI) çözülmemeli — bayat ESKI id onu etkilemez
    assert api._wait_ack("estop_6_YENI", timeout=0.1) is None


def test_KRITIK_estop_ONAY_GELMEYINCE_operator_UYARILIR(monkeypatch):
    """_estop_ack_watch: onay gelmezse _push_notification ile AÇIK uyarı + error log."""
    uyarilar = []
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": uyarilar.append((msg, sev)))
    api._register_ack("estop_6_777")  # ama kimse resolve etmeyecek → timeout

    # gerçek watch (2s timeout) yerine kısa: fonksiyonu doğrudan ama düşük timeout'la taklit
    # _estop_ack_watch sabit 2.0s bekler; testi hızlandırmak için _wait_ack'i kısalt.
    orij = api._wait_ack
    monkeypatch.setattr(api, "_wait_ack", lambda cid, timeout: orij(cid, 0.2))
    api._estop_ack_watch(6, "estop_6_777")

    assert uyarilar, "onay gelmedi ama operatör UYARILMADI (sessiz başarısızlık geri geldi)"
    assert uyarilar[0][1] == "error"
    assert "onay" in uyarilar[0][0].lower()


def test_KRITIK_estop_onaylaninca_UYARI_YOK(monkeypatch):
    """Karşıt-kanıt: ESP onaylarsa gereksiz alarm çalmaz."""
    uyarilar = []
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": uyarilar.append((msg, sev)))
    api._register_ack("estop_7_888")
    api._resolve_ack("estop_7_888", True)
    api._estop_ack_watch(7, "estop_7_888")
    assert not uyarilar, "onay geldiği hâlde yanlış alarm çaldı"


def test_KARSIT_KANIT_subscribe_ve_kapsam_YERINDE():
    """Regresyon: ack subscribe + handler dalı + register çağrısı KODDA duruyor mu."""
    src = inspect.getsource(api)
    assert 'subscribe("pemf/coil/+/ack")' in src, "ack subscribe düşmüş — onaylar HİÇ gelmez"
    assert 'msg_type == "ack"' in src, "handler ack dalı düşmüş"
    assert "_register_ack(command_id)" in src, "E-stop publish öncesi ack kaydı düşmüş"
    # ESP kapsamı: watch yalnız ESP bobinleri için anlamlı (STM ack MQTT yollamaz)
    assert api.ESP_COIL_IDS == {6, 7, 8}, f"ESP_COIL_IDS beklenmedik: {api.ESP_COIL_IDS}"
