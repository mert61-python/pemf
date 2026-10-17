# Author: mertaygn, cglrgrkn
"""SGI-1.1 (bağımsız inceleme) — CH3 ÷5 düzeltilmiş satır SÜRÜMLER ARASI taşımada ÇİFT bölünmemeli.

Ölçülen (549ce2b0): yeni sürüm cihazın dışa aktarımı ÷5'li değeri + işareti ('bolu5') + orijinali taşır. ESKİ sürüm cihaz (saha 1.9.50 —
CH3 öncesi kod) `import_rows` ile alırken hedef şemada olmayan sütunları ATAR → değer ÷5'li ama İŞARETSİZ yazılır; o cihaz yeni sürüme
yükseltilince açılış göçü işaretsiz satırı YENİDEN böler (13,3 → 2,66 → 0,532; ÷25) ve "orijinal" sütununa gerçek orijinal (13,3) değil
bir kez bölünmüş değer (2,66) yazılır — ekrandaki "özgün değer kayıtta saklıdır" notu yanlış olur.
Sözleşme: dışa aktarım ÷5'li satırı ÖZGÜN değer + boş işaretle verir (her sürüm onu "eski kayıt" diye alır; yeni sürüm içe aktarırken bir kez
böler, eski sürüm kendi eski verisiyle tutarlı saklar, yükseltmede bir kez bölünür). Yeni → yeni taşımada sonuç DEĞİŞMEZ (KARŞIT).
"Eski sürüm" taklidi CH'nin kendi kapısındaki yöntemdir (CH3 sütunları eklenmez, ÷5 göçü yok); eski `import_rows` ile tek fark sondaki göç
çağrısıdır (git diff f4f07422 549ce2b0 -- thdb_bakim.py).
"""

from __future__ import annotations

import json

import pytest

_YENI = ("alan_duzeltme", "magnetic_field_mt_orijinal", "field_avg_orijinal")


@pytest.fixture(autouse=True)
def _duz_ve_izole():
    import utils.secrets_manager as sm

    sm._cache = None
    yield
    sm._cache = None


def _eski_surum(monkeypatch):
    from database import thdb_sema
    from database.treatment_history_db import TreatmentHistoryDB

    orj = thdb_sema.SemaKarisimi._safe_add_column

    def _eski_sema(self, cursor, table, column_def, log_msg=None):
        if column_def.split()[0] in _YENI:
            return None
        return orj(self, cursor, table, column_def, log_msg)

    monkeypatch.setattr(thdb_sema.SemaKarisimi, "_safe_add_column", _eski_sema)
    monkeypatch.setattr(TreatmentHistoryDB, "_mt_bolu5_gocu", lambda self, zorla=False: 0)


def _eski_satirli_yeni_cihaz(kok, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    with monkeypatch.context() as m:
        _eski_surum(m)
        db = TreatmentHistoryDB(kok)
        sid = db.start_session("Manuel", patient_name="Eski")
        with db._get_connection() as c:
            c.execute(
                "INSERT INTO session_coil_runs (session_id, coil_id, started_epoch, ended_epoch, duration_seconds, frequency_hz,"
                " duty_percent, intensity_mt, hw_type, created_at) VALUES (?, 6, 1.0, 61.0, 60, 50, 40, 2.0, 'stm32', 1.0)",
                (sid,),
            )
            run_id = c.execute("SELECT max(id) FROM session_coil_runs").fetchone()[0]
            c.executemany(
                "INSERT INTO sensor_samples (session_id, coil_id, sample_ts, temperature_c, magnetic_field_mt, created_at,"
                " coil_run_id) VALUES (?, ?, ?, ?, ?, 1.0, ?)",
                [(sid, "6", 10.0, 30.0, 13.3, run_id), (sid, "6", 70.0, 31.0, 10.0, run_id)],
            )
            c.execute(
                "INSERT INTO sensor_run_summary (coil_run_id, sample_count, temp_avg, field_avg, created_at)"
                " VALUES (?, 2, 30.5, 11.65, 1.0)",
                (run_id,),
            )
            c.commit()
        db.close_connections()
    db = TreatmentHistoryDB(kok)  # yeni sürüm açılışı → ÷5 ('bolu5', orijinal saklı)
    return db


def _oku(db):
    with db._get_connection() as c:
        orn = [
            tuple(r)
            for r in c.execute(
                "SELECT magnetic_field_mt, magnetic_field_mt_orijinal, alan_duzeltme FROM sensor_samples"
                " WHERE magnetic_field_mt IS NOT NULL ORDER BY sample_ts"
            )
        ]
        oz = [
            tuple(r) for r in c.execute("SELECT field_avg, field_avg_orijinal, alan_duzeltme FROM sensor_run_summary")
        ]
    return orn, oz


@pytest.fixture
def duz(monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(TreatmentHistoryDB, "_import_sqlcipher", lambda self: None)


def test_KRITIK_yeni_surum_paketi_ESKI_surumden_gecip_YUKSELTILINCE_bir_kez_bolunur(tmp_path, monkeypatch, duz):
    from database.treatment_history_db import TreatmentHistoryDB

    a = _eski_satirli_yeni_cihaz(tmp_path / "A", monkeypatch)
    assert [r[0] for r in _oku(a)[0]] == [pytest.approx(2.66), pytest.approx(2.0)], "öncül: A'da göç olmadı"
    paket = json.loads(json.dumps(a.export_rows(), default=str))
    a.close_connections()

    with monkeypatch.context() as m:  # ESKİ sürüm cihaz paketi alır
        _eski_surum(m)
        b = TreatmentHistoryDB(tmp_path / "B")
        b.import_rows(paket, replace=False)
        b.close_connections()
    b = TreatmentHistoryDB(tmp_path / "B")  # aynı cihaz yeni sürüme yükseltilir
    orn, oz = _oku(b)
    assert [r[0] for r in orn] == [pytest.approx(2.66), pytest.approx(2.0)], (
        f"ÇİFT BÖLME: eski sürümden geçen ÷5'li değer yükseltmede yeniden bölündü {orn}"
    )
    assert [r[1] for r in orn] == [13.3, 10.0], f"'orijinal' gerçek orijinal değil: {orn}"
    assert oz == [(pytest.approx(2.33), 11.65, "bolu5")], oz


def test_KARSIT_yeni_surumden_yeni_surume_tasima_DEGISMEZ(tmp_path, monkeypatch, duz):
    from database.treatment_history_db import TreatmentHistoryDB

    a = _eski_satirli_yeni_cihaz(tmp_path / "A", monkeypatch)
    paket = json.loads(json.dumps(a.export_rows(), default=str))
    a.close_connections()
    d = TreatmentHistoryDB(tmp_path / "D")
    d.import_rows(paket, replace=False)
    orn, oz = _oku(d)
    assert orn == [(pytest.approx(2.66), 13.3, "bolu5"), (pytest.approx(2.0), 10.0, "bolu5")], orn
    assert oz == [(pytest.approx(2.33), 11.65, "bolu5")], oz
    # İkinci açılış da dokunmaz (bir kez).
    d.close_connections()
    assert _oku(TreatmentHistoryDB(tmp_path / "D")) == (orn, oz)
