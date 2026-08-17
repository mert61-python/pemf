# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""`_pemfvet` mDNS KAYDI, AÇILIŞTA LAN IP YOKSA BİR DAHA YAPILMIYORDU (denetim bulgusu 8, cid. 2).

`servers/auto_discovery.start_mdns` LAN IP yoksa ilk kaydı bilerek ATLIYOR (loopback yayınlamak
telefonu kendi 127.0.0.1'ine gönderir) ve log *"arayüz gelince kaydolacak"* diyor. Ama `_reregister`
`_mdns_service_info is None` ise ERKEN DÖNÜYORDU — yani tam da kaydın atlandığı durumda re-register
hiç çalışmıyordu. Ölçüldü: `get_shared_zeroconf` HİÇ çağrılmıyor. Kardeş yayıncı doğru yapıyor
(`services/mdns_service.py:219-236` ServiceInfo'yu SIFIRDAN kuruyor) → `_mqtt` toparlanıyor,
`_pemfvet` toparlanmıyordu.

⚠️ RAPORUN ÖNERDİĞİ TEK SATIRLIK DÜZELTME YETERSİZDİ (analizle ortaya çıktı). İki ayrı senaryo var:
  S1 açılışta hiç adres yok → adres gelince `ensure_interfaces_current` arayüz KÜMESİNİ değişmiş
     görür ve callback'i çağırır → guard düzeltilirse TOPARLANIR.
  S2 adres VAR ama default route YOK (offline klinik / hotspot-only, bkz. `scripts/start_hotspot.ps1`)
     → `_get_local_ip()` UDP connect'e dayandığı için kalıcı `127.0.0.1` döner; arayüz kümesi
     DEĞİŞMEDİĞİ için `zeroconf_singleton.ensure_interfaces_current` callback'leri HİÇ çağırmaz →
     guard'ı düzeltmek S2'de HİÇBİR ŞEY düzeltmez.
Bu yüzden düzeltme iki parçalı: (a) guard `_mdns_started` bayrağına çevrildi, (b) `_get_local_ip`
rota bulamazsa `ifaddr` tabanlı gerçek arayüz adresine düşüyor.

⚠️ Guard'ı TAMAMEN SİLMEK bir REGRESYON olurdu: `stop_mdns()` callback'i listeden silmiyor, yani
guard kalkarsa bir arayüz değişimi KASITLI OLARAK KALDIRILMIŞ servisi diriltir
(`mdns_service.py:222-223` bunu açıkça yasaklıyor). Aşağıdaki 3. test bu yönü kilitler — yani süit,
iki hatalı düzeltme yönünü BİRBİRİNDEN AYIRT EDİYOR.

⚠️ KAPSAM DIŞI (bilerek): `_mqtt` yayıncısının kendi `_get_local_ip`i (`mdns_service.py:38-47`) AYNI
kör noktayı taşıyor → offline klinikte `_pemfvet` toparlanır, `pemf-gateway.local` HÂLÂ yayınlanmaz.
İkinci dosya = daha büyük yama; ayrı kalem.
"""

import os
import socket as _stdlib_socket

os.environ.pop("PEMF_SIMULATE", None)

import pytest


class _SahteZeroconf:
    """`register_service`/`unregister_service` çağrılarını kaydeden sahte. Soket AÇILMAZ."""

    def __init__(self):
        self.kayitlar = []
        self.silmeler = []

    def register_service(self, info):
        self.kayitlar.append(info)

    def unregister_service(self, info):
        self.silmeler.append(info)


@pytest.fixture()
def ad(monkeypatch):
    """`servers.auto_discovery` + izole modül global'leri + sahte Zeroconf.

    ⚠️ MODÜL GLOBAL'LERİ TESTLER ARASI SIZAR: başka bir test `_mdns_service_info`yi dolu bırakırsa
    1. test düzeltme OLMADAN da geçer (yanlış-yeşil). Bu yüzden her testte sıfırlanıyor.
    ⚠️ `from servers import auto_discovery` TEK yol: `import auto_discovery` ikinci bir modül nesnesi
    ve İKİNCİ bir global kümesi doğurur (bu depoda bu tuzağa bir kez düşüldü).
    ⚠️ Yama hedefi `utils.zeroconf_singleton.*`: `auto_discovery` bu adları FONKSİYON İÇİNDE import
    ediyor, dolayısıyla `servers.auto_discovery.get_shared_zeroconf` diye bir isim YOK — oraya
    yamalamak AttributeError verir ve yanlış yere yamalanırsa test GERÇEK Zeroconf'u açıp UDP 5353'te
    çakışırdı. Her test sahtenin GERÇEKTEN çağrıldığını doğrular."""
    from servers import auto_discovery

    zc = _SahteZeroconf()
    monkeypatch.setattr("utils.zeroconf_singleton.get_shared_zeroconf", lambda: zc)
    monkeypatch.setattr("utils.zeroconf_singleton.add_reregister_callback", lambda cb: None)

    monkeypatch.setattr(auto_discovery, "_mdns_service_info", None, raising=False)
    monkeypatch.setattr(auto_discovery, "_zeroconf_instance", None, raising=False)
    monkeypatch.setattr(auto_discovery, "_mdns_port", 8000, raising=False)
    monkeypatch.setattr(auto_discovery, "_mdns_device_name", "PEMF-Vet", raising=False)
    # Yamadan ÖNCE de çalışsın: o hâlde kullanılmayan bir attr olur (test kurulumu kırılmaz).
    monkeypatch.setattr(auto_discovery, "_mdns_started", True, raising=False)

    return auto_discovery, zc


def _rota_yok(monkeypatch, ad_modulu):
    """UDP connect'i patlat (default route YOK) — stdlib `socket`e GLOBAL dokunmadan."""

    class _Shim:
        AF_INET = _stdlib_socket.AF_INET
        SOCK_DGRAM = _stdlib_socket.SOCK_DGRAM

        @staticmethod
        def socket(*a, **k):
            raise OSError("network is unreachable (taklit: default route yok)")

    monkeypatch.setattr(ad_modulu, "socket", _Shim)


def test_KRITIK_ilk_kayit_ATLANDIYSA_reregister_YINE_KAYDEDER(ad, monkeypatch):
    """S1: ilk kayıt LAN IP yokluğundan atlandı → arayüz gelince re-register KAYDETMELİ."""
    auto_discovery, zc = ad
    monkeypatch.setattr(auto_discovery, "_get_local_ip", lambda: "192.168.9.9")

    auto_discovery._reregister()

    assert len(zc.kayitlar) == 1, (
        "re-register HIC kayit yapmadi → `_pemfvet` surec omru boyunca yayinlanmaz "
        "(eski guard `_mdns_service_info is None` erken donuyordu)"
    )
    # ⚠️ Yalnız "çağrıldı" yetmez: 127.0.0.1 yayınlayan bir yama da geçerdi → ADRES baytları.
    assert zc.kayitlar[0].addresses == [_stdlib_socket.inet_aton("192.168.9.9")]
    assert auto_discovery._mdns_service_info is not None, "kayit sonrasi info saklanmadi"


def test_KRITIK_ROUTE_YOKKEN_ilk_kayit_LAN_IP_ile_YAPILIR(ad, monkeypatch):
    """S2: adres var ama default route yok (offline klinik / hotspot-only).

    Guard düzeltmesi bu senaryoyu KURTARMAZ — `ensure_interfaces_current` arayüz kümesini değişmemiş
    görüp callback'leri hiç çağırmaz. Kurtaran şey `_get_local_ip`'in ifaddr'a düşmesidir."""
    auto_discovery, zc = ad
    _rota_yok(monkeypatch, auto_discovery)
    monkeypatch.setattr("utils.zeroconf_singleton._real_lan_ipv4s", lambda: ["192.168.9.9"])

    assert auto_discovery._get_local_ip() == "192.168.9.9", (
        "rota yokken gercek LAN IP bulunamadi → `_pemfvet` hic yayinlanmaz"
    )
    assert auto_discovery.start_mdns(port=8000) is True
    assert len(zc.kayitlar) == 1, "rota yokken ilk kayit yapilmadi"
    assert zc.kayitlar[0].addresses == [_stdlib_socket.inet_aton("192.168.9.9")]


def test_KRITIK_stop_sonrasi_reregister_CANLANDIRMAZ(ad, monkeypatch):
    """⚠️ SAHİP KARARI KİLİDİ: kasıtlı olarak kaldırılmış servis DİRİLTİLMEMELİ.

    `stop_mdns()` callback'i `_reregister_cbs`'ten SİLMİYOR (kaldırma API'si yok). Guard'ı tamamen
    silen "naif" düzeltme bu testi KIRAR — süit iki hatalı yönü ayırt eder."""
    auto_discovery, zc = ad
    monkeypatch.setattr(auto_discovery, "_get_local_ip", lambda: "192.168.9.9")

    assert auto_discovery.start_mdns(port=8000) is True
    assert len(zc.kayitlar) == 1
    auto_discovery.stop_mdns()

    auto_discovery._reregister()  # arayüz değişimi taklidi

    assert len(zc.kayitlar) == 1, "stop_mdns SONRASI re-register servisi DIRILTTI (kasitli kaldirma geri alindi)"


def test_hicbir_kayitta_loopback_YAYINLANMAZ(ad, monkeypatch):
    """⚠️ Audit P3 kararı: 127.* ServiceInfo YAYINLANMAZ (telefon kendi loopback'ine gider).

    Yeni ifaddr düşüşü bunu ZAYIFLATMAMALI: aday bulunmazsa yine `127.0.0.1` dönülür ve kayıt
    atlanır. Bu test, yamanın "her hâlükârda bir şey yayınla"ya kaymadığının kanıtı."""
    auto_discovery, zc = ad
    _rota_yok(monkeypatch, auto_discovery)
    monkeypatch.setattr("utils.zeroconf_singleton._real_lan_ipv4s", lambda: [])

    assert auto_discovery._get_local_ip() == "127.0.0.1"
    assert auto_discovery.start_mdns(port=8000) is True  # başlatma yine BAŞARILI sayılır
    assert zc.kayitlar == [], "loopback adresi mDNS'e YAYINLANDI"

    auto_discovery._reregister()
    assert zc.kayitlar == [], "re-register loopback YAYINLADI"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
