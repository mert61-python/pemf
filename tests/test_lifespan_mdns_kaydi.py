# Author: mertaygn, cglrgrkn
"""D0Ö.10 (B-10.104) KAPISI — test süitinin lifespan girişleri GERÇEK mDNS kaydı YAPMAZ.

ARIZA (ölçüldü, DENETIM-10 B-10.104): `with TestClient(api_server.app)` lifespan'ı
`_start_mdns_service` thread'ini başlatıyor → `start_mdns` → `get_shared_zeroconf()` →
`register_service('PEMF-Vet-…._pemfvet._tcp.local.')`. Yani süit LAN'a `_pemfvet._tcp` ilanı
yapabiliyordu: aynı Wi-Fi'deki telefonlar TEST SÜRECİNİ cihaz sanıp keşfeder. `_get_local_ip()`
UDP rota hilesi engellense de `ifaddr` ile gerçek LAN IP'sini bulur → kayıt yine olur.

ÇÖZÜM (yalnız test aparatı; ürün kodu değişmez): `tests/conftest.py` her testte
`api_server._start_mdns_service`'i kaydeden bir boş-işlemle değiştirir (`_MDNS_ENGELLENEN`).
mDNS'i SINAYAN testler `start_mdns`/`get_shared_zeroconf`'u doğrudan çağırır — onlara dokunulmaz.

KAPI: `get_shared_zeroconf` SAYAÇLI SAHTEYLE sarılır (ağa ÇIKMAZ — koruma kalksa bile paket
gitmez), yerel IP TEST-NET'e sabitlenir (makinenin ağ durumundan bağımsız: gerçek LAN IP'si
olmayan CI'da da senaryo kurulur). Lifespan girilir; `register_service` çağrısı 0 olmalı ve
lifespan'ın mDNS başlatıcısına GERÇEKTEN ulaştığı (conftest kaydı +1) ayrıca doğrulanır.

MUTASYON: conftest'teki mDNS korumasını kaldırmak → KIRMIZI (sahte sayaç 1 kayıt görür).

EK (bağımsız inceleme, tur 2): (a) koruma OTURUM kapsamlı olmalı — modül kapsamlı bir
`with TestClient` fixture'ı, fonksiyon kapsamlı bir yama kurulmadan ÖNCE lifespan'a girer;
(b) B-10.104'ün ikinci yarısı: lifespan SÜREÇ SONUNA DEK yaşayan daemon'lar başlatıyordu
(`_start_background_threads`: session-watchdog, sensor-persist, daily-maintenance,
esp-telemetry-watchdog, efield-live, PEMF_SIMULATE ile hw-sim). Conftest onu da kaydeden bir
boş-işlemle değiştirir. MUTASYON: arka plan yaması silinirse (b), yama fonksiyon kapsamına
dönerse (a) KIRMIZI.
"""

import sys
import threading
from pathlib import Path

import pytest

#: `api_server._start_background_threads`in başlattığı, SÜREÇ SONUNA DEK yaşayan daemon'lar.
ARKA_PLAN_DAEMONLARI = (
    "session-watchdog",
    "sensor-persist",
    "daily-maintenance",
    "esp-telemetry-watchdog",
    "efield-live",
    "hw-sim",
)


class _SayacliZeroconf:
    """Ağa çıkmayan sayaçlı sahte Zeroconf: yalnız register_service çağrısını kaydeder."""

    def __init__(self):
        self.kayitlar = []

    def register_service(self, info, *a, **k):
        self.kayitlar.append(getattr(info, "name", repr(info)))

    def unregister_service(self, *a, **k):
        pass

    def unregister_all_services(self, *a, **k):
        pass

    def close(self, *a, **k):
        pass


def _mdns_sahnesi(mp) -> _SayacliZeroconf:
    """Kaydı KURULABİLİR kıl (TEST-NET yerel IP) ama ağa çıkarma (sayaçlı sahte)."""
    import servers.auto_discovery as ad
    import utils.zeroconf_singleton as zs

    sahte = _SayacliZeroconf()
    mp.setattr(zs, "get_shared_zeroconf", lambda *a, **k: sahte)
    # Kayıt, zeroconf tekiline bir yeniden-kayıt geri çağrısı da bırakırdı (sonraki testlere sızmasın).
    mp.setattr(zs, "add_reregister_callback", lambda *a, **k: None)
    mp.setattr(ad, "_get_local_ip", lambda *a, **k: "192.0.2.10")  # TEST-NET: kayıt KURULABİLİR
    return sahte


def _mdns_threadlerini_bekle():
    for t in threading.enumerate():
        if t.name == "PEMFmDNSService":
            t.join(timeout=10)


def _kayitli_conftest():
    """pytest'in YÜKLEDİĞİ conftest (`import conftest` başka kipte ikinci kopya yaratabilir)."""
    c = sys.modules.get("conftest")
    assert c is not None and Path(c.__file__).resolve() == (Path(__file__).parent / "conftest.py").resolve(), (
        "kayıtlı tests/conftest.py bulunamadı (içe aktarma kipi değişmiş olabilir)"
    )
    return c


def test_KRITIK_lifespan_GERCEK_mdns_kaydi_YAPMAZ(monkeypatch):
    from fastapi.testclient import TestClient
    from servers import api_server

    _c = _kayitli_conftest()
    sahte = _mdns_sahnesi(monkeypatch)
    koruma = getattr(_c, "_MDNS_ENGELLENEN", None)
    n0 = len(koruma) if koruma is not None else 0
    with TestClient(api_server.app):
        pass
    _mdns_threadlerini_bekle()

    assert sahte.kayitlar == [], f"lifespan GERÇEK mDNS kaydı yaptı (LAN'a _pemfvet ilanı): {sahte.kayitlar}"
    assert koruma is not None and len(koruma) > n0, (
        "lifespan mDNS başlatıcısı conftest korumasına ULAŞMADI — senaryo kurulamadı ya da koruma yok"
    )


@pytest.fixture(scope="module")
def _modul_kapsamli_lifespan():
    """Süitteki modül kapsamlı istemci fixture'larının `with` biçimi: FONKSİYON kapsamlı her şeyden
    ÖNCE lifespan'a girer. Sahne (sayaçlı sahte zeroconf) burada kendi MonkeyPatch'iyle kurulur."""
    from fastapi.testclient import TestClient
    from servers import api_server

    mp = pytest.MonkeyPatch()
    try:
        sahte = _mdns_sahnesi(mp)
        with TestClient(api_server.app):
            pass
        _mdns_threadlerini_bekle()
        yield sahte
    finally:
        mp.undo()


def test_KRITIK_MODUL_kapsamli_lifespan_da_GERCEK_mdns_kaydi_YAPMAZ(_modul_kapsamli_lifespan):
    assert _modul_kapsamli_lifespan.kayitlar == [], (
        "modül kapsamlı bir fixture'ın lifespan'ı GERÇEK mDNS kaydı yaptı — conftest koruması "
        f"oturum kapsamlı değil: {_modul_kapsamli_lifespan.kayitlar}"
    )


def test_KRITIK_lifespan_SURE_SONUNA_KALAN_daemon_BASLATMAZ(monkeypatch):
    """B-10.104 ikinci yarısı: ilk lifespan girişi sonsuz daemon'lar başlatıyor, bunlar süreç sonuna dek
    yaşıyordu — session-watchdog her 1 sn aktif seansı tarayıp SONRAKİ testlerin seansını durdurabiliyor,
    daily-maintenance 60 sn sonra o an yamalı DB'de retention/yedek koşuyordu. `PEMF_SIMULATE=1` burada
    YALNIZ hw-sim'in de engellendiğini sınamak için (koruma yoksa o da başlar)."""
    from fastapi.testclient import TestClient
    from servers import api_server

    _c = _kayitli_conftest()
    monkeypatch.setenv("PEMF_SIMULATE", "1")
    # Başlatıcı idempotent: süreçte önce bir lifespan koştuysa bayrak True kalır ve koruma olmasa bile
    # hw-sim bu girişte başlamaz (kol kör olurdu) → bayrak sıfırlanır.
    monkeypatch.setattr(api_server, "_bg_threads_started", False)
    koruma = getattr(_c, "_ARKA_PLAN_ENGELLENEN", None)
    n0 = len(koruma) if koruma is not None else 0
    once = set(threading.enumerate())
    with TestClient(api_server.app):
        pass
    for t in threading.enumerate():  # lifespan'ın kısa ömürlü yardımcıları kendiliğinden biter
        if t.name in ("PEMFmDNSService", "FastAPIMQTTListener"):
            t.join(timeout=10)

    # Ad listesine değil FARKA bakılır (tur 3): yeni adlı bir kalıcı daemon da yakalanır.
    yeni = sorted(t.name for t in set(threading.enumerate()) - once if t.is_alive())
    assert yeni == [], f"lifespan test bitince de YAŞAYAN thread bıraktı: {yeni}"
    canli = sorted(t.name for t in threading.enumerate() if t.name in ARKA_PLAN_DAEMONLARI)
    assert canli == [], f"süreçte lifespan daemon'ları yaşıyor: {canli}"
    assert koruma is not None and len(koruma) > n0, (
        "lifespan arka plan başlatıcısı conftest korumasına ULAŞMADI — senaryo kurulamadı ya da koruma yok"
    )
