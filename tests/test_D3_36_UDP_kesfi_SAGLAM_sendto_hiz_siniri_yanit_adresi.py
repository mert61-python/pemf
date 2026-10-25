# Author: mertaygn, cglrgrkn
"""D3.36 (B-4.16 · B-4.19 · B-4.26) — UDP keşfi sağlam: sendto hatası döngüyü ÖLDÜRMEZ; yanıtlanamaz kaynak süzülür; hız sınırı
`clear()` yerine eskiyen girdileri atar; yanıt adresi rota yokken de döngü adresi DEĞİL.

ÖLÇÜLEN (HEAD): (1) geçerli istek + `sendto` OSError(10065) → dış `except` → döngü biter, keşif süreç ömrü boyunca kapanır;
(2) 256 girdide `_disc_rl.clear()` → 300 dolgu kaynağıyla karışık akışta kurbana 0,5 sn'de 5 yanıt; (3) `connect` ENETUNREACH →
yanıt `ip` = 127.0.0.1. GERÇEK `UdpDiscoveryService._run` döngüsü; sahte yalnız soket ve saat (EN ALT katta).
"""

from __future__ import annotations

import errno
import json
import socket
import time

import pytest

ISTEK = json.dumps({"type": "discovery"}).encode()


class _Soket:
    def __init__(self, gelenler, sendto_hatasi_ilk=False, servis=None):
        self.gelenler = list(gelenler)
        self.gonderilen: list[tuple] = []
        self._hata = sendto_hatasi_ilk
        self._servis = servis

    def recvfrom(self, n):
        if not self.gelenler:
            self._servis._stop_event.set()
            raise socket.timeout()
        veri, adres, saat = self.gelenler.pop(0)
        if saat is not None:
            _SAAT[0] = saat
        return veri, adres

    def sendto(self, veri, adres):
        if self._hata:
            self._hata = False
            raise OSError(10065, "ana bilgisayara ulaşılamıyor")
        self.gonderilen.append((adres[0], _SAAT[0]))

    def close(self):
        pass


_SAAT = [1000.0]


@pytest.fixture
def servis(monkeypatch):
    from services import headless_services as hs

    monkeypatch.setattr(time, "time", lambda: _SAAT[0])
    monkeypatch.setattr(hs, "get_local_ip", lambda: "192.168.137.1")
    s = hs.UdpDiscoveryService(api_port=8123, discovery_port=5051, mqtt_port=1883)
    monkeypatch.setattr(s, "_publish", lambda *a, **k: None)
    return s


def _kos(servis, monkeypatch, gelenler, **kw):
    sok = _Soket(gelenler, servis=servis, **kw)

    def _ac():
        servis._socket = sok

    monkeypatch.setattr(servis, "_open_socket", _ac)
    servis._run()
    return sok


def test_KRITIK_B_4_16_sendto_HATASI_dongu_OLDURMEZ_sonraki_istege_yanit(servis, monkeypatch):
    sok = _kos(
        servis,
        monkeypatch,
        [(ISTEK, ("192.168.1.5", 40000), 1000.0), (ISTEK, ("192.168.1.6", 40001), 1000.1)],
        sendto_hatasi_ilk=True,
    )
    assert [ip for ip, _ in sok.gonderilen] == ["192.168.1.6"], (
        f"ilk sendto hatasından sonra keşif öldü: {sok.gonderilen}"
    )


@pytest.mark.parametrize("kaynak", ["0.0.0.0", "255.255.255.255", "224.0.0.251"])
def test_KRITIK_B_4_16_yanitlanamaz_kaynak_SUZULUR(servis, monkeypatch, kaynak):
    sok = _kos(servis, monkeypatch, [(ISTEK, (kaynak, 40000), 1000.0)])
    assert sok.gonderilen == []


def test_KRITIK_B_4_19_dolgu_kaynaklariyla_kurbana_YANSITMA_YOK(servis, monkeypatch):
    akis = []
    t = 2000.0
    for tur in range(5):
        for i in range(260):  # dolgu: her turda tabloyu taşıracak kadar farklı (sahte) özel kaynak
            akis.append((ISTEK, (f"10.{tur}.{i // 250}.{i % 250}", 40000), t))
        akis.append((ISTEK, ("192.168.1.99", 40000), t))  # kurban (sahte kaynak)
        t += 0.09  # beş tur 0,5 sn içinde
    sok = _kos(servis, monkeypatch, akis)
    kurbana = [s for ip, s in sok.gonderilen if ip == "192.168.1.99"]
    assert len(kurbana) <= 1, f"kurbana 0,5 sn'de {len(kurbana)} yanıt (hız sınırı silindi)"


def test_KRITIK_B_4_26_rota_yokken_yanit_adresi_DONGU_degil(monkeypatch):
    from services import headless_services as hs

    class _Bag:
        def connect(self, *a):
            raise OSError(errno.ENETUNREACH, "ağa ulaşılamıyor")

        def close(self):
            pass

    monkeypatch.setattr(hs.socket, "socket", lambda *a, **k: _Bag())
    monkeypatch.setattr(
        hs.socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 2, 17, "", ("127.0.0.1", 0)), (2, 2, 17, "", ("192.168.137.1", 0))],
    )
    assert hs.get_local_ip() == "192.168.137.1"
    s = hs.UdpDiscoveryService(api_port=8123, discovery_port=5051, mqtt_port=1883)
    assert not s._create_response()["ip"].startswith("127.")


def test_KARSIT_D3_36_gecerli_tek_istek_YANITLANIR(servis, monkeypatch):
    sok = _kos(servis, monkeypatch, [(ISTEK, ("192.168.1.5", 40000), 3000.0)])
    assert [ip for ip, _ in sok.gonderilen] == ["192.168.1.5"]
