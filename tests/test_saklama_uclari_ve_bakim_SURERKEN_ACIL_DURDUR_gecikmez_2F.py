# -*- coding: utf-8 -*-
"""2-F · Ö.4-Y8 — saklama / KVKK yüzeyleri tedavi DB'si KİLİTLİYKEN ACİL DURDUR'u ve STOP'u bekletmez.

2-F'nin yeni ya da değişen yüzeyleri: `/api/settings/retention` GET (PII + anonimleştirme bekleyen sayıları — iki DB okuması) ve POST
(`anonymize_acknowledge` onay YAZIMI), günlük bakım turunun KVKK anonimleştirmesi (`services.kvkk_anonimlestirme.tur`) ve haftalık VACUUM.
Hepsi tedavi DB'sinde yazım kilidi bekleyebilir (VACUUM / anonimleştirme / başka yazar). Kural: bunlar olay döngüsünü tutmaz; ACİL DURDUR
yanıtı ve donanım STOP'u kilit sürerken de gecikmez.
ÖLÇÜM: tek PAYLAŞILAN olay döngüsü (httpx ASGITransport — TestClient her istekte yeni döngü açar, bunu göremez), GERÇEK `HardwareController`
(`gercek_hc`), arıza GERÇEK kilit (ikinci bağlantı `BEGIN EXCLUSIVE` + yazım), en az 3 EŞZAMANLI onay yazımı + 3 okuma isteği kilitte beklerken
ACİL DURDUR; aynı anda arka planda bakım turu (anonimleştirme) kilitte bekler.
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
        transport=httpx.ASGITransport(app=o.api.app, client=("127.0.0.1", 50131)), base_url="http://cihaz", timeout=60
    )


class _Kilit:
    """Tedavi DB'sine ikinci bağlantıdan GERÇEK yazım kilidi (`BEGIN EXCLUSIVE` + yazım), `sure` sn tutar."""

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


def test_KRITIK_retention_onay_yazimlari_ve_bakim_turu_KILITTE_beklerken_ACIL_DURDUR_gecikmez(o):
    from services import kvkk_anonimlestirme as kv

    o.db.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=1, kim="")  # bakım turu kanonik adımdan sonra tedavi DB'sine yazacak

    async def _s():
        async with _istemci(o) as c:
            with _Kilit(o.db.db_path, 6.0):
                bakim = threading.Thread(target=lambda: kv.tur(o.pdb, o.db), daemon=True)
                bakim.start()
                cagri = o.hc.stop_all_cagri
                # ⚠️ Zaman, kilitte bekleyecek istekler kuyruğa girmeden ÖNCE başlar ve ACİL DURDUR onlarla EŞZAMANLI gönderilir: bir uç
                # olay döngüsünü senkron tutarsa ACİL DURDUR görevi o tıkanıklığın ARKASINDA kalır ve süre bunu içerir. (İlk sürüm
                # süreyi `sleep` döndükten sonra başlatıyordu → döngü tıkanıklığı ölçülmüyordu; senkron mutant YEŞİL kaldı — ölçüldü.)
                t0 = time.monotonic()
                yazimlar = [
                    asyncio.create_task(c.post("/api/settings/retention", json={"anonymize_acknowledge": True}))
                    for _ in range(3)
                ]
                okumalar = [asyncio.create_task(c.get("/api/settings/retention")) for _ in range(3)]
                acil = asyncio.create_task(c.post("/api/hardware/emergency_stop"))
                r = await acil
                sure = time.monotonic() - t0
                stop = o.hc.stop_all_cagri - cagri
                bekleyen_yazim = sum(1 for t in yazimlar if not t.done())
            for t in yazimlar + okumalar:
                await t
            bakim.join(30)
            return r, sure, stop, bekleyen_yazim

    r, sure, stop, bekleyen_yazim = asyncio.run(_s())
    assert r.status_code == 200 and stop >= 1, f"kilitte ACİL DURDUR çalışmadı: {r.status_code} stop={stop}"
    assert sure < 1.0, f"saklama uçları / bakım turu kilitte beklerken ACİL DURDUR {sure:.2f} sn bekledi (Ö.4-Y8)"
    assert bekleyen_yazim == 3, (
        f"aparat: onay yazımları ACİL DURDUR sırasında kilitte beklemiyordu ({bekleyen_yazim}/3)"
    )


def test_KRITIK_PII_sure_ve_onay_yazimlari_KILITTE_beklerken_ACIL_DURDUR_gecikmez(o):
    """D2.55: `POST /api/settings/retention` `days` ve `acknowledge` yazımları (eskiden olay döngüsünde senkron) kilitte beklerken."""

    async def _s():
        async with _istemci(o) as c:
            with _Kilit(o.db.db_path, 6.0):
                cagri = o.hc.stop_all_cagri
                t0 = time.monotonic()  # ⚠️ istekler kuyruğa girmeden ÖNCE (yukarıdaki testin notu)
                yazimlar = [
                    asyncio.create_task(c.post("/api/settings/retention", json=g))
                    for g in ({"days": 730}, {"days": 365}, {"acknowledge": True}, {"acknowledge": True})
                ]
                acil = asyncio.create_task(c.post("/api/hardware/emergency_stop"))
                r = await acil
                sure = time.monotonic() - t0
                stop = o.hc.stop_all_cagri - cagri
                bekleyen_yazim = sum(1 for t in yazimlar if not t.done())
            for t in yazimlar:
                await t
            return r, sure, stop, bekleyen_yazim

    r, sure, stop, bekleyen_yazim = asyncio.run(_s())
    assert r.status_code == 200 and stop >= 1, f"kilitte ACİL DURDUR çalışmadı: {r.status_code} stop={stop}"
    assert sure < 1.0, f"PII süre/onay yazımları kilitte beklerken ACİL DURDUR {sure:.2f} sn bekledi (Ö.4-Y8)"
    assert bekleyen_yazim == 4, f"aparat: yazımlar ACİL DURDUR sırasında kilitte beklemiyordu ({bekleyen_yazim}/4)"


def test_KARSIT_kilit_GERCEKTEN_yazimi_bekletiyor(o):
    """Araç kör değil: kilit sürerken onay yazımı busy_timeout kadar bekler (kilitsiz anında döner)."""

    async def _s():
        async with _istemci(o) as c:
            t0 = time.monotonic()
            await c.post("/api/settings/retention", json={"anonymize_acknowledge": True})
            kilitsiz = time.monotonic() - t0
            with _Kilit(o.db.db_path, 3.0):
                t1 = time.monotonic()
                await c.post("/api/settings/retention", json={"anonymize_acknowledge": True})
                kilitli = time.monotonic() - t1
            return kilitsiz, kilitli

    kilitsiz, kilitli = asyncio.run(_s())
    assert kilitli > 1.5 and kilitsiz < 1.5, (kilitsiz, kilitli)
