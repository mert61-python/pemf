# -*- coding: utf-8 -*-
"""2-E incelemesi A-8 + A-9 (S-E2I.10) — sağlık ucu ve `recovery-status` tedavi DB'si G/Ç'sini olay döngüsünde YAPMAZ (Ö.4-Y8).

ÖLÇÜLEN KUSUR: `GET /api/health` (auth-muaf, arayüz ve launcher sık yoklar) `get_treatment_db(_app_data_dir())` (ilk çağrıda DB kurulumu:
`mkdir` + `sqlite3.connect` + şema) ve `_kayit_db_hazir()`ı, `GET /api/system/recovery-status` tedavi DB'si okumasını ve kod dosyası izini
OLAY DÖNGÜSÜNDE yapıyordu. Veri kökü asılı bir ağ sürücüsündeyse (ya da SQLite dosya açılışı takılırsa) döngü donar, ACİL DURDUR bekler.
Düzeltme: sağlık DB durumu C02 / E2-3.10 kalıbı — TEK-UÇUŞLU daemon iş parçacığı + `shield(wrap_future)` + süre sınırı (ortak havuzu
TÜKETMEZ: N eşzamanlı yoklama tek sorgu); süre dolarsa son tamamlanan sonuç, yoksa dürüst "yanıt vermiyor". `recovery-status` `to_thread`.
ÖLÇÜM: tek PAYLAŞILAN olay döngüsü (httpx ASGITransport), GERÇEK `HardwareController`; arıza EN ALT katta: test kökündeki dosyalar için
`sqlite3.connect` 3 sn takılıp G/Ç hatası verir (asılı ağ sürücüsü benzetimi; WAL'da kilitçi EXCLUSIVE alamadığından kilit yerine bu kat).
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time

import ai_pro_aparati as ap
import pytest

ASILI_SN = 4.0  # sağlık süre sınırının (2,5 sn) üstünde


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _asili_kok(o, monkeypatch, tmp_path):
    """Veri kökü `tmp/asili`: oradaki her `sqlite3.connect` ASILI_SN takılır ve G/Ç hatası verir (öteki DB'ler — ACİL DURDUR yolu dahil —
    gerçek bağlantıyla sürer). Dönen sayaç takılan çağrıları sayar."""
    kok = tmp_path / "asili"
    kok.mkdir()
    orj = sqlite3.connect
    sayac = {"n": 0, "bitti": threading.Event()}

    def _connect(yol, *a, **k):
        if str(yol).startswith(str(kok)):
            sayac["n"] += 1
            time.sleep(ASILI_SN)
            sayac["bitti"].set()
            raise sqlite3.OperationalError("disk I/O error (asili ag surucusu — aparat)")
        return orj(yol, *a, **k)

    monkeypatch.setattr(sqlite3, "connect", _connect)
    monkeypatch.setattr(o.api, "_app_data_dir", lambda: kok)
    return sayac


def _istemci(o):
    import httpx

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=o.api.app, client=("127.0.0.1", 50177)), base_url="http://cihaz", timeout=30
    )


def test_KRITIK_saglik_ve_recovery_yoklamalari_ASILI_DBde_beklerken_ACIL_DURDUR_gecikmez(o, monkeypatch, tmp_path):
    """MUTASYON: sağlık DB durumu yeniden satır içi → KIRMIZI; recovery-status satır içi → KIRMIZI."""
    sayac = _asili_kok(o, monkeypatch, tmp_path)

    async def _s():
        async with _istemci(o) as c:
            cagri = o.hc.stop_all_cagri
            t0 = time.monotonic()  # ⚠️ istekler kuyruğa girmeden ÖNCE (Ö.4-Y8 kapısının dersi)
            yoklamalar = [asyncio.create_task(c.get("/api/health")) for _ in range(10)]
            yoklamalar += [asyncio.create_task(c.get("/api/system/recovery-status")) for _ in range(3)]
            acil = asyncio.create_task(c.post("/api/hardware/emergency_stop"))
            r = await acil
            sure = time.monotonic() - t0
            stop = o.hc.stop_all_cagri - cagri
            for t in yoklamalar:
                await t
            return r, sure, stop

    r, sure, stop = asyncio.run(_s())
    sayac["bitti"].wait(ASILI_SN + 2)
    assert sayac["n"] >= 1, "aparat: asılı bağlantı hiç denenmedi (uç DB'ye dokunmadı mı?)"
    assert r.status_code == 200 and stop >= 1, f"ACİL DURDUR çalışmadı: {r.status_code} stop={stop}"
    assert sure < 1.0, (
        f"sağlık / recovery-status yoklamaları asılı DB'de beklerken ACİL DURDUR {sure:.2f} sn bekledi (Ö.4-Y8)"
    )


def test_KRITIK_saglik_ASILI_DBde_SURE_SINIRLI_ve_TEK_UCUS(o, monkeypatch, tmp_path):
    """10 eşzamanlı sağlık yoklaması: her biri süre sınırında döner (asılı sorgunun 4 sn'sini beklemez) ve asılı sorgu TEK kez başlar
    (ortak havuz tükenmez). Durum dürüst: dbReady BİLİNMİYOR (null) + neden — `false` DEĞİL: launcher güncelleme sonrası tek istekte
    `dbReady == false` görürse güncellemeyi GERİ ALIR (yavaş ama sağlam açılış yanlışlıkla geri alınırdı); null = bilinmiyor → normal onay.
    MUTASYON: tek-uçuş yok → KIRMIZI; süre dolunca `false` / `true` → KIRMIZI."""
    from servers import system_router as sr

    sayac = _asili_kok(o, monkeypatch, tmp_path)
    # ⚠️ Ölçüt SORGU sayısı (her sorgu kendi iş parçacığında): `connect` sayacı kör kalıyordu — `get_treatment_db`'nin kayıt kilidi
    # sorguları sıraya sokar, ölçüm anında yalnız ilki `connect`e ulaşmıştır (tek-uçuşsuz mutant YEŞİL kaldı — ölçüldü).
    orj = sr._saglik_db_durumu
    sorgu = {"n": 0}

    def _say(_api):
        sorgu["n"] += 1
        return orj(_api)

    monkeypatch.setattr(sr, "_saglik_db_durumu", _say)

    async def _s():
        async with _istemci(o) as c:
            t0 = time.monotonic()
            yanitlar = await asyncio.gather(*[c.get("/api/health") for _ in range(10)])
            return yanitlar, time.monotonic() - t0

    yanitlar, sure = asyncio.run(_s())
    sayac["bitti"].wait(ASILI_SN + 2)
    assert all(y.status_code == 200 for y in yanitlar)
    assert sure < ASILI_SN - 0.5, f"sağlık yoklaması asılı DB sorgusunu bekledi ({sure:.2f} sn)"
    assert sorgu["n"] == 1, (
        f"asılı DB sağlık sorgusu {sorgu['n']} kez başladı — tek-uçuş yok (iş parçacığı / havuz tükenir)"
    )
    g = yanitlar[0].json()
    assert g["dbReady"] is None and "yanıt vermiyor" in (g["dbSebep"] or ""), (
        f"asılı DB'de sağlık 'bilinmiyor' (null + neden) demiyor: {g.get('dbReady')!r} {g.get('dbSebep')!r}"
    )


def test_KARSIT_saglikli_DBde_saglik_GERCEK_durumu_soyler(o):
    async def _s():
        async with _istemci(o) as c:
            return await c.get("/api/health")

    g = asyncio.run(_s()).json()
    assert g["dbReady"] is True and isinstance(g["atRestEncrypted"], bool), g
