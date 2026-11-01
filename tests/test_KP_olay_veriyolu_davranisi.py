# -*- coding: utf-8 -*-
"""KP (Y236 · kapsam) — `event_bus.py` davranışı: eşleşme / öncelik / süzgeç, zayıf referans temizliği, eşzamansız teslim yolları, kapanış.

Olay veriyolu güvenlik zincirinde (ör. `hardware.stm.disconnected` → acil durdurma) eşzamanlı abone yayımlayıcının iş parçacığında koşar
(hafıza: "olay veriyolu eşzamanlı abone"). Bu dosyadan önce abonelikten çıkma, ölü abone temizliği, döngüsüz eşzamansız teslim ve kapanışın
görev iptali hiç koşmuyordu (%58). Her test KENDİ `EventBus` örneğini kullanır; tekil (singleton) yalnız son testte ve geri konarak.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import threading
from types import SimpleNamespace

import event_bus as eb
import pytest


@pytest.fixture
def bus():
    b = eb.EventBus(max_workers=2)
    try:
        yield b
    finally:
        if b._running:
            b.shutdown()


def test_KRITIK_eslesme_ONCELIK_sirasi_ve_suzgec(bus):
    gelen: list = []
    bus.subscribe("esp.*", lambda e: gelen.append(("joker", e.event_type)), "j", priority=eb.EventPriority.LOW)
    bus.subscribe("esp.bobin", lambda e: gelen.append(("tam", e.data)), "t", priority=eb.EventPriority.CRITICAL)
    bus.subscribe("*", lambda e: gelen.append(("hepsi", e.source)), "h")
    bus.subscribe("esp.bobin", lambda e: gelen.append(("suzgec", e.data)), "s", filter_func=lambda e: e.data == 9)
    assert bus.publish("esp.bobin", 6, source="test") is True
    assert ("tam", 6) in gelen and ("joker", "esp.bobin") in gelen and ("hepsi", "test") in gelen
    assert ("suzgec", 6) not in gelen, "süzgeç olayı geçirdi"
    tam = [s.subscriber_id for s in bus._subscribers["esp.bobin"]]
    assert tam == ["t", "s"], f"aynı türde öncelik sırası bozuk: {tam}"
    gelen.clear()
    bus.publish("stm.kopma", 1)
    assert gelen == [("hepsi", None)], "joker 'esp.*' başka öneki yakaladı"
    assert bus._stats["events_published"] == 2


def test_aboneligi_iptal_bos_tur_silinir_bilinmeyen_False(bus):
    bus.subscribe("a", lambda e: None, "x")
    bus.subscribe("a", lambda e: None, "y")
    assert bus.unsubscribe("a", "x") is True and [s.subscriber_id for s in bus._subscribers["a"]] == ["y"]
    assert bus.unsubscribe("a", "y") is True and "a" not in bus._subscribers
    assert bus.unsubscribe("yok", "x") is False


def test_abone_ol_ve_iptal_ICERDEN_hata_verirse_False(bus, monkeypatch):
    monkeypatch.setattr(bus, "_is_qt_bound_callback", lambda cb: (_ for _ in ()).throw(RuntimeError("x")))
    assert bus.subscribe("a", lambda e: None, "x") is False

    class _Bozuk(dict):
        def __contains__(self, k):
            raise RuntimeError("bozuk sözlük")

    bus._subscribers = _Bozuk()
    assert bus.unsubscribe("a", "x") is False


def test_KRITIK_bagli_metot_ZAYIF_referansla_tutulur_nesne_olunce_ATLANIR_ve_TEMIZLENIR(bus):
    class Dinleyici:
        def __init__(self):
            self.n = 0

        def al(self, e):
            self.n += 1

    d = Dinleyici()
    bus.subscribe("a", d.al, "d")
    bus.subscribe("b", d.al, "d2")
    bus.subscribe("b", lambda e: None, "canli")
    bus.publish("a", 1)
    assert d.n == 1
    del d
    gc.collect()
    assert bus.publish("a", 2) is True, "ölü abone yayını düşürdü"
    bus._perform_cleanup()
    assert "a" not in bus._subscribers, "yalnız ölü abonesi olan tür silinmedi (bellek sızıntısı)"
    assert [s.subscriber_id for s in bus._subscribers["b"]] == ["canli"]


def test_temizlik_erisilemeyen_aboneyi_de_kaldirir_ve_gecmisi_50ye_indirir(bus):
    bozuk = SimpleNamespace(subscriber_id="bozuk", priority=eb.EventPriority.NORMAL)
    bozuk.get_callback = lambda: (_ for _ in ()).throw(RuntimeError("erişilemez"))
    bus._subscribers["z"] = [bozuk]
    bus._event_history = [eb.Event("x", i) for i in range(80)]
    bus._perform_cleanup()
    assert "z" not in bus._subscribers and len(bus._event_history) == 50


def test_gecmis_100_ile_sinirli_ve_periyodik_temizlik_tetiklenir(bus):
    for i in range(105):
        bus.publish("x", i)
    assert len(bus._event_history) == 100 and bus._event_history[-1].data == 104
    bus._cleanup_interval = 0
    bus._last_cleanup = 0
    bus.publish("x", "son")
    assert len(bus._event_history) == 50, "periyodik temizlik tetiklenmedi"


def test_KRITIK_esZamanli_abone_patlarsa_yayin_SURER_hata_IZIYLE_gunluklenir(bus, caplog):
    gelen: list = []

    def patlar(e):
        raise ValueError("abone hatası")

    bus.subscribe("stm.kopma", patlar, "p", priority=eb.EventPriority.HIGH)
    bus.subscribe("stm.kopma", lambda e: gelen.append(e.data), "acil")
    bus.subscribe("stm.kopma", lambda e: None, "suzgec_patlar", filter_func=lambda e: 1 / 0)
    with caplog.at_level(logging.ERROR, logger="event_bus"):
        assert bus.publish("stm.kopma", "durdur") is True
    assert gelen == ["durdur"], "patlayan abone acil durdurma abonesini engelledi"
    assert bus._stats["failed_deliveries"] == 2
    kayit = next(r for r in caplog.records if "Sync callback failed" in r.getMessage())
    assert kayit.exc_info and "stm.kopma" in kayit.getMessage(), "hata izi (traceback) yok — DENETİM P3"


def test_kapali_veriyolu_yayinlamaz_ic_hata_False(bus, monkeypatch):
    monkeypatch.setattr(bus, "_add_to_history", lambda e: (_ for _ in ()).throw(RuntimeError("x")))
    assert bus.publish("a", 1) is False
    bus.shutdown()
    assert bus.publish("a", 1) is False


def test_KRITIK_esZamansiz_abone_calisan_dongude_GOREV_olarak_teslim_edilir(bus):
    gelen: list = []

    async def al(e):
        gelen.append(e.data)

    async def patlar(e):
        raise ValueError("x")

    bus.subscribe("a", al, "al")
    bus.subscribe("a", patlar, "p")

    async def _kos():
        assert await bus.publish_async("a", 7) is True  # yürütücüde yayın (döngü yok) → yürütücü kolu
        bus.publish("a", 8)  # döngü İÇİNDEN yayın → görev
        assert bus._pending_tasks, "görev izlenmiyor"
        for _ in range(10):
            await asyncio.sleep(0.01)
        assert not bus._pending_tasks, "biten görev izleme kümesinden düşmedi (sızıntı)"

    asyncio.run(_kos())
    bus._executor.shutdown(wait=True)
    assert sorted(gelen) == [7, 8]
    assert bus._stats["events_processed"] >= 2 and bus._stats["failed_deliveries"] >= 2


def test_esZamansiz_abone_DONGUSUZ_yayinda_yurutucude_kendi_dongusuyle_calisir(bus, caplog):
    bitti = threading.Event()

    async def al(e):
        bitti.set()

    bus.subscribe("a", al, "al")
    with caplog.at_level(logging.WARNING, logger="event_bus"):
        bus.publish("a", 1)
    assert bitti.wait(5), "döngü yokken eşzamansız abone hiç çalışmadı"
    assert any("No event loop available" in r.getMessage() for r in caplog.records)


def test_publish_async_dongu_YOKKEN_ates_et_unut(bus):
    gelen = threading.Event()
    bus.subscribe("a", lambda e: gelen.set(), "x")
    c = bus.publish_async("a", 1)
    with pytest.raises(StopIteration) as s:
        c.send(None)  # döngü olmadan sür: get_running_loop RuntimeError → yürütücüye at, True dön
    assert s.value.value is True and gelen.wait(5)


def test_esZamansiz_cagri_kollari_olu_iptal_ve_yurutucu_hatasi(bus, monkeypatch, caplog):
    olu = eb.Subscription(
        callback_ref=lambda: None, strong_callback=None, event_type="a", subscriber_id="o", is_async=True
    )
    asyncio.run(bus._call_async_callback(olu, eb.Event("a", 1)))  # ölü → sessiz atla
    bus._call_sync_callback(eb.Subscription(None, None, "a", "o2"), eb.Event("a", 1))
    assert bus._stats["failed_deliveries"] == 0

    async def uzun(e):
        await asyncio.sleep(10)

    sub = eb.Subscription(None, uzun, "a", "u", is_async=True)

    async def _iptal():
        t = asyncio.ensure_future(bus._call_async_callback(sub, eb.Event("a", 1)))
        await asyncio.sleep(0)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

    asyncio.run(_iptal())
    monkeypatch.setattr(eb.asyncio, "new_event_loop", lambda: (_ for _ in ()).throw(OSError("döngü yok")))
    bus._run_async_in_executor(sub, eb.Event("a", 1))
    assert bus._stats["failed_deliveries"] == 1
    assert any("Async callback execution in executor failed" in r.getMessage() for r in caplog.records)


def test_KRITIK_kapanis_bekleyen_gorevleri_IPTAL_eder_yurutucuyu_bosaltir(bus, caplog):
    async def uzun(e):
        await asyncio.sleep(10)

    bus.subscribe("a", uzun, "u")

    class _IptalPatlar:
        def done(self):
            return False

        def cancel(self):
            raise RuntimeError("iptal edilemedi")

    async def _kos():
        bus.publish("a", 1)
        gorev = next(iter(bus._pending_tasks))
        bus._pending_tasks.add(_IptalPatlar())
        bus.shutdown()  # döngü İÇİNDE: iptal + yürütücüye yer tutucu (shutdown öncesi)
        for _ in range(5):
            await asyncio.sleep(0)
        assert gorev.cancelled()

    asyncio.run(_kos())
    assert not bus._running and not bus._subscribers and not bus._event_history
    assert any("Failed to cancel async task" in r.getMessage() for r in caplog.records)


def test_kapanis_dongu_DISINDA_ve_yurutucu_hatasinda_da_tamamlanir(caplog):
    b = eb.EventBus(max_workers=1)

    class _Gorev:
        cancelled = False

        def done(self):
            return False

        def cancel(self):
            _Gorev.cancelled = True

    b._pending_tasks.add(_Gorev())
    b._executor = SimpleNamespace(
        shutdown=lambda **k: (_ for _ in ()).throw(RuntimeError("kapanmadı")), submit=lambda *a: None
    )
    b.shutdown()
    assert _Gorev.cancelled and not b._running
    assert any("Executor shutdown warning" in r.getMessage() for r in caplog.records)


def test_genel_islevler_TEKIL_veriyolunu_kullanir(monkeypatch):
    monkeypatch.setattr(eb, "_event_bus_instance", None)
    gelen: list = []
    try:
        assert eb.subscribe("g", lambda e: gelen.append(e.data), "x") is True
        assert eb.get_event_bus() is eb.get_event_bus()
        assert eb.publish("g", 1) is True
        assert asyncio.run(eb.publish_async("g", 2)) is True
        assert eb.unsubscribe("g", "x") is True
        assert gelen == [1, 2]
    finally:
        eb.get_event_bus().shutdown()
