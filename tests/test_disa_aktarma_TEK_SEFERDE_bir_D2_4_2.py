# -*- coding: utf-8 -*-
"""D2-4.2 (2-D incelemesi, orkestratör · Ö.4-Y8) — aynı anda TEK cihaz taşıma dışa aktarması; ikinci istek beklemez, hemen 409.

ÖLÇÜLEN KUSUR (HEAD `a76ee0d`, orkestratör sondası O1, tek PAYLAŞILAN olay döngüsü, gerçek `HardwareController`): `/api/data/export`
eşzamanlılığı sınırsızdı (D2.E02 yalnız İÇE aktarmayı tek kritik bölgeye aldı). 2000 seans + 200 000 sensör satırlı klinikte 25 eşzamanlı
dışa aktarma (A-01: LAN'daki eşleşmiş istemciden de gelebilir) CPU yoğun iş parçacıklarıyla GIL'i doyurdu: ACİL DURDUR yanıtı 5,1 sn (düz)
/ 12,0 sn (SQLCipher), ilk donanım STOP paketi 1,8 / 2,9 sn; tek dışa aktarmada 0,34 / 0,47 sn.
DÜZELTME: `_DISA_AKTARMA_KILIDI` — tek dışa aktarma; ikincisi 409 `YEDEK_ALMA_SURUYOR`; kilit iş BİTİNCE bırakılır (`asyncio.shield` +
görev bitiş geri çağrısı — istemci koparsa da iş parçacığı sürerken yeni bir dışa aktarma başlamaz).
GERÇEK: uç gövdesi, DB'ler, paket şifrelemesi (zamanlama için şifreleme girişinde Event ile BEKLETİLİR — iş aynen yapılır), ACİL DURDUR
(`gercek_hc`). Tek olay döngüsü (httpx ASGITransport).
"""

from __future__ import annotations

import asyncio
import threading
import time

import ai_pro_aparati as ap
import pytest
import veri_tasima_aparati as vta

PAROLA = "D2-4-2-parola"


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc
    from utils import data_export as de

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            tdb, hdb = vta.cihaz_kur(monkeypatch, tmp_path / "A")
            vta.doldur(tdb, hdb, ["H1", "H2", "H3"], seans_basi=2, sensor=2)
            vta.uclari_bagla(monkeypatch, tdb, hdb)
            ns.dbler = (tdb, hdb)
            ns.girdi, ns.birak = threading.Event(), threading.Event()
            ns.esz, ns.en_cok = [0], [0]
            ns.kilit = threading.Lock()
            orj = de.encrypt_bundle

            def _bekleyen(paket, parola):
                with ns.kilit:
                    ns.esz[0] += 1
                    ns.en_cok[0] = max(ns.en_cok[0], ns.esz[0])
                ns.girdi.set()
                try:
                    ns.birak.wait(30)
                    return orj(paket, parola)
                finally:
                    with ns.kilit:
                        ns.esz[0] -= 1

            monkeypatch.setattr(de, "encrypt_bundle", _bekleyen)
            yield ns
            ns.birak.set()
            vta.kapat(tdb, hdb)
    finally:
        ns.geri()


def _istemci(o):
    import httpx

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=o.api.app, client=("127.0.0.1", 50124)), base_url="http://cihaz", timeout=60
    )


async def _girdiyi_bekle(o):
    t0 = time.monotonic()
    while not o.girdi.is_set() and time.monotonic() - t0 < 20:
        await asyncio.sleep(0.01)
    assert o.girdi.is_set(), "aparat: ilk dışa aktarma şifreleme adımına gelmedi"


def test_KRITIK_D2_4_2_esZAMANLI_disa_aktarma_TEK_ikincisi_409(o):
    async def _s():
        async with _istemci(o) as c:
            ilk = asyncio.create_task(c.post("/api/data/export", json={"passphrase": PAROLA}))
            await _girdiyi_bekle(o)
            t0 = time.monotonic()
            digerleri = await asyncio.gather(
                *[c.post("/api/data/export", json={"passphrase": PAROLA}) for _ in range(5)]
            )
            sure = time.monotonic() - t0
            o.birak.set()
            return await ilk, digerleri, sure

    ilk, digerleri, sure = asyncio.run(_s())
    kodlar = [r.status_code for r in digerleri]
    assert o.en_cok[0] == 1, (
        f"aynı anda {o.en_cok[0]} dışa aktarma koştu — eşzamanlılık sınırsız (ACİL DURDUR aç kalır); kodlar {kodlar}"
    )
    assert kodlar == [409] * 5, f"ilk dışa aktarma sürerken ikinci istekler reddedilmedi: {kodlar}"
    assert all("yedek alma" in r.json().get("detail", "").lower() for r in digerleri), digerleri[0].text[:200]
    assert sure < 5, f"ikinci istekler BEKLEDİ ({sure:.1f} sn) — beklemeden 409 dönmeli"
    assert ilk.status_code == 200, ilk.text[:200]


def test_KRITIK_D2_4_2_istemci_koparsa_KILIT_is_bitince_birakilir(o):
    async def _s():
        async with _istemci(o) as c:
            ilk = asyncio.create_task(c.post("/api/data/export", json={"passphrase": PAROLA}))
            await _girdiyi_bekle(o)
            ilk.cancel()  # istemci vazgeçti; iş parçacığı şifrelemeyi sürdürüyor
            try:
                await ilk
            except asyncio.CancelledError:
                pass
            ara = await c.post("/api/data/export", json={"passphrase": PAROLA})
            o.birak.set()
            t0 = time.monotonic()
            while o.esz[0] and time.monotonic() - t0 < 20:
                await asyncio.sleep(0.02)
            await asyncio.sleep(0.2)
            son = await c.post("/api/data/export", json={"passphrase": PAROLA})
            return ara, son

    ara, son = asyncio.run(_s())
    assert ara.status_code == 409, (
        f"istemci kopunca kilit HEMEN bırakıldı — iş parçacığı sürerken yeni dışa aktarma başladı ({ara.status_code}); "
        f"eşzamanlı iş en çok {o.en_cok[0]}"
    )
    assert son.status_code == 200, f"iş bitince kilit bırakılmadı: {son.status_code} {son.text[:200]}"


def test_KARSIT_Y8_disa_aktarma_SURERKEN_ACIL_DURDUR_calisir(o):
    async def _s():
        async with _istemci(o) as c:
            ilk = asyncio.create_task(c.post("/api/data/export", json={"passphrase": PAROLA}))
            await _girdiyi_bekle(o)
            cagri = o.hc.stop_all_cagri
            t0 = time.monotonic()
            r = await c.post("/api/hardware/emergency_stop")
            sure = time.monotonic() - t0
            o.birak.set()
            await ilk
            return r, sure, o.hc.stop_all_cagri - cagri

    r, sure, fark = asyncio.run(_s())
    assert r.status_code == 200 and fark >= 1, (
        f"dışa aktarma sürerken ACİL DURDUR çalışmadı: {r.status_code} {r.text[:200]}"
    )
    assert sure < 3.0, f"ACİL DURDUR {sure:.2f} sn bekledi"


def test_KARSIT_D2_4_2_ardisik_disa_aktarmalar_200(o):
    o.birak.set()

    async def _s():
        async with _istemci(o) as c:
            return [await c.post("/api/data/export", json={"passphrase": PAROLA}) for _ in range(3)]

    kodlar = [r.status_code for r in asyncio.run(_s())]
    assert kodlar == [200, 200, 200], kodlar
