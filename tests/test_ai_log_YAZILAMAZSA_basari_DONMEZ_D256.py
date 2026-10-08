# -*- coding: utf-8 -*-
"""D2.56 (B-3.86) — AI analizi geçmişe YAZILAMAZSA `/api/ai/log` "success" DÖNMEZ; hata kodu + eylem söyleyen gerekçe döner.

ÖLÇÜLEN KUSUR (DENETIM-03 B-3.86, K12 "başarısızlıkta başarı"): `add_ai_analysis` her hatayı (disk korkuluğu dahil) yutup
`None` döndürüyor, uç `{"status": "success", "id": None}` ile 200 veriyordu → hekimin analizi geçmişe hiç yazılmıyor, arayüz
sessiz; değerlendirme ve PDF üretilemiyor. Kayıt DB'si yoksa da 200 `{"status": "error"}` dönüyordu (istemci `ok` görür).
Kapı GERÇEK uçla (`POST /api/ai/log`), GERÇEK `TreatmentHistoryDB` ve GERÇEK disk korkuluğuyla (`_ensure_write_guardrail`;
yalnız disk durumu ÖLÇÜMÜ "kritik" verilir — fırlatan korkuluğun kendisi). Satır sayısı SQL ile.
Arayüz yarısı: `apps/ui/src/screens/__tests__/aiKaydiYazilamadi.D256.web.test.tsx` bu dosyanın ürettiği fikstürü okur
(`D256_FIKSTUR_YAZ=1` ile yenilenir; bayatlarsa tazelik kapısı KIRMIZI).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_KOK = Path(__file__).resolve().parents[1]
_FIKSTUR = _KOK / "apps" / "ui" / "src" / "screens" / "__tests__" / "__fixtures__" / "aiLogYazilamadi.D256.json"
GOVDE = {
    "mode": "veterinarian",
    "module_id": "disease",
    "module": "Hastalık Teşhisi",
    "patient_name": "Mia",
    "patient_id": "u-mia",
    "summary": "Gastroenteritis %71",
    "operator_email": "",
}


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    try:
        yield type(
            "O",
            (),
            {
                "db": db,
                "api": api,
                "yerel": TestClient(api.app, client=("127.0.0.1", 51234)),
                "lan": TestClient(api.app, client=("192.168.1.50", 51235)),
            },
        )
    finally:
        db.close_connections()


def _disk_kritik(o, monkeypatch):
    monkeypatch.setattr(
        type(o.db), "get_disk_space_status", lambda self: {"critical": True, "free_mb": 120, "threshold_mb": 500}
    )


def _satir(o) -> int:
    with o.db._get_connection() as c:
        return c.execute("SELECT COUNT(*) FROM ai_analyses").fetchone()[0]


def yazilamadi_yaniti(o, monkeypatch) -> dict:
    _disk_kritik(o, monkeypatch)
    r = o.yerel.post("/api/ai/log", json=GOVDE)
    return {"durum": r.status_code, "govde": r.json()}


def test_KRITIK_disk_korkulugu_yazimi_reddedince_BASARI_DONMEZ(o, monkeypatch):
    y = yazilamadi_yaniti(o, monkeypatch)
    assert _satir(o) == 0, "ön koşul: korkuluk yazımı reddetmeli"
    assert y["durum"] >= 400, f"yazılamayan AI kaydı için {y['durum']} {y['govde']} döndü (başarısızlıkta başarı)"
    assert y["govde"].get("status") != "success" and y["govde"].get("id") is None
    detay = str(y["govde"].get("detail") or "")
    assert "kaydedilemedi" in detay and "yeniden" in detay, f"gerekçe eylem söylemiyor: {detay!r}"


def test_KRITIK_DB_yazim_hatasi_da_BASARI_DONMEZ(o, monkeypatch):
    import sqlite3

    def _kilitli(self, *a, **k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(type(o.db), "_ensure_write_guardrail", _kilitli)
    r = o.yerel.post("/api/ai/log", json=GOVDE)
    assert r.status_code >= 400 and r.json().get("status") != "success", f"{r.status_code} {r.text[:200]}"


def test_KRITIK_beklenmeyen_hata_da_BASARI_ya_da_200_DONMEZ(o, monkeypatch):
    def _patla(_db):
        raise RuntimeError("beklenmeyen (test)")

    monkeypatch.setattr(o.api, "_migrate_ai_jsonl_once", _patla)
    r = o.yerel.post("/api/ai/log", json=GOVDE)
    assert r.status_code >= 400, f"beklenmeyen hatada {r.status_code} {r.text[:200]} (istemci ok görür)"
    assert _satir(o) == 0


def test_KRITIK_kayit_DB_yoksa_BASARI_DONMEZ(o, monkeypatch):
    monkeypatch.setattr(o.api, "_get_treatment_db", lambda: None)
    r = o.yerel.post("/api/ai/log", json=GOVDE)
    assert r.status_code >= 400, f"kayıt DB'si yokken {r.status_code} {r.text[:200]} (istemci ok görür)"


def test_KARSIT_normal_yazim_200_success_ve_SATIR_var(o):
    r = o.yerel.post("/api/ai/log", json=GOVDE)
    assert r.status_code == 200 and r.json().get("status") == "success" and isinstance(r.json().get("id"), int)
    assert _satir(o) == 1


def test_KARSIT_A01_LAN_istemcisi_normal_yazim_200(o):
    r = o.lan.post("/api/ai/log", json=GOVDE)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    assert _satir(o) == 1


def test_KRITIK_arayuz_fiksturu_GERCEK_backend_yanitiyla_AYNI(o, monkeypatch):
    beklenen = yazilamadi_yaniti(o, monkeypatch)
    if os.environ.get("D256_FIKSTUR_YAZ") == "1":
        _FIKSTUR.write_text(json.dumps(beklenen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert _FIKSTUR.exists(), "arayüz fikstürü yok (D256_FIKSTUR_YAZ=1 ile üret)"
    assert json.loads(_FIKSTUR.read_text(encoding="utf-8")) == beklenen, (
        "arayüz fikstürü backend'in GERÇEK /api/ai/log hata yanıtından BAYATLADI (D256_FIKSTUR_YAZ=1 ile yenile)"
    )
