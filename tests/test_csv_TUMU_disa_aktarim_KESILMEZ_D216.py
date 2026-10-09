# -*- coding: utf-8 -*-
"""D2.16 (B-3.24) — "Tümünü dışa aktar" CSV'si 10.000 seans sınırında SESSİZCE kesilmez.

ÖLÇÜLEN KUSUR (DENETIM-03 B-3.24, 2-D'de yeniden ölçüldü): `/api/history/export_csv` geçmişi `limit=10000` ile tek sorguda çekiyordu;
yoğun bir klinikte (~1,4 yıl) tam geçmiş CSV'sinde EN ESKİ tıbbi kayıtlar eksik çıkıyor ve bunu gösteren hiçbir işaret yoktu.
DÜZELTME: dışa aktarma geçmişi anahtar kümesi (keyset, `before_id`) sayfalarıyla sonuna kadar okur — sınır yok.
APARAT: gerçek `TreatmentHistoryDB` (10.001 seans, ürünün kendi tablosuna toplu SQL), gerçek uç (TestClient, cihazın kendisi).
"""

from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient

N = 10_001


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database import sqlcipher_util as su
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import history_router as hr

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    with tdb._get_connection() as c:
        c.executemany(
            "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode, patient_name, session_status) "
            "VALUES (?, ?, 'Manuel', ?, 'completed')",
            [(f"2025-{1 + i % 12:02d}-{1 + i % 28:02d}", "10:00:00", f"Hasta{i:05d}") for i in range(N)],
        )
        c.commit()
    api.app.dependency_overrides[hr.get_db] = lambda: tdb
    try:
        yield type("O", (), {"tdb": tdb, "c": TestClient(api.app, client=("127.0.0.1", 53216))})
    finally:
        api.app.dependency_overrides.pop(hr.get_db, None)
        tdb.close()


def _satirlar(r) -> list:
    assert r.status_code == 200, r.text[:200]
    metin = r.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(metin)))[1:]


def test_KRITIK_D216_TUMU_csv_10001_seansin_HEPSINI_icerir_en_eski_kayit_DUSMEZ(o):
    satirlar = _satirlar(o.c.get("/api/history/export_csv"))
    assert len(satirlar) == N, (
        f"'Tümünü dışa aktar' CSV'si {len(satirlar)} satır — {N} seans var; en eski {N - len(satirlar)} tıbbi kayıt SESSİZCE düştü"
    )
    adlar = {s[1] for s in satirlar}
    assert "Hasta00000" in adlar, "EN ESKİ seans CSV'de yok"


def test_KARSIT_D216_kimlik_listesiyle_yalniz_O_seanslar(o):
    with o.tdb._get_connection() as c:
        ilk = [r[0] for r in c.execute("SELECT id FROM treatment_sessions ORDER BY id LIMIT 3")]
    satirlar = _satirlar(o.c.get("/api/history/export_csv", params={"session_ids": ",".join(map(str, ilk))}))
    assert sorted(int(s[0]) for s in satirlar) == sorted(ilk)
