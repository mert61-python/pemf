# -*- coding: utf-8 -*-
"""KP (Y236 · kapsam) — (uykudaki) `database/session_manager.py`: yapılandırma sınırları, parametre / sensör yığınları, seans sonu, zorla bitirme.

Bugün üründe çağıranı yok (D2.59 / D6.60) ama SİLİNMEZ ve yeniden bağlanırsa hasta geçmişine yazar; D259 yalnız PII yolunu kilitliyordu
(%52). GERÇEK: TreatmentHistoryDB (tmp); hata kolları en alt katta (`db` yöntemleri) düşürülür → istisna yukarı SIZMAZ, sinyal yayılır.
"""

from __future__ import annotations

import json
import logging

import pytest


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    from database import session_manager as smod
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    db = TreatmentHistoryDB(tmp_path / "db")
    monkeypatch.setattr(smod, "get_treatment_db", lambda *_a, **_k: db)
    try:
        yield smod, db, tmp_path
    finally:
        db.close_connections()


def _sinyaller(m):
    olan: list = []
    m.session_started.connect(lambda sid: olan.append(("basladi", sid)))
    m.session_ended.connect(lambda sid: olan.append(("bitti", sid)))
    m.session_error.connect(lambda msg: olan.append(("hata", msg)))
    return olan


def test_yapilandirma_SINIRLARI_uygulanir(ortam):
    smod, _db, tmp = ortam
    (tmp / "uygulama").mkdir()
    (tmp / "uygulama" / "config.json").write_text(
        json.dumps({"performance": {"sqlite": {"sensor_batch_size": 5, "sensor_flush_interval_seconds": 99}}}),
        encoding="utf-8",
    )
    m = smod.SessionManager(tmp / "uygulama")
    assert (m._sensor_batch_size, m._sensor_flush_interval_seconds) == (10, 30.0), "yığın boyutu / aralık sınırlanmadı"


def test_yapilandirma_HIC_bulunamazsa_varsayilanla_acilir(ortam, monkeypatch, caplog):
    smod, _db, tmp = ortam
    import utils.path_utils as pu

    monkeypatch.setattr(pu, "kaynak_kokunu_bul", lambda *a, **k: tmp / "kaynak_yok")
    monkeypatch.setattr(pu, "resource_path", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("paket yok")))
    m = smod.SessionManager(tmp / "bos")
    assert (m._sensor_batch_size, m._sensor_flush_interval_seconds) == (50, 5.0)
    assert any("performance config yüklenemedi" in r.getMessage() for r in caplog.records)


def test_KRITIK_seans_yasam_dongusu_parametre_not_sensor_DISKE_ulasir(ortam):
    smod, db, tmp = ortam
    m = smod.SessionManager(tmp)
    m._batch_size = 2
    m._sensor_batch_size = 2
    olan = _sinyaller(m)
    sid = m.start_session(
        "Manuel",
        target_condition="artrit",
        operator_name="Dr X",
        patient_name="Pamuk",
        initial_parameters={"frequency_hz": 10},
    )
    assert sid and olan == [("basladi", sid)]
    m.add_parameter("intensity_mt", 1.5, unit="mT")
    m.add_parameter("pulse_duration_ms", 20)  # 2. parametre → yığın boyutu → DİSKE
    with db._get_connection() as c:
        n = c.execute("SELECT COUNT(*) FROM session_parameters WHERE session_id=?", (sid,)).fetchone()[0]
    assert n == 2, "yığın dolunca parametreler diske yazılmadı"
    m.add_parameter("duration", {"value": 30})
    m.update_parameters({"frequency_hz": 12, "hasta_kilo": 4})
    m.add_note("ilk not")
    m.add_note("ikinci not")
    assert m.session_parameters["patient_notes"] == "ilk not\nikinci not"
    m.add_sensor_sample(
        6, {"temperature": 37.0, "magnetic_field": 1.2, "current": 0.4, "pwm_duty": 40, "sensors_ok": True}
    )
    m.add_sensor_sample(6, {"object_temp": 37.5, "pwm_duty_cycle": 41})  # 2. örnek → yığın boyutu → DİSKE
    with db._get_connection() as c:
        orn = c.execute(
            "SELECT temperature_c FROM sensor_samples WHERE session_id=? ORDER BY sample_ts", (sid,)
        ).fetchall()
    assert [r[0] for r in orn] == [37.0, 37.5], "sensör örnekleri diske ulaşmadı / ad eşlemesi bozuk"
    bilgi = m.get_session_info()
    assert bilgi["session_id"] == sid and bilgi["treatment_mode"] == "Manuel" and bilgi["duration_minutes"] == 0
    assert m.end_session(final_notes="son not", actual_duration=4.6) is True
    assert olan[-1] == ("bitti", sid) and m.current_session_id is None and m.get_session_info() == {}
    d = db.get_session_details(sid)
    assert d is not None, "seans ayrıntısı okunamadı"
    with db._get_connection() as c:
        satir = dict(c.execute("SELECT * FROM treatment_sessions WHERE id=?", (sid,)).fetchone())
    assert satir["duration_minutes"] == 5, "gerçek süre (4,6 dk → 5) yazılmadı"
    assert "son not" in (satir.get("patient_notes") or ""), "son not seansa yazılmadı"


def test_seans_YOKKEN_islemler_no_op(ortam):
    smod, _db, tmp = ortam
    m = smod.SessionManager(tmp)
    m.update_parameters({"a": 1})
    m.add_parameter("a", 1)
    m.add_note("x")
    m.add_sensor_sample(1, {"temperature": 1})
    m._flush_sensor_sample_batch()
    m._flush_parameter_batch()
    assert m.session_parameters == {} and m._parameter_batch == [] and m._sensor_sample_batch == []
    assert m.end_session() is False and m.get_session_duration() == 0 and m.get_session_info() == {}
    m.force_end_session()  # aktif seans yok → sessiz


def test_aktif_seans_varken_yenisi_ONCE_eskisini_bitirir(ortam):
    smod, db, tmp = ortam
    m = smod.SessionManager(tmp)
    olan = _sinyaller(m)
    a = m.start_session("Manuel")
    m.add_parameter("frequency_hz", 9)  # yığında bekleyen parametre de bitişte DİSKE gider
    b = m.start_session("Otonom")
    assert a != b and ("bitti", a) in olan and m.current_session_id == b
    with db._get_connection() as c:
        assert c.execute("SELECT COUNT(*) FROM session_parameters WHERE session_id=?", (a,)).fetchone()[0] == 1


def test_baslatma_ve_bitirme_HATASI_sinyalle_bildirilir_istisna_sizmaz(ortam, monkeypatch):
    smod, db, tmp = ortam
    m = smod.SessionManager(tmp)
    olan = _sinyaller(m)
    gercek, dus = db.start_session, {"bir": True}

    def _bir_kez_dus(**k):
        if dus.pop("bir", False):
            raise RuntimeError("disk dolu")
        return gercek(**k)

    monkeypatch.setattr(db, "start_session", _bir_kez_dus)
    assert m.start_session("Manuel") is None
    assert olan and olan[-1][0] == "hata" and "disk dolu" in olan[-1][1]
    sid = m.start_session("Manuel")
    monkeypatch.setattr(db, "end_session", lambda **k: (_ for _ in ()).throw(RuntimeError("yazılamadı")))
    assert m.end_session() is False and olan[-1][0] == "hata" and m.current_session_id == sid


def test_hastaya_baglanamazsa_seans_YINE_acilir(ortam, monkeypatch, caplog):
    smod, db, tmp = ortam
    m = smod.SessionManager(tmp)
    monkeypatch.setattr(db, "upsert_patient", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("hasta DB kilitli")))
    assert m.start_session("Manuel", patient_name="Pamuk", patient_uuid="u-1")
    assert any("Seans hastaya bağlanamadı" in r.getMessage() for r in caplog.records)


def test_yigin_YAZILAMAZSA_temizlenir_tekrar_dongusu_olmaz(ortam, monkeypatch, caplog):
    smod, db, tmp = ortam
    m = smod.SessionManager(tmp)
    m.start_session("Manuel")
    m._parameter_batch.append((m.current_session_id, "a", "1"))
    monkeypatch.setattr(db, "_get_connection", lambda: (_ for _ in ()).throw(OSError("bağlantı yok")))
    m._flush_parameter_batch()
    assert m._parameter_batch == [] and any("Failed to flush parameter batch" in r.getMessage() for r in caplog.records)


def test_sensor_yigini_SURE_dolunca_yazilir_kaydedilemezse_uyarir(ortam, monkeypatch, caplog):
    smod, db, tmp = ortam
    m = smod.SessionManager(tmp)
    m.start_session("Manuel")
    m._sensor_flush_interval_seconds = 0.0  # her örnek süre koşuluyla yazılır
    monkeypatch.setattr(db, "add_sensor_samples_batch", lambda sid, ornek: 0)
    with caplog.at_level(logging.WARNING):
        m.add_sensor_sample(1, {"temperature": 36.6})
    assert m._sensor_sample_batch == [] and any(
        "Sensor sample batch kaydedilemedi" in r.getMessage() for r in caplog.records
    )


def test_verilen_seans_kimligiyle_bitirme_ve_sayi_olmayan_sure(ortam):
    smod, db, tmp = ortam
    m = smod.SessionManager(tmp)
    sid = m.start_session("Manuel")
    m.current_session_id = None  # çağıran kimliği açıkça verir (eski arayüz)
    assert m.end_session(session_id=sid, actual_duration="bilinmiyor") is True
    with db._get_connection() as c:
        assert c.execute("SELECT end_time FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]


def test_zorla_bitirme_normalde_bitirir_hata_olursa_DURUMU_temizler(ortam, monkeypatch, caplog):
    smod, _db, tmp = ortam
    m = smod.SessionManager(tmp)
    m.start_session("Manuel")
    m.force_end_session()
    assert m.current_session_id is None
    m.start_session("Manuel", operator_name="Dr X")
    monkeypatch.setattr(m, "end_session", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kilit")))
    m.force_end_session()
    assert (m.current_session_id, m.session_start_time, m.session_parameters, m.operator_name) == (None, None, {}, None)
    assert any("Zorla sonlandırma hatası" in r.getMessage() for r in caplog.records)


def _say(db, tablo, sid):
    with db._get_connection() as c:
        return c.execute(f"SELECT COUNT(*) FROM {tablo} WHERE session_id=?", (sid,)).fetchone()[0]


def test_KRITIK_seans_bitince_YIGINDA_bekleyen_sensor_ornegi_DISKE_yazilir(ortam):
    """Yığın eşiği / süresi dolmadan seans biterse bekleyen sensör örneği → end_session onu yazar (veri kaybı yok)."""
    smod, db, tmp = ortam
    m = smod.SessionManager(tmp)
    m._sensor_batch_size, m._sensor_flush_interval_seconds = 1000, 10_000.0
    sid = m.start_session("Manuel")
    m._last_sensor_flush_ts = smod.time.monotonic()  # süre koşulu tetiklenmesin
    m.add_sensor_sample(3, {"temperature": 36.9})
    assert len(m._sensor_sample_batch) == 1 and _say(db, "sensor_samples", sid) == 0, (
        "örnek erken yazıldı — senaryo kurulamadı"
    )
    assert m.end_session() is True
    assert _say(db, "sensor_samples", sid) == 1, "seans sonunda yığındaki sensör örneği kayboldu"


def test_not_eklenirken_ESZAMANLI_gelen_son_parametre_ve_ornek_de_DISKE_yazilir(ortam, monkeypatch):
    """end_session ilk boşaltmadan sonra final notunu eklerken başka iş parçacığı parametre / örnek ekleyebilir → ikinci boşaltma onları da yazar."""
    smod, db, tmp = ortam
    m = smod.SessionManager(tmp)
    m._batch_size, m._sensor_batch_size, m._sensor_flush_interval_seconds = 1000, 1000, 10_000.0
    sid = m.start_session("Manuel")
    m._last_sensor_flush_ts = smod.time.monotonic()
    gercek_not = m.add_note

    def _not_ve_eszamanli_yazici(not_):
        gercek_not(not_)
        m.add_parameter("frequency_hz", 11)  # telemetri iş parçacığının seans biterken yaptığı son yazım
        m.add_sensor_sample(4, {"temperature": 37.2})

    monkeypatch.setattr(m, "add_note", _not_ve_eszamanli_yazici)
    assert m.end_session(final_notes="kapanış notu") is True
    assert _say(db, "session_parameters", sid) == 1, "not sonrası gelen son parametre yazılmadı"
    assert _say(db, "sensor_samples", sid) == 1, "not sonrası gelen son sensör örneği yazılmadı"


def test_tekil_yonetici(ortam, monkeypatch):
    smod, _db, tmp = ortam
    monkeypatch.setattr(smod, "_session_manager_instance", None)
    assert smod.get_session_manager(tmp) is smod.get_session_manager(tmp / "baska")
