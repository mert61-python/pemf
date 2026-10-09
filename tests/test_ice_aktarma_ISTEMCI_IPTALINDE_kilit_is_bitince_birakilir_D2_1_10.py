# -*- coding: utf-8 -*-
"""D2-1.10 (2-D incelemesi, A1) — KÖR KAPI: D2.E02'nin "istemci bağlantıyı koparsa da kilit iş BİTİNCE bırakılır" iddiası kilitli değil.

`import_clinic_data` içe aktarmayı `asyncio.shield` içinde koşturur; bitiş geri çağrısı kilidi bırakır. `shield` kaldırılırsa istemci vazgeçince
(arayüz zaman aşımı, sekme kapanması, ağ kopması) iç görev de İPTAL olur, geri çağrı kilidi HEMEN bırakır — oysa `asyncio.to_thread`'deki
`import_rows` iş parçacığında sürmektedir. O arada gelen ikinci geri yükleme hedefi boş görüp aynı paketi yazar: kayıtlar İKİYE katlanır (D2.E02'nin
kapattığı asıl kusur, başka kapıdan). 2-D kapısı (test_ice_aktarma_TEK_kritik_bolge_ikinci_istek_409_D2E02.py) istemci iptalini hiç kurmuyor:
`shield`siz mutant orada YEŞİL [ÖLÇTÜM kayit/K5_mutasyon.txt a1k5_m1: 12 passed].
APARAT: gerçek DB'ler, gerçek paket, tek olay döngüsü (httpx ASGITransport). Pencere deterministik: hedefin `import_rows`u İLK girişte
`serbest` olayına dek bekler (ürün kodu değişmez; örnek özniteliği sarılır). İstemci iptali = `asyncio.wait_for` zaman aşımı.
"""

from __future__ import annotations

import asyncio
import threading
import time

import httpx
from veri_tasima_aparati import PAROLA, cihaz_kur, disa_aktar, doldur, kapat, sayimlar, uclari_bagla


def test_KRITIK_D2E02_istemci_VAZGECINCE_kilit_is_BITINCE_birakilir_ikinci_istek_409_kayit_COGALMAZ(
    tmp_path, monkeypatch
):
    from servers import api_server as api

    ta, ha = cihaz_kur(monkeypatch, tmp_path / "A")
    uclari_bagla(monkeypatch, ta, ha)
    doldur(ta, ha, ["Mia", "Pamuk", "Tarcin"], seans_basi=2)
    paket = disa_aktar(api.app)
    kaynak = sayimlar(ta, ha)
    tb, hb = cihaz_kur(monkeypatch, tmp_path / "B")  # BOŞ hedef
    uclari_bagla(monkeypatch, tb, hb)
    gercek = tb.import_rows
    giris = {"n": 0}
    ilk_iceride = threading.Event()
    serbest = threading.Event()

    def _sarili(data, replace=False):
        giris["n"] += 1
        if giris["n"] == 1:
            ilk_iceride.set()
            serbest.wait(20)
        return gercek(data, replace)

    monkeypatch.setattr(tb, "import_rows", _sarili)
    govde = {"passphrase": PAROLA, "blob_b64": paket["data_b64"]}

    async def _kos():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api.app, client=("127.0.0.1", 50123)),
            base_url="http://cihaz",
            timeout=120,
        ) as c:
            ilk = asyncio.ensure_future(c.post("/api/data/import", json=govde))
            while not ilk_iceride.is_set():
                await asyncio.sleep(0.01)
            ilk.cancel()  # istemci vazgeçti (zaman aşımı / bağlantı koptu) — iş cihazda sürüyor
            try:
                await ilk
            except asyncio.CancelledError:
                pass
            kilit_iptal_sonrasi = api._VERI_TASIMA_KILIDI.locked()
            ikinci = await c.post("/api/data/import", json=govde)
            serbest.set()
            t0 = time.monotonic()
            while api._VERI_TASIMA_KILIDI.locked() and time.monotonic() - t0 < 30:
                await asyncio.sleep(0.02)
            await asyncio.sleep(0.2)
            return kilit_iptal_sonrasi, ikinci, api._VERI_TASIMA_KILIDI.locked()

    try:
        kilit_iptal_sonrasi, ikinci, kilit_son = asyncio.run(_kos())
        sonra = sayimlar(tb, hb)
        assert kilit_iptal_sonrasi, "istemci vazgeçince kilit, iş (import_rows) iş parçacığında SÜRERKEN bırakıldı"
        assert ikinci.status_code == 409, (
            f"ilk geri yükleme cihazda sürerken (istemcisi vazgeçmişti) ikinci istek {ikinci.status_code} aldı: {ikinci.text[:160]}"
        )
        assert sonra["treatment_sessions"] == kaynak["treatment_sessions"], (
            f"kayıtlar ÇOĞALDI: {sonra['treatment_sessions']} seans (paket {kaynak['treatment_sessions']})"
        )
        assert not kilit_son, "iş bitti ama kilit bırakılmadı"
    finally:
        serbest.set()
        kapat(ta, ha, tb, hb)
