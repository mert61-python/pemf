# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""mDNS KURULUM HATASI, ARAYÜZ MONİTÖRÜNÜ VE `_pemfvet`i BİRDEN ÖLDÜRÜYORDU (denetim 2026-08-17).

`MDNSService._ip_monitor_loop`un kurulum bloğu bir istisna atarsa `self._running = False; return`
yapıyordu → `while self._running` döngüsüne HİÇ girilmiyordu. Sonuç İKİ yayıncıyı birden bitiriyor:

  · `utils/zeroconf_singleton.ensure_interfaces_current`ın **TEK** çağrıcısı o döngüdür (depo
    geneli ölçüldü) → arayüz/IP değişimi izleme tamamen durur;
  · `servers/auto_discovery._reregister` **YALNIZCA** o callback listesinden çağrılıyor, yani
    `_pemfvet`in toparlanma yolu da SESSİZCE ölüyordu. Üstelik o yol bu denetimin kendi eklediği
    düzeltmeydi → iki yayıncı arasında **belgelenmemiş bağımlılık**.

Kurulum gerçek bir yarışta patlıyor: `Zeroconf(interfaces=ips)` adaptörleri YENİDEN sayıyor (arada
Wi-Fi düşerse/hotspot kapanırsa fırlar — klinikte olağan) ve `register_service`
`NotRunningException`/`EventLoopBlocked`/`ServiceNameAlreadyRegistered` atabiliyor; oradaki eleme
yalnız `NonUniqueNameException`ı tanıyor.

Görünürlük de yoktu: tek bir ERROR logu; `is_running()` "hiç başlatılmadı"dan ayırt edilemiyor;
`mdns_running` değişimi olay yayınlamıyor ve hiçbir istemci onu okumuyor; hiçbir watchdog
`MDNSService`i yeniden başlatmıyor.

⚠️ ÇÖZÜM: kurulum AYRI metoda çıkarıldı ve döngü onu MEVCUT 30 sn'lik turda yeniden deniyor —
yeni thread, yeni uyku, yeni bağımlılık YOK. Backoff LOG'a uygulandı, uykuya değil.
"""

import os
import threading

os.environ.pop("PEMF_SIMULATE", None)

import pytest


class _SahteZeroconf:
    def __init__(self):
        self.kayitlar = []

    def register_service(self, info):
        self.kayitlar.append(info)

    def unregister_service(self, info):
        pass


@pytest.fixture()
def md(monkeypatch):
    from services import mdns_service

    monkeypatch.setattr("utils.zeroconf_singleton.add_reregister_callback", lambda cb: None)
    return mdns_service


def _tek_tur_kos(mdns_service, svc, monkeypatch, tur: int = 1):
    """`_ip_monitor_loop`u THREAD AÇMADAN, sayılı tur koştur.

    ⚠️ `time.sleep` yamalanır: gerçek 30 sn beklemek yerine sayaç düşer ve `_running` kapanır."""
    kalan = {"n": tur}

    def _uyku(sn):
        kalan["n"] -= 1
        if kalan["n"] <= 0:
            svc._running = False

    monkeypatch.setattr(mdns_service.time, "sleep", _uyku)
    svc._running = True
    svc._ip_monitor_loop()


def test_KRITIK_kurulum_hatasi_ARAYUZ_MONITORUNU_OLDURMEZ(md, monkeypatch):
    """Kurulum patlasa bile `ensure_interfaces_current` ÇAĞRILMALI (`_pemfvet`in tek kurtarma yolu)."""
    mdns_service = md
    cagrildi = {"n": 0}

    def _patlat():
        raise RuntimeError("No adapter found for IP address (taklit yaris)")

    monkeypatch.setattr("utils.zeroconf_singleton.get_shared_zeroconf", _patlat)
    monkeypatch.setattr(
        "utils.zeroconf_singleton.ensure_interfaces_current",
        lambda: cagrildi.__setitem__("n", cagrildi["n"] + 1),
    )

    svc = mdns_service.MDNSService(mqtt_port=1883)
    _tek_tur_kos(mdns_service, svc, monkeypatch, tur=2)

    assert cagrildi["n"] >= 1, (
        "kurulum hatasi arayuz monitorunu OLDURDU -> ensure_interfaces_current'in TEK cagricisi "
        "olur ve `_pemfvet`in toparlanma yolu da SESSIZCE biter"
    )


def test_KRITIK_kurulum_SONRAKI_turda_YENIDEN_DENENIR(md, monkeypatch):
    """İlk turda patlayan kurulum, ikinci turda başarılı olabilmeli (mDNS geri gelmeli)."""
    mdns_service = md
    zc = _SahteZeroconf()
    sayac = {"n": 0}

    def _bazen_patla():
        sayac["n"] += 1
        if sayac["n"] == 1:
            raise RuntimeError("ilk denemede yaris (taklit)")
        return zc

    monkeypatch.setattr("utils.zeroconf_singleton.get_shared_zeroconf", _bazen_patla)
    monkeypatch.setattr("utils.zeroconf_singleton.ensure_interfaces_current", lambda: None)
    monkeypatch.setattr(mdns_service, "_get_local_ip", lambda: "192.168.137.1")

    svc = mdns_service.MDNSService(mqtt_port=1883)
    _tek_tur_kos(mdns_service, svc, monkeypatch, tur=3)

    assert sayac["n"] >= 2, "kurulum YENIDEN DENENMEDI (tek denemede vazgecti)"
    assert zc.kayitlar, "yeniden denemede `_mqtt` KAYDEDILMEDI -> pemf-gateway.local hic yayinlanmaz"


def test_KARSIT_KANIT_kurulum_BASARILIYSA_tekrar_denenmez(md, monkeypatch):
    """Karşıt-kanıt: sağlam kurulumda gereksiz yeniden kurulum YAPILMAMALI."""
    mdns_service = md
    zc = _SahteZeroconf()
    sayac = {"n": 0}

    def _get():
        sayac["n"] += 1
        return zc

    monkeypatch.setattr("utils.zeroconf_singleton.get_shared_zeroconf", _get)
    monkeypatch.setattr("utils.zeroconf_singleton.ensure_interfaces_current", lambda: None)
    monkeypatch.setattr(mdns_service, "_get_local_ip", lambda: "192.168.137.1")

    svc = mdns_service.MDNSService(mqtt_port=1883)
    _tek_tur_kos(mdns_service, svc, monkeypatch, tur=3)

    assert sayac["n"] == 1, f"saglam kurulum her turda YENIDEN yapiliyor ({sayac['n']} kez)"
    assert len(zc.kayitlar) == 1, "servis birden fazla kez register edildi"


def test_KARSIT_KANIT_stop_dongunun_disina_cikarir(md, monkeypatch):
    """⚠️ Audit P3 kararı: `stop()` sonrası döngü DEVAM ETMEMELİ (sonsuz retry olmasın)."""
    mdns_service = md
    monkeypatch.setattr(
        "utils.zeroconf_singleton.get_shared_zeroconf", lambda: (_ for _ in ()).throw(RuntimeError("x"))
    )
    monkeypatch.setattr("utils.zeroconf_singleton.ensure_interfaces_current", lambda: None)

    svc = mdns_service.MDNSService(mqtt_port=1883)
    svc._running = False  # stop() sonrası

    # ⚠️ `sleep` yamalanmıyor: döngüye HİÇ girilmemeli, yoksa gerçek 30 sn beklenir ve test asılır.
    bitti = threading.Event()

    def _kos():
        svc._ip_monitor_loop()
        bitti.set()

    t = threading.Thread(target=_kos, daemon=True)
    t.start()
    assert bitti.wait(5.0), "stop() sonrasi dongu DEVAM ETTI (sonsuz retry)"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
