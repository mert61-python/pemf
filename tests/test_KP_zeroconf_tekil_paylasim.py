# -*- coding: utf-8 -*-
"""KP-1 · `utils/zeroconf_singleton.py` · sözleşmeler: süreç başına TEK paylaşılan Zeroconf, yalnız GERÇEK LAN IPv4'lerine açık bağlanma
(loopback / APIPA / 0.0.0.0 / IPv6 / yinelenen ayıklanır), bağlanamazsa güvenli varsayılana (InterfaceChoice.All) düşme, arayüz seti
GENİŞLEYİNCE yeniden bağlanıp yayıncıları yeniden kaydetme (geri çağrılar kilit DIŞINDA — kilitlenme yok), yalnız DARALINCA Zeroconf'a
dokunmama (saha 2026-08-29: hotspot gel-git'i mDNS kaydını 2-4 sn öldürüyordu), kapanışta kapatıp sıfırlama.

Ağa ÇIKILMAZ: arayüz sayımı (`ifaddr.get_adapters`) ve `zeroconf.Zeroconf` EN ALT katta sahte; modülün süreç geneli durumu her testte geri konur.
Taban (cfb481ee) %40,24 — bu yollar hiç koşmuyordu.
"""

from __future__ import annotations

import logging
import threading
from types import SimpleNamespace

import ifaddr
import pytest
import utils.zeroconf_singleton as zs
import zeroconf


class _Zc:
    """Sahte Zeroconf: kurulum argümanını ve kapatmayı kaydeder; istenirse açık arayüzle kurulumda / kapatmada patlar."""

    kurulan: list = []
    arayuzle_patla = False
    kapatmada_patla = False

    def __init__(self, interfaces=None):
        if interfaces is not None and _Zc.arayuzle_patla:
            raise OSError("arayüze bağlanılamadı")
        self.interfaces = interfaces
        self.kapandi = False
        _Zc.kurulan.append(self)

    def close(self):
        self.kapandi = True
        if _Zc.kapatmada_patla:
            raise RuntimeError("kapatılamadı")


def _adaptor(*ipler):
    """ifaddr biçimi: her IP için `is_IPv4` + `ip` (IPv4 str, IPv6 demet)."""
    return SimpleNamespace(ips=[SimpleNamespace(is_IPv4=isinstance(ip, str), ip=ip) for ip in ipler])


@pytest.fixture
def ortam(monkeypatch):
    durum = SimpleNamespace(adaptorler=[])
    _Zc.kurulan, _Zc.arayuzle_patla, _Zc.kapatmada_patla = [], False, False
    monkeypatch.setattr(zeroconf, "Zeroconf", _Zc)
    monkeypatch.setattr(ifaddr, "get_adapters", lambda: durum.adaptorler)
    # süreç geneli durum: monkeypatch eski NESNELERİ geri koyar (liste yerinde değiştirilse de)
    monkeypatch.setattr(zs, "_zc", None)
    monkeypatch.setattr(zs, "_bound_ips", [])
    monkeypatch.setattr(zs, "_reregister_cbs", [])
    monkeypatch.setattr(zs, "_lock", threading.Lock())  # kilitlenen bir koşu (mutant) sonraki testleri asmasın
    return durum


def test_KRITIK_yalniz_GERCEK_LAN_IPv4_sayilir_loopback_APIPA_IPv6_yinelenen_ayiklanir(ortam):
    ortam.adaptorler = [
        _adaptor("192.168.1.43", ("fe80::1", 0, 3)),
        _adaptor("127.0.0.1", "169.254.10.5"),
        _adaptor("0.0.0.0", "192.168.137.1", "192.168.1.43"),
    ]
    assert zs._real_lan_ipv4s() == ["192.168.1.43", "192.168.137.1"]


def test_arayuz_sayimi_DUSERSE_bos_liste_ve_TAM_ZINCIRLI_uyari(ortam, monkeypatch, caplog):
    monkeypatch.setattr(ifaddr, "get_adapters", lambda: (_ for _ in ()).throw(OSError("GetAdaptersAddresses")))
    with caplog.at_level(logging.WARNING, logger=zs.logger.name):
        assert zs._real_lan_ipv4s() == []
    kayit = next(r for r in caplog.records if "InterfaceChoice.All" in r.getMessage())
    assert kayit.exc_info, "çok-homed riskine düşüş zincirsiz günlüklendi"


def test_KRITIK_paylasilan_ornek_TEK_ve_gercek_arayuzlere_ACIK_baglanir(ortam):
    ortam.adaptorler = [_adaptor("192.168.1.43", "192.168.137.1")]
    a = zs.get_shared_zeroconf()
    assert a is zs.get_shared_zeroconf(), "ikinci yayıncı ayrı Zeroconf aldı (UDP 5353'te iki responder)"
    assert len(_Zc.kurulan) == 1 and a.interfaces == ["192.168.1.43", "192.168.137.1"]
    assert zs._bound_ips == ["192.168.1.43", "192.168.137.1"]


def test_acik_baglama_DUSERSE_varsayilana_duser_bagli_ip_kaydi_bos(ortam, caplog):
    ortam.adaptorler = [_adaptor("192.168.1.43")]
    _Zc.arayuzle_patla = True
    with caplog.at_level(logging.WARNING, logger=zs.logger.name):
        z = zs.get_shared_zeroconf()
    assert z.interfaces is None and zs._bound_ips == []
    assert any("açık-arayüz bağlama başarısız" in r.getMessage() for r in caplog.records)


def test_gercek_IP_yoksa_varsayilan_InterfaceChoice_All(ortam):
    ortam.adaptorler = [_adaptor("127.0.0.1")]
    z = zs.get_shared_zeroconf()
    assert z.interfaces is None and zs._bound_ips == []


def test_geri_cagri_IKI_kez_kaydedilmez(ortam):
    cb = lambda: None  # noqa: E731
    zs.add_reregister_callback(cb)
    zs.add_reregister_callback(cb)
    assert zs._reregister_cbs == [cb], "aynı yayıncı iki kez yeniden kaydedilecekti"


def test_degisiklik_YOKSA_ya_da_ornek_YOKSA_ya_da_IP_YOKSA_yeniden_baglanmaz(ortam):
    ortam.adaptorler = [_adaptor("192.168.1.43")]
    assert zs.ensure_interfaces_current() is False, "henüz örnek yokken yeniden bağlandı"
    z = zs.get_shared_zeroconf()
    assert zs.ensure_interfaces_current() is False and zs._zc is z and not z.kapandi
    ortam.adaptorler = []
    assert zs.ensure_interfaces_current() is False and zs._zc is z, "IP sayılamayınca çalışan örnek atıldı"


def test_KRITIK_arayuz_seti_YALNIZ_DARALINCA_Zeroconf_KORUNUR_takip_guncellenir(ortam):
    ortam.adaptorler = [_adaptor("192.168.1.43", "192.168.137.1")]
    z = zs.get_shared_zeroconf()
    ortam.adaptorler = [_adaptor("192.168.1.43")]  # hotspot boşta kaldı → kayboldu
    assert zs.ensure_interfaces_current() is False
    assert zs._zc is z and not z.kapandi and len(_Zc.kurulan) == 1, "daralmada Zeroconf kapatıldı (mDNS 2-4 sn ölür)"
    assert zs._bound_ips == ["192.168.1.43"]
    ortam.adaptorler = [_adaptor("192.168.1.43", "192.168.137.1")]  # geri geldi → GENİŞLEME → yeniden bağlanır
    assert zs.ensure_interfaces_current() is True and zs._zc is not z and z.kapandi


def test_KRITIK_genislemede_yeniden_baglanir_yayincilar_KILIT_DISINDA_yeniden_kaydedilir(ortam, caplog):
    ortam.adaptorler = [_adaptor("192.168.1.43")]
    eski = zs.get_shared_zeroconf()
    goren: list = []

    def _yayinci():  # gerçek yayıncılar burada get_shared_zeroconf() çağırır → kilit tutuluyorsa KİLİTLENİR
        goren.append(zs.get_shared_zeroconf())

    def _patlayan():
        raise RuntimeError("kayıt düştü")

    zs.add_reregister_callback(_patlayan)
    zs.add_reregister_callback(_yayinci)
    ortam.adaptorler = [_adaptor("192.168.1.43", "10.0.0.7")]
    sonuc: list = []
    t = threading.Thread(target=lambda: sonuc.append(zs.ensure_interfaces_current()), daemon=True)
    with caplog.at_level(logging.WARNING, logger=zs.logger.name):
        t.start()
        t.join(5)
    assert not t.is_alive(), "geri çağrı kilit içinde çalıştı → kilitlenme"
    assert sonuc == [True] and eski.kapandi
    assert zs._zc.interfaces == ["192.168.1.43", "10.0.0.7"] and zs._bound_ips == ["192.168.1.43", "10.0.0.7"]
    assert goren == [zs._zc], "patlayan yayıncı diğerinin yeniden kaydını engelledi"
    assert any("re-register callback hatası" in r.getMessage() for r in caplog.records)


def test_yeniden_yaratmada_eski_kapatma_ve_acik_baglama_DUSERSE_varsayilana_duser(ortam, caplog):
    ortam.adaptorler = [_adaptor("192.168.1.43")]
    eski = zs.get_shared_zeroconf()
    _Zc.kapatmada_patla = True
    _Zc.arayuzle_patla = True
    ortam.adaptorler = [_adaptor("192.168.1.43", "10.0.0.7")]
    with caplog.at_level(logging.WARNING, logger=zs.logger.name):
        assert zs.ensure_interfaces_current() is True
    assert eski.kapandi and zs._zc is not eski and zs._zc.interfaces is None and zs._bound_ips == []
    assert any("yeniden-yaratma" in r.getMessage() for r in caplog.records)


def test_kapanista_KAPATIR_ve_SIFIRLAR_kapatma_patlasa_da(ortam):
    zs.close_shared_zeroconf()  # örnek yokken sessiz
    ortam.adaptorler = [_adaptor("192.168.1.43")]
    z = zs.get_shared_zeroconf()
    _Zc.kapatmada_patla = True
    zs.close_shared_zeroconf()
    assert z.kapandi and zs._zc is None and zs._bound_ips == []
    _Zc.kapatmada_patla = False
    assert zs.get_shared_zeroconf() is not z, "kapanıştan sonra eski (kapalı) örnek geri verildi"
