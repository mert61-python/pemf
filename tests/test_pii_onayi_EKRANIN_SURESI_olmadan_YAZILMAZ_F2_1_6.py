# -*- coding: utf-8 -*-
"""F2-1.6 (2-F incelemesi · A1) · A-09 — PII maskeleme onayı, ekranın GÖSTERDİĞİ süre (`acknowledge_days`) gönderilmeden yazılmaz.

ÖLÇÜLEN KUSUR (`_inceleme\\K2\\sonda_k2_onay_ucu.py`, GERÇEK uç + GERÇEK headless tur): D2.55'in 409 koruması YALNIZ istemci
`acknowledge_days` gönderirse çalışıyor. (a) Ekran "1 seans, 365 gün" gösterdi; süre arada ortamla 30'a düştü; `{"acknowledge": true}`
(eski / başka istemci) → 200, onay `{'gun': 30, 'sayi': 3}`, sonraki tur 3 seansı maskeledi — operatörün GÖRMEDİĞİ kapsam. (b) Tek istekte
`{"days": 30, "acknowledge": true}` → 200, 30 günlük kapsamın sayısı hiçbir ekranda gösterilmeden onaylandı ve maskelendi.
A-09: "etkilenecek kayıt sayısı GÖSTERİLİR" — sunucu, onayın gösterilen süreye verildiğini istemcinin beyanı olmadan bilemez.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database import treatment_history_db as thm
    from servers import api_server as api
    from servers import system_router as sr

    for ad in ("PEMF_RETAIN_PII_DAYS", "PEMF_MASK_HISTORY_PII"):
        monkeypatch.delenv(ad, raising=False)
    db = thm.TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(sr, "_pii_ayar_db", lambda: db)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    with db._get_connection() as c:
        for g in (400, 100, 40):
            c.execute(
                "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode, patient_name, operator_name) "
                "VALUES (?,?,?,?,?)",
                ((datetime.now() - timedelta(days=g)).strftime("%Y-%m-%d"), "10:00", "Manuel", f"Hasta{g}", "Dr F216"),
            )
        c.commit()
    try:
        yield type("O", (), {"db": db, "c": TestClient(api.app, client=("127.0.0.1", 51216))})
    finally:
        db.close_connections()


def test_KRITIK_ekranin_suresi_GONDERILMEDEN_onay_YAZILMAZ(o, monkeypatch):
    """MUTASYON: `acknowledge_days` zorunluluğu kaldırılır → KIRMIZI."""
    assert o.c.get("/api/settings/retention").json()["pending"] == 1  # ekran: 1 seans, 365 gün
    monkeypatch.setenv("PEMF_RETAIN_PII_DAYS", "30")  # süre ekran açıkken değişti
    r = o.c.post("/api/settings/retention", json={"acknowledge": True})
    assert r.status_code == 409, f"ekranın süresi bilinmeden onay kabul edildi: {r.status_code} {o.db.pii_onayi_oku()}"
    assert o.db.pii_onayi_oku() is None


def test_KRITIK_sure_DEGISIKLIGI_ve_onay_AYNI_istekte_yazilmaz(o):
    """Yeni sürenin etkileyeceği kayıt sayısı hiçbir ekranda gösterilmeden onaylanamaz: önce süre, sonra (sayıyı gören) onay."""
    r = o.c.post("/api/settings/retention", json={"days": 30, "acknowledge": True, "acknowledge_days": 30})
    assert r.status_code == 409, (
        f"süre değişikliği + onay tek istekte kabul edildi: {r.status_code} {o.db.pii_onayi_oku()}"
    )
    assert o.db.pii_onayi_oku() is None
    assert o.db.pii_suresi_oku() is None, "409'da süre de yazılmamalı (hiçbir şey yazılmaz)"
    # ekran 365 gösterdi (acknowledge_days doğru) ama aynı istek süreyi 30'a çekiyor → 30 günün sayısı görülmedi
    r = o.c.post("/api/settings/retention", json={"days": 30, "acknowledge": True, "acknowledge_days": 365})
    assert r.status_code == 409 and o.db.pii_onayi_oku() is None, (
        f"görülmeyen yeni süre onaylandı: {o.db.pii_onayi_oku()}"
    )


def test_KARSIT_ekranin_gosterdigi_sureyle_onay_YAZILIR(o):
    assert o.c.post("/api/settings/retention", json={"days": 30}).status_code == 200
    g = o.c.get("/api/settings/retention").json()
    assert (g["days"], g["pending"]) == (30, 3), g
    r = o.c.post("/api/settings/retention", json={"acknowledge": True, "acknowledge_days": g["days"]})
    assert r.status_code == 200 and o.db.pii_onayi_var_mi(30), r.text
