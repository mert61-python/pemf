# -*- coding: utf-8 -*-
"""B2-1.8 (2-B incelemesi · A1 · KÖR KAPI) — D2.17: silme özeti okunamazsa silme KISITLANMAZ ve iz `ozet_okunamadi: true` der.

ÖLÇÜLEN KÖR NOKTA: 2-B raporu (D2.17) "özet okunamazsa silme KISITLANMAZ, iz `ozet_okunamadi: true` der" diyor; bu dal HİÇBİR
testte koşmuyor (`grep ozet_okunamadi tests/` → 0). Mutant f4 (özet hatasında silme 500'e döner) ve f5 (iz bayraksız `{}`)
D2.17 + D2.43 + sessiz-yutma kümesinde 31/31 YEŞİL kaldı. Ürün HEAD'de doğru (bu kollar HEAD'de yeşil); kapı mutantta kırmızı.
Arıza: özet okuyucusu gerçek SQLite istisnasını atar (seans_silme_ozeti → sqlite3.OperationalError).
Önerilen yer: tests/test_seans_silme_OZET_OKUNAMAZSA_silinir_iz_soyler_B2_1_8.py
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens
    from servers.history_router import get_db

    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    api.app.dependency_overrides[get_db] = lambda: tdb
    operator_tokens.temizle_hepsi()
    try:
        yield type("O", (), {"tdb": tdb, "c": TestClient(api.app, client=("127.0.0.1", 51834))})
    finally:
        api.app.dependency_overrides.pop(get_db, None)
        tdb.close_connections()


@pytest.mark.parametrize("uc", ["POST /delete", "DELETE /{id}"])
def test_KRITIK_ozet_okunamazsa_seans_YINE_silinir_ve_iz_SOYLER(o, monkeypatch, uc):
    sid = int(o.tdb.start_session(treatment_mode="Manuel", patient_name="Boncuk", operator_email="tek@klinik.com"))

    def _bozuk(_sid):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(o.tdb, "seans_silme_ozeti", _bozuk)
    if uc == "POST /delete":
        r = o.c.post("/api/history/delete", json={"session_id": sid})
    else:
        r = o.c.delete(f"/api/history/{sid}")
    with o.tdb._get_connection() as c:
        kalan = c.execute("SELECT COUNT(*) FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]
    assert (r.status_code, kalan) == (200, 0), f"özet okunamadı diye silme kısıtlandı: {r.status_code} {r.text[:120]}"
    iz = [json.loads(s["detail"] or "{}") for s in o.tdb.denetim_oku(5, "history.delete")]
    assert iz and iz[0].get("ozet_okunamadi") is True, iz
