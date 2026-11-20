# -*- coding: utf-8 -*-
"""Y306 (sahip 19-11, madde 6): MLX bir bobinin değil KABİNİN sensörü — PDF / CSV ve bildirimlerde de "Kabin sensörü (MLX)" adıyla, bobin
satırlarından AYRI. Kanal → sensör eşlemesi TEK sabit (`utils.kabin_sensoru.MLX_KANALI`, bugün 6); eski kayıtlar da yeni adla (veri
göçü YOK — DB'de `coil_id` 6 kalır; JSON uçları AYNEN).
GERÇEK: şifreli tedavi DB'si (geçici kök) + `export_coil_runs_csv` + katalog (TR + EN)."""

from __future__ import annotations

import csv
import io

import pytest


def test_tek_sabit_ve_kanal_denetimi():
    from utils import kabin_sensoru as ks

    assert ks.MLX_KANALI == 6
    assert all(ks.kabin_sensoru_kanali_mi(v) for v in (6, "6", 6.0, " 6 "))
    assert not any(ks.kabin_sensoru_kanali_mi(v) for v in (7, "7", None, "", "x", [6]))


@pytest.fixture
def db(tmp_path, monkeypatch):
    """CH3 düzeneği (düz kip): geçici veri kökünde gerçek şema."""
    import utils.secrets_manager as sm
    from database.treatment_history_db import TreatmentHistoryDB

    sm._cache = None
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(TreatmentHistoryDB, "_import_sqlcipher", lambda self: None)
    d = TreatmentHistoryDB(tmp_path / "veri")
    yield d
    d.close_connections()
    sm._cache = None


def _seans(db) -> int:
    with db._get_connection() as c:
        cur = c.execute(
            "INSERT INTO treatment_sessions (session_date, start_time, session_status, treatment_mode) VALUES "
            "('2026-11-19', '18:07:00', 'stopped', 'AI Pro')"
        )
        c.commit()
        return int(cur.lastrowid)


def _kosu(db, sid, bobin, alan, sure):
    rid = db.start_coil_run(sid, bobin, started_epoch=1000.0, frequency_hz=100, duty_percent=30, phase=0, hw_type="STM")
    db.end_coil_run(rid, 1000.0 + sure)
    db.add_sensor_run_summary(rid, sample_count=3, field_avg=alan)
    return rid


@pytest.mark.parametrize("dil,ad", [("tr", "Kabin sensörü (MLX)"), ("en", "Cabin sensor (MLX)")])
def test_KRITIK_CSV_kanal_6_alani_bobin_satirinda_BOS_AYRI_kabin_satirinda(db, dil, ad):
    from servers import history_router as h
    from utils import ceviri

    sid = _seans(db)
    _kosu(db, sid, 1, 0.8, 60)
    _kosu(db, sid, 6, 1.2, 60)
    _kosu(db, sid, 6, 1.5, 120)
    jeton = ceviri.istek_dili_var.set(dil)
    try:
        satirlar = list(csv.reader(io.StringIO(h.export_coil_runs_csv(sid, db=db).body.decode("utf-8-sig"))))
    finally:
        ceviri.istek_dili_var.reset(jeton)
    baslik, veri = satirlar[0], satirlar[1:]
    i_alan = len(baslik) - 3
    assert len(baslik) == 15 and all(len(s) == 15 for s in veri), (baslik, veri)
    bobin = {s[0]: s for s in veri if s[0] in ("1", "6")}
    assert float(next(s for s in veri if s[0] == "1")[i_alan]) == pytest.approx(0.8)  # başka bobin AYNEN
    assert [s[i_alan] for s in veri if s[0] == "6"] == ["", ""], "kabin alanı bobin 6 satırında kaldı"
    kabin = [s for s in veri if s[0] == ad]
    assert len(kabin) == 1 and float(kabin[0][i_alan]) == pytest.approx((1.2 * 60 + 1.5 * 120) / 180), kabin
    assert kabin[0][i_alan + 1] == "6" and set(kabin[0][1:i_alan]) == {""}
    assert bobin


def test_KARSIT_kabin_kanalinda_alan_YOKSA_kabin_satiri_YOK(db):
    from servers import history_router as h

    sid = _seans(db)
    _kosu(db, sid, 1, 0.8, 60)
    _kosu(db, sid, 6, None, 60)
    veri = list(csv.reader(io.StringIO(h.export_coil_runs_csv(sid, db=db).body.decode("utf-8-sig"))))[1:]
    assert len(veri) == 2 and {s[0] for s in veri} == {"1", "6"}


@pytest.mark.parametrize(
    "dil,beklenen",
    [
        ("tr", ["Kabin sensörü (MLX, kartta kanal 6)", "Kabin sensörünün (MLX, kartta kanal 6)"]),
        ("en", ["cabin sensor (MLX, board channel 6)", "cabin sensor (MLX, board channel 6)"]),
    ],
)
def test_KRITIK_bildirimler_KABIN_sensoru_der_bobin_DEMEZ(dil, beklenen):
    from utils import ceviri

    m = [ceviri.t(f"bildirim.{k}", dil=dil, coil=6) for k in ("alanDogrulanamadi", "alanDoygun")]
    for metin, parca in zip(m, beklenen):
        assert parca in metin and "Bobin 6" not in metin and "coil 6" not in metin, metin
