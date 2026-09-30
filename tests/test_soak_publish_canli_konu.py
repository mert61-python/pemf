# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D0Ö.17 (B-10.218) KAPISI — soak yayıncısı canlı `pemf/` konularına ONAYSIZ yayın yapmaz, yayın
sonucunu ve TÜKETİMİ ölçmeden 0 dönmez.

ARIZA (DENETIM-10 B-10.218): `scripts/soak_publish_5hz_8coil.py` varsayılan olarak GERÇEK
`pemf/coil/<n>/sensors` konusuna sahte telemetri basıyordu: ESP açık bir makinede (1.9.50 sahası)
bobin 1-8'in canlı durumunu ezer ve ESP bayatlık bekçisini tazeler → gerçek sensör kopması
MASKELENİR. `publish()` sonucunu okumadan ve hiçbir TÜKETİMİ ölçmeden 0 dönüyordu (abone yokken de).

KAPI: betiğin GERÇEK `main()`i SAHTE paho modülüyle çağrılır (`sys.modules`'a enjekte — paho kurulu
olmasa da kapı KOŞAR; ağ ve broker YOK). (i) Canlı `pemf/` öneki + onay yok → istemci kurulmadan
≠0. (ii) `publish()` rc≠0 (tümü ya da KISMİ) → ≠0; hiç yayın → ≠0. (iii) D0Ö.17 ek: tüketim sondası
MQTT v5 + QoS 1 ile PUBACK reason code okur — başta tüketici YOK (16) ya da ÖLÇÜLEMEDİ (PUBACK yok)
→ yük HİÇ basılmadan 3; sonda tüketici düştüyse 3. Karşıt: tüketici VAR + rc=0 → 0; `--canli-onay`
ile canlı önek YAYINLANIR. Ürünün GERÇEK `on_connect` filtreleri betiğin ad alanına pinlidir.
D0Ö.17 ek-2 (tur 5): SONDALAR dahil tüm yayınlar ad alanına pinli; sonda ürünün yok saydığı bobin 0
konusuna gider; önce rastgele konuda KALİBRASYON (broker abonesizliği bildirmiyorsa ya da joker abone
varsa ÖLÇÜLEMEZ → 3); 0/16 dışı PUBACK kodu ÖLÇÜLEMEDİ. D0Ö.17 ek-3 (tur 6): kalibrasyonun ÖLÇÜLEMEDİ
kolları (bağlanamadı / PUBACK yok / 135) da yük basmadan 3 ve ileti GERÇEK nedeni söyler. D0Ö.17 ek-4 (tur 7):
neden yalnız karar satırının neden parçasında aranır (ham sonda yankısı iddiayı karşılamasın); PUBACK-yok kimlik
reddini de anar; ürün pini işleyiciyi GERÇEK kayıt yolundan (`_start_mqtt_for_api` → atanan `on_message`) alır.
MUTASYON: onay denetimini ya da rc okumasını kaldırmak → KIRMIZI.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

KOK = Path(__file__).resolve().parents[1]
V5, V311 = 5, 4


class _SahteIstemci:
    def __init__(self, ayar: dict, kayit: dict, *a, **k):
        self.ayar = ayar
        self.kayit = kayit
        self.protokol = k.get("protocol", V311)
        self.on_publish = None
        kayit["istemci"].append(self.protokol)

    def connect(self, *a, **k):
        if self.ayar["baglanti_hatasi"]:  # broker kapalı (ör. mosquitto çalışmıyor)
            raise ConnectionRefusedError(10061, "hedef makine baglantiyi reddetti")
        self.kayit["baglanti"] += 1

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass

    def publish(self, topic, payload=None, qos=0, retain=False):
        mid = len(self.kayit["yayin"]) + 1
        self.kayit["yayin"].append((topic, qos, self.protokol))
        if qos == 1:  # tüketim sondası: PUBACK geri çağrısı
            if topic.startswith("soak-kalibrasyon/"):  # kimsenin abone olmadığı rastgele konu
                kod = self.ayar["kalibrasyon_kodu"]
            else:
                kod = self.ayar["sonda_kodlari"].pop(0) if self.ayar["sonda_kodlari"] else None
            if kod is not None and self.on_publish is not None:
                # Gerçek paho 2.x: v3.1.1 PUBACK'inde reason code YOK → geri çağrı hep "Success" (0) verir;
                # yani v3 sondası abone olmasa da "VAR" der. Yalnız v5 broker'ın 16'sını taşır.
                self.on_publish(self, None, mid, SimpleNamespace(value=kod if self.protokol == V5 else 0), None)
            return SimpleNamespace(rc=0, mid=mid)
        i = self.kayit["yuk"]
        self.kayit["yuk"] += 1
        return SimpleNamespace(rc=self.ayar["yuk_rc"](i), mid=mid)


def _betik(monkeypatch, yuk_rc=lambda i: 0, sonda_kodlari=(0, 0), kalibrasyon_kodu=16, baglanti_hatasi=False) -> tuple:
    """`kalibrasyon_kodu`: rastgele konudaki sondanın PUBACK kodu (16 = broker abonesizliği BİLDİRİYOR;
    None = PUBACK hiç gelmez). `baglanti_hatasi`: her `connect()` reddedilir (broker kapalı)."""
    ayar = {
        "yuk_rc": yuk_rc,
        "sonda_kodlari": list(sonda_kodlari),
        "kalibrasyon_kodu": kalibrasyon_kodu,
        "baglanti_hatasi": baglanti_hatasi,
    }
    kayit = {"istemci": [], "baglanti": 0, "yayin": [], "yuk": 0}
    client = types.ModuleType("paho.mqtt.client")
    client.Client = lambda *a, **k: _SahteIstemci(ayar, kayit, *a, **k)
    client.CallbackAPIVersion = SimpleNamespace(VERSION2=2)
    client.MQTT_ERR_SUCCESS = 0
    client.MQTTv5 = V5
    client.MQTTv311 = V311
    paho, mqtt_paket = types.ModuleType("paho"), types.ModuleType("paho.mqtt")
    paho.mqtt, mqtt_paket.client = mqtt_paket, client
    for ad, mod in (("paho", paho), ("paho.mqtt", mqtt_paket), ("paho.mqtt.client", client)):
        monkeypatch.setitem(sys.modules, ad, mod)
    spec = importlib.util.spec_from_file_location("soak_publish_kapi", KOK / "scripts" / "soak_publish_5hz_8coil.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m, kayit


def _kos(m, monkeypatch, *arg) -> int:
    monkeypatch.setattr(sys, "argv", ["soak_publish_5hz_8coil.py", "--duration-sec", "1", *arg])
    return m.main()


def _yuk(kayit) -> list[str]:
    return [t for t, qos, _p in kayit["yayin"] if qos == 0]


def test_KRITIK_varsayilan_CANLI_konuya_onaysiz_YAYIN_YAPMAZ(monkeypatch):
    m, kayit = _betik(monkeypatch)
    rc = _kos(m, monkeypatch)
    canli = [t for t, _q, _p in kayit["yayin"] if t.startswith("pemf/")]
    assert rc != 0 and not canli and kayit["baglanti"] == 0, (
        f"soak canlı konuya ONAYSIZ yayın yaptı (rc={rc}, {len(canli)} canlı yayın, bağlantı={kayit['baglanti']}) — "
        "ESP bayatlık bekçisini tazeler, gerçek sensör kopmasını maskeler (B-10.218)"
    )
    assert not kayit["istemci"], "onaysız canlı önekte MQTT istemcisi bile kurulmamalı"


def test_KRITIK_urun_AD_ALANINDAKI_baska_onek_de_ONAY_ister(monkeypatch):
    """Ürünün TÜM abonelikleri `pemf/` altında (sensors/status/events/alarm/ack, gateway/bridge)."""
    m, kayit = _betik(monkeypatch)
    rc = _kos(m, monkeypatch, "--topic-prefix", "pemf/test")
    assert rc != 0 and not kayit["yayin"] and kayit["baglanti"] == 0, (
        f"'pemf/' ad alanına onaysız yayın (rc={rc}, {len(kayit['yayin'])} yayın)"
    )


def test_KARSIT_KANIT_canli_onay_ve_TUKETICI_varken_canli_onek_YAYINLANIR(monkeypatch):
    m, kayit = _betik(monkeypatch)
    assert _kos(m, monkeypatch, "--canli-onay") == 0
    assert _yuk(kayit) and all(t.startswith("pemf/coil/") for t in _yuk(kayit))


def test_KRITIK_publish_BASARISIZSA_cikis_SIFIR_DEGIL(monkeypatch):
    m, kayit = _betik(monkeypatch, yuk_rc=lambda i: 4)  # MQTT_ERR_NO_CONN
    rc = _kos(m, monkeypatch, "--topic-prefix", "test/pemf/coil")
    assert _yuk(kayit), "senaryo kurulamadı: hiç yük yayını denenmedi"
    assert rc != 0, f"publish() rc≠0 iken betik {rc} döndü — yayın doğrulanmadan 'başarılı' (B-10.218)"


def test_KRITIK_KISMI_yayin_hatasi_cikis_SIFIR_DEGIL(monkeypatch):
    """Gerçekçi arıza kısmidir (koşu ortasında broker kopuşu): ilk yayınlar kabul, sonrası rc=4.
    Tüm yayınlar reddedilince 'hiç yayın yok' kolu tek başına ≠0 verdiği için bu kol AYRI ölçülür."""
    m, kayit = _betik(monkeypatch, yuk_rc=lambda i: 0 if i < 10 else 4)
    rc = _kos(m, monkeypatch, "--topic-prefix", "test/pemf/coil")
    assert kayit["yuk"] > 10, "senaryo: hem kabul hem ret olmalı"
    assert rc != 0, f"yayınların bir kısmı reddedildiği hâlde çıkış {rc}"


def test_hic_yayin_YAPILAMAZSA_cikis_SIFIR_DEGIL(monkeypatch):
    m, kayit = _betik(monkeypatch)
    monkeypatch.setattr(
        sys, "argv", ["soak_publish_5hz_8coil.py", "--duration-sec", "0", "--topic-prefix", "test/pemf/coil"]
    )
    rc = m.main()
    assert not _yuk(kayit), "senaryo: süre 0 iken yük beklenmiyordu"
    assert rc != 0, "hiç yayın yapılmadığı hâlde 0 döndü (ölçülmeyen soak 'başarılı' sayılmaz)"


def test_KARSIT_KANIT_test_oneki_TUKETICI_ve_basarili_yayinda_cikis_SIFIR(monkeypatch):
    m, kayit = _betik(monkeypatch)
    assert _kos(m, monkeypatch, "--topic-prefix", "test/pemf/coil") == 0
    assert _yuk(kayit) and all(t.startswith("test/pemf/coil/") for t in _yuk(kayit))
    # D0Ö.17 ek-2 (tur 5, ORTA): QoS 1 SONDALAR dahil TÜM yayınlar — ek-1 bu pini yalnız QoS 0 yüke
    # daraltmıştı; sonda konusunu önekten koparan mutant ("pemf/coil/1/sensors") 12 testte YEŞİLDİ ve
    # önekli, ONAYSIZ bir koşu canlı ürüne sahte telemetri basardı.
    tum = [t for t, _q, _p in kayit["yayin"]]
    urunde = [t for t in tum if t.split("/", 1)[0] == m.URUN_AD_ALANI]
    assert not urunde, f"onaysız test önekli koşu ÜRÜN ad alanına yayın yaptı: {urunde}"
    oneksiz = [t for t in tum if not t.startswith(("test/pemf/coil/", "soak-kalibrasyon/"))]
    assert not oneksiz, f"önek (ya da kalibrasyon) dışı yayın: {oneksiz}"


def test_KRITIK_sonda_URUNUN_YOK_SAYDIGI_bobin_0_konusuna_yapilir(monkeypatch):
    """`--canli-onay`da sonda canlı konuya gider: bobin 1'e değil `<önek>/0/sensors`e — aynı
    `pemf/coil/+/sensors` filtresiyle eşleşir (abone ölçümü aynı) ama ürün bobin 0'ı damga, kayıt ve durum
    yazımından ÖNCE erken döndürür (`api_server` sensör işleyicisi: `0 <= coil_index < 8` değilse `return`)."""
    m, kayit = _betik(monkeypatch)
    assert _kos(m, monkeypatch, "--canli-onay") == 0
    sondalar = [t for t, q, _p in kayit["yayin"] if q == 1 and not t.startswith("soak-kalibrasyon/")]
    assert sondalar == ["pemf/coil/0/sensors", "pemf/coil/0/sensors"], f"sonda konusu: {sondalar}"


def _kayitli_mqtt_isleyicisi(monkeypatch, api) -> tuple:
    """Ürünün GERÇEK kayıt yolunu (`_start_mqtt_for_api`) sahte bir paho istemcisiyle koşturur ve istemciye ATANAN
    `on_message`'ı döndürür. D0Ö.17 ek-4 (tur 7): işleyici adla (`api._on_mqtt_message_api`) çağrılıyordu — ürün
    `on_message`'ı bir sarmalayıcıya bağlasa ya da `message_callback_add` ile sensör konusunu başka işleyiciye
    yönlendirse kapı yine yeşil kalırdı. Bağlantı KURULMAZ (connect_async/loop_start kayıt tutan boş çağrılar)."""

    class _KayitliIstemci:
        def __init__(self, *a, **k):
            self.cagrilar: list[str] = []

        def __getattr__(self, ad):
            if ad.startswith("on_"):
                raise AttributeError(ad)
            return lambda *a, **k: self.cagrilar.append(ad)

    kurulan: list = []
    client = types.ModuleType("paho.mqtt.client")
    client.Client = lambda *a, **k: kurulan.append(_KayitliIstemci()) or kurulan[-1]
    client.CallbackAPIVersion = SimpleNamespace(VERSION1=1, VERSION2=2)
    paho, mqtt_paket = types.ModuleType("paho"), types.ModuleType("paho.mqtt")
    paho.mqtt, mqtt_paket.client = mqtt_paket, client
    for ad, mod in (("paho", paho), ("paho.mqtt", mqtt_paket), ("paho.mqtt.client", client)):
        monkeypatch.setitem(sys.modules, ad, mod)
    monkeypatch.setattr(api.live_state, "esp_etkin", lambda: True)
    monkeypatch.setattr(api, "_mqtt_credentials", lambda: ("", ""))
    monkeypatch.setattr(api, "_mqtt_client_id", lambda *a, **k: "d0o-test")
    monkeypatch.setattr(api, "_mqtt_client_api", None)
    api._start_mqtt_for_api()
    assert kurulan, "ürün MQTT dinleyicisini kurmadı (kayıt yolu değişti mi?)"
    istemci = kurulan[-1]
    assert "message_callback_add" not in istemci.cagrilar, f"konu ayrı işleyiciye yönlendirildi: {istemci.cagrilar}"
    return istemci.on_message, istemci


class _SahteMesaj:
    """paho `MQTTMessage` yerine minimum yüzey (bkz. test_esp_kopus_ws_yayini)."""

    def __init__(self, topic: str, yuk: str, retain: bool = False):
        self.topic = topic
        self.payload = yuk.encode("utf-8")
        self.retain = retain


def test_KRITIK_URUN_bobin_0_sondasini_YAN_ETKISIZ_duser(monkeypatch):
    """D0Ö.17 ek-3 (tur 6): `--canli-onay` sondasının güvenliği ürünün bobin 0'ı damga / kayıt / canlı durum /
    WS yayınından ÖNCE düşürmesine dayanıyor (api_server `0 <= coil_index < 8`) — bu varsayım ürün tarafında
    KAPISIZDI ("geçersiz mesajları da kaydet" ya da 0 tabanlı bobin kimliği sondayı sessizce canlı yan etkiye
    çevirirdi). GERÇEK `_on_mqtt_message_api`, betiğin GERÇEK sonda yüküyle sürülür. Karşıt: aynı yük bobin
    1'de yan etki yapar (kapı ölçüyor). Kaydedici casustur — diske yazılmaz; bobin 1 durumu geri yüklenir."""
    import copy

    from servers import api_server as api

    # D0Ö.17 ek-4 (tur 7): betik SAHTE paho ile yüklenir (dosya başlığının sözü: paho kurulu olmasa da kapı koşar);
    # yük paho'dan bağımsız.
    m, _ = _betik(monkeypatch)
    yuk = m.build_payload(0, -1, 1.0)
    isleyici, istemci = _kayitli_mqtt_isleyicisi(monkeypatch, api)

    yayinlar: list = []
    kayitlar: list = []
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda msg: yayinlar.append(msg))
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api._sensor_kaydedici, "kaydet", lambda *a, **k: kayitlar.append(a))
    monkeypatch.setattr(api, "_coil_last_telemetry", {})
    with api._live_state_lock:
        bobinler_once = copy.deepcopy(api._live_state["coils"])
    try:
        isleyici(istemci, None, _SahteMesaj(f"{m.URUN_AD_ALANI}/coil/0/sensors", yuk))
        with api._live_state_lock:
            bobinler_sonra = copy.deepcopy(api._live_state["coils"])
        assert not kayitlar, f"bobin 0 sondası SENSÖR KAYDINA yazıldı: {kayitlar}"
        assert not api._coil_last_telemetry, f"bobin 0 sondası telemetri DAMGASINI tazeledi: {api._coil_last_telemetry}"
        assert not yayinlar, f"bobin 0 sondası WS'ye yayınlandı: {yayinlar}"
        assert bobinler_sonra == bobinler_once, "bobin 0 sondası canlı bobin durumunu DEĞİŞTİRDİ"

        # Karşıt: aynı yük bobin 1'de GERÇEKTEN yan etki yapar — kapı ölçüm yapıyor, kör değil (dört kanalın hepsi).
        isleyici(istemci, None, _SahteMesaj(f"{m.URUN_AD_ALANI}/coil/1/sensors", yuk))
        with api._live_state_lock:
            bobinler_bobin1 = copy.deepcopy(api._live_state["coils"])
        assert kayitlar and api._coil_last_telemetry and yayinlar, "karşıt: bobin 1 mesajı yan etki yapmadı"
        assert bobinler_bobin1 != bobinler_once, "karşıt: bobin 1 mesajı canlı durumu değiştirmedi (kol kör)"
    finally:
        with api._live_state_lock:  # `coils` = {indeks: bobin sözlüğü} (live_state); nesneler yerinde geri yüklenir
            for indeks, once in bobinler_once.items():
                api._live_state["coils"][indeks].clear()
                api._live_state["coils"][indeks].update(once)


def test_KRITIK_KALIBRASYON_broker_abonesizligi_BILDIRMIYORSA_OLCULEMEZ(monkeypatch, capsys):
    """MQTT 5 §3.4.2.1'de 16 göndermek MAY; 16 yerine 0 dönen broker ya da bir joker (`#`) abone ürün
    konusunda sahte 'VAR' üretir. Kimsenin abone olmadığı rastgele konu önce sondalanır: orada da 'VAR'
    çıkarsa tüketim ÖLÇÜLEMEZ → yük basılmaz, 3."""
    m, kayit = _betik(monkeypatch, kalibrasyon_kodu=0)
    rc = _kos(m, monkeypatch, "--topic-prefix", "test/pemf/coil")
    assert rc == 3 and not _yuk(kayit), f"kalibrasyon 'VAR' dediği hâlde rc={rc}, {len(_yuk(kayit))} yük"
    neden = _kalibrasyon_nedeni(capsys.readouterr().err)
    assert "KOK duzeyinde joker" in neden, f"VAR kolunun nedeni söylenmedi: {neden!r}"


def _kalibrasyon_nedeni(hata: str) -> str:
    """Karar satırının YALNIZ neden parçası ("… dedi — <neden>. Soak YAPILMADI."). D0Ö.17 ek-4 (tur 7): satır ham
    sonda sonucunu da yankılıyor — jeton ham metne girerse (sınıflama 'beklenmeyen'e düşse bile) iddia oradan
    karşılanırdı ("SABİT anahtar alt-dize" tuzağı)."""
    karar = next((s for s in hata.splitlines() if "TUKETIM OLCULEMEZ" in s), "")
    return karar.split("' dedi — ", 1)[1] if "' dedi — " in karar else ""


def test_KRITIK_KALIBRASYON_OLCULEMEDI_kollari_GERCEK_NEDENLE_3(monkeypatch, capsys):
    """D0Ö.17 ek-3 (tur 6): kalibrasyon ÖLÇÜLEMEDİ dönünce de yük basılmaz ve 3 — ileti her sonuçta sabit
    "abonesizliği bildirmiyor ya da joker abone var" diyordu; en sık hata olan KAPALI broker yanlış nedenle
    bildiriliyordu. Ayrıca `if kalibrasyon == "VAR": return 3` daraltması bu kollarda YÜK basardı."""
    durumlar = {
        "baglanamadi": ({"baglanti_hatasi": True}, ("--host/--port",)),
        # D0Ö.17 ek-4 (tur 7): kimlik isteyen broker da PUBACK göndermez — neden yalnız "v5" demesin.
        "puback_yok": ({"kalibrasyon_kodu": None}, ("MQTT v5", "kimlik")),
        "acl_135": ({"kalibrasyon_kodu": 135}, ("ACL",)),
    }
    for ad, (ayar, beklenenler) in durumlar.items():
        m, kayit = _betik(monkeypatch, **ayar)
        monkeypatch.setattr(m, "SONDA_ZAMAN_ASIMI_S", 0.05)  # PUBACK beklemesi 5 sn sürmesin
        rc = _kos(m, monkeypatch, "--topic-prefix", "test/pemf/coil")
        neden = _kalibrasyon_nedeni(capsys.readouterr().err)
        assert rc == 3 and not _yuk(kayit), f"{ad}: kalibrasyon ölçülemediği hâlde rc={rc}, {len(_yuk(kayit))} yük"
        assert all(b in neden for b in beklenenler), f"{ad}: neden yanlış/eksik: {neden!r}"
        assert "joker" not in neden and "beklenmeyen" not in neden, f"{ad}: sınıflama düştü: {neden!r}"


def test_KRITIK_beklenmeyen_PUBACK_kodu_OLCULEMEDI(monkeypatch, capsys):
    """0/16 dışı kod (135 Not authorized, 151 Quota…) ÖLÇÜLEMEDİ'dir — 'VAR' değil (ACL reddinde v3 QoS 0
    yük broker'da sessizce düşer)."""
    m, kayit = _betik(monkeypatch, sonda_kodlari=(135,))
    rc = _kos(m, monkeypatch, "--topic-prefix", "test/pemf/coil")
    assert rc == 3 and not _yuk(kayit), f"PUBACK 135 iken rc={rc}"
    assert "OLCULEMEDI" in capsys.readouterr().err


def test_KRITIK_TUKETICI_YOKSA_yuk_BASILMAZ_ve_cikis_SIFIR_DEGIL(monkeypatch, capsys):
    """Abonesiz konuya yük = soak hiçbir şey ölçmez (ESP kapalıyken dinleyici hiç başlamaz)."""
    m, kayit = _betik(monkeypatch, sonda_kodlari=(16,))
    rc = _kos(m, monkeypatch, "--topic-prefix", "test/pemf/coil")
    assert rc == 3 and not _yuk(kayit), f"tüketici yokken rc={rc}, {len(_yuk(kayit))} yük yayını"
    assert "TUKETICI YOK" in capsys.readouterr().err


def test_KRITIK_TUKETIM_OLCULEMEZSE_VAR_sayilmaz(monkeypatch, capsys):
    """PUBACK gelmezse (broker v5 desteklemiyor / cevap yok) sonuç ÖLÇÜLEMEDİ'dir, 'var' DEĞİL."""
    m, kayit = _betik(monkeypatch, sonda_kodlari=(None,))
    monkeypatch.setattr(m, "SONDA_ZAMAN_ASIMI_S", 0.05)
    rc = _kos(m, monkeypatch, "--topic-prefix", "test/pemf/coil")
    assert rc == 3 and not _yuk(kayit), f"tüketim ölçülemediği hâlde rc={rc}"
    assert "OLCULEMEDI" in capsys.readouterr().err


def test_KRITIK_TUKETICI_kosu_sirasinda_DUSERSE_cikis_SIFIR_DEGIL(monkeypatch):
    m, kayit = _betik(monkeypatch, sonda_kodlari=(0, 16))
    rc = _kos(m, monkeypatch, "--topic-prefix", "test/pemf/coil")
    assert _yuk(kayit), "senaryo: başta tüketici vardı, yük basılmalıydı"
    assert rc == 3, f"sonda tüketici düştüğü hâlde çıkış {rc}"


def test_KRITIK_sonda_MQTTv5_ve_QoS1_ile_yapilir(monkeypatch):
    """v3.1.1'de PUBACK reason code YOKTUR (paho 'başarılı' der) — v3 sonda her zaman 'VAR' sanırdı."""
    m, kayit = _betik(monkeypatch)
    assert _kos(m, monkeypatch, "--topic-prefix", "test/pemf/coil") == 0
    sondalar = [(q, p) for _t, q, p in kayit["yayin"] if q == 1]
    assert sondalar == [(1, V5)] * 3, f"sonda v5 + QoS1 değil / kalibrasyon + başta + sonda yapılmadı: {sondalar}"


def test_KRITIK_urunun_GERCEK_abonelikleri_betigin_AD_ALANINDA(monkeypatch):
    """Betik 'canlı' kararını ad alanına göre verir; ürün `pemf/` DIŞINDA (ya da ilk seviyesi joker)
    bir filtreye abone olursa betik onu canlı saymaz — bu kapı o gün KIRMIZI olmalı."""
    from servers import api_server

    m, _kayit = _betik(monkeypatch)
    filtreler: list[str] = []
    monkeypatch.setattr(api_server, "_push_notification", lambda *a, **k: None)
    with api_server._live_state_lock:
        eski = api_server._live_state["mqtt"]
    try:
        api_server._on_mqtt_connect_api(
            SimpleNamespace(subscribe=lambda konu, *a, **k: filtreler.append(konu)), None, {}, 0
        )
    finally:
        with api_server._live_state_lock:
            api_server._live_state["mqtt"] = eski
    assert filtreler, "kurulum: ürün hiç abone olmadı — kapı anlamsız"
    disarida = [f for f in filtreler if f.split("/", 1)[0] != m.URUN_AD_ALANI]
    assert not disarida, f"ürün betiğin canlı saymadığı filtrelere abone: {disarida}"
    assert all(m.canli_urun_konusu_mu(f.rsplit("/", 2)[0]) for f in filtreler if f.endswith("/sensors"))
