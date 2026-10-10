# -*- coding: utf-8 -*-
"""F2-3.5 (2-F incelemesi A3, K2 · A-06 / Legal §6) — Ayarlar → Veri Saklama Süresi kartının metni DAVRANIŞI söyler: onay yokken hiçbir
seans kaydı maskelenmez. Kart eskiden onaysız durumda da "adlar 365 gün sonra kalıcı olarak maskelenir" diyordu (ölçüldü).

Bu dosya kapının PYTHON yarısıdır: (1) GERÇEK `/api/settings/retention` + GERÇEK headless bakım turu — onaysız tur maskelemez, ekranın
okuduğu yanıt `acknowledged: false`; (2) arayüz yarısının (`screens/__tests__/veriSaklamaMetni.F235.web.test.tsx`) okuduğu iki GERÇEK
yanıt fikstürü (yeni klinik · onaysız + 1 bekleyen) — bayatlarsa KIRMIZI; yenilemek: `F235_FIKSTUR_YAZ=1` (yalnız dosyanın tamamı
yeşilken kalıcı — S-A2.5). PatientDatabase + TreatmentHistoryDB tmp; uç TestClient (yerel istemci).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIKSTUR_DIZINI = Path(__file__).resolve().parents[1] / "apps" / "ui" / "src" / "screens" / "__tests__" / "__fixtures__"


@pytest.fixture
def o(tmp_path, monkeypatch):
    import database.patient_database as pdbm
    from database import treatment_history_db as thm
    from servers import api_server as api
    from servers import system_router as sr

    for ad in ("PEMF_RETAIN_PII_DAYS", "PEMF_MASK_HISTORY_PII"):
        monkeypatch.delenv(ad, raising=False)
    db = thm.TreatmentHistoryDB(tmp_path / "gecmis")
    pdb = pdbm.PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(api, "_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(sr, "_pii_ayar_db", lambda: db)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(pdbm, "get_patient_database", lambda *a, **k: pdb)
    try:
        yield type("O", (), {"db": db, "c": TestClient(api.app, client=("127.0.0.1", 51956))})
    finally:
        db.close_connections()


def _seans(db, ad, gun):
    sid = int(db.start_session(treatment_mode="Manuel", patient_name=ad, operator_name="Dr F235"))
    db.end_session(sid, duration_minutes=5)
    with db._get_connection() as c:
        c.execute(
            "UPDATE treatment_sessions SET session_date=date('now', ?), created_at=? WHERE id=?",
            (f"-{gun} days", time.time() - gun * 86400, sid),
        )
        c.commit()


def _adlar(db):
    with db._get_connection() as c:
        return [r[0] for r in c.execute("SELECT patient_name FROM treatment_sessions ORDER BY id")]


def _bakim_turu(db):
    from services.headless_db_maintenance import HeadlessDBMaintenance

    b = HeadlessDBMaintenance.__new__(HeadlessDBMaintenance)
    b.db = db
    b._run_maintenance()


def _fikstur(ad: str, beklenen: dict) -> None:
    f = FIKSTUR_DIZINI / ad
    if os.environ.get("F235_FIKSTUR_YAZ") == "1":
        f.write_text(json.dumps(beklenen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert f.exists(), f"arayüz fikstürü yok (F235_FIKSTUR_YAZ=1 ile üret): {ad}"
    assert json.loads(f.read_text(encoding="utf-8")) == beklenen, f"arayüz fikstürü GERÇEK yanıttan BAYATLADI: {ad}"


def test_KRITIK_onaysiz_bakim_turu_MASKELEMEZ_ve_ekran_onaysiz_durumu_GORUR(o):
    """Kartın 'onay verilmeden hiçbir seans kaydı maskelenmez' cümlesinin dayanağı. MUTASYON: onaysız maskeleme → KIRMIZI."""
    _seans(o.db, "Taze F235", 10)
    _seans(o.db, "Eski F235", 400)
    durum = o.c.get("/api/settings/retention").json()
    assert (durum["days"], durum["acknowledged"], durum["pending"]) == (365, False, 1), durum
    _bakim_turu(o.db)
    assert _adlar(o.db) == ["Taze F235", "Eski F235"], (
        "onay yokken bakım turu seans adını MASKELEDİ (kart 'maskelenmez' diyor)"
    )


def test_KRITIK_arayuz_fiksturleri_GERCEK_retention_yanitiyla_AYNI(o):
    _seans(o.db, "Taze F235", 10)
    r = o.c.get("/api/settings/retention")
    assert r.status_code == 200, r.text
    _fikstur("retentionYeniKlinik.F235.json", {"durum": r.status_code, "govde": r.json()})
    _seans(o.db, "Eski F235", 400)
    r2 = o.c.get("/api/settings/retention")
    assert r2.status_code == 200, r2.text
    _fikstur("retentionOnaysizBekleyen.F235.json", {"durum": r2.status_code, "govde": r2.json()})
