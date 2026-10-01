# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.15 · B-4.15 — DB açılamasa da cihaz kayıt defteri yayını (uzaktan erişim) SÜRER.

ÖLÇÜLEN (DENETİM-04 B-4.15, sonda D9): `CloudSyncWorker._sync_loop` hasta ve tedavi DB'lerini
döngüden ÖNCE ve `try` DIŞINDA açıyordu. Tek bir açılış hatası (yarım göç → `GocBekliyorHatasi`,
anahtar uyuşmazlığı → `RuntimeError`) iş parçacığını öldürüyor; cihaz kayıt defteri yayını —
mobilin uzaktan bağlantısı — süreç ömrü boyunca SESSİZCE duruyordu. Hasta senkronu varsayılan
KAPALIYKEN bile (DB'ye hiç gerek yokken). B-3.8 (D1.37) sonrası DB'siz açılışta bu yol olağanlaşır
(C1-8).

GERÇEK `_sync_loop`; sahte olan yalnız DB fabrikaları, yayın ve senkron gövdeleri (ağ YOK,
Supabase istemcisi sahte nesne).
"""

from __future__ import annotations

import threading
import time
import types

import pytest


def _bekle(kosul, sure=5.0) -> bool:
    son = time.monotonic() + sure
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.005)
    return kosul()


#: Bağımsız inceleme (r4): aparat eskiden yalnız TEDAVİ DB'sini patlatıyordu — hasta DB'si yine döngü
#: öncesinde ve try dışında açılsa (mutant) kapı yeşil kalıyordu. B-4.15 "tek bir DB açılış hatası (yarım
#: göç, anahtar uyuşmazlığı)" der: açılamayan DB ve hata türü ayrı ayrı denenir.
_DUSEN = {"tedavi": {"tedavi"}, "hasta": {"hasta"}, "ikisi": {"tedavi", "hasta"}}
_HATALAR = ("goc_bekliyor", "anahtar_runtime")


@pytest.fixture(params=[(d, h) for d in _DUSEN for h in _HATALAR], ids=lambda p: f"{p[0]}-{p[1]}")
def senkron_aparati(request, monkeypatch):
    import servers.sync_worker as sw
    from database.sqlcipher_util import GocBekliyorHatasi

    dusen_db, hata_turu = request.param
    durum = types.SimpleNamespace(yayin=0, db_deneme=0, senkron=0, db_acilsin=threading.Event())

    def _fabrika(ad):
        def ac(*_a, **_k):
            if ad in _DUSEN[dusen_db] and not durum.db_acilsin.is_set():
                durum.db_deneme += 1
                if hata_turu == "goc_bekliyor":
                    raise GocBekliyorHatasi("DB duz-metin, at-rest gocu bekliyor (test)")
                raise RuntimeError("SQLCipher anahtar uyusmazligi (test)")
            return object()

        return ac

    monkeypatch.setattr(sw, "get_treatment_db", _fabrika("tedavi"))
    monkeypatch.setattr(sw, "get_patient_database", _fabrika("hasta"))
    w = sw.CloudSyncWorker("", "", interval_sec=0.01)  # boş yapılandırma: gerçek istemci KURULMAZ
    w.client = object()
    w.supabase_url, w.supabase_key = "https://ornek.invalid", "x"

    def yayinla():
        durum.yayin += 1
        return True

    def senkronla(_db):
        durum.senkron += 1

    w._publish_device_registry = yayinla
    w._sync_patients = senkronla
    w._sync_sessions = lambda _db: None
    isler: list[threading.Thread] = []

    def baslat(hasta_senkronu: bool) -> threading.Thread:
        w.patient_sync_enabled = hasta_senkronu
        t = threading.Thread(target=w._sync_loop, daemon=True, name="test-CloudSyncWorker-D115")
        t.start()
        isler.append(t)
        return t

    yield durum, baslat
    w.stop_event.set()
    for t in isler:
        t.join(5)
    assert not any(t.is_alive() for t in isler), "senkron iş parçacığı durdurulamadı (aparat)"


def test_KRITIK_hasta_senkronu_KAPALIYKEN_DB_acilamasa_kayit_YAYINI_surer(senkron_aparati):
    durum, baslat = senkron_aparati
    t = baslat(False)
    assert _bekle(lambda: durum.yayin >= 3), (
        f"DB açılış hatası senkron iş parçacığını ÖLDÜRDÜ (yayın {durum.yayin}) — hasta senkronu kapalıyken "
        "bile cihaz kayıt defteri / uzaktan erişim yayını süreç ömrü boyunca DURUR"
    )
    assert t.is_alive()


def test_KRITIK_hasta_senkronu_ACIKKEN_DB_acilamasa_yayin_surer_ve_DB_gelince_TOPARLANIR(senkron_aparati):
    durum, baslat = senkron_aparati
    t = baslat(True)
    assert _bekle(lambda: durum.yayin >= 3 and durum.db_deneme >= 2), (
        f"yayın {durum.yayin}, DB denemesi {durum.db_deneme} — DB hatası yayını durdurdu ya da açılış yeniden DENENMİYOR"
    )
    assert t.is_alive() and durum.senkron == 0
    durum.db_acilsin.set()
    assert _bekle(lambda: durum.senkron >= 1), "DB açılabilir olunca hasta senkronu kendiliğinden DEVAM ETMEDİ"
    assert t.is_alive()
