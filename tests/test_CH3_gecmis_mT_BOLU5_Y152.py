# Author: mertaygn, cglrgrkn
"""CH3 · Y152 (sahip, 2026-10-15) — GEÇMİŞ SEANSLARDAKİ ÖLÇÜLEN mT DEĞERLERİ 5'E BÖLÜNÜR.

TEZGÂH (Oturum 13, TD2): eski firmware MLX90393 kazanç ayarını doğrulamadan yazıyordu; sensör varsayılanında kaldı → ölçülen alan TAM
5,00× büyük (Dünya alanı sınaması 4–5×). TD2 (`e77537fc`) yeni firmware'le yalnız GERİ OKUNARAK doğrulanmış (`GS=`) alanı kabul eder;
işaretsiz eski `B=` atılır → TD2 SONRASI yazılan her ölçülen alan doğru ölçekte.
ÖLÇÜLEN DURUM (taban `cc76f758`): ölçülen alan tedavi DB'sinde iki yerde — `sensor_samples.magnetic_field_mt` (dakika ortalaması) ve
`sensor_run_summary.field_avg` (bobin koşusu özeti). Satırda "doğrulanmış mı" bilgisi YOK; düzeltme / orijinal / not YOK.
SÖZLEŞME (Y152): göç YALNIZ eski kayıtlara (işaret `alan_duzeltme = ''`), BİR KEZ (idempotent; ikinci açılış yeniden bölmez), ORİJİNAL
`*_orijinal` sütununda SAKLANIR (geri alınabilir), düzeltilen satır `alan_duzeltme = 'bolu5'`; yeni yazım `'yok'` taşır ve hiçbir zaman
bölünmez; göç tek işlemde (yarıda kalırsa hiçbir satır değişmez, DB yine açılır, sonraki açılış tamamlar); şifreli ve düz-metin DB'de aynı.
Gösterim: seans ayrıntısı + `coil_runs.csv` "düzeltildi (÷5, yaklaşık — tezgâhta 4–5× ölçüldü)" notu taşır.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

NOT_METNI = "düzeltildi (÷5, yaklaşık — tezgâhta 4–5× ölçüldü)"
_YENI_SUTUNLAR = ("alan_duzeltme", "magnetic_field_mt_orijinal", "field_avg_orijinal")


@pytest.fixture(autouse=True)
def _sir_onbellegini_izole_et():
    import utils.secrets_manager as sm

    sm._cache = None
    yield
    sm._cache = None


@pytest.fixture(params=["duz", "sifreli"])
def kip(request, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    if request.param == "duz":
        monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
        monkeypatch.setattr(TreatmentHistoryDB, "_import_sqlcipher", lambda self: None)
    else:
        pytest.importorskip("sqlcipher3", reason="şifreli kol sqlcipher3 ister")
        monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    return request.param


def _eski_db_kur(app_data, monkeypatch):
    """CH3 ÖNCESİ kod: CH3 sütunları YOK, göç YOK; satırlar eski kodun INSERT'iyle (işaretsiz) yazılır."""
    from database import thdb_sema
    from database.treatment_history_db import TreatmentHistoryDB

    orj = thdb_sema.SemaKarisimi._safe_add_column

    def _eski_sema(self, cursor, table, column_def, log_msg=None):
        if column_def.split()[0] in _YENI_SUTUNLAR:
            return None
        return orj(self, cursor, table, column_def, log_msg)

    with monkeypatch.context() as m:
        m.setattr(thdb_sema.SemaKarisimi, "_safe_add_column", _eski_sema)
        m.setattr(TreatmentHistoryDB, "_mt_bolu5_gocu", lambda self: None, raising=False)
        db = TreatmentHistoryDB(app_data)
        sid = db.start_session("Manuel", patient_name="Eski")
        with db._get_connection() as c:
            kolonlar = {r[1] for r in c.execute("PRAGMA table_info(sensor_samples)")}
            assert not (set(_YENI_SUTUNLAR) & kolonlar), f"öncül: eski şema kurulamadı {kolonlar}"
            c.execute(
                "INSERT INTO session_coil_runs (session_id, coil_id, started_epoch, ended_epoch, duration_seconds, frequency_hz,"
                " duty_percent, intensity_mt, hw_type, created_at) VALUES (?, 6, 1.0, 61.0, 60, 50, 40, 2.0, 'stm32', 1.0)",
                (sid,),
            )
            run_id = c.execute("SELECT max(id) FROM session_coil_runs").fetchone()[0]
            c.executemany(
                "INSERT INTO sensor_samples (session_id, coil_id, sample_ts, temperature_c, magnetic_field_mt, created_at,"
                " coil_run_id) VALUES (?, ?, ?, ?, ?, 1.0, ?)",
                [
                    (sid, "6", 10.0, 30.0, 13.3, run_id),
                    (sid, "6", 70.0, 31.0, 10.0, run_id),
                    (sid, "1", 70.0, None, None, run_id),
                ],
            )
            c.execute(
                "INSERT INTO sensor_run_summary (coil_run_id, sample_count, temp_avg, field_avg, created_at) VALUES (?, 2, 30.5, 11.65, 1.0)",
                (run_id,),
            )
            c.commit()
        db.close_connections()
    return sid, run_id


def _ac(app_data):
    from database.treatment_history_db import TreatmentHistoryDB

    return TreatmentHistoryDB(app_data)


def _satirlar(db, sid):
    with db._get_connection() as c:
        orn = c.execute(
            "SELECT magnetic_field_mt, magnetic_field_mt_orijinal, alan_duzeltme, temperature_c FROM sensor_samples"
            " WHERE session_id = ? ORDER BY sample_ts, coil_id DESC",
            (sid,),
        ).fetchall()
        oz = c.execute(
            "SELECT field_avg, field_avg_orijinal, alan_duzeltme, temp_avg FROM sensor_run_summary s"
            " JOIN session_coil_runs r ON r.id = s.coil_run_id WHERE r.session_id = ?",
            (sid,),
        ).fetchall()
    return [tuple(r) for r in orn], [tuple(r) for r in oz]


def test_KRITIK_eski_DB_gocu_BOLU5_orijinal_SAKLI_isaretli(temp_app_data, monkeypatch, kip):
    sid, _run = _eski_db_kur(temp_app_data, monkeypatch)
    db = _ac(temp_app_data)
    orn, oz = _satirlar(db, sid)
    assert orn[0][:3] == (pytest.approx(2.66), 13.3, "bolu5") and orn[0][3] == 30.0, orn
    assert orn[1][:3] == (pytest.approx(2.0), 10.0, "bolu5"), orn
    # Ölçülmemiş (NULL) alan BÖLÜNMEZ ve "düzeltildi" sayılmaz (not uydurulmaz).
    assert orn[2][0] is None and orn[2][1] is None and orn[2][2] != "bolu5", orn
    assert oz == [(pytest.approx(2.33), 11.65, "bolu5", 30.5)], oz
    if kip == "sifreli":
        assert db.at_rest_encrypted is True


def test_KRITIK_ikinci_ve_ucuncu_acilis_YENIDEN_BOLMEZ(temp_app_data, monkeypatch, kip):
    sid, _run = _eski_db_kur(temp_app_data, monkeypatch)
    ilk = _satirlar(_ac(temp_app_data), sid)
    for _ in range(2):
        db = _ac(temp_app_data)
        assert _satirlar(db, sid) == ilk
        db.close_connections()


def test_KRITIK_yeni_yazim_YOK_isaretli_ve_ASLA_bolunmez(temp_app_data, monkeypatch, kip):
    """TD2 sonrası (doğrulanmış ölçek) yazılan alan: 'yok' işareti; göç bayrağı silinse bile sonraki açılış dokunmaz."""
    sid, run_id = _eski_db_kur(temp_app_data, monkeypatch)
    db = _ac(temp_app_data)
    yeni = db.start_session("Manuel", patient_name="Yeni")
    db.add_sensor_samples_batch(yeni, [{"coil_id": "6", "sample_ts": 99.0, "magnetic_field_mt": 2.5}])
    db.add_sensor_run_summary(run_id, sample_count=1, field_avg=2.5)
    with db._get_connection() as c:
        c.execute("DELETE FROM system_settings WHERE setting_key = 'mt_bolu5_goc'")
        c.commit()
    db.close_connections()
    db = _ac(temp_app_data)
    with db._get_connection() as c:
        r = c.execute(
            "SELECT magnetic_field_mt, magnetic_field_mt_orijinal, alan_duzeltme FROM sensor_samples WHERE session_id = ?",
            (yeni,),
        ).fetchone()
        s = c.execute(
            "SELECT field_avg, field_avg_orijinal, alan_duzeltme FROM sensor_run_summary WHERE coil_run_id = ?",
            (run_id,),
        ).fetchone()
    assert tuple(r) == (2.5, None, "yok"), tuple(r)
    assert tuple(s) == (2.5, None, "yok"), tuple(s)


def test_KRITIK_yarim_goc_GUVENLI_hicbir_satir_degismez_DB_acilir_sonra_TAMAMLANIR(temp_app_data, monkeypatch, kip):
    from database import thdb_telemetri

    sid, _run = _eski_db_kur(temp_app_data, monkeypatch)
    orj = thdb_telemetri.MT_OZET_BOL_SQL
    monkeypatch.setattr(thdb_telemetri, "MT_OZET_BOL_SQL", "UPDATE yok_boyle_tablo SET x = 1")
    db = _ac(temp_app_data)  # göç ikinci adımda düşer — DB yine açılır
    with db._get_connection() as c:
        degerler = [
            r[0]
            for r in c.execute(
                "SELECT magnetic_field_mt FROM sensor_samples WHERE session_id = ? ORDER BY sample_ts, coil_id DESC",
                (sid,),
            )
        ]
        isaretler = {r[0] for r in c.execute("SELECT alan_duzeltme FROM sensor_samples")}
        bayrak = c.execute("SELECT setting_value FROM system_settings WHERE setting_key = 'mt_bolu5_goc'").fetchone()
    assert degerler == [13.3, 10.0, None], f"yarım göç satır değiştirdi: {degerler}"
    assert "bolu5" not in isaretler and bayrak is None
    db.close_connections()
    monkeypatch.setattr(thdb_telemetri, "MT_OZET_BOL_SQL", orj)
    orn, oz = _satirlar(_ac(temp_app_data), sid)
    assert [r[0] for r in orn][:2] == [pytest.approx(2.66), pytest.approx(2.0)] and oz[0][0] == pytest.approx(2.33)


def test_geri_alma_ORIJINALDEN_mumkun(temp_app_data, monkeypatch, kip):
    """Geri alınabilirlik (Y152): `*_orijinal` sütunlarından eski değer birebir geri yüklenebilir (rapordaki geri alma SQL'i)."""
    sid, _run = _eski_db_kur(temp_app_data, monkeypatch)
    db = _ac(temp_app_data)
    with db._get_connection() as c:
        c.execute(
            "UPDATE sensor_samples SET magnetic_field_mt = magnetic_field_mt_orijinal, magnetic_field_mt_orijinal = NULL,"
            " alan_duzeltme = 'geri' WHERE alan_duzeltme = 'bolu5'"
        )
        c.execute(
            "UPDATE sensor_run_summary SET field_avg = field_avg_orijinal, field_avg_orijinal = NULL, alan_duzeltme = 'geri'"
            " WHERE alan_duzeltme = 'bolu5'"
        )
        c.commit()
        assert [
            r[0]
            for r in c.execute(
                "SELECT magnetic_field_mt FROM sensor_samples WHERE session_id = ? ORDER BY sample_ts, coil_id DESC",
                (sid,),
            )
        ] == [13.3, 10.0, None]


# ── Gösterim: seans ayrıntısı + coil_runs.csv ──────────────────────────────────────────────────────────────────────────────


def test_KRITIK_seans_ayrintisi_ve_CSV_DUZELTILDI_notu(temp_app_data, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import history_router as h

    monkeypatch.setattr(TreatmentHistoryDB, "_import_sqlcipher", lambda self: None)
    sid, run_id = _eski_db_kur(temp_app_data, monkeypatch)
    db = _ac(temp_app_data)
    d = h.get_session_full_details(sid, db=db)
    oz = d["coil_runs"][0]["summary"]
    assert oz["field_avg"] == pytest.approx(2.33) and oz.get("field_avg_orijinal") == 11.65, oz
    assert oz.get("alan_notu") == NOT_METNI, oz
    assert d["session"].get("alan_notu") == NOT_METNI, d["session"]
    ornek = [s for s in d["sensor_samples"] if s.get("magnetic_field_mt") is not None]
    assert ornek and all(s.get("alan_duzeltildi") is True for s in ornek), ornek
    r = h.export_coil_runs_csv(sid, db=db)
    satirlar = list(csv.reader(io.StringIO(r.body.decode("utf-8-sig"))))
    # Y306 (madde 6): kanal 6 = kabin sensörü → alan ve ÷5 notu bobin satırında değil, AYRI "Kabin sensörü (MLX)" satırında.
    baslik, veri = satirlar[0], next(s for s in satirlar[1:] if s[0] == "Kabin sensörü (MLX)")
    assert satirlar[1][0] == "6" and satirlar[1][-1] == "" and satirlar[1][baslik.index("Ort.Alan(mT)")] == "", (
        satirlar[1]
    )
    assert baslik[-1] == "Alan notu" and veri[-1] == NOT_METNI, (baslik, veri)
    assert float(veri[baslik.index("Ort.Alan(mT)")]) == pytest.approx(2.33)


def test_KARSIT_yeni_seans_NOT_tasimaz(temp_app_data, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import history_router as h

    monkeypatch.setattr(TreatmentHistoryDB, "_import_sqlcipher", lambda self: None)
    db = _ac(temp_app_data)
    sid = db.start_session("Manuel", patient_name="Yeni")
    with db._get_connection() as c:
        c.execute(
            "INSERT INTO session_coil_runs (session_id, coil_id, started_epoch, ended_epoch, duration_seconds, created_at)"
            " VALUES (?, 6, 1.0, 61.0, 60, 1.0)",
            (sid,),
        )
        run_id = c.execute("SELECT max(id) FROM session_coil_runs").fetchone()[0]
        c.commit()
    db.add_sensor_run_summary(run_id, sample_count=1, field_avg=2.5)
    db.add_sensor_samples_batch(
        sid, [{"coil_id": "6", "sample_ts": 9.0, "magnetic_field_mt": 2.5, "coil_run_id": run_id}]
    )
    d = h.get_session_full_details(sid, db=db)
    assert d["coil_runs"][0]["summary"]["field_avg"] == 2.5 and not d["coil_runs"][0]["summary"].get("alan_notu")
    assert not d["session"].get("alan_notu")
    assert all(s.get("alan_duzeltildi") is False for s in d["sensor_samples"])
    veri = list(csv.reader(io.StringIO(h.export_coil_runs_csv(sid, db=db).body.decode("utf-8-sig"))))[1]
    assert veri[-1] == ""


# ── Doz / sürüş / bulut: ölçülen alan GİRMEZ (ölç ve kanıtla) ───────────────────────────────────────────────────────────────


def test_bulut_seans_yuku_OLCULEN_ALAN_tasimaz():
    """Y152 "bulut kopyaları normal eşitlemeyle düzeltilir": seans PUSH yükünde ölçülen alan YOK (yalnız reçete `intensity_mt`) →
    bulutta düzeltilecek ölçülen mT değeri yok; `sync_status` sıfırlanmaz. Yük ölçülen alan taşımaya başlarsa bu kapı kırmızı olur
    (o gün düzeltilen seanslar yeniden kuyruğa alınmalı)."""
    import ast

    kaynak = (Path(__file__).resolve().parents[1] / "apps" / "backend" / "servers" / "sync_worker.py").read_text(
        encoding="utf-8"
    )
    fn = next(d for d in ast.walk(ast.parse(kaynak)) if isinstance(d, ast.FunctionDef) and d.name == "_sync_sessions")
    anahtarlar = {
        k.value
        for d in ast.walk(fn)
        if isinstance(d, ast.Dict)
        for k in d.keys
        if isinstance(k, ast.Constant) and isinstance(k.value, str)
    }
    assert "intensity_mt" in anahtarlar, "araç kör: seans yükü bulunamadı"
    assert not {k for k in anahtarlar if "field" in k or "magnetic" in k or "alan" in k}, anahtarlar


def test_ai_pro_achieved_B_OLCUMDEN_gelmez():
    """TD2 notu yeniden ölçüldü: AI Pro dozunun `achieved_B`'si sabit (1 mT) / YAML — DB'deki ölçülen alandan beslenmez."""
    from servers import ai_pro_hedef, ai_router

    assert ai_router._AI_ACHIEVED_B == 0.001 and ai_pro_hedef.KEDI_ACHIEVED_B == 0.001


# ── Cihaz taşıma: CH3 ÖNCESİ dışa aktarım dosyası içe aktarılınca da düzeltilir ─────────────────────────────────────────────


def test_KRITIK_CH3_oncesi_disa_aktarim_ICE_AKTARILINCA_duzeltilir_sonrasi_DOKUNULMAZ(temp_app_data, monkeypatch):
    """Göç bayrağı ('tamam') kurulu bir cihaza, işaret sütunu TAŞIMAYAN eski bir dışa aktarım (CH3 öncesi sürüm) içe aktarılır →
    eski satırlar ÷5 + orijinal saklı; CH3 sonrası dosyanın 'yok' satırı ve 'bolu5' satırı DEĞİŞMEZ (çift bölme yok)."""
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.setattr(TreatmentHistoryDB, "_import_sqlcipher", lambda self: None)
    db = _ac(temp_app_data)
    assert db._get_system_setting("mt_bolu5_goc") == "tamam", "öncül: taze DB'de göç bayrağı kurulmadı"
    seans = {
        "id": 1,
        "session_date": "2026-09-01",
        "start_time": "10:00",
        "treatment_mode": "Manuel",
        "patient_name": "Eski",
    }
    kosu = {
        "id": 7,
        "session_id": 1,
        "coil_id": 6,
        "started_epoch": 1.0,
        "ended_epoch": 61.0,
        "duration_seconds": 60,
        "created_at": 1.0,
    }
    veri = {
        "treatment_sessions": [seans],
        "session_coil_runs": [kosu],
        "sensor_run_summary": [{"id": 3, "coil_run_id": 7, "sample_count": 2, "field_avg": 11.65, "created_at": 1.0}],
        "sensor_samples": [
            # CH3 ÖNCESİ dosya: işaret sütunu YOK
            {"id": 1, "session_id": 1, "coil_id": "6", "sample_ts": 10.0, "magnetic_field_mt": 13.3, "created_at": 1.0},
            # CH3 SONRASI dosya: doğrulanmış ölçek ve daha önce düzeltilmiş satır
            {"id": 2, "session_id": 1, "coil_id": "6", "sample_ts": 20.0, "magnetic_field_mt": 2.5, "created_at": 1.0,
             "alan_duzeltme": "yok"},
            {"id": 3, "session_id": 1, "coil_id": "6", "sample_ts": 30.0, "magnetic_field_mt": 2.0, "created_at": 1.0,
             "alan_duzeltme": "bolu5", "magnetic_field_mt_orijinal": 10.0},
        ],
    }  # fmt: skip
    db.import_rows(veri, replace=True)
    with db._get_connection() as c:
        orn = [
            tuple(r)
            for r in c.execute(
                "SELECT magnetic_field_mt, magnetic_field_mt_orijinal, alan_duzeltme FROM sensor_samples ORDER BY sample_ts"
            )
        ]
        oz = [
            tuple(r) for r in c.execute("SELECT field_avg, field_avg_orijinal, alan_duzeltme FROM sensor_run_summary")
        ]
    assert orn[0] == (pytest.approx(2.66), 13.3, "bolu5"), orn
    assert orn[1] == (2.5, None, "yok") and orn[2] == (2.0, 10.0, "bolu5"), orn
    assert oz == [(pytest.approx(2.33), 11.65, "bolu5")], oz


# ── Arayüz fikstürü: GERÇEK seans ayrıntısı yanıtından (elle yazılmaz) ─────────────────────────────────────────────────────

_FIKSTUR = (
    Path(__file__).resolve().parents[1]
    / "apps"
    / "ui"
    / "src"
    / "screens"
    / "__tests__"
    / "__fixtures__"
    / "alanDuzeltme.CH3.json"
)


def test_arayuz_fiksturu_GERCEK_yanitla_AYNI(temp_app_data, monkeypatch):
    """`alanDuzeltme.CH3.test.tsx`in girdisi: göç edilmiş eski DB + yeni seansın GERÇEK `/details` yanıtı. Bayatlarsa KIRMIZI;
    yeniden üretmek için `CH3_FIKSTUR_YAZ=1`. Zamana bağlı alanlar sabitlenir."""
    import json
    import os

    from database.treatment_history_db import TreatmentHistoryDB
    from servers import history_router as h

    monkeypatch.setattr(TreatmentHistoryDB, "_import_sqlcipher", lambda self: None)
    sid, _run = _eski_db_kur(temp_app_data, monkeypatch)
    db = _ac(temp_app_data)
    eski = h.get_session_full_details(sid, db=db)
    yeni_sid = db.start_session("Manuel", patient_name="Yeni")
    with db._get_connection() as c:
        c.execute(
            "INSERT INTO session_coil_runs (session_id, coil_id, started_epoch, ended_epoch, duration_seconds, created_at)"
            " VALUES (?, 6, 1.0, 61.0, 60, 1.0)",
            (yeni_sid,),
        )
        yeni_run = c.execute("SELECT max(id) FROM session_coil_runs").fetchone()[0]
        c.commit()
    db.add_sensor_run_summary(yeni_run, sample_count=1, field_avg=2.5)
    yeni = h.get_session_full_details(yeni_sid, db=db)

    def _sabit(d):
        oturum = {k: ("SABIT" if v is not None and k not in ("alan_notu",) else v) for k, v in d["session"].items()}
        oturum["id"] = 7  # arayüz yalnız istenen seansın (`sessionId`) ayrıntısını çizer
        return {**d, "session": oturum}

    metin = (
        json.dumps({"eski": _sabit(eski), "yeni": _sabit(yeni)}, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    )
    if os.environ.get("CH3_FIKSTUR_YAZ") == "1":
        _FIKSTUR.write_text(metin, encoding="utf-8")
    assert _FIKSTUR.exists(), "arayüz fikstürü yok (CH3_FIKSTUR_YAZ=1 ile üret)"
    assert json.loads(_FIKSTUR.read_text(encoding="utf-8")) == json.loads(metin), (
        "arayüz fikstürü BAYAT: gerçek seans ayrıntısı yanıtı değişti (CH3_FIKSTUR_YAZ=1 ile yeniden üret, jest kapısını koş)"
    )
