# Author: mertaygn, cglrgrkn
"""KP-1 · apps/backend/servers/api_server.py · sözleşmeler: ESP / MQTT yolu — `_mqtt_publish` (PUBACK beklemesi beklenmedik
istisna verse de `is_published` karar verir, bağlantı hatası False), `_mqtt_credentials` (depo ve kasa okunamazsa ortam
değişkenleri), START onay bekçisi (bayat NACK koşuyu kapatmaz, güncel NACK'te koşu kapatma / bildirim hatası yutulur, zaman
aşımı yayını), bekçi iş parçacığı açılamazsa bekleyen kayıt temizlenir, ESP yayın döngüsü bir bobinin hatasında durmaz,
E-stop onay bekçisi bildirim hatasını yutar, reconcile (seans kapsıyorsa STOP yok; arada seans açılırsa yayın yok; bildirim
hatası yutulur), E-stop bulut aynası (teslim sayımı / bağlantı hatası), broker sondası, gözetimsiz süre çözümü.

Sahte EN ALT katta: soket (`socket.create_connection`), paho istemcisi (`paho.mqtt.client.Client`), kasa
(`utils.secrets_manager.get_secret`), makine kimlik deposu (`utils.mqtt_kimlik.backend_kimligi`), bildirim gönderimi
(`_push_notification` — arıza biçimi `ConnectionResetError`), iş parçacığı açılışı (`threading.Thread.start` → `RuntimeError`),
kayıt kuyruğu (`utils.dongu_disi_yazim.calistir` — yürütücü kapalı `RuntimeError`).
"""

from __future__ import annotations

import logging
import threading
from types import SimpleNamespace

import pytest
from topoloji import ESP_BOBIN, TUM_ESP, esp_yolu_gerekir


@pytest.fixture
def api(monkeypatch):
    from servers import api_server as a
    from servers import live_state as ls

    yayin: list = []
    bildirim: list = []
    monkeypatch.setattr(a, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: yayin.append(m))
    monkeypatch.setattr(a, "_push_notification", lambda m, s="info", mesajlar=None: bildirim.append((m, s)))
    with a._esp_intent_lock:
        niyet = (
            dict(a._esp_commanded_running),
            dict(a._esp_stop_zamani),
            dict(a._reconcile_last_stop),
            dict(a._reconcile_last_notify),
        )
    with a._pending_acks_lock:
        bekleyen = (dict(a._pending_acks), dict(a._son_start_kimligi))
    try:
        yield SimpleNamespace(a=a, yayin=yayin, bildirim=bildirim)
    finally:
        with a._esp_intent_lock:
            for hedef, kaynak in zip(
                (a._esp_commanded_running, a._esp_stop_zamani, a._reconcile_last_stop, a._reconcile_last_notify), niyet
            ):
                hedef.clear()
                hedef.update(kaynak)
        with a._pending_acks_lock:
            a._pending_acks.clear()
            a._pending_acks.update(bekleyen[0])
            a._son_start_kimligi.clear()
            a._son_start_kimligi.update(bekleyen[1])


def _bildirim_patlar(o, monkeypatch):
    def _patlayan(*_a, **_k):
        raise ConnectionResetError("bildirim kanalı kapandı")

    monkeypatch.setattr(o.a, "_push_notification", _patlayan)


class _Info:
    def __init__(self, yayinlandi=True, bekleme_hatasi=None):
        self._y = yayinlandi
        self._h = bekleme_hatasi

    def wait_for_publish(self, timeout=None):
        if self._h is not None:
            raise self._h

    def is_published(self):
        return self._y


class _WouldBlock(Exception):
    """paho ≥2 `wait_for_publish` zaman aşımında attığı türden (ValueError/RuntimeError/OSError DIŞI) istisna."""


def _paho_kur(monkeypatch, *, connect_hata=None, info=None):
    import paho.mqtt.client as pm

    kayit = SimpleNamespace(yayin=[], kimlik=None, baglanti=None, tls=False, loop=[])

    class _Client:
        def __init__(self, *a, **k):
            pass

        def username_pw_set(self, u, p):
            kayit.kimlik = (u, p)

        def tls_set(self):
            kayit.tls = True

        def connect(self, host, port, *a, **k):
            if connect_hata is not None:
                raise connect_hata
            kayit.baglanti = (host, port)

        def publish(self, topic, yuk, qos=0):
            kayit.yayin.append((topic, yuk, qos))
            return info or _Info()

        def loop_start(self):
            kayit.loop.append("start")

        def loop_stop(self):
            kayit.loop.append("stop")

        def disconnect(self):
            kayit.loop.append("disconnect")

    monkeypatch.setattr(pm, "Client", _Client)
    return kayit


class _Soket:
    def close(self):
        pass


def _soket_acik(monkeypatch):
    import socket

    adresler: list = []

    def _baglan(adres, timeout=None):
        adresler.append(adres)
        return _Soket()

    monkeypatch.setattr(socket, "create_connection", _baglan)
    return adresler


def _kasa(monkeypatch, degerler: dict):
    from utils import secrets_manager

    monkeypatch.setattr(secrets_manager, "get_secret", lambda ad, *a, **k: degerler.get(ad, k.get("default")))


def test_yayin_PUBACK_beklemesi_beklenmedik_istisna_verse_de_is_published_karar_verir(api, monkeypatch):
    """ESP etkin, broker sondası açık, `wait_for_publish` ValueError/RuntimeError/OSError DIŞI istisna, `is_published` True →
    `_mqtt_publish` True döner ve START niyeti (doğrulanmış yayın) bobin için True kaydedilir; yayın qos=1 ile tek kez gider."""
    esp_yolu_gerekir()
    a = api.a
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    _soket_acik(monkeypatch)
    _kasa(monkeypatch, {})
    monkeypatch.setattr("utils.mqtt_kimlik.backend_kimligi", lambda: (None, None))
    paho = _paho_kur(monkeypatch, info=_Info(True, _WouldBlock("yanıt bekleniyor")))
    a._esp_commanded_running.pop(ESP_BOBIN, None)
    assert a._mqtt_publish(f"pemf/coil/{ESP_BOBIN}/control", {"command": "start", "command_id": "kp1"}) is True
    assert a._esp_commanded_running.get(ESP_BOBIN) is True
    assert [(t, q) for t, _y, q in paho.yayin] == [(f"pemf/coil/{ESP_BOBIN}/control", 1)]
    assert paho.loop == ["start", "stop", "disconnect"]


def test_yayin_BAGLANTI_hatasi_False_ve_START_niyeti_kaydedilmez(api, monkeypatch):
    """Sonda açık ama paho `connect` ConnectionRefusedError → `_mqtt_publish` False; START niyeti True YAZILMAZ, yayın yok."""
    esp_yolu_gerekir()
    a = api.a
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    _soket_acik(monkeypatch)
    _kasa(monkeypatch, {})
    monkeypatch.setattr("utils.mqtt_kimlik.backend_kimligi", lambda: (None, None))
    paho = _paho_kur(monkeypatch, connect_hata=ConnectionRefusedError(10061, "reddedildi"))
    a._esp_commanded_running.pop(ESP_BOBIN, None)
    assert a._mqtt_publish(f"pemf/coil/{ESP_BOBIN}/control", {"command": "start", "command_id": "kp2"}) is False
    assert a._esp_commanded_running.get(ESP_BOBIN) is None
    assert paho.yayin == []


@pytest.mark.parametrize(
    ("kullanici", "parola", "beklenen"), [("op", "gizli", ("op", "gizli")), ("", "", (None, None))]
)
def test_kimlik_DEPO_ve_KASA_okunamazsa_ortam_degiskenleri(api, monkeypatch, kullanici, parola, beklenen):
    """Makine kimlik deposu ve kasa istisna atıyor → (PEMF_MQTT_USER, PEMF_MQTT_PASS); ikisi de boşsa (None, None) — anonim."""
    from utils import mqtt_kimlik, secrets_manager

    def _patlayan(*_a, **_k):
        raise OSError("depo okunamadı")

    monkeypatch.setattr(mqtt_kimlik, "backend_kimligi", _patlayan)
    monkeypatch.setattr(secrets_manager, "get_secret", _patlayan)
    monkeypatch.setenv("PEMF_MQTT_USER", kullanici)
    monkeypatch.setenv("PEMF_MQTT_PASS", parola)
    assert api.a._mqtt_credentials() == beklenen


def test_START_bekcisi_BAYAT_nack_kosuyu_kapatmaz_bildirim_hatasi_yutulur(api, monkeypatch, caplog):
    """NACK gelen START, bobinin SON start'ı değil (araya yeni start girmiş) + bildirim kanalı patlıyor → bekçi istisnasız döner,
    `coil_ack` {ok: False, reason: nack} yayınlanır, koşu kapatma DENENMEZ, "ONCEKI start … reddedildi" uyarısı yazılır."""
    a = api.a
    kapatilan: list = []
    monkeypatch.setattr(a, "_finish_coil_run", lambda *x, **k: kapatilan.append(x))
    _bildirim_patlar(api, monkeypatch)
    a._register_ack("kp-eski", bobin=ESP_BOBIN or 8)
    a._resolve_ack("kp-eski", False, bobin=ESP_BOBIN or 8)
    a._son_start_kimligi[ESP_BOBIN or 8] = "kp-yeni"
    caplog.set_level(logging.WARNING)
    a._start_ack_watch(ESP_BOBIN or 8, "kp-eski", run_id=41)
    ack = [m for m in api.yayin if m.get("type") == "coil_ack"]
    assert len(ack) == 1 and ack[0]["data"]["ok"] is False and ack[0]["data"]["reason"] == "nack"
    assert kapatilan == []
    assert any("ONCEKI start kp-eski reddedildi" in r.getMessage() for r in caplog.records)


def test_START_bekcisi_GUNCEL_nack_kosu_kapatma_hatasi_ve_bildirim_hatasi_yutulur(api, monkeypatch, caplog):
    """Güncel START'a NACK + koşu kapatma kuyruğu kapalı (RuntimeError) + bildirim kanalı patlıyor → bekçi istisnasız döner,
    `coil_ack` nack yayınlanır, "NACK sonrasi run kapatma hatasi" (debug) yazılır."""
    from utils import dongu_disi_yazim

    a = api.a
    b = ESP_BOBIN or 8

    def _kuyruk(fn, *x, ad="kayit", **k):
        if str(ad).startswith("bobin kosu kaydi bitir"):
            raise RuntimeError("cannot schedule new futures after shutdown")
        return fn(*x, **k)

    monkeypatch.setattr(dongu_disi_yazim, "calistir", _kuyruk)
    _bildirim_patlar(api, monkeypatch)
    a._register_ack("kp-guncel", bobin=b)
    a._resolve_ack("kp-guncel", False, bobin=b)
    a._son_start_kimligi[b] = "kp-guncel"
    caplog.set_level(logging.DEBUG)
    a._start_ack_watch(b, "kp-guncel", run_id=42)
    assert [m["data"]["reason"] for m in api.yayin if m.get("type") == "coil_ack"] == ["nack"]
    assert any(r.getMessage() == "NACK sonrasi run kapatma hatasi" for r in caplog.records)


def test_START_bekcisi_ZAMAN_ASIMI_yayini_bildirim_hatasinda_da(api, monkeypatch):
    """Bekleyen kayıt yok (onay gelmeyecek) + bildirim kanalı patlıyor → `coil_ack` {ok: None, reason: timeout} yayınlanır,
    istisna sızmaz."""
    a = api.a
    _bildirim_patlar(api, monkeypatch)
    a._start_ack_watch(ESP_BOBIN or 8, "kp-yok")
    ack = [m["data"] for m in api.yayin if m.get("type") == "coil_ack"]
    assert len(ack) == 1 and ack[0]["ok"] is None and ack[0]["reason"] == "timeout"


def test_START_bekcisi_is_parcacigi_ACILAMAZSA_bekleyen_kayit_temizlenir(api, monkeypatch, caplog):
    """Yayın başarılı ama `start-ack-*` iş parçacığı açılamıyor → `_pending_acks`ten o komut silinir, uyarı yazılır."""
    a = api.a
    b = ESP_BOBIN or 8
    gercek = threading.Thread

    class _Acilmayan(gercek):
        def start(self):
            if str(self.name).startswith("start-ack-"):
                raise RuntimeError("can't start new thread")
            return super().start()

    monkeypatch.setattr(threading, "Thread", _Acilmayan)
    a._register_ack("kp-izsiz", bobin=b)
    caplog.set_level(logging.WARNING)
    a._start_ack_izle_arka_planda(b, "kp-izsiz", True, run_id=None)
    assert "kp-izsiz" not in a._pending_acks
    assert any(f"start-ack bekcisi baslatilamadi (bobin {b})" == r.getMessage() for r in caplog.records)


def test_ESP_toplu_yayin_bir_bobinde_PATLASA_da_digerleri_denenir(api, monkeypatch):
    """`_mqtt_publish` her çağrıda istisna atıyor → `_esp_control_broadcast` istisna sızdırmaz ve TÜM ESP bobinleri için
    `pemf/coil/<id>/control` denenir (komut + önek kimliği + ek alanlar yükte)."""
    a = api.a
    denenen: list = []

    def _patlayan(topic, payload):
        denenen.append((topic, payload["command"], payload["command_id"].split("_")[0], payload.get("x")))
        raise OSError("broker yok")

    monkeypatch.setattr(a, "_mqtt_publish", _patlayan)
    a._esp_control_broadcast("selftest", "kpst", {"x": 1})
    assert denenen == [(f"pemf/coil/{i}/control", "selftest", "kpst", 1) for i in sorted(TUM_ESP)]


@pytest.mark.parametrize(("sonuc", "gunluk"), [(False, "REDDETTİ (NACK)"), (None, "ONAYI GELMEDI")])
def test_ESTOP_onay_bekcisi_bildirim_hatasini_yutar_gunluge_yazar(api, monkeypatch, caplog, sonuc, gunluk):
    """E-stop onayı NACK ya da zaman aşımı + bildirim kanalı patlıyor → bekçi istisnasız döner, hata günlüğe yazılır."""
    a = api.a
    b = ESP_BOBIN or 8
    _bildirim_patlar(api, monkeypatch)
    if sonuc is False:
        a._register_ack("kp-estop", bobin=b)
        a._resolve_ack("kp-estop", False, bobin=b)
    caplog.set_level(logging.ERROR)
    a._estop_ack_watch(b, "kp-estop")
    assert any(gunluk in r.getMessage() and f"bobin {b}" in r.getMessage() for r in caplog.records)


def _reconcile_hazirla(api, monkeypatch):
    a = api.a
    b = ESP_BOBIN
    a._esp_commanded_running[b] = False
    a._esp_stop_zamani.pop(b, None)
    a._reconcile_last_stop.pop(b, None)
    a._reconcile_last_notify.pop(b, None)
    hedefler: list = []
    gercek = threading.Thread

    class _Tutan(gercek):
        def start(self):
            if str(self.name).startswith("reconcile-stop-"):
                hedefler.append(self._target)
                return None
            return super().start()

    monkeypatch.setattr(threading, "Thread", _Tutan)
    yayin: list = []
    monkeypatch.setattr(a, "_mqtt_publish", lambda t, p: yayin.append((t, p["command"])) or True)
    return a, b, hedefler, yayin


def test_reconcile_AKTIF_seans_bobini_kapsiyorsa_STOP_planlanmaz(api, monkeypatch):
    """ESP 'çalışıyor' + niyet yok + aktif seans bu bobini kapsıyor → STOP iş parçacığı kurulmaz, hız sınırı damgası yazılmaz."""
    esp_yolu_gerekir()
    a, b, hedefler, yayin = _reconcile_hazirla(api, monkeypatch)
    monkeypatch.setitem(a._active_session, "is_active", True)
    monkeypatch.setitem(a._active_session, "coil_ids", [b])
    a._reconcile_esp_calisiyor(b, {"running": True})
    assert hedefler == [] and b not in a._reconcile_last_stop and yayin == []


def test_reconcile_ARADA_seans_acilirsa_STOP_yayinlanmaz(api, monkeypatch):
    """STOP planlandıktan sonra (iş parçacığı koşmadan) bobini kapsayan seans açıldı → `_stop_gonder` yayın YAPMAZ."""
    esp_yolu_gerekir()
    a, b, hedefler, yayin = _reconcile_hazirla(api, monkeypatch)
    monkeypatch.setitem(a._active_session, "is_active", False)
    a._reconcile_esp_calisiyor(b, {"running": True})
    assert len(hedefler) == 1
    monkeypatch.setitem(a._active_session, "is_active", True)
    monkeypatch.setitem(a._active_session, "coil_ids", [b])
    hedefler[0]()
    assert yayin == []


def test_reconcile_STOP_yayinlanir_bildirim_hatasi_yutulur(api, monkeypatch):
    """Seans yok → planlanan `_stop_gonder` hedefli STOP yayınlar; bildirim kanalı patlasa da istisna sızmaz ve bildirim
    damgası (5 dk sınırı) yazılır."""
    esp_yolu_gerekir()
    a, b, hedefler, yayin = _reconcile_hazirla(api, monkeypatch)
    monkeypatch.setitem(a._active_session, "is_active", False)
    _bildirim_patlar(api, monkeypatch)
    a._reconcile_esp_calisiyor(b, {"running": True})
    hedefler[0]()
    assert yayin == [(f"pemf/coil/{b}/control", "stop")]
    assert b in a._reconcile_last_notify


def test_bulut_aynasi_TESLIM_sayar_bekleme_istisnasi_yutulur(api, monkeypatch, caplog):
    """Bulut sırları tanımlı, her yayının PUBACK beklemesi istisna atıyor ama yayınlanmış → her bobin için iki konu (control +
    esp32_<id>/command) TLS + kimlikle yayınlanır, "2/2 yayin teslim edildi" yazılır, istemci kapatılır."""
    a = api.a
    _kasa(
        monkeypatch,
        {"mqtt_cloud_host": "bulut.ornek", "mqtt_cloud_user": "u", "mqtt_cloud_pass": "p", "mqtt_cloud_port": "8883"},
    )
    paho = _paho_kur(monkeypatch, info=_Info(True, OSError("zaman aşımı")))
    caplog.set_level(logging.WARNING)
    a._estop_cloud_mirror([8], "kp-test")
    assert paho.tls is True and paho.kimlik == ("u", "p") and paho.baglanti == ("bulut.ornek", 8883)
    assert [t for t, _y, _q in paho.yayin] == ["pemf/coil/8/control", "pemf/esp32_8/command"]
    assert any("(kp-test): 2/2 yayin teslim edildi" in r.getMessage() for r in caplog.records)
    assert paho.loop[-2:] == ["stop", "disconnect"]


def test_bulut_aynasi_BAGLANTI_hatasi_yerel_yolu_etkilemez(api, monkeypatch, caplog):
    """Bulut `connect` OSError → ayna istisna sızdırmaz, "E-stop bulut aynasi basarisiz" uyarısı yazılır, yayın yok."""
    a = api.a
    _kasa(monkeypatch, {"mqtt_cloud_host": "bulut.ornek", "mqtt_cloud_user": "u", "mqtt_cloud_pass": "p"})
    paho = _paho_kur(monkeypatch, connect_hata=OSError("ağ yok"))
    caplog.set_level(logging.WARNING)
    a._estop_cloud_mirror([8], "kp-test")
    assert paho.yayin == []
    assert any("E-stop bulut aynasi basarisiz" in r.getMessage() for r in caplog.records)


def test_broker_sondasi_ACIK_soket_True(api, monkeypatch):
    """127.0.0.1:1883'e sonda bağlantısı kurulabiliyor → `_broker_reachable` True (soket kapatılır)."""
    adresler = _soket_acik(monkeypatch)
    assert api.a._broker_reachable() is True
    assert adresler == [("127.0.0.1", 1883)]


@pytest.mark.parametrize("ham", ["abc", None, "0", -5])
def test_gozetimsiz_sure_SAYI_DEGIL_ya_da_SIFIR_klinik_kapak(api, ham):
    """ESP süresi sayıya çevrilemiyor / 0 / negatif → `_esp_duration_seconds` klinik gözetimsiz kapağı verir
    (`GOZETIMSIZ_VARSAYILAN_DAKIKA` × 60 sn); STM dakika çevirisi sayı olmayanda 0 (süresiz değil, kapaklı yol)."""
    from controllers.hardware_controller import GOZETIMSIZ_VARSAYILAN_DAKIKA

    assert api.a._esp_duration_seconds(ham) == GOZETIMSIZ_VARSAYILAN_DAKIKA * 60
    assert api.a._duration_seconds_to_stm_minutes(ham) == 0
