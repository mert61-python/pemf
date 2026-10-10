# -*- coding: utf-8 -*-
"""F2-2.2 (2-F incelemesi A2) — Ö.4-Y8 kapısının (test_saklama_uclari_ve_bakim_SURERKEN_ACIL_DURDUR_gecikmez_2F) YARIŞA bağlı körlüğü.

ÖLÇÜLEN: 2-F'nin kendi mutantı `f2_y8_m1_onay_dongude` (anonimleştirme onay yazımı olay döngüsünde senkron) HEAD'de 3 koşunun 2'sinde
YEŞİL. D2.55 (bc4469f) POST'a onay yazımından ÖNCE iki `to_thread` durağı ekledi; ACİL DURDUR tek durakla (kendi iş parçacığı) yarışı
çoğu koşuda KAZANIYOR → döngüyü 3 × 5 sn donduran mutant görünmüyor (kırmızı koşuda ACİL DURDUR 6,11 sn). Ayrıca GET kollarının
okumaları WAL'da yazım kilidinde BEKLEMEZ → okumayı döngüye alan mutantlar her koşuda yeşil.
DÜZELTME (kapı): ACİL DURDUR TEK atış değil, kilit SÜRERKEN 0,25 sn aralıkla KADEMELİ (8 atış); her atışın gecikmesi KENDİ gönderim
anından ölçülür (döngü hangi anda donarsa donsun bir atış onun arkasında kalır) + GET kolu için GERÇEK ürün kilidi: hasta DB'sinin
`PatientDatabase.lock`'u (ertelenmiş / toplu silme VACUUM'u bunu tutar) tutulurken bekleyen sayısı okuyan GET'ler.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from datetime import datetime, timedelta

import ai_pro_aparati as ap
import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    from database import patient_database as pmod
    from kayitci_donanim import gercek_hc
    from servers import system_router as sr

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            ns.pdb = pmod.PatientDatabase(str(tmp_path / "patients.db"))
            pid = ns.pdb.add_patient({"name": "Kilit Hasta", "owner": "S"})
            with ns.pdb._get_connection() as c:
                c.execute(
                    "UPDATE patients SET last_treatment_at=? WHERE id=?",
                    ((datetime.now() - timedelta(days=2200)).isoformat(), pid),
                )
                c.commit()
            monkeypatch.setattr(pmod, "get_patient_database", lambda *a, **k: ns.pdb)
            monkeypatch.setattr(sr, "_pii_ayar_db", lambda: ns.db)
            yield ns
    finally:
        ns.geri()


def _istemci(o):
    import httpx

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=o.api.app, client=("127.0.0.1", 50133)), base_url="http://cihaz", timeout=60
    )


class _TedaviKilidi:
    """Tedavi DB'sine ikinci bağlantıdan GERÇEK yazım kilidi (`BEGIN EXCLUSIVE` + yazım)."""

    def __init__(self, yol, sure):
        self.yol, self.sure = str(yol), sure
        self.alindi = threading.Event()
        self.th = threading.Thread(target=self._tut, daemon=True)

    def _tut(self):
        c = sqlite3.connect(self.yol, timeout=10, isolation_level=None)
        try:
            c.execute("BEGIN EXCLUSIVE")
            c.execute(
                "INSERT OR REPLACE INTO system_settings (setting_key, setting_value) VALUES ('kilit_sondasi', '1')"
            )
            self.alindi.set()
            time.sleep(self.sure)
            c.execute("ROLLBACK")
        finally:
            c.close()

    def __enter__(self):
        self.th.start()
        assert self.alindi.wait(10), "aparat: kilit alınamadı"
        return self

    def __exit__(self, *a):
        self.th.join(self.sure + 10)


class _HastaDbKilidi:
    """Ürünün KENDİ süreç içi kilidi: `PatientDatabase.lock` (ertelenmiş / toplu silme VACUUM'u bu kilidi tutar)."""

    def __init__(self, pdb, sure):
        self.pdb, self.sure = pdb, sure
        self.alindi = threading.Event()
        self.th = threading.Thread(target=self._tut, daemon=True)

    def _tut(self):
        with self.pdb.lock:
            self.alindi.set()
            time.sleep(self.sure)

    def __enter__(self):
        self.th.start()
        assert self.alindi.wait(10), "aparat: hasta DB kilidi alınamadı"
        return self

    def __exit__(self, *a):
        self.th.join(self.sure + 10)


async def _kademeli_acil(c, o, atis=8, aralik=0.25):
    """ACİL DURDUR'u DÖNGÜ DIŞINDAKİ bir iş parçacığından `aralik` sn arayla `atis` kez döngüye sunar (`run_coroutine_threadsafe`);
    her atışın gecikmesi KENDİ sunuluş anından (duvar saati, döngüden bağımsız) yanıta kadar. ⚠️ Atışlar döngünün kendi
    `asyncio.sleep`iyle aralanırsa döngü donukken atış da gecikir ve donma ÖLÇÜLMEZ (ilk sürümde ölçüldü: yeşil kalan mutant)."""
    dongu = asyncio.get_running_loop()
    gelecekler = []

    async def _bir(t_sunus):
        r = await c.post("/api/hardware/emergency_stop")
        return time.monotonic() - t_sunus, r.status_code

    def _atisci():
        for _ in range(atis):
            t = time.monotonic()
            gelecekler.append(asyncio.run_coroutine_threadsafe(_bir(t), dongu))
            time.sleep(aralik)

    th = threading.Thread(target=_atisci, daemon=True, name="f222-atisci")
    th.start()
    while th.is_alive():
        await asyncio.sleep(0.02)
    return list(await asyncio.gather(*(asyncio.wrap_future(g) for g in gelecekler)))


def test_KRITIK_onay_yazimlari_KILITTE_beklerken_KADEMELI_ACIL_DURDUR_her_atista_gecikmez(o):
    """MUTASYON: anonimleştirme onay yazımı / PII yazımı / saat onayı döngüde senkron → bir atış döngü donmasının arkasında kalır →
    KIRMIZI."""
    from services import kvkk_anonimlestirme as kv

    o.db.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=1, kim="")

    async def _s():
        async with _istemci(o) as c:
            with _TedaviKilidi(o.db.db_path, 6.0):
                cagri = o.hc.stop_all_cagri
                yazimlar = [
                    asyncio.create_task(c.post("/api/settings/retention", json=g))
                    for g in (
                        {"anonymize_acknowledge": True},
                        {"anonymize_acknowledge": True},
                        {"anonymize_acknowledge": True},
                        {"days": 730},
                        {"acknowledge": True, "acknowledge_days": 730},  # F2-1.6: onay ekranın süresiyle
                        {"clock_confirm": True},  # F2-1.2: saat onayı da tedavi DB'sine yazar
                    )
                ]
                sureler = await _kademeli_acil(c, o)
                stop = o.hc.stop_all_cagri - cagri
                bekleyen = sum(1 for t in yazimlar if not t.done())
            for t in yazimlar:
                await t
            return sureler, stop, bekleyen

    sureler, stop, bekleyen = asyncio.run(_s())
    assert all(k == 200 for _, k in sureler) and stop >= len(sureler), (sureler, stop)
    assert bekleyen >= 1, f"aparat: yazımlar kilitte beklemiyordu ({bekleyen})"
    en_uzun = max(s for s, _ in sureler)
    assert en_uzun < 1.0, (
        f"onay/süre yazımları kilitte beklerken bir ACİL DURDUR atışı {en_uzun:.2f} sn bekledi (Ö.4-Y8): {sureler}"
    )


def test_KRITIK_hasta_DB_kilidi_tutulurken_retention_GET_ve_onay_KADEMELI_ACIL_DURDUR_gecikmez(o):
    """MUTASYON: anonimleştirme durumu (bekleyen sayısı — `PatientDatabase.lock`) döngüde okunur → KIRMIZI."""

    async def _s():
        async with _istemci(o) as c:
            with _HastaDbKilidi(o.pdb, 3.0):
                cagri = o.hc.stop_all_cagri
                okumalar = [asyncio.create_task(c.get("/api/settings/retention")) for _ in range(3)]
                sureler = await _kademeli_acil(c, o, atis=6)
                stop = o.hc.stop_all_cagri - cagri
            for t in okumalar:
                await t
            return sureler, stop, [t.result().status_code for t in okumalar]

    sureler, stop, kodlar = asyncio.run(_s())
    assert all(k == 200 for _, k in sureler) and stop >= len(sureler), (sureler, stop)
    assert kodlar == [200, 200, 200], kodlar
    en_uzun = max(s for s, _ in sureler)
    assert en_uzun < 1.0, (
        f"hasta DB kilidi tutulurken retention GET'leri ACİL DURDUR'u {en_uzun:.2f} sn bekletti: {sureler}"
    )


def test_KARSIT_hasta_DB_kilidi_GET_i_GERCEKTEN_bekletiyor(o):
    """Araç kör değil: `PatientDatabase.lock` tutulurken retention GET kilit süresi kadar bekler."""

    async def _s():
        async with _istemci(o) as c:
            with _HastaDbKilidi(o.pdb, 2.0):
                t = time.monotonic()
                r = await c.get("/api/settings/retention")
                return time.monotonic() - t, r.status_code

    sure, kod = asyncio.run(_s())
    assert kod == 200 and sure > 1.2, (sure, kod)
