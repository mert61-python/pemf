# Author: mertaygn, cglrgrkn
"""A-04 · D1.104 (D-2.1) — yerel broker KİMLİKLİ: anonim istemcinin sahte ack'i E-stop onayı SAYILMAZ.

ÖLÇÜLEN KUSUR (HEAD 1dae755; GERÇEK mosquitto 2.0.18 + kurulum betiğinin yapılandırması): broker anonim. LAN'daki bir
istemci `pemf/coil/+/control`'a abone olup E-stop'un `command_id`'sini görüyor ve `pemf/coil/8/ack`'e `{success:true}`
yayınlıyor → backend'in E-stop ack bekçisi "ESP ONAYLADI" der; gerçek ESP yokken / bobin durmamışken operatörün
"bobini elle kontrol edin" uyarısı ÇIKMAZ. Ayrıca ack HERHANGİ bir bobin konusundan gelse teyit sayılıyordu.

DÜZELTME: `utils.mqtt_kimlik hazirla` (ESP dönüşünde) broker'a parola + ACL parçası yazar — kurulum yapılandırması onu
SONDA içerir; backend kimliği AYNI adımda (STOP yayınları kimlikli broker'da da geçer); ESP firmware'i aynı adımın
başlığıyla (`MqttKimlik.h`) kimlikle bağlanır. Backend ack'i komutun BOBİN konusuna bağlar.

KAPI (gerçek broker 127.0.0.1:rastgele; ürün kodu 127.0.0.1:1883'ten YÖNLENDİRİLİR, değişmez — `mosquitto_aparat`):
  KRİTİK — gerçek ESP yokken anonim saldırgan control'u dinleyip ack sahteler → E-stop ack bekçisi TEYİT ETMEZ,
           operatör UYARILIR; saldırgan kimlikli broker'a BAĞLANAMAZ.
  KRİTİK — backend rolü ack YAZAMAZ, ESP rolü control YAZAMAZ (yetki).
  KRİTİK — ESP ack'i YANLIŞ bobin konusundan gönderirse teyit sayılmaz.
  KRİTİK (değişmez) — E-stop STOP yayın SAYISI değişmez (ESP bobini başına control + eski konu) ve hepsi PUBACK alır.
  KARŞIT — ESP kimliğiyle gelen gerçek ack TEYİT edilir; hazırlanmamış broker bugünkü gibi anonim kabul eder.
HEAD'de hazırlama aracı yok → aynı senaryolar kurulum yapılandırmasıyla (anonim) koşar: önce-kırmızı oradan ölçülür.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
import types

import capraz
import mosquitto_aparat as ma
import pytest

_ESP_YOK = "mosquitto ikilisi yok (Linux CI) — Windows CI aynı kapıyı paketteki mosquitto 2.0.18 ile koşar"
_ACK_BEKLEME_SN = 2.8  # ürünün E-stop ack bekçisi 2.0 sn bekler


def _kimlik_modulu():
    try:
        from utils import mqtt_kimlik

        return mqtt_kimlik
    except ImportError:
        return None  # HEAD (A-04 öncesi): hazırlama aracı YOK → broker kurulum yapılandırmasıyla (anonim) koşar


@contextlib.contextmanager
def _ortam(monkeypatch, tmp_path, *, hazirla: bool = True):
    if ma.ikili() is None:
        capraz.atla(_ESP_YOK)
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc
    from servers import api_server as api0

    gercek_yayin, gercek_bekci = api0._mqtt_publish, api0._estop_ack_watch
    monkeypatch.setenv("PEMF_DEVICE_IDENTITY_DIR", str(tmp_path / "makine"))
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    for ad in ("PEMF_MQTT_USER", "PEMF_MQTT_PASS"):
        monkeypatch.delenv(ad, raising=False)
    mk = _kimlik_modulu()
    kimlik = None
    if mk is not None:
        mk._onbellek.clear()
        if hazirla:
            mk.hazirla()  # varsayılan broker dizini = <makine>/mosquitto = kurulumun $MosqDataRoot'u
            kimlik = mk.kimlikleri_oku()
    veri = tmp_path / "makine" / "mosquitto"
    # Kurulum betiğinin yaptığı (yapısal kapı pinler): conf.d + yalnız yorumdan oluşan yer tutucu parça — mosquitto
    # Windows'ta BOŞ include_dir'de AÇILMAZ (ölçüldü: rc=3 "Unable to open include_dir").
    (veri / "conf.d").mkdir(parents=True, exist_ok=True)
    (veri / "conf.d" / "00_pemf_taban.conf").write_text("# PEMF yer tutucu" + chr(10), encoding="ascii")
    port = ma.bos_port()
    broker = ma.Broker(ma.kurulum_yapilandirmasi(port, veri), tmp_path / "broker", port).basla()
    istemciler: list = []
    ns = None
    try:
        ma.yonlendir(monkeypatch, port)
        ns = ap.kur(monkeypatch, tmp_path)
        monkeypatch.setattr(ns.api, "_mqtt_publish", gercek_yayin)
        monkeypatch.setattr(ns.api, "_estop_ack_watch", gercek_bekci)
        monkeypatch.setattr(ns.api, "_mqtt_client_api", getattr(ns.api, "_mqtt_client_api", None))
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.api._start_mqtt_for_api()
            o = types.SimpleNamespace(api=ns.api, ns=ns, port=port, kimlik=kimlik, broker=broker, istemciler=istemciler)
            _dinleyici_hazir(o)
            yield o
    finally:
        ma.kapat(*istemciler)
        if ns is not None:
            dinleyici = getattr(ns.api, "_mqtt_client_api", None)
            if dinleyici is not None:
                ma.kapat(dinleyici)
            ns.geri()
        broker.dur()
        if mk is not None:
            mk._onbellek.clear()


def _rol(o, rol: str):
    """Rolün istemcisi: kimlik hazırlandıysa o rolün kimliği, değilse (HEAD) anonim."""
    if not o.kimlik:
        k, p = None, None
    else:
        from utils import mqtt_kimlik as mk

        k = mk.ESP_KULLANICI if rol == "esp" else mk.BACKEND_KULLANICI
        p = o.kimlik[k]
    c, rc = ma.istemci(o.port, k, p, ad=rol)
    assert c is not None, f"aparat: {rol} rolü broker'a bağlanamadı (rc={rc})"
    o.istemciler.append(c)
    return c


def _dinleyici_hazir(o) -> None:
    """Backend dinleyicisi bağlandı ve ack'e ABONE: sonda ack'i cihaz rolünden yayınlanır, `_wait_ack` True dönmeli."""
    api = o.api
    son = time.monotonic() + 10
    while time.monotonic() < son and not (api._mqtt_client_api is not None and api._mqtt_client_api.is_connected()):
        time.sleep(0.05)
    assert api._mqtt_client_api is not None and api._mqtt_client_api.is_connected(), (
        "aparat: backend dinleyicisi bağlanmadı"
    )
    cihaz = _rol(o, "esp")
    for i in range(20):
        sonda = f"sonda_{i}_{time.time_ns()}"
        api._register_ack(sonda)
        cihaz.publish("pemf/coil/8/ack", json.dumps({"command_id": sonda, "success": True}), qos=1)
        if api._wait_ack(sonda, 0.5) is True:
            return
    raise AssertionError("aparat: backend dinleyicisi ack konusunu almıyor")


def _ack_veren_cihaz(o, *, rol: str | None, ack_bobini=None, anonim: bool = False):
    """`pemf/coil/+/control`'u dinler, her STOP'a `{success:true}` ack basar (ack_bobini: ack'in YAYINLANDIĞI konu)."""
    if anonim:
        c, rc = ma.istemci(o.port, ad="saldirgan")
        if c is None:
            return None, rc, []
        o.istemciler.append(c)
    else:
        c, rc = _rol(o, rol), 0
    sahtelenen: list = []
    kilit = threading.Lock()

    def _dinle(istemci, _u, m):
        try:
            p = json.loads(m.payload.decode("utf-8"))
        except Exception:
            return
        if str(p.get("command", "")).lower() == "stop" and p.get("command_id"):
            bobin = ack_bobini if ack_bobini is not None else m.topic.split("/")[2]
            istemci.publish(
                f"pemf/coil/{bobin}/ack", json.dumps({"command_id": p["command_id"], "success": True}), qos=1
            )
            with kilit:
                sahtelenen.append(p["command_id"])

    c.on_message = _dinle
    c.subscribe("pemf/coil/+/control", qos=1)
    time.sleep(0.4)
    return c, rc, sahtelenen


def _estop_uyarilari(o, b0: int) -> list:
    return [m for m, t in o.ns.bildirim[b0:] if t == "error" and "Bobin 8" in m and ("GELMED" in m or "REDDED" in m)]


def test_KRITIK_D1104_anonim_saldirgan_sahte_ackle_E_STOP_onayini_TAKLIT_EDEMEZ(monkeypatch, tmp_path):
    with _ortam(monkeypatch, tmp_path) as o:
        _saldirgan, rc, sahtelenen = _ack_veren_cihaz(o, rol=None, anonim=True)
        b0 = len(o.ns.bildirim)
        yanit = o.api._emergency_stop_all("manual")
        time.sleep(_ACK_BEKLEME_SN)
        uyarilar = _estop_uyarilari(o, b0)
    assert yanit["mqttResults"] == [{"coilId": 8, "mqtt": "success"}], f"aparat: E-stop STOP'u yayınlanamadı: {yanit}"
    assert uyarilar, (
        "anonim saldırganın sahte ack'i E-stop'u 'ESP ONAYLADI' gösterdi — gerçek ESP yokken operatör UYARILMADI "
        f"(D-2.1). saldırgan bağlantı rc={rc}, sahtelenen komut sayısı={len(sahtelenen)}"
    )
    assert rc not in (0, None), f"anonim istemci kimlikli broker'a BAĞLANABİLDİ (rc={rc})"


def test_KARSIT_D1104_ESP_kimligiyle_gelen_gercek_ack_TEYIT_edilir(monkeypatch, tmp_path):
    with _ortam(monkeypatch, tmp_path) as o:
        _cihaz, _rc, ackler = _ack_veren_cihaz(o, rol="esp")
        b0 = len(o.ns.bildirim)
        o.api._emergency_stop_all("manual")
        time.sleep(_ACK_BEKLEME_SN)
        uyarilar = _estop_uyarilari(o, b0)
    assert ackler, "aparat: cihaz STOP'u almadı"
    assert not uyarilar, f"gerçek ESP ack'i teyit edilmedi — sahte uyarı: {uyarilar}"


def test_KRITIK_D1104_ESP_acki_YANLIS_bobin_konusundan_gelirse_teyit_SAYILMAZ(monkeypatch, tmp_path):
    with _ortam(monkeypatch, tmp_path) as o:
        _cihaz, _rc, ackler = _ack_veren_cihaz(o, rol="esp", ack_bobini=6)
        b0 = len(o.ns.bildirim)
        o.api._emergency_stop_all("manual")
        time.sleep(_ACK_BEKLEME_SN)
        uyarilar = _estop_uyarilari(o, b0)
    assert ackler, "aparat: cihaz STOP'u almadı"
    assert uyarilar, "bobin 8'in E-stop'u bobin 6'nın ack konusundan gelen ack'le 'ESP ONAYLADI' sayıldı (ack kaynağı)"


def test_KRITIK_D1104_backend_rolu_ack_YAZAMAZ_ESP_rolu_control_YAZAMAZ(monkeypatch, tmp_path):
    with _ortam(monkeypatch, tmp_path) as o:
        gozcu = _rol(o, "backend")
        alinan: list = []
        gozcu.on_message = lambda _c, _u, m: alinan.append((m.topic, m.payload.decode("utf-8", "replace")))
        gozcu.subscribe([("pemf/coil/8/ack", 1), ("pemf/coil/8/control", 1)])
        time.sleep(0.4)
        backend_rolu, esp_rolu = _rol(o, "backend"), _rol(o, "esp")
        backend_rolu.publish("pemf/coil/8/ack", '{"command_id":"sahte_backend","success":true}', qos=1)
        esp_rolu.publish("pemf/coil/8/control", '{"command":"start","command_id":"sahte_esp"}', qos=1)
        esp_rolu.publish("pemf/coil/8/ack", '{"command_id":"gercek_esp","success":true}', qos=1)
        time.sleep(0.8)
    yukler = [y for _, y in alinan]
    assert any("gercek_esp" in y for y in yukler), f"aparat: gözcü ESP ack'ini almadı: {alinan}"
    assert not any("sahte_backend" in y for y in yukler), (
        "backend rolü ack konusuna YAZABİLDİ (ack kaynağı doğrulanmıyor)"
    )
    assert not any("sahte_esp" in y for y in yukler), (
        "ESP rolü control konusuna YAZABİLDİ (bobine komut sahtelenebilir)"
    )


def test_KRITIK_D1104_E_STOP_yayin_SAYISI_DEGISMEZ_ve_kimlikli_brokerda_PUBACK_alir(monkeypatch, tmp_path):
    with _ortam(monkeypatch, tmp_path) as o:
        gercek = o.api._mqtt_publish
        sayac: list = []
        kilit = threading.Lock()

        def _sayan(topic, payload):
            r = gercek(topic, payload)
            with kilit:
                sayac.append((topic, str(payload.get("command")), r))
            return r

        monkeypatch.setattr(o.api, "_mqtt_publish", _sayan)
        _cihaz, _rc, ackler = _ack_veren_cihaz(o, rol="esp")
        yanit = o.api._emergency_stop_all("manual")
        time.sleep(0.6)
        bobinler = sorted(o.api.ESP_COIL_IDS)
    beklenen = sorted(
        [(f"pemf/coil/{b}/control", "stop") for b in bobinler] + [(f"pemf/esp32_{b}/command", "stop") for b in bobinler]
    )
    assert sorted((t, k) for t, k, _ in sayac) == beklenen, f"E-stop STOP yayınları değişti (Ö.4-Y8): {sayac}"
    assert all(r for *_, r in sayac), (
        f"kimlikli broker'da STOP yayını PUBACK almadı (backend kimliği STOP yolunu kapsamıyor): {sayac}"
    )
    assert all(r["mqtt"] == "success" for r in yanit["mqttResults"]), yanit
    assert len(ackler) == len(bobinler), f"aparat: cihaz her ESP bobini için STOP almadı: {ackler}"


def test_KARSIT_D1104_hazirlanmamis_broker_BUGUNKU_gibi_anonim_kabul_eder_STOP_yolu_degismez(monkeypatch, tmp_path):
    with _ortam(monkeypatch, tmp_path, hazirla=False) as o:
        anonim, rc = ma.istemci(o.port, ad="anonim")
        o.istemciler.append(anonim)
        kimlik = o.api._mqtt_credentials()
        yanit = o.api._emergency_stop_all("manual")
    assert rc == 0, f"hazırlanmamış broker anonim istemciyi REDDETTİ (rc={rc}) — kimliksiz ESP'ler kopardı"
    assert kimlik == (None, None), f"hazırlanmamış sistemde backend kimlik gönderiyor: kullanıcı={kimlik[0]!r}"
    assert yanit["mqttResults"] == [{"coilId": 8, "mqtt": "success"}], yanit
