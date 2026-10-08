# -*- coding: utf-8 -*-
"""C2-2.4 (2-C inceleme A2) — KÖR KAPI: kapanmış seansın durum mührü (Kesintiye Uğradı / İptal / Acil Durdurma / Donanım
Reddetti) açılış kurtarmasında "Elektrik Kesintisi" diye YENİDEN mühürlenmez — her sebep öneki için.

2-C (D2.E07/E06) kapıları kurtarmayı yalnız `ai-pro-durdurma` → `completed` kolunda ölçüyor; kurtarma sorgusunu
`session_status IN ('active', 'interrupted')` yapan mutant ilgili 11 dosyada (E06, E15/E07, model_muhru, çökme kurtarma, D179,
durum etiketi, D166/D178, başlatma iptal kolları, AI Pro hata sınıfları) **70/70 YEŞİL** kaldı (`_inceleme/kayit/k2_mutasyon.txt`) —
Y90'ın "Kesintiye Uğradı" satırı yeniden açılışta "Elektrik Kesintisi" olsa hiçbir kapı görmez.
Önek tablosu KAYNAKTAN (AST) türetilir — yeni bir önek eklenip burada kolu olmazsa kapı KIRMIZI (tablo/kapı birlikte).
GERÇEK: `_finalize_session_db` (sebep → durum), `recover_stale_active_sessions(max_age_hours=0)` (açılış), tedavi DB'si; SQL.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
if not (_KOK / "apps").is_dir():  # _inceleme/C2-2.x altında koşulursa
    _KOK = Path(__file__).resolve().parents[2]

# sebep (çağrı yerindeki biçim) → beklenen kalıcı durum
BEKLENEN = {
    "acil-durdurma:manual": "EMERGENCY_STOPPED",
    "donanim-reddi:hicbir-bobin-surulmedi": "HARDWARE_REJECTED",
    "iptal-ai-pro": "cancelled",
    "iptal:surus-oncesi-durdurma": "cancelled",
    "ai-pro-kesinti": "interrupted",
    "ai-devralma": "interrupted",
    "kapanis": "interrupted",
    "ai-pro-durdurma": "completed",
    "sure-doldu": "completed",
}


def _onekler():
    agac = ast.parse((_KOK / "apps/backend/servers/api_server.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef) and n.name == "_finalize_session_db")
    return sorted(
        {
            n.test.args[0].value
            for n in ast.walk(fn)
            if isinstance(n, ast.If)
            and isinstance(n.test, ast.Call)
            and getattr(n.test.func, "attr", "") == "startswith"
            and getattr(n.test.func.value, "id", "") == "_sebep"
        }
    )


def test_KRITIK_onek_tablosunun_HER_onekinin_kurtarma_kolu_VAR():
    onekler = _onekler()
    assert len(onekler) >= 6, f"araç: önek tablosu okunamadı ({onekler})"
    kolsuz = [o for o in onekler if not any(s.startswith(o) for s in BEKLENEN)]
    assert not kolsuz, f"kurtarma kolu OLMAYAN sebep öneki: {kolsuz} — BEKLENEN'e ekleyin"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(api, "_bekleyen_vacuumu_arka_planda", lambda: None)
    try:
        yield type("O", (), {"db": db, "api": api})
    finally:
        db.close_connections()


@pytest.mark.parametrize("sebep", sorted(BEKLENEN))
def test_KRITIK_kapanan_seans_ACILIS_KURTARMASINDA_yeniden_MUHURLENMEZ(o, sebep):
    sid = int(o.db.start_session(treatment_mode="Manuel", patient_name="Boncuk"))
    o.db.set_session_meta(sid, started_epoch=time.time() - 120)
    o.api._finalize_session_db(sid, time.time() - 120, reason=sebep, start_mono=time.monotonic() - 120)
    with o.db._get_connection() as c:
        once = c.execute("SELECT session_status FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()[0]
    assert once == BEKLENEN[sebep], f"ön koşul: '{sebep}' → {once} (beklenen {BEKLENEN[sebep]})"
    o.db.recover_stale_active_sessions(max_age_hours=0)  # yeniden açılış
    with o.db._get_connection() as c:
        sonra = c.execute("SELECT session_status FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()[0]
    assert sonra == once, f"'{sebep}' ile kapanan seans ({once}) açılış kurtarmasında '{sonra}' diye yeniden mühürlendi"


def test_KARSIT_kapanmamis_seans_kurtarmada_ELEKTRIK_KESINTISI_olur(o):
    sid = int(o.db.start_session(treatment_mode="Manuel", patient_name="Boncuk"))
    o.db.recover_stale_active_sessions(max_age_hours=0)
    with o.db._get_connection() as c:
        assert (
            c.execute("SELECT session_status FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()[0]
            == "ABORTED_DUE_TO_POWER"
        )
