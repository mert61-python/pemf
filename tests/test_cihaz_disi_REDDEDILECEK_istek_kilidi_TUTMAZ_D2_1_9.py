# -*- coding: utf-8 -*-
"""D2-1.9 (2-D incelemesi, A1) — cihaz DIŞI (LAN) bir istemcinin REDDEDİLECEK geri yükleme isteği `_VERI_TASIMA_KILIDI`'ni tam DB okuması
boyunca tutar; cihazın KENDİ yedeği bu sırada yanlış metinli 409 alır.

ÖLÇÜLEN KUSUR (HEAD a76ee0d, `servers/api_server.py:6533-6620`): kilit `_enforce_privileged`'dan hemen sonra alınır; Y111 cihaz denetimi
ise paketin çözülmesinden, hedefin TÜM tedavi satırlarının (`export_rows`) ve hastalarının okunmasından SONRA gelir. LAN'daki eşleşmiş bir
istemcinin (telefon uygulaması) dolu cihaza gönderdiği ve zaten 403 alacak geri yükleme isteği bu süre boyunca kilidi tutar: 150 bin sensör
satırlı şifreli hedefte ~1 sn — cihazın kendi "Şifreli Yedek Oluştur"u 5/6 denemede 409 "Geri yükleme bu cihazda sürüyor — … İşlemi
tekrarlamayın ve uygulamayı yeniden başlatmayın" aldı [ÖLÇTÜM kayit/K5_sonda.txt k5a]. Cihazda geri yükleme YOK; metin yanlış, pencere
hedef DB boyuyla büyür (`export_rows` tüm satırları belleğe okur).
DÜZELTME: cihaz dışı istekte hedef doluluğu ÖNCE ucuz sorguyla (EXISTS) denetlenir; doluysa paket çözülmeden ve tam okuma yapılmadan 403.
Cihazın kendi geri yüklemesi ve BOŞ cihaza cihaz dışından ilk içe aktarma (Y111 karşıtı) DEĞİŞMEZ.
APARAT: gerçek DB'ler, gerçek paket, tek olay döngüsü. Pencere deterministik: hedefin `export_rows`u kilit TUTULURKEN çağrılırsa `serbest`e dek
bekler (yalnız içe aktarma yolundaki çağrı; dışa aktarma kilit tutulurken export_rows'a hiç girmez).
"""

from __future__ import annotations

import asyncio
import threading

import httpx
import pytest
from veri_tasima_aparati import PAROLA, cihaz_kur, disa_aktar, doldur, kapat, sayimlar, uclari_bagla

LAN = ("192.168.1.80", 52001)
CIHAZ = ("127.0.0.1", 50123)


@pytest.fixture
def kur(tmp_path, monkeypatch):
    from servers import api_server as api
    from servers import auth

    monkeypatch.setattr(auth, "check_token", lambda t: t == "CIHAZ-TOKEN")
    ta, ha = cihaz_kur(monkeypatch, tmp_path / "A")
    uclari_bagla(monkeypatch, ta, ha)
    doldur(ta, ha, ["Mia", "Pamuk"], seans_basi=2)
    paket = disa_aktar(api.app)
    tb, hb = cihaz_kur(monkeypatch, tmp_path / "B")
    uclari_bagla(monkeypatch, tb, hb)
    gercek = tb.export_rows
    durum = {"kilitliyken_okuma": 0}
    serbest = threading.Event()

    def _sarili():
        if api._VERI_TASIMA_KILIDI.locked():
            durum["kilitliyken_okuma"] += 1
            serbest.wait(10)
        return gercek()

    monkeypatch.setattr(tb, "export_rows", _sarili)
    try:
        yield api, paket, tb, hb, durum, serbest
    finally:
        serbest.set()
        kapat(ta, ha, tb, hb)


def _senaryo(api, paket, serbest, durum):
    async def _kos():
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=api.app, client=LAN), base_url="http://cihaz", timeout=60
            ) as lan,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=api.app, client=CIHAZ), base_url="http://cihaz", timeout=60
            ) as cihaz,
        ):
            g = asyncio.ensure_future(
                lan.post(
                    "/api/data/import",
                    json={"passphrase": PAROLA, "blob_b64": paket["data_b64"], "confirm": "REPLACE_ALL"},
                    headers={"X-API-Key": "CIHAZ-TOKEN"},
                )
            )
            for _ in range(300):  # LAN isteği ya kilit altında tam okumaya girdi ya da bitti
                if durum["kilitliyken_okuma"] or g.done():
                    break
                await asyncio.sleep(0.01)
            kendi = await cihaz.post("/api/data/export", json={"passphrase": PAROLA})
            serbest.set()
            return await g, kendi

    return asyncio.run(_kos())


def test_KRITIK_Y111_DOLU_cihaza_LAN_REPLACE_ALL_kilidi_TUTMAZ_cihazin_yedegi_409_ALMAZ(kur):
    api, paket, tb, hb, durum, serbest = kur
    doldur(tb, hb, ["Zeytin"], seans_basi=1)  # DOLU hedef
    once = sayimlar(tb, hb)
    r_lan, kendi = _senaryo(api, paket, serbest, durum)
    assert r_lan.status_code == 403, f"aparat/Y111: LAN isteği {r_lan.status_code} {r_lan.text[:160]}"
    assert kendi.status_code == 200, (
        f"cihaz dışından gelen ve REDDEDİLECEK geri yükleme isteği kilidi tutarken cihazın KENDİ yedeği {kendi.status_code} aldı: "
        f"{kendi.text[:160]} (kilit altında tam okuma: {durum['kilitliyken_okuma']})"
    )
    assert sayimlar(tb, hb) == once


def test_KARSIT_Y111_BOS_cihaza_LAN_ilk_ice_aktarma_BUGUNKU_gibi(kur):
    api, paket, tb, hb, durum, serbest = kur
    serbest.set()
    r_lan, _kendi = _senaryo(api, paket, serbest, durum)
    assert r_lan.status_code == 200 and r_lan.json()["counts"]["treatment_sessions"] == 4, (
        f"{r_lan.status_code} {r_lan.text[:200]}"
    )
