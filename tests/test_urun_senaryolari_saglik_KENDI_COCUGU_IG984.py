# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""İG-9.84 (İG-9.8 ikizi) — `scripts/urun_senaryolari.py` `kostur` sağlık yoklaması YANITI KENDİ ÇOCUĞUNA bağlar; EXE yalnız
loopback'te ve işletim sisteminin verdiği BOŞ portta açılır.

ARIZA (ölçüldü, HEAD 5bc99be1): `kostur` portu 8201'den başlayan SABİT bir sayaçla seçiyor, `/api/health` 200 dönen HERHANGİ
bir yanıtı "ayakta" sayıyordu ve EXE'ye `PEMF_API_HOST` vermiyordu (ürün varsayılanı 0.0.0.0):
  (1) portu tutan yetim / elle açılmış / başka bir backend varken kendi EXE'si hiç açılmasa da senaryo YABANCININ yanıtını
      ölçüyor ve "geçti" yazıyordu (build AI kapısının D4.28 öncesi kusurunun aynısı);
  (2) her açılış LAN'a açık bir port + her yeni EXE yolu için güvenlik duvarı uyarısı (GÖRÜNÜR pencere) demekti.
Build AI kapısı bunu D4.28 / S-YH.9'da çözdü (nonce + boş loopback portu + `PEMF_API_HOST=127.0.0.1`); senaryo aracı aynı deseni alır.

ÖLÇÜM: EXE yerine küçük bir SAHTE EXE (Python) — gerçek `Popen` ile başlar, aldığı `--port`, `PEMF_API_HOST`, `PEMF_HEALTH_NONCE`
değerlerini kaydeder ve YALNIZ 127.0.0.1'de dinler (test hiçbir koşulda LAN dinleyicisi açmaz). Yabancı dinleyici `127.0.0.1:0`'da
(işletim sistemi seçer). Sahip portları (8000/8100/1883/5173/8177/8200) hiçbir kolda kullanılmaz.
MUTASYON: nonce karşılaştırmasını kaldırmak / `PEMF_API_HOST` satırını silmek / sabit sayaca dönmek → KIRMIZI.
"""

from __future__ import annotations

import http.server
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from exe_kapisi_surucusu import YALITIM_DEGISKENLERI, AltSurecVekili, urun_senaryolari_modulu

#: Sahibin servis portları — burada PİNLİ (ürün betiğinden okunmaz).
SAHIP_PORTLARI = frozenset({8000, 8100, 1883, 5173, 8177, 8200})

_SAHTE_EXE = r'''
import http.server, json, os, sys, time
a = sys.argv[1:]
port = int(a[a.index("--port") + 1])
nonce = os.environ.get("PEMF_HEALTH_NONCE")
with open(os.environ["IG984_KAYIT"], "w", encoding="utf-8") as f:
    json.dump({"port": port, "host": os.environ.get("PEMF_API_HOST", "0.0.0.0"), "nonce": nonce, "argv": a}, f)
if os.environ.get("IG984_KIP") == "uyu":  # canlı ama backend DEĞİL (port tutmaz, yanıt vermez)
    time.sleep(60)
    sys.exit(0)
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        b = json.dumps({"status": "ok", "launcherNonce": nonce}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *x):
        pass
http.server.HTTPServer(("127.0.0.1", port), H).serve_forever()  # test YALNIZ loopback'te dinler
'''


class _Yabanci(http.server.BaseHTTPRequestHandler):
    """Portu tutan yabancı backend: 200 + nonce'suz (ya da başka nonce'lu) sağlık yanıtı."""

    istekler: list = []

    def do_GET(self):
        _Yabanci.istekler.append(self.path)
        b = json.dumps({"status": "ok", "launcherNonce": "BASKA-BIR-SURECIN-NONCE"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


@pytest.fixture
def yabanci():
    sunucu = http.server.HTTPServer(("127.0.0.1", 0), _Yabanci)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    _Yabanci.istekler = []
    try:
        yield sunucu.server_address[1]
    finally:
        sunucu.shutdown()
        sunucu.server_close()


def _senaryo(tmp_path: Path, monkeypatch, kip: str, port: int | None = None):
    """`kostur`u SAHTE EXE ile hazırla. `port` verilirse kostur'un seçeceği port ZORLA o olur (yabancı dinleyici yarışı)."""
    for ad in YALITIM_DEGISKENLERI:
        monkeypatch.delenv(ad, raising=False)
    us = urun_senaryolari_modulu()
    sahte = tmp_path / "sahte_exe.py"
    sahte.write_text(_SAHTE_EXE, encoding="utf-8")
    kayit = tmp_path / "sahte_exe_kayit.json"
    monkeypatch.setenv("IG984_KAYIT", str(kayit))
    monkeypatch.setenv("IG984_KIP", kip)
    gercek_popen = subprocess.Popen
    cocuklar = []

    def _popen(argv, **kw):
        p = gercek_popen([sys.executable, str(sahte), *[str(x) for x in argv[1:]]], **kw)
        cocuklar.append(p)
        return p

    monkeypatch.setattr(us, "subprocess", AltSurecVekili(Popen=_popen))
    calisma = tmp_path / "calisma"
    calisma.mkdir()
    monkeypatch.setattr(us, "CALISMA", calisma)
    if port is not None:
        # Hem eski sayaç (port = _port + 1) hem boş-port seçicisi aynı porta yönlenir: ölçülen şey seçim değil YANIT doğrulaması.
        monkeypatch.setattr(us, "_port", port - 1, raising=False)
        monkeypatch.setattr(us, "_bos_loopback_portu", lambda: port, raising=False)
    return us, kayit, cocuklar


def _bos_port() -> int:
    """Testin KENDİ seçtiği boş loopback portu (bu süreçte bind edilir → süit ağ bekçisi çocuğun dinlediği bu porta bağlanmaya
    izin verir). Kendi-çocuk kollarında kostur'un seçimi bu porta yönlenir: ölçülen şey yanıt doğrulaması ve host'tur."""
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _temizle(us, cocuklar):
    for p in cocuklar:
        us.durdur(p)


def test_KRITIK_portu_YABANCI_tutarken_kendi_EXE_si_acilmadiysa_AYAKTA_sayilmaz(tmp_path, monkeypatch, yabanci):
    us, kayit, cocuklar = _senaryo(tmp_path, monkeypatch, kip="uyu", port=yabanci)
    try:
        _p, _log, ayakta, port = us.kostur(tmp_path / "veri", sifreli=False, sure=6)
    finally:
        _temizle(us, cocuklar)
    assert port == yabanci, (
        f"kostur EXE portunu boş-port seçicisinden (`_bos_loopback_portu`) almıyor: {port} != {yabanci} — sabit port / sayaç (İG-9.84)"
    )
    assert _Yabanci.istekler, "aparat: kostur yabancı dinleyiciyi hiç yoklamadı (ölçüm kör)"
    assert ayakta is False, (
        "kostur portu tutan YABANCI sürecin /api/health 200 yanıtını kendi EXE'sininki saydı — senaryo yanlış süreci ölçer "
        "(İG-9.84; çözüm: PEMF_HEALTH_NONCE yansımalı, build AI kapısı D4.28 deseni)"
    )


def test_KRITIK_kendi_EXE_si_YALNIZ_loopbackte_ve_nonce_ile_AYAKTA(tmp_path, monkeypatch):
    us, kayit, cocuklar = _senaryo(tmp_path, monkeypatch, kip="sunucu", port=_bos_port())
    try:
        _p, _log, ayakta, port = us.kostur(tmp_path / "veri", sifreli=False, sure=30)
    finally:
        _temizle(us, cocuklar)
    k = json.loads(kayit.read_text(encoding="utf-8"))
    assert ayakta is True, f"kendi (nonce'u yansıtan) EXE'si ayakta sayılmadı: {k}"
    assert k["host"] == "127.0.0.1", (
        f"EXE PEMF_API_HOST={k['host']!r} ile açılıyor — LAN'a açık port + güvenlik duvarı uyarısı (görünür pencere) (İG-9.84)"
    )
    assert k["port"] == port and port not in SAHIP_PORTLARI, (
        f"EXE sahip portunda / beklenmeyen portta: {k['port']} / {port}"
    )
    assert k["nonce"], "EXE'ye tek-seferlik PEMF_HEALTH_NONCE verilmedi — yanıt kendi sürecine bağlanamaz"


def test_KRITIK_iki_acilis_FARKLI_nonce_ve_BOS_port(tmp_path, monkeypatch, yabanci):
    """Port sabit sayaçtan değil işletim sisteminden: yabancının tuttuğu port ASLA seçilmez; her açılışın nonce'u ayrı."""
    us, kayit, cocuklar = _senaryo(tmp_path, monkeypatch, kip="uyu")
    monkeypatch.setattr(us, "_port", yabanci - 1, raising=False)  # eski sayaç olsaydı yabancının portunu seçerdi
    goruldu = []
    try:
        for _ in range(2):
            _p, _log, _ayakta, port = us.kostur(tmp_path / "veri", sifreli=False, sure=1, saglik_bekle=False)
            goruldu.append((port, json.loads(kayit.read_text(encoding="utf-8"))["nonce"]))
    finally:
        _temizle(us, cocuklar)
    assert all(p != yabanci and p not in SAHIP_PORTLARI for p, _n in goruldu), (
        f"kostur DOLU (yabancının tuttuğu) ya da sahip portunu seçti: {goruldu} (yabancı {yabanci}) — sabit sayaç (İG-9.84)"
    )
    assert goruldu[0][1] and goruldu[0][1] != goruldu[1][1], f"nonce yok ya da açılışlar arasında aynı: {goruldu}"


def test_KARSIT_cagiranin_verdigi_nonce_KORUNUR_C7(tmp_path, monkeypatch):
    """C7/C8 senaryosu kendi nonce'unu `ek` ile verir — kostur onu ezmemeli ve yine kendi çocuğunu tanımalı."""
    us, kayit, cocuklar = _senaryo(tmp_path, monkeypatch, kip="sunucu", port=_bos_port())
    try:
        _p, _log, ayakta, _port = us.kostur(
            tmp_path / "veri", sifreli=False, ek={"PEMF_HEALTH_NONCE": "OLCUM-NONCE-4f8c1e"}, sure=30
        )
    finally:
        _temizle(us, cocuklar)
    assert ayakta is True
    assert json.loads(kayit.read_text(encoding="utf-8"))["nonce"] == "OLCUM-NONCE-4f8c1e"
