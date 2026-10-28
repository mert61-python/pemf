# -*- coding: utf-8 -*-
"""SON-A1.2 (22-SON A1a · C09 / D1S7 kapı gücü) — seans ayrıntısının inf temizleyicisi (`history_router._json_sonlu`) SONLU değerleri BİREBİR
bırakır.

ÖLÇÜLEN ZAYIFLIK (uç 8b002fc0): C09'un kapısı (`test_gecmis_detay_INF_kosu_satiri_500_vermez_D1S7.py`) "sonlu alanlar korunmalı" iddiasını
yalnız 1 ondalıklı (1.5) ve tam sayı (100 / 25) değerlerle ölçüyordu: temizleyiciye `round(x, 1)` koyan mutant kapıda YEŞİL kaldı. Seans
ayrıntısı hekimin gördüğü doz değerlerini (ayarlanan / ölçülen mT, frekans, duty, süre) taşır — temizleyici yalnız ±inf'i `null` yapmalı,
sonlu değere DOKUNMAMALI. Eski satır EN ALT katta (doğrudan SQL) kurulur; iç içe yapı (session + coil_runs) aynı yanıttan okunur.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

#: Kesirli, çok basamaklı sonlu değerler (yuvarlama / anlamlı basamak kısaltması / int'e çevirme bunları DEĞİŞTİRİR).
_FREKANS = 7.8312345678
_DUTY = 33.3333333333
_MT = 1.2345678901
_SURE = 59.987654321


@pytest.fixture
def ortam(temp_app_data, monkeypatch):
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb
    from servers import api_server, history_router

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    db = thdb.TreatmentHistoryDB(temp_app_data / "gecmis")
    api_server.app.dependency_overrides[history_router.get_db] = lambda: db
    try:
        yield db, TestClient(api_server.app, client=("127.0.0.1", 50000), raise_server_exceptions=False)
    finally:
        api_server.app.dependency_overrides.pop(history_router.get_db, None)
        db.close()


def _satirlar(db):
    sid = db.start_session(treatment_mode="Manuel", patient_name="SONLU-test")
    simdi = time.time()
    with db._get_connection() as c:
        # 1.9.50'nin inf satırı (temizleyici GERÇEKTEN koşsun) + kesirli sonlu değerli sağlam satır
        c.execute(
            "INSERT INTO session_coil_runs (session_id, coil_id, started_epoch, ended_epoch, duration_seconds, frequency_hz, "
            "duty_percent, phase, intensity_mt, hw_type, created_at) VALUES (?, 1, ?, ?, 60, ?, 10, 0, 1.5, 'stm32', ?)",
            (sid, simdi - 60, simdi, float("inf"), simdi),
        )
        c.execute(
            "INSERT INTO session_coil_runs (session_id, coil_id, started_epoch, ended_epoch, duration_seconds, frequency_hz, "
            "duty_percent, phase, intensity_mt, hw_type, created_at) VALUES (?, 2, ?, ?, ?, ?, ?, 0, ?, 'stm32', ?)",
            (sid, simdi - 60, simdi, _SURE, _FREKANS, _DUTY, _MT, simdi),
        )
        c.commit()
    return sid


def test_KRITIK_inf_temizleyici_SONLU_kesirli_degerleri_BIREBIR_birakir(ortam):
    db, istemci = ortam
    sid = _satirlar(db)
    r = istemci.get(f"/api/history/{sid}/details")
    assert r.status_code == 200, r.text[:200]
    kosular = {k["coil_id"]: k for k in r.json()["coil_runs"]}
    assert kosular[1]["frequency_hz"] is None, "aparat: inf satırı temizleyiciden geçmedi"
    k2 = kosular[2]
    olculen = {a: k2[a] for a in ("frequency_hz", "duty_percent", "intensity_mt", "duration_seconds")}
    beklenen = {"frequency_hz": _FREKANS, "duty_percent": _DUTY, "intensity_mt": _MT, "duration_seconds": _SURE}
    assert olculen == beklenen, (
        f"seans ayrıntısı SONLU doz değerlerini değiştirdi (yalnız ±inf null olmalı): {olculen} != {beklenen}"
    )
