# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D0Ö.17 (B-10.218) KAPISI — soak yayıncısı canlı `pemf/coil/+/sensors` konusuna ONAYSIZ yayın yapmaz.

ARIZA (DENETIM-10 B-10.218): `scripts/soak_publish_5hz_8coil.py` varsayılan olarak GERÇEK
`pemf/coil/<n>/sensors` konusuna sahte telemetri basıyordu: ESP açık bir makinede (1.9.50 sahası)
bobin 1-8'in canlı durumunu ezer ve ESP bayatlık bekçisini tazeler → gerçek sensör kopması
MASKELENİR. Ayrıca `publish()` sonucunu okumadan 0 dönüyordu (broker yokken de "başarılı").

KAPI: betiğin GERÇEK `main()`i SAHTE paho istemcisiyle çağrılır (ağ YOK, broker YOK). (i) Canlı
`pemf/` öneki + onay bayrağı yok → istemci kurulmadan/bağlanılmadan ≠0. (ii) Açık test öneki +
`publish()` rc≠0 → ≠0; hiç yayın yapılamazsa ≠0. Karşıt-kanıt: test öneki + rc=0 → 0; `--canli-onay`
ile canlı önek YAYINLANIR (bayrak gerçekten işler).
MUTASYON: onay denetimini ya da rc okumasını kaldırmak → KIRMIZI.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

KOK = Path(__file__).resolve().parents[1]


class _SahteIstemci:
    def __init__(self, rc: int, kayit: dict):
        self._rc = rc
        self._kayit = kayit
        kayit["istemci"] += 1

    def connect(self, *a, **k):
        self._kayit["baglanti"] += 1

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass

    def publish(self, topic, payload=None, qos=0, retain=False):
        self._kayit["yayin"].append(topic)
        return SimpleNamespace(rc=self._rc, mid=len(self._kayit["yayin"]))


def _betik(monkeypatch, rc: int) -> tuple:
    pytest.importorskip("paho.mqtt.client")
    spec = importlib.util.spec_from_file_location("soak_publish_kapi", KOK / "scripts" / "soak_publish_5hz_8coil.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    kayit = {"istemci": 0, "baglanti": 0, "yayin": []}
    sahte_mqtt = SimpleNamespace(
        Client=lambda *a, **k: _SahteIstemci(rc, kayit),
        CallbackAPIVersion=SimpleNamespace(VERSION2=2),
        MQTT_ERR_SUCCESS=0,
    )
    monkeypatch.setattr(m, "mqtt", sahte_mqtt)
    return m, kayit


def _kos(m, monkeypatch, *arg) -> int:
    monkeypatch.setattr(sys, "argv", ["soak_publish_5hz_8coil.py", "--duration-sec", "1", *arg])
    return m.main()


def test_KRITIK_varsayilan_CANLI_konuya_onaysiz_YAYIN_YAPMAZ(monkeypatch):
    m, kayit = _betik(monkeypatch, rc=0)
    rc = _kos(m, monkeypatch)
    canli = [t for t in kayit["yayin"] if t.startswith("pemf/")]
    assert rc != 0 and not canli and kayit["baglanti"] == 0, (
        f"soak canlı konuya ONAYSIZ yayın yaptı (rc={rc}, {len(canli)} canlı yayın, bağlantı={kayit['baglanti']}) — "
        "ESP bayatlık bekçisini tazeler, gerçek sensör kopmasını maskeler (B-10.218)"
    )
    assert kayit["istemci"] == 0, "onaysız canlı önekte MQTT istemcisi bile kurulmamalı"


def test_KRITIK_urun_AD_ALANINDAKI_baska_onek_de_ONAY_ister(monkeypatch):
    """Ürünün TÜM abonelikleri `pemf/` altında (sensors/status/events/alarm/ack, gateway/bridge)."""
    m, kayit = _betik(monkeypatch, rc=0)
    rc = _kos(m, monkeypatch, "--topic-prefix", "pemf/test")
    assert rc != 0 and not kayit["yayin"] and kayit["baglanti"] == 0, (
        f"'pemf/' ad alanına onaysız yayın (rc={rc}, {len(kayit['yayin'])} yayın)"
    )


def test_KARSIT_KANIT_canli_onay_ile_canli_onek_YAYINLANIR(monkeypatch):
    m, kayit = _betik(monkeypatch, rc=0)
    assert _kos(m, monkeypatch, "--canli-onay") == 0
    assert kayit["yayin"] and all(t.startswith("pemf/coil/") for t in kayit["yayin"])


def test_KRITIK_publish_BASARISIZSA_cikis_SIFIR_DEGIL(monkeypatch):
    m, kayit = _betik(monkeypatch, rc=4)  # MQTT_ERR_NO_CONN
    rc = _kos(m, monkeypatch, "--topic-prefix", "test/pemf/coil")
    assert kayit["yayin"], "senaryo kurulamadı: hiç yayın denenmedi"
    assert rc != 0, f"publish() rc≠0 iken betik {rc} döndü — yayın doğrulanmadan 'başarılı' (B-10.218)"


def test_hic_yayin_YAPILAMAZSA_cikis_SIFIR_DEGIL(monkeypatch):
    m, kayit = _betik(monkeypatch, rc=0)
    monkeypatch.setattr(
        sys, "argv", ["soak_publish_5hz_8coil.py", "--duration-sec", "0", "--topic-prefix", "test/pemf/coil"]
    )
    rc = m.main()
    assert not kayit["yayin"], "senaryo: süre 0 iken yayın beklenmiyordu"
    assert rc != 0, "hiç yayın yapılmadığı hâlde 0 döndü (ölçülmeyen soak 'başarılı' sayılmaz)"


def test_KARSIT_KANIT_test_oneki_ve_basarili_yayinda_cikis_SIFIR(monkeypatch):
    m, kayit = _betik(monkeypatch, rc=0)
    assert _kos(m, monkeypatch, "--topic-prefix", "test/pemf/coil") == 0
    assert kayit["yayin"] and all(t.startswith("test/pemf/coil/") for t in kayit["yayin"])
