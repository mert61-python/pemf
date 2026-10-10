# -*- coding: utf-8 -*-
"""E2-3.10 (2-E incelemesi A3) — Y118 `veriKokuAgda` alanı `/api/health`te olay döngüsünü TUTMAZ; asılan sürücü türü sorgusu ACİL DURDUR'u
bekletmez (Ö.4-Y8: gecikme de kapılanmadır).

Y118 `async def health_check` içinde, yerel/LAN her sağlık isteğinde `veri_koku_ag_paylasiminda_mi` → `GetDriveTypeW`'yi (sarmalayıcı
`path_utils._surucu_turu`) SATIR İÇİ çağırır. Ölçüldü (2-E incelemesi A3 K4): sarmalayıcı EN ALT katta 3 sn bekletilince sağlık isteği
uçuştayken gelen ACİL DURDUR **2,1 sn** bekledi (TEK paylaşılan döngü). `GetDriveTypeW`'nin ağ / yeniden bağlanan SMB sürücüsünde gerçekten
asılıp asılmadığı BİLİNMİYOR (gerçek paylaşım yok) — ama sözleşme "E-stop hiçbir şeye kapılanmaz": döngüde koşan bir sistem çağrısı onu
bekletebiliyor.
Kapı: httpx.AsyncClient + ASGITransport + asyncio.run (TestClient her istekte yeni döngü açar — döngü donmasını göremez). E-stop, sağlık
isteği başladıktan 1,0 sn sonra GELİR; süre o andan yanıta ölçülür.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

GEC = 3.0


async def _olc(app):
    a = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 50000)), base_url="http://cihaz")
    b = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 50002)), base_url="http://cihaz")
    async with a, b:
        t0 = time.monotonic()
        saglik = asyncio.create_task(a.get("/api/health"))
        hedef = t0 + 1.0
        await asyncio.sleep(1.0)
        r = await b.post("/api/hardware/emergency_stop")
        estop = time.monotonic() - hedef
        s = await saglik
    return r.status_code, estop, s.status_code, s.json().get("veriKokuAgda")


@pytest.mark.parametrize("yavas", [False, True], ids=["taban", "surucu_turu_asili_3sn"])
def test_KRITIK_saglik_ucu_surucu_turu_ASILSA_da_ESTOP_beklemez_E2310(monkeypatch, yavas):
    from servers import api_server as api
    from utils import path_utils

    cagri = []
    asil = path_utils._surucu_turu

    def _en_alt(kok):
        cagri.append(kok)
        if yavas:
            time.sleep(GEC)
        return asil(kok)

    monkeypatch.setattr(path_utils, "_surucu_turu", _en_alt)
    kod, estop, skod, bayrak = asyncio.run(_olc(api.app))
    assert skod == 200 and (isinstance(bayrak, bool) or (yavas and bayrak is None)), (
        f"sağlık ucu bayrağı ({skod}, {bayrak})"
    )
    assert cagri, "aparat: sürücü türü sorgusu hiç çağrılmadı (yol sürücü harfli değil mi?)"
    assert kod == 200 and estop < 1.0, (
        f"sağlık ucunun sürücü türü sorgusu asılıyken ACİL DURDUR {estop:.2f} sn bekledi (Ö.4-Y8: gecikme de kapılanmadır)"
    )


def test_KRITIK_asili_surucu_sorgusu_TEK_ucusta_ortak_havuzu_TUKETMEZ_E2310(monkeypatch):
    """2-E incelemesi orkestratörü: sorgu `to_thread` + `wait_for` ile koşsaydı zaman aşımı yalnız BEKLEYENİ bırakır, asılı işi değil —
    her yoklama ortak havuzdan bir iş parçacığı sızdırır; havuz (bu makinede 20) dolunca `to_thread` kullanan her uç (DB yazımları,
    onaylar) asılır (hafıza: "asılı disk + to_thread ortak havuz"). Sözleşme: asılı sorgu sürerken 25 eşzamanlı yoklama → sorgu EN ÇOK
    1 kez başlar ve kısa bir `to_thread` işi hemen koşar."""
    import threading

    from servers import api_server as api
    from utils import path_utils

    cagri = []
    birak = threading.Event()

    def _asili(kok):
        cagri.append(kok)
        birak.wait(5)
        return 3  # DRIVE_FIXED

    monkeypatch.setattr(path_utils, "_surucu_turu", _asili)

    async def _kos():
        c = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api.app, client=("127.0.0.1", 50003)), base_url="http://cihaz", timeout=30
        )
        async with c:
            try:
                yanitlar = await asyncio.gather(*[c.get("/api/health") for _ in range(25)])
                t0 = time.monotonic()
                try:
                    await asyncio.wait_for(asyncio.to_thread(lambda: 1), timeout=1.0)
                    havuz = time.monotonic() - t0
                except asyncio.TimeoutError:
                    havuz = None
                return [r.status_code for r in yanitlar], [r.json().get("veriKokuAgda") for r in yanitlar], havuz
            finally:
                birak.set()

    kodlar, bayraklar, havuz = asyncio.run(_kos())
    assert set(kodlar) == {200} and set(bayraklar) == {None}, (kodlar, bayraklar)
    assert len(cagri) <= 1, (
        f"asılı sürücü sorgusu {len(cagri)} kez başlatıldı — her yoklama yeni bir asılı iş parçacığı bırakıyor"
    )
    assert havuz is not None and havuz < 0.5, (
        f"ortak iş parçacığı havuzu asılı sorgularla TÜKENDİ: kısa bir to_thread işi {havuz} sn'de koşamadı"
    )
