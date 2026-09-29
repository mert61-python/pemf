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
"""

import sys
import threading
from pathlib import Path


def _kayitli_conftest():
    """pytest'in YÜKLEDİĞİ conftest (`import conftest` başka kipte ikinci kopya yaratabilir)."""
    c = sys.modules.get("conftest")
    assert c is not None and Path(c.__file__).resolve() == (Path(__file__).parent / "conftest.py").resolve(), (
        "kayıtlı tests/conftest.py bulunamadı (içe aktarma kipi değişmiş olabilir)"
    )
    return c


def test_KRITIK_lifespan_GERCEK_mdns_kaydi_YAPMAZ(monkeypatch):
    import servers.auto_discovery as ad
    import utils.zeroconf_singleton as zs
    from fastapi.testclient import TestClient
    from servers import api_server

    _c = _kayitli_conftest()
    kayitlar = []

    class _SayacliZeroconf:
        """Ağa çıkmayan sayaçlı sahte Zeroconf: yalnız register_service çağrısını kaydeder."""

        def register_service(self, info, *a, **k):
            kayitlar.append(getattr(info, "name", repr(info)))

        def unregister_service(self, *a, **k):
            pass

        def unregister_all_services(self, *a, **k):
            pass

        def close(self, *a, **k):
            pass

    sahte = _SayacliZeroconf()
    monkeypatch.setattr(zs, "get_shared_zeroconf", lambda *a, **k: sahte)
    # Kayıt, zeroconf tekiline bir yeniden-kayıt geri çağrısı da bırakırdı (sonraki testlere sızmasın).
    monkeypatch.setattr(zs, "add_reregister_callback", lambda *a, **k: None)
    monkeypatch.setattr(ad, "_get_local_ip", lambda *a, **k: "192.0.2.10")  # TEST-NET: kayıt KURULABİLİR

    koruma = getattr(_c, "_MDNS_ENGELLENEN", None)
    n0 = len(koruma) if koruma is not None else 0
    with TestClient(api_server.app):
        pass
    for t in threading.enumerate():
        if t.name == "PEMFmDNSService":
            t.join(timeout=10)

    assert kayitlar == [], f"lifespan GERÇEK mDNS kaydı yaptı (LAN'a _pemfvet ilanı): {kayitlar}"
    assert koruma is not None and len(koruma) > n0, (
        "lifespan mDNS başlatıcısı conftest korumasına ULAŞMADI — senaryo kurulamadı ya da koruma yok"
    )
