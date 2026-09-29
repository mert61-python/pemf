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
            kod = self.ayar["sonda_kodlari"].pop(0) if self.ayar["sonda_kodlari"] else None
            if kod is not None and self.on_publish is not None:
                # Gerçek paho 2.x: v3.1.1 PUBACK'inde reason code YOK → geri çağrı hep "Success" (0) verir;
                # yani v3 sondası abone olmasa da "VAR" der. Yalnız v5 broker'ın 16'sını taşır.
                self.on_publish(self, None, mid, SimpleNamespace(value=kod if self.protokol == V5 else 0), None)
            return SimpleNamespace(rc=0, mid=mid)
        i = self.kayit["yuk"]
        self.kayit["yuk"] += 1
        return SimpleNamespace(rc=self.ayar["yuk_rc"](i), mid=mid)


def _betik(monkeypatch, yuk_rc=lambda i: 0, sonda_kodlari=(0, 0)) -> tuple:
    ayar = {"yuk_rc": yuk_rc, "sonda_kodlari": list(sonda_kodlari)}
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
    assert sondalar == [(1, V5), (1, V5)], f"sonda v5 + QoS1 değil / başta-sonda iki kez yapılmadı: {sondalar}"


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
