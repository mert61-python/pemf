# Author: mertaygn, cglrgrkn
"""SGI-1.2 (bağımsız inceleme) — CH3'ün iki iddiası KAPISIZDI (mutantta yeşil kaldı):

1. "NULL 'ölçülmedi' satırına dokunulmaz, not uydurulmaz" — CH kapısı bunu yalnız DAKİKA ÖRNEĞİNDE sınıyordu. Koşu ÖZETİNİN ölçülen alanı
   NULL iken (`field_avg IS NOT NULL` koşulu silinince) özet 'bolu5' işaretlenir, `/details` "düzeltildi" notu ve Seans Detayı " *" basar —
   hiç ölçülmemiş alana "düzeltildi" der (mutant K1d: 16 / 16 yeşil).
2. "İçe aktarma sonrası göç düşerse ayar 'bekliyor'a çekilir → sonraki açılış yeniden dener" — `if zorla:` dalı silinince (mutant K1c)
   16 / 16 yeşil; o durumda ayar 'tamam' kalır, içe aktarılan eski (~5×) satırlar bir daha hiç düzeltilmez.
Gerçek TreatmentHistoryDB + gerçek SQLite dosyası; arıza EN ALT katta (göç deyimi gerçek `OperationalError` verir).
"""

from __future__ import annotations

import pytest

_YENI = ("alan_duzeltme", "magnetic_field_mt_orijinal", "field_avg_orijinal")


@pytest.fixture(autouse=True)
def _duz(monkeypatch):
    import utils.secrets_manager as sm
    from database.treatment_history_db import TreatmentHistoryDB

    sm._cache = None
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(TreatmentHistoryDB, "_import_sqlcipher", lambda self: None)
    yield
    sm._cache = None


def _eski_db(kok, monkeypatch, field_avg):
    from database import thdb_sema
    from database.treatment_history_db import TreatmentHistoryDB

    orj = thdb_sema.SemaKarisimi._safe_add_column

    def _eski_sema(self, cursor, table, column_def, log_msg=None):
        if column_def.split()[0] in _YENI:
            return None
        return orj(self, cursor, table, column_def, log_msg)

    with monkeypatch.context() as m:
        m.setattr(thdb_sema.SemaKarisimi, "_safe_add_column", _eski_sema)
        m.setattr(TreatmentHistoryDB, "_mt_bolu5_gocu", lambda self, zorla=False: 0)
        db = TreatmentHistoryDB(kok)
        sid = db.start_session("Manuel", patient_name="Eski")
        with db._get_connection() as c:
            c.execute(
                "INSERT INTO session_coil_runs (session_id, coil_id, started_epoch, ended_epoch, duration_seconds, created_at)"
                " VALUES (?, 1, 1.0, 61.0, 60, 1.0)",
                (sid,),
            )
            run_id = c.execute("SELECT max(id) FROM session_coil_runs").fetchone()[0]
            c.execute(
                "INSERT INTO sensor_run_summary (coil_run_id, sample_count, temp_avg, field_avg, created_at) VALUES (?, 2, 30.5, ?, 1.0)",
                (run_id, field_avg),
            )
            c.commit()
        db.close_connections()
    return sid, run_id


def test_KRITIK_olculmemis_NULL_kosu_ozeti_DUZELTILDI_isaretlenmez_not_uydurulmaz(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import history_router as h

    sid, run_id = _eski_db(tmp_path, monkeypatch, None)
    db = TreatmentHistoryDB(tmp_path)
    assert db._get_system_setting("mt_bolu5_goc") == "tamam", "öncül: göç koşmadı"
    with db._get_connection() as c:
        r = c.execute(
            "SELECT field_avg, alan_duzeltme FROM sensor_run_summary WHERE coil_run_id = ?", (run_id,)
        ).fetchone()
    assert r[0] is None and r[1] != "bolu5", f"ölçülmemiş (NULL) özet 'düzeltildi' işaretlendi: {tuple(r)}"
    d = h.get_session_full_details(sid, db=db)
    assert not d["coil_runs"][0]["summary"].get("alan_notu"), d["coil_runs"][0]["summary"]
    assert not d["session"].get("alan_notu"), d["session"]


def test_KRITIK_ice_aktarma_sonrasi_goc_DUSERSE_ayar_BEKLIYOR_sonraki_acilis_TAMAMLAR(tmp_path, monkeypatch):
    from database import thdb_telemetri
    from database.treatment_history_db import TreatmentHistoryDB

    db = TreatmentHistoryDB(tmp_path)
    assert db._get_system_setting("mt_bolu5_goc") == "tamam", "öncül: taze DB'de göç bayrağı yok"
    veri = {
        "treatment_sessions": [
            {"id": 1, "session_date": "2026-09-01", "start_time": "10:00", "treatment_mode": "Manuel"}
        ],
        "sensor_samples": [
            {"id": 1, "session_id": 1, "coil_id": "6", "sample_ts": 10.0, "magnetic_field_mt": 13.3, "created_at": 1.0},
        ],
    }
    orj = thdb_telemetri.MT_ORNEK_BOL_SQL
    monkeypatch.setattr(
        thdb_telemetri, "MT_ORNEK_BOL_SQL", "UPDATE yok_boyle_tablo SET x = 1"
    )  # gerçek OperationalError
    db.import_rows(veri, replace=False)
    with db._get_connection() as c:
        deger = c.execute("SELECT magnetic_field_mt, alan_duzeltme FROM sensor_samples").fetchone()
    assert tuple(deger) == (13.3, ""), f"düşen göç satır değiştirdi: {tuple(deger)}"
    assert db._get_system_setting("mt_bolu5_goc") == "bekliyor", (
        "içe aktarma sonrası göç düştü ama ayar 'tamam' kaldı — sonraki açılış eski satırları HİÇ düzeltmez"
    )
    db.close_connections()
    monkeypatch.setattr(thdb_telemetri, "MT_ORNEK_BOL_SQL", orj)
    db = TreatmentHistoryDB(tmp_path)
    with db._get_connection() as c:
        deger = c.execute(
            "SELECT magnetic_field_mt, magnetic_field_mt_orijinal, alan_duzeltme FROM sensor_samples"
        ).fetchone()
    assert tuple(deger) == (pytest.approx(2.66), 13.3, "bolu5"), tuple(deger)
