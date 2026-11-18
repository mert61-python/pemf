# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) B5 — sürücü denetleyicisi (`servers/modul_denetleyici.py`), KIRMIZI KANITLI: her kural için kuralı çiğneyen bir sürücü
yakalanır; örnek modül ve takılan test modülü TEMİZ geçer. Kurallar: beyan edilen bağlantı dışında ağ yok · keşif (zeroconf) yok · alt süreç
yok · modül klasörü dışına yazma yok · dinamik kod yok · MQTT yalnız `pemf/modul/<kimlik>/` + kalıcı ileti yok · `Surucu(BobinSurucusu)`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BAS = "from servers.modul_surucu import BobinSurucusu\n"
SON = "\nclass Surucu(BobinSurucusu):\n    pass\n"


def _kodlar(kaynak: str, baglanti: str = "seri", kimlik: str = "dene") -> list[str]:
    from servers.modul_denetleyici import denetle_kaynak

    return [k for _, k, _ in denetle_kaynak(kaynak, {"baglanti": baglanti, "kimlik": kimlik})]


def test_KRITIK_GA_B5_ORNEK_ve_TEST_modulleri_TEMIZ():
    from servers.modul_denetleyici import denetle

    assert denetle(KOK / "moduller" / "ornek") == []
    assert denetle(KOK / "tests" / "veri" / "moduller" / "takilan") == []


@pytest.mark.parametrize(
    "kaynak,baglanti,beklenen",
    [
        ("import socket\n", "seri", "beyansizBaglanti"),  # seri modül ağa çıkamaz
        ("import serial\n", "wifi", "beyansizBaglanti"),  # wifi modül seri porta (ana STM) dokunamaz
        ("from serial.tools import list_ports\n", "ble", "beyansizBaglanti"),
        ("import multiprocessing\n", "sahte", "beyansizBaglanti"),  # yalnız .connection
        ("from multiprocessing import Process\n", "sahte", "beyansizBaglanti"),
        ("import zeroconf\n", "wifi", "yasakModul"),  # keşfe yanıt / tarama YOK
        ("import subprocess\n", "seri", "yasakModul"),
        ("from urllib import request\n", "wifi", "yasakModul"),
        ("import requests\n", "wifi", "yasakModul"),
        ("import importlib\n", "seri", "yasakModul"),
        ("import ctypes\n", "usb", "yasakModul"),
        ("import shutil\n", "seri", "yasakModul"),
        ("import os\nos.system('x')\n", "seri", "altSurecVeyaDosya"),
        ("import os\nos.spawnl(0, 'x')\n", "seri", "altSurecVeyaDosya"),
        ("import os\nos.execv('x', [])\n", "seri", "altSurecVeyaDosya"),
        ("import os\nos.remove('/x')\n", "seri", "altSurecVeyaDosya"),
        ("open('C:/x.txt', 'w')\n", "seri", "klasorDisiYazma"),
        ("open('x.txt', mode='a')\n", "seri", "klasorDisiYazma"),
        ("kip = 'w'\nopen('x.txt', kip)\n", "seri", "klasorDisiYazma"),
        ("from pathlib import Path\nPath('x').write_text('y')\n", "seri", "klasorDisiYazma"),
        ("eval('1')\n", "seri", "dinamikKod"),
        ("__import__('socket')\n", "seri", "dinamikKod"),
        (
            "import paho.mqtt.client as m\nc = m.Client()\nc.publish('pemf/coil/1/control', 'x')\n",
            "wifi",
            "mqttKonuAlaniDisi",
        ),
        (
            "import paho.mqtt.client as m\nc = m.Client()\nc.publish('pemf/modul/dene/x', 'y', 0, True)\n",
            "wifi",
            "mqttKaliciIleti",
        ),
        (
            "import paho.mqtt.client as m\nc = m.Client()\nc.publish('pemf/modul/dene/x', 'y', retain=True)\n",
            "wifi",
            "mqttKaliciIleti",
        ),
        ("def f(\n", "seri", "sozdizimi"),
    ],
)
def test_KRITIK_GA_B5_kural_IHLALI_yakalanir(kaynak, baglanti, beklenen):
    assert beklenen in _kodlar(BAS + kaynak + SON, baglanti)


def test_KRITIK_GA_B5_IZINLI_kullanim_TEMIZ():
    temiz = [
        ("import serial\nfrom serial.tools import list_ports\n", "seri"),
        (
            "import socket\nimport paho.mqtt.client as m\nc = m.Client()\nc.publish('pemf/modul/dene/x', 'y', retain=False)\n",
            "wifi",
        ),
        ("import bleak\n", "ble"),
        ("import usb.core\nimport hid\n", "usb"),
        ("from multiprocessing.connection import Client\nfrom multiprocessing import connection\n", "sahte"),
        ("open('oku.txt')\nopen('oku.txt', 'r')\n", "seri"),
        ("import os, sys, time, json, threading\nx = os.environ.get('A')\n", "seri"),
    ]
    for kaynak, b in temiz:
        assert _kodlar(BAS + kaynak + SON, b) == [], kaynak
    yazan = (
        BAS
        + "class Surucu(BobinSurucusu):\n    def f(self):\n        open(self.dosya_yolu('k.json'), 'w')\n        self.write_text('x')\n"
    )
    assert _kodlar(yazan) == []  # yalnız modül klasörüne (dosya_yolu) yazma serbest


def test_KRITIK_GA_B5_SURUCU_SINIFI_zorunlu_ve_dosya_hatalari(tmp_path, capsys):
    from servers.modul_denetleyici import denetle, main

    assert "surucuSinifiYok" in _kodlar(BAS + "class Surucu:\n    pass\n")
    assert "surucuSinifiYok" in _kodlar(BAS)
    assert "beyansizBaglanti" in _kodlar(
        BAS + "import socket\n" + SON, "bilinmeyen"
    )  # beyansız bağlantı türü → hiçbir ağ izni yok
    (tmp_path / "a").mkdir()
    assert denetle(tmp_path / "a") == [(0, "surucuYok", "surucu.py")]
    (tmp_path / "a" / "surucu.py").write_text(BAS + "import socket\n" + SON, encoding="utf-8")
    (tmp_path / "a" / "modul.json").write_text("{bozuk", encoding="utf-8")
    assert denetle(tmp_path / "a") == [
        (2, "beyansizBaglanti", "socket")
    ]  # modul.json okunamazsa hiçbir bağlantı izinli değil
    (tmp_path / "a" / "modul.json").write_text("[1]", encoding="utf-8")
    assert denetle(tmp_path / "a") == [(2, "beyansizBaglanti", "socket")]
    (tmp_path / "a" / "modul.json").write_text(json.dumps({"baglanti": "wifi", "kimlik": "a"}), encoding="utf-8")
    assert denetle(tmp_path / "a") == []
    assert main([str(tmp_path / "a")]) == 0
    assert main([str(KOK / "tests" / "veri" / "moduller" / "takilan"), str(tmp_path / "yok")]) == 1
    cikti = capsys.readouterr().out
    assert "surucuYok" in cikti and "2 modül · 1 bulgu" in cikti
    import sys

    sys.argv[1:] = []
    assert main() == 0
