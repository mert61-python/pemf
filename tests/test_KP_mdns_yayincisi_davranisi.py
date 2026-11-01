# -*- coding: utf-8 -*-
"""KP (Y236 · kapsam) — `services/mdns_service.py` (`pemf-gateway.local` → MQTT) yaşam döngüsü ve kenar kolları.

Mevcut kapılar (rota yok, benzersiz ad, monitör ölmez, yeniden kayıt) çekirdeği kilitliyor; başlat / durdur hata kolları, ad çakışması,
döngünün hata sayacı ve bağımsız çalıştırma (`main`) koşmuyordu (%56). Ağa ÇIKILMAZ: modül-yerel `socket`, `time` ve paylaşılan Zeroconf
(`utils.zeroconf_singleton`) en alt katta sahte; gerçek `zeroconf.ServiceInfo` yalnız nesne kurar (ağ yok).
"""

from __future__ import annotations

import logging
import socket as gercek_socket
import sys
from types import SimpleNamespace

import pytest
from services import mdns_service as ms


class _Zc:
    def __init__(self, kayit_hatasi=None, silme_hatasi=None):
        self.kayitli, self.silinen = [], []
        self._kh, self._sh = list(kayit_hatasi or []), silme_hatasi

    def register_service(self, info):
        if self._kh:
            raise self._kh.pop(0)
        self.kayitli.append(info)

    def unregister_service(self, info):
        if self._sh:
            raise self._sh
        self.silinen.append(info)


@pytest.fixture
def zc(monkeypatch):
    import utils.zeroconf_singleton as zs

    durum = SimpleNamespace(zc=_Zc(), geri=[], esitle=0, lan=["192.168.137.1"])
    monkeypatch.setattr(zs, "get_shared_zeroconf", lambda: durum.zc)
    monkeypatch.setattr(zs, "add_reregister_callback", lambda cb: durum.geri.append(cb))
    monkeypatch.setattr(zs, "_real_lan_ipv4s", lambda: durum.lan)

    def _esitle():
        durum.esitle += 1

    monkeypatch.setattr(zs, "ensure_interfaces_current", _esitle)
    return durum


def _udp(monkeypatch, ip=None):
    """Modül-yerel `socket`: UDP sondası `ip` döner ya da (None) rota yok → düşer. `inet_aton` gerçek."""

    class _S:
        def connect(self, adres):
            if ip is None:
                raise OSError("rota yok")

        def getsockname(self):
            return (ip, 5555)

        def close(self):
            pass

    monkeypatch.setattr(
        ms,
        "socket",
        SimpleNamespace(AF_INET=2, SOCK_DGRAM=2, socket=lambda *a: _S(), inet_aton=gercek_socket.inet_aton),
    )


def test_yerel_ip_UDP_sondasi_yoksa_LAN_adayi_o_da_yoksa_LOOPBACK(monkeypatch, zc):
    _udp(monkeypatch, "10.1.2.3")
    assert ms._get_local_ip() == "10.1.2.3"
    _udp(monkeypatch, "127.0.0.1")
    assert ms._get_local_ip() == "192.168.137.1", "loopback dönen UDP sondasında LAN adayına düşülmedi"
    _udp(monkeypatch, None)
    zc.lan = []
    assert ms._get_local_ip() == "127.0.0.1"
    import utils.zeroconf_singleton as zs

    monkeypatch.setattr(zs, "_real_lan_ipv4s", lambda: (_ for _ in ()).throw(OSError("ifaddr yok")))
    assert ms._get_local_ip() == "127.0.0.1"


def test_KRITIK_kurulum_LAN_ipsiyle_kaydeder_LOOPBACKi_YAYINLAMAZ_geri_cagrisini_baglar(monkeypatch, zc):
    s = ms.MDNSService(mqtt_port=1884, ip_override="192.168.137.1")
    s._ip_monitor_kurulum()
    info = zc.zc.kayitli[0]
    assert (
        info.port == 1884
        and info.server == "pemf-gateway.local."
        and gercek_socket.inet_ntoa(info.addresses[0]) == "192.168.137.1"
    )
    assert zc.geri == [s._reregister_mqtt] and s.get_current_ip() == "192.168.137.1"
    zc.zc = _Zc()
    l = ms.MDNSService(ip_override="127.0.0.1")
    l._ip_monitor_kurulum()
    assert zc.zc.kayitli == [], "127.* mDNS'e yayınlandı (#32) — ESP / telefon kendi loopback'ine gider"


def test_ad_cakismasinda_RASTGELE_ekle_yeniden_kaydeder_baska_hata_YUKARI_gider(monkeypatch, zc):
    from zeroconf._exceptions import NonUniqueNameException

    zc.zc = _Zc(kayit_hatasi=[NonUniqueNameException("var")])
    s = ms.MDNSService(ip_override="192.168.1.9")
    s._ip_monitor_kurulum()
    assert s._service_name.startswith("PEMF-Gateway-") and len(s._service_name) == len("PEMF-Gateway-") + 4
    assert zc.zc.kayitli and zc.zc.kayitli[0].name.startswith(s._service_name)
    zc.zc = _Zc(kayit_hatasi=[RuntimeError("EventLoopBlocked")])
    with pytest.raises(RuntimeError):
        ms.MDNSService(ip_override="192.168.1.9")._ip_monitor_kurulum()


def test_zeroconf_istisna_modulu_YOKSA_kurulum_yine_calisir(monkeypatch, zc):
    monkeypatch.setitem(sys.modules, "zeroconf._exceptions", None)
    s = ms.MDNSService(ip_override="192.168.1.9")
    s._ip_monitor_kurulum()
    assert zc.zc.kayitli


def test_baslat_durdur_kollari(monkeypatch, zc, caplog):
    calisti: list = []
    s = ms.MDNSService()
    monkeypatch.setattr(s, "_ip_monitor_loop", lambda: calisti.append(1))
    assert s.start() is True and s.is_running()
    s._ip_monitor_thread.join(5)
    assert calisti == [1]
    assert s.start() is True and calisti == [1], "zaten çalışırken ikinci izleyici açıldı"
    s._zeroconf, s._service_info = zc.zc, "bilgi"
    s.stop()
    assert zc.zc.silinen == ["bilgi"] and not s.is_running() and s._zeroconf is None
    s.stop()  # zaten durmuş → sessiz
    s._running, s._zeroconf, s._service_info = True, _Zc(silme_hatasi=RuntimeError("x")), "bilgi"
    s.stop()
    assert s._service_info is None and any("mDNS durdurma hatası" in r.getMessage() for r in caplog.records)
    b = ms.MDNSService(mqtt_port="sayi-degil")
    assert b.start() is False and not b.is_running()
    monkeypatch.setitem(sys.modules, "zeroconf", None)
    assert ms.MDNSService().start() is False, "zeroconf yokken başlatma True döndü"


def test_KRITIK_dongu_kurulum_hatasinda_OLMEZ_sayac_ve_arayuz_esitleme(monkeypatch, zc):
    bildirim: list = []
    monkeypatch.setattr(ms, "dongu_hatasini_bildir", lambda m, *a, **k: bildirim.append(m))
    s = ms.MDNSService(ip_override="192.168.1.9")
    s._running = True
    deneme = {"n": 0}

    def _kurulum():
        deneme["n"] += 1
        if deneme["n"] <= 10:
            raise RuntimeError("adaptör yeniden sayıldı")

    monkeypatch.setattr(s, "_ip_monitor_kurulum", _kurulum)
    tur = {"n": 0}

    def _uyku(sn):
        tur["n"] += 1
        if tur["n"] == 12:
            s._running = False

    sahte_zaman = SimpleNamespace(time=lambda: 0.0, sleep=_uyku)
    monkeypatch.setattr(ms, "time", sahte_zaman)
    s._ip_monitor_loop()
    assert deneme["n"] == 11, "kurulum hatası döngüyü öldürdü ya da yeniden denenmedi"
    assert sum("kurulum hatasi" in m for m in bildirim) == 1 and sum("hala basarisiz" in m for m in bildirim) == 1
    assert zc.esitle >= 10, "kurulum başarısızken arayüz eşitleme (_pemfvet toparlanması) atlandı"


def test_dongu_esitleme_hatasini_bildirir_durdurulunca_cikar(monkeypatch, zc):
    bildirim: list = []
    monkeypatch.setattr(ms, "dongu_hatasini_bildir", lambda m, *a, **k: bildirim.append(m))
    import utils.zeroconf_singleton as zs

    monkeypatch.setattr(zs, "ensure_interfaces_current", lambda: (_ for _ in ()).throw(OSError("5353")))
    s = ms.MDNSService(ip_override="192.168.1.9")
    s._running = True
    n = {"t": 0}

    def _uyku(sn):
        n["t"] += 1
        if n["t"] >= 2:
            s._running = False

    monkeypatch.setattr(ms, "time", SimpleNamespace(time=lambda: 1000.0, sleep=_uyku))
    s._ip_monitor_loop()
    assert any("arayüz-monitör hatası" in m for m in bildirim)


def test_yeniden_kayit_kollari(monkeypatch, zc, caplog):
    s = ms.MDNSService(ip_override="192.168.1.20")
    s._reregister_mqtt()
    assert zc.zc.kayitli == [], "stop() sonrası (çalışmıyorken) servis yeniden yayınlandı (Audit P3)"
    s._running = True
    s._reregister_mqtt()
    assert len(zc.zc.kayitli) == 1 and s.get_current_ip() == "192.168.1.20"
    s._ip_override = "127.0.0.1"
    s._reregister_mqtt()
    assert len(zc.zc.kayitli) == 1
    s._ip_override = "192.168.1.21"
    zc.zc = _Zc(kayit_hatasi=[RuntimeError("NotRunning")])
    s._reregister_mqtt()
    assert any("_mqtt re-register hatası" in r.getMessage() for r in caplog.records)


def test_bagimsiz_calistirma_main_baslatamazsa_cikis_1_calisirsa_sinyalle_durur(monkeypatch):
    sinyal: dict = {}
    monkeypatch.setattr(logging, "basicConfig", lambda **k: None)
    import signal

    monkeypatch.setattr(signal, "signal", lambda s, h: sinyal.__setitem__(s, h))
    monkeypatch.setattr(ms.MDNSService, "start", lambda self: False)
    with pytest.raises(SystemExit) as c:
        ms.main()
    assert c.value.code == 1
    durdu: list = []
    monkeypatch.setattr(ms.MDNSService, "start", lambda self: True)
    monkeypatch.setattr(ms.MDNSService, "stop", lambda self: durdu.append(1))
    monkeypatch.setattr(
        ms, "time", SimpleNamespace(time=lambda: 0.0, sleep=lambda sn: (_ for _ in ()).throw(KeyboardInterrupt()))
    )
    ms.main()
    assert durdu == [1] and signal.SIGINT in sinyal and signal.SIGTERM in sinyal
    with pytest.raises(SystemExit) as c:
        sinyal[signal.SIGINT](signal.SIGINT, None)
    assert c.value.code == 0 and durdu == [1, 1]


def test_modul_DOGRUDAN_calistirilinca_main_kosar_yayin_kurulamazsa_CIKIS_1(monkeypatch):
    """`python -m services.mdns_service` (bağımsız yayıncı) zeroconf yokken → yayın kurulamaz, süreç çıkış kodu 1 ile biter (asılı kalmaz)."""
    import runpy

    monkeypatch.setattr(logging, "basicConfig", lambda **k: None)  # kök günlükçüye işleyici eklenmesin
    monkeypatch.setitem(sys.modules, "zeroconf", None)  # içe aktarma EN ALT katta düşer
    with pytest.raises(SystemExit) as c:
        runpy.run_path(ms.__file__, run_name="__main__")
    assert c.value.code == 1
