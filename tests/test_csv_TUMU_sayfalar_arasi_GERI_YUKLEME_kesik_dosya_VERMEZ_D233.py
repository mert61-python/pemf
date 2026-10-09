# -*- coding: utf-8 -*-
"""A3 · D2-3.3 — D2.16 sayfalaması (`93611a8`) "Tümünü" CSV'yi TEK anlık görüntüden değil SAYFA SAYFA okur; sayfalar arasında gerçek bir
REPLACE_ALL geri yükleme commit edilirse CSV ESKİ geçmişin yalnız ilk sayfasıyla (5000 / 10 001) 200 döner — işaretsiz kesik dosya
(B-3.24'ün kendi belirtisi). Kök neden: `treatment_sessions.id` AUTOINCREMENT → geri yüklenen satırların kimlikleri eskilerin hepsinden
büyük → `id < before_id` sayfası boş → döngü "son sayfa" sanıp biter. Eskiden (tek sorgu) dosya ya tümüyle eski ya tümüyle yeni idi.

ZİNCİR (gerçek): `/api/history/export_csv` (cihazın kendisi) ve `/api/data/import` (REPLACE_ALL, cihazın kendisi, operatörsüz klinik —
Kural 2) AYNI olay döngüsünde (httpx ASGITransport); gerçek TreatmentHistoryDB (10 001 seans) + gerçek dışa aktarma paketi. Belirlenimci
araya girme: CSV'nin 1. sayfası okununca (gerçek `get_session_history` döndükten sonra) CSV iş parçacığı geri yükleme bitene dek bekletilir.
Depo yeri: tests/test_csv_TUMU_sayfalar_arasi_GERI_YUKLEME_kesik_dosya_VERMEZ_D233.py
"""

from __future__ import annotations

import asyncio
import csv
import io
import threading

import httpx
from veri_tasima_aparati import PAROLA, cihaz_kur, disa_aktar, doldur, kapat, uclari_bagla

N = 10_001


def test_KRITIK_D233_TUMU_csv_sayfalar_arasinda_GERI_YUKLEME_olursa_KESIK_dosya_vermez(tmp_path, monkeypatch):
    from servers import api_server as api
    from servers import history_router as hr

    ta, ha = cihaz_kur(monkeypatch, tmp_path / "A")
    uclari_bagla(monkeypatch, ta, ha)
    doldur(ta, ha, ["Yedek1", "Yedek2", "Yedek3"], seans_basi=1, sensor=0, analiz=False)
    paket = disa_aktar(api.app)
    tb, hb = cihaz_kur(monkeypatch, tmp_path / "B")
    with tb._get_connection() as c:
        c.executemany(
            "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode, patient_name, session_status) "
            "VALUES (?, '10:00:00', 'Manuel', ?, 'completed')",
            [(f"2025-{1 + i % 12:02d}-{1 + i % 28:02d}", f"Hasta{i:05d}") for i in range(N)],
        )
        c.commit()
    uclari_bagla(monkeypatch, tb, hb)
    api.app.dependency_overrides[hr.get_db] = lambda: tb
    sayfa1, devam = threading.Event(), threading.Event()
    asil = tb.get_session_history

    def _sarmal(*a, **k):
        s = asil(*a, **k)
        if not sayfa1.is_set():
            sayfa1.set()
            devam.wait(60)
        return s

    monkeypatch.setattr(tb, "get_session_history", _sarmal)

    async def _kos():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api.app, client=("127.0.0.1", 50123)),
            base_url="http://cihaz",
            timeout=120,
        ) as c:
            csv_gorev = asyncio.ensure_future(c.get("/api/history/export_csv"))
            await asyncio.to_thread(sayfa1.wait, 60)
            try:
                ri = await c.post(
                    "/api/data/import",
                    json={"passphrase": PAROLA, "blob_b64": paket["data_b64"], "confirm": "REPLACE_ALL"},
                )
            finally:
                devam.set()
            return ri, await csv_gorev

    try:
        ri, rc = asyncio.run(_kos())
        assert sayfa1.is_set(), "aparat: CSV ilk sayfayı okumadı"
        assert ri.status_code == 200, f"aparat: geri yükleme {ri.status_code} {ri.text[:200]}"
        with tb._get_connection() as c:
            sonra = c.execute("SELECT count(*) FROM treatment_sessions").fetchone()[0]
        assert sonra == 3, f"aparat: geri yükleme sonrası {sonra} seans"
        if rc.status_code == 200:
            satirlar = list(csv.reader(io.StringIO(rc.content.decode("utf-8-sig"))))[1:]
            eski = sum(1 for s in satirlar if s[1].startswith("Hasta"))
            yeni = sum(1 for s in satirlar if s[1].startswith("Yedek"))
            assert (eski, yeni) in ((N, 0), (0, 3)), (
                f"'Tümünü' CSV 200 ama TUTARSIZ: {eski} eski + {yeni} yeni satır (geri yükleme öncesi {N}, sonrası 3) — "
                "sayfalar arasında geri yükleme oldu, dosya işaretsiz KESİK"
            )
        else:
            assert rc.status_code == 409, f"CSV {rc.status_code} {rc.text[:200]}"
            assert "geri yükleme" in rc.text.lower(), rc.text[:300]
        # KARŞIT (aynı kurulum): geri yükleme BİTTİKTEN sonra yeni "Tümünü" CSV'si engellenmez ve yeni durumu eksiksiz verir.
        from fastapi.testclient import TestClient

        r2 = TestClient(api.app, client=("127.0.0.1", 53219)).get("/api/history/export_csv")
        assert r2.status_code == 200, f"geri yükleme bittikten sonra CSV {r2.status_code} {r2.text[:200]}"
        adlar2 = [s[1] for s in list(csv.reader(io.StringIO(r2.content.decode("utf-8-sig"))))[1:]]
        assert sorted(adlar2) == ["Yedek1", "Yedek2", "Yedek3"], adlar2[:5]
    finally:
        api.app.dependency_overrides.pop(hr.get_db, None)
        kapat(ta, ha, tb, hb)


def test_KARSIT_D233_geri_yukleme_yokken_TUMU_csv_eksiksiz(tmp_path, monkeypatch):
    from servers import api_server as api
    from servers import history_router as hr

    tb, hb = cihaz_kur(monkeypatch, tmp_path / "B")
    with tb._get_connection() as c:
        c.executemany(
            "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode, patient_name, session_status) "
            "VALUES ('2025-01-01', '10:00:00', 'Manuel', ?, 'completed')",
            [(f"Hasta{i:05d}",) for i in range(N)],
        )
        c.commit()
    api.app.dependency_overrides[hr.get_db] = lambda: tb
    try:
        from fastapi.testclient import TestClient

        r = TestClient(api.app, client=("127.0.0.1", 53218)).get("/api/history/export_csv")
        assert r.status_code == 200
        assert len(list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))[1:]) == N
    finally:
        api.app.dependency_overrides.pop(hr.get_db, None)
        kapat(tb, hb)
