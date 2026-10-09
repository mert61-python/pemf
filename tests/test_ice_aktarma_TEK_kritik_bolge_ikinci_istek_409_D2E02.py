# -*- coding: utf-8 -*-
"""D2.E02 (İG-6.5) — `/api/data/import`: "hedef dolu mu" denetimi + içe aktarma TEK kritik bölgede; eşzamanlı ikinci istek 409.

ÖLÇÜLEN KUSUR (ADAY-DOGRULAMA-D2 İG-6.5, 2-D'de yeniden ölçüldü): `dolu` denetimi ile `import_rows` arasında kilit yoktu. Arayüzün 8 sn
zaman aşımı (İG-6.21) operatörü "Tekrar deneyin"e yönlendiriyordu; ilk geri yükleme cihazda sürerken gelen ikinci istek de hedefi BOŞ
görüp aynı paketi EKLEME kipinde yazıyordu → tüm seans/koşu/sensör/AI kayıtları İKİYE KATLANIYORDU (sahada 4000 seans ölçüldü).
DÜZELTME: süreç içi kilit; ikinci istek BEKLEMEZ, hemen 409 "geri yükleme sürüyor" alır (beklemek SQLCipher'da dakikalık işi ikilerdi).
Geri yükleme sürerken dışa aktarma da 409 (yarım içe aktarılmış durumu yedek diye vermesin).

APARAT: iki ayrı veri kökü (kaynak A, BOŞ hedef B), gerçek DB'ler, GERÇEK `/api/data/export` paketi, tek olay döngüsünde iki eşzamanlı
`/api/data/import` (httpx ASGITransport). Pencere deterministik: hedefin `import_rows`u İLK girişte ikinci istek de girene ya da
sonuçlanana dek bekler (ürün kodu değişmez; örnek özniteliği sarılır).
"""

from __future__ import annotations

import asyncio
import threading
import time

import httpx
import pytest
from veri_tasima_aparati import PAROLA, cihaz_kur, disa_aktar, doldur, kapat, sayimlar, uclari_bagla


def _iki_cihaz(tmp_path, monkeypatch):
    from servers import api_server as api

    ta, ha = cihaz_kur(monkeypatch, tmp_path / "A")
    uclari_bagla(monkeypatch, ta, ha)
    doldur(ta, ha, ["Mia", "Pamuk", "Tarcin"], seans_basi=2)
    paket = disa_aktar(api.app)
    kaynak = sayimlar(ta, ha)
    tb, hb = cihaz_kur(monkeypatch, tmp_path / "B")
    uclari_bagla(monkeypatch, tb, hb)
    return api, (ta, ha), (tb, hb), paket, kaynak


def _pencere(monkeypatch, tb):
    gercek = tb.import_rows
    durum = {"giris": 0}
    ikinci_bitti = threading.Event()

    def _sarili(data, replace=False):
        durum["giris"] += 1
        if durum["giris"] == 1:
            bas = time.monotonic()
            while durum["giris"] < 2 and not ikinci_bitti.is_set() and time.monotonic() - bas < 20:
                time.sleep(0.02)
        return gercek(data, replace)

    monkeypatch.setattr(tb, "import_rows", _sarili)
    return durum, ikinci_bitti


def _eszamanli(app, govde, durum, ikinci_bitti, ikinci=("POST", "/api/data/import")):
    async def _kos():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 50123)), base_url="http://cihaz", timeout=120
        ) as c:
            t1 = asyncio.create_task(c.post("/api/data/import", json=govde))
            bas = time.monotonic()
            while durum["giris"] < 1 and not t1.done() and time.monotonic() - bas < 30:
                await asyncio.sleep(0.02)
            assert durum["giris"] >= 1, "aparat: ilk istek içe aktarmaya girmedi"
            ikinci_govde = govde if ikinci[1] == "/api/data/import" else {"passphrase": PAROLA}
            r2 = await c.request(ikinci[0], ikinci[1], json=ikinci_govde)
            ikinci_bitti.set()
            r1 = await t1
            return r1, r2

    return asyncio.run(_kos())


def test_KRITIK_D2E02_eszamanli_iki_geri_yukleme_kayitlari_COGALTMAZ_ikincisi_409(tmp_path, monkeypatch):
    api, a, (tb, hb), paket, kaynak = _iki_cihaz(tmp_path, monkeypatch)
    try:
        durum, ikinci_bitti = _pencere(monkeypatch, tb)
        govde = {"passphrase": PAROLA, "blob_b64": paket["data_b64"], "confirm": "REPLACE_ALL"}
        r1, r2 = _eszamanli(api.app, govde, durum, ikinci_bitti)
        hedef = sayimlar(tb, hb)
        assert r1.status_code == 200, r1.text[:300]
        assert hedef["treatment_sessions"] == kaynak["treatment_sessions"], (
            f"eşzamanlı ikinci geri yükleme kayıtları ÇOĞALTTI: kaynak {kaynak['treatment_sessions']} seans, hedef "
            f"{hedef['treatment_sessions']} (ikinci yanıt {r2.status_code})"
        )
        assert hedef["ai_analyses"] == kaynak["ai_analyses"] and hedef["sensor_samples"] == kaynak["sensor_samples"]
        assert r2.status_code == 409, f"ikinci istek 409 almadı: {r2.status_code} {r2.text[:200]}"
        assert "sürüyor" in r2.json().get("detail", ""), r2.text[:300]
    finally:
        kapat(*a, tb, hb)


def test_KRITIK_D2E02_geri_yukleme_SURERKEN_disa_aktarma_409(tmp_path, monkeypatch):
    """Yarım içe aktarılmış durum "yedek" diye dışarı verilmez."""
    api, a, (tb, hb), paket, kaynak = _iki_cihaz(tmp_path, monkeypatch)
    try:
        durum, ikinci_bitti = _pencere(monkeypatch, tb)
        govde = {"passphrase": PAROLA, "blob_b64": paket["data_b64"], "confirm": "REPLACE_ALL"}
        r1, r2 = _eszamanli(api.app, govde, durum, ikinci_bitti, ikinci=("POST", "/api/data/export"))
        assert r1.status_code == 200, r1.text[:300]
        assert r2.status_code == 409, f"geri yükleme sürerken dışa aktarma {r2.status_code} döndü"
    finally:
        kapat(*a, tb, hb)


def test_KARSIT_D2E02_ARDISIK_ikinci_geri_yukleme_REPLACE_ile_calisir_kilit_BIRAKILIR(tmp_path, monkeypatch):
    api, a, (tb, hb), paket, kaynak = _iki_cihaz(tmp_path, monkeypatch)
    from veri_tasima_aparati import istekler

    try:
        govde = {"passphrase": PAROLA, "blob_b64": paket["data_b64"], "confirm": "REPLACE_ALL"}
        r1, r2 = istekler(
            api.app, [("POST", "/api/data/import", govde, None), ("POST", "/api/data/import", govde, None)]
        )
        assert r1.status_code == 200 and r2.status_code == 200, (r1.text[:200], r2.text[:200])
        assert sayimlar(tb, hb)["treatment_sessions"] == kaynak["treatment_sessions"]
        # hata yolunda da kilit bırakılır: yanlış parola → 400, ardından doğru istek yine kabul edilir
        (r3,) = istekler(api.app, [("POST", "/api/data/import", {**govde, "passphrase": "yanlis-parola-2026x"}, None)])
        assert r3.status_code == 400
        (r4,) = istekler(api.app, [("POST", "/api/data/import", govde, None)])
        assert r4.status_code == 200, f"hata yolundan sonra kilit BIRAKILMADI: {r4.status_code} {r4.text[:200]}"
    finally:
        kapat(*a, tb, hb)


@pytest.fixture(autouse=True)
def _kilit_sizmaz():
    """Bir testin istisnası kilidi tutarsa sonraki testler sahte 409 almasın (aparat güvenliği)."""
    yield
    from servers import api_server as api

    k = getattr(api, "_VERI_TASIMA_KILIDI", None)
    if k is not None and k.locked():
        k.release()
        pytest.fail("aparat: veri taşıma kilidi test sonunda TUTULU kaldı")
