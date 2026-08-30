# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""`_mqtt` mDNS SERVİSİ, DEFAULT ROUTE YOKKEN HİÇ YAYINLANMIYORDU (denetim 2026-08-17, cid. 2).

`services/mdns_service._get_local_ip` tek aşamalıydı: UDP `connect(("8.8.8.8", 80))` DEFAULT ROUTE
ister. Offline klinikte ya da hotspot-only kurulumda (`scripts/start_hotspot.ps1` kendi yorumunda
*"özellikle offline klinikte GetInternetConnectionProfile null"* diyor) route YOKTUR → fonksiyon
kalıcı `127.0.0.1` dönüyor, çağıranların 127.* guard'ı (ilk kayıt **ve** re-register) kaydı atlıyor
ve `pemf-gateway.local` SÜREÇ ÖMRÜ BOYUNCA yayınlanmıyordu.

Log *"arayüz gelince kaydolacak"* diyordu ama o söz TUTULAMIYORDU: tek kurtarma yolu
`utils/zeroconf_singleton.ensure_interfaces_current` ve o da arayüz KÜMESİ değişmediği için
(`set(ips) == set(_bound_ips)` → erken `return False`) callback'leri hiç çağırmıyor — hotspot IP'si
zaten baştan var. Bu, `_pemfvet` için b30d7bd'de ölçülüp kabul edilen S2 senaryosunun BİREBİR aynısı.

⚠️ EN GÜÇLÜ KANIT AYNI FONKSİYONUN İÇİNDEYDİ: `_get_local_ip()` 127.0.0.1 dönerken dört satır sonra
`get_shared_zeroconf()` AYNI süreçte `ifaddr` ile gerçek IP'yi bulup Zeroconf'u ona bağlıyordu.
Doğru adres zaten eldeydi, yalnız ServiceInfo'ya konmuyordu.

KLİNİK ETKİ: `pemf-gateway.local`, ESP32 bobinlerinin (6-8) MQTT broker'ını bulma yoludur.
Offline klinikte bobinler broker'a bağlanamaz → tedavi başlatılamaz.

⚠️ Bu kalem denetimin KENDİ açık borcuydu: `tests/test_pemfvet_mdns_yeniden_kayit.py` başlığı ve
`docs/denetim-bulgular.md` "KAPSAM DIŞI (bilerek) … ikinci dosya = daha büyük yama; ayrı kalem" diyordu.
"""

import os
import socket as _stdlib_socket

os.environ.pop("PEMF_SIMULATE", None)

import pytest


class _SahteZeroconf:
    """`register_service` çağrılarını kaydeder. SOKET AÇILMAZ."""

    def __init__(self):
        self.kayitlar = []
        self.silmeler = []

    def register_service(self, info):
        self.kayitlar.append(info)

    def unregister_service(self, info):
        self.silmeler.append(info)


def _rota_yok(monkeypatch, mod):
    """UDP connect'i patlat (default route YOK) — stdlib `socket`e GLOBAL dokunmadan.

    ⚠️ `inet_aton` SHIM'DE OLMAK ZORUNDA: `mdns_service._build_service_info` MODÜL-SEVİYE
    `socket.inet_aton`ı kullanıyor (kardeş `auto_discovery` yerel import yapıyor, bu yapmıyor).
    Shim'de olmasaydı test, doğru yama varken bile `AttributeError` yüzünden kırmızı olurdu —
    yani YANLIŞ SEBEPLE kırmızı.
    ⚠️ Sayaç: geliştirici makinesinde default route VAR (ölçüldü: UDP sonda 192.168.1.48 dönüyor).
    Rota taklidi gerçekten devreye girmediyse test düzeltmeden ÖNCE de geçerdi."""
    sayac = {"n": 0}

    class _Shim:
        AF_INET = _stdlib_socket.AF_INET
        SOCK_DGRAM = _stdlib_socket.SOCK_DGRAM
        inet_aton = staticmethod(_stdlib_socket.inet_aton)

        @staticmethod
        def socket(*a, **k):
            sayac["n"] += 1
            raise OSError("network is unreachable (taklit: default route yok)")

    monkeypatch.setattr(mod, "socket", _Shim)
    return sayac


@pytest.fixture()
def md(monkeypatch):
    """`services.mdns_service` + sahte Zeroconf. TEK import yolu (iki modül nesnesi tuzağı yok)."""
    from services import mdns_service

    zc = _SahteZeroconf()
    monkeypatch.setattr("utils.zeroconf_singleton.get_shared_zeroconf", lambda: zc)
    monkeypatch.setattr("utils.zeroconf_singleton.add_reregister_callback", lambda cb: None)
    return mdns_service, zc


def test_KRITIK_ROTA_YOKKEN_gercek_LAN_IP_bulunur(md, monkeypatch):
    """`_get_local_ip` rota yoksa ifaddr'a düşmeli — yoksa hiçbir kayıt yapılamaz."""
    mdns_service, _ = md
    sayac = _rota_yok(monkeypatch, mdns_service)
    monkeypatch.setattr("utils.zeroconf_singleton._real_lan_ipv4s", lambda: ["192.168.137.1"])

    ip = mdns_service._get_local_ip()

    assert sayac["n"] >= 1, "rota taklidi DEVREYE GIRMEDI → test gercek agi olcuyor (yanlis-yesil)"
    assert ip == "192.168.137.1", (
        f"rota yokken gercek LAN IP bulunamadi (donen: {ip!r}) → `pemf-gateway.local` HIC yayinlanmaz, "
        "ESP bobinleri (6-8) broker'i bulamaz"
    )


def test_KRITIK_ROTA_YOKKEN_mqtt_servisi_KAYDEDILIR(md, monkeypatch):
    """Uçtan uca: rota yokken `_ip_monitor_loop`un ilk kaydı GERÇEKTEN yapılmalı.

    ⚠️ Döngü thread'i başlatılmaz; `_ip_monitor_loop` DOĞRUDAN çağrılır ve ilk turdan sonra
    `_running` kapatılarak sonsuz döngüden çıkılır."""
    mdns_service, zc = md
    sayac = _rota_yok(monkeypatch, mdns_service)
    monkeypatch.setattr("utils.zeroconf_singleton._real_lan_ipv4s", lambda: ["192.168.137.1"])
    monkeypatch.setattr("utils.zeroconf_singleton.ensure_interfaces_current", lambda: False)

    svc = mdns_service.MDNSService(mqtt_port=1883)
    svc._running = True

    # İlk turdan sonra döngüyü kes: `time.sleep` yerine bayrağı düşür.
    orijinal_uyku = mdns_service.time.sleep

    def _tek_tur(sn):
        svc._running = False
        return orijinal_uyku(0)

    monkeypatch.setattr(mdns_service.time, "sleep", _tek_tur)

    svc._ip_monitor_loop()

    assert sayac["n"] >= 1, "rota taklidi DEVREYE GIRMEDI (yanlis-yesil)"
    assert len(zc.kayitlar) == 1, (
        f"rota yokken `_mqtt` KAYDEDILMEDI (kayit sayisi {len(zc.kayitlar)}) → offline klinikte "
        "ESP bobinleri broker'a baglanamaz, tedavi baslatilamaz"
    )
    # ⚠️ Yalnız "çağrıldı" yetmez: 127.0.0.1 yayınlayan bir yama da geçerdi → ADRES baytları.
    assert zc.kayitlar[0].addresses == [_stdlib_socket.inet_aton("192.168.137.1")]
    assert svc._last_ip == "192.168.137.1", "durum raporuna hala 127.0.0.1 yaziliyor"


def test_ROTA_VARSA_davranis_DEGISMEZ_karsit_kanit(md, monkeypatch):
    """Karşıt-kanıt: default route varken ifaddr'a HİÇ düşülmemeli (davranış aynen korunur)."""
    mdns_service, _ = md
    cagrildi = {"ifaddr": False}

    def _ifaddr():
        cagrildi["ifaddr"] = True
        return ["10.0.0.9"]

    monkeypatch.setattr("utils.zeroconf_singleton._real_lan_ipv4s", _ifaddr)

    class _Sahte:
        AF_INET = _stdlib_socket.AF_INET
        SOCK_DGRAM = _stdlib_socket.SOCK_DGRAM
        inet_aton = staticmethod(_stdlib_socket.inet_aton)

        @staticmethod
        def socket(*a, **k):
            class _S:
                def connect(self, adr):
                    pass

                def getsockname(self):
                    return ("192.168.1.48", 0)

                def close(self):
                    pass

            return _S()

    monkeypatch.setattr(mdns_service, "socket", _Sahte)

    assert mdns_service._get_local_ip() == "192.168.1.48"
    assert cagrildi["ifaddr"] is False, "rota VARKEN gereksiz yere ifaddr'a dusuldu"


def test_hicbir_ADAY_yoksa_loopback_DONER_ve_YAYINLANMAZ(md, monkeypatch):
    """⚠️ Audit P3 / #32 kararı: 127.* mDNS'e YAYINLANMAZ.

    Yeni ifaddr düşüşü bunu ZAYIFLATMAMALI — aday yoksa yine `127.0.0.1` dönülür ve çağıranların
    guard'ı kaydı atlar. Yamanın "her hâlükârda bir şey yayınla"ya kaymadığının kanıtı."""
    mdns_service, zc = md
    _rota_yok(monkeypatch, mdns_service)
    monkeypatch.setattr("utils.zeroconf_singleton._real_lan_ipv4s", lambda: [])
    monkeypatch.setattr("utils.zeroconf_singleton.ensure_interfaces_current", lambda: False)

    assert mdns_service._get_local_ip() == "127.0.0.1"

    svc = mdns_service.MDNSService(mqtt_port=1883)
    svc._running = True
    svc._reregister_mqtt()

    assert zc.kayitlar == [], "loopback adresi mDNS'e YAYINLANDI"


def test_stop_sonrasi_reregister_CANLANDIRMAZ(md, monkeypatch):
    """⚠️ SAHİP KARARI KİLİDİ (Audit P3): `stop()` sonrası callback re-publish ETMEMELİ.

    Yama `_running` guard'ına dokunmuyor; bu test onu kilitler."""
    mdns_service, zc = md
    _rota_yok(monkeypatch, mdns_service)
    monkeypatch.setattr("utils.zeroconf_singleton._real_lan_ipv4s", lambda: ["192.168.137.1"])

    svc = mdns_service.MDNSService(mqtt_port=1883)
    svc._running = False  # stop() sonrası durum

    svc._reregister_mqtt()

    assert zc.kayitlar == [], "stop() SONRASI re-register servisi DIRILTTI"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
