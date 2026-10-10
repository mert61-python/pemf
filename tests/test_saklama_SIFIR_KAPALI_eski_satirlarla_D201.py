# -*- coding: utf-8 -*-
"""D2.01 (B-3.77) — "0 = adım kapalı" saklama sözleşmesi ESKİ satırlarla, davranışla ölçülür.

ÖLÇÜLEN KÖRLÜK: `test_treatment_retention.py::test_retention_steps_can_be_disabled` tüm süreleri 0 verip sayaçların 0 olduğunu
iddia ediyordu — ama veritabanında silinecek ESKİ satır YOKTU. `apply_data_retention_policy`'deki herhangi bir `if <süre> > 0:`
koşulu `if True:` yapılınca adım `purge_old_*(0)` → `max(1, 0)` = 1 GÜNLÜK silmeye düşer; taze satırlar 1 günden yeni olduğu
için mutant yeşil kalıyordu. Oysa sahada "0" yazan klinikte bu, bir günden eski TÜM telemetriyi, seans olaylarını (ACİL DURDUR
kanıtı dahil), ölü outbox'ı ve UYGULANAN DOZU geri dönüşsüz siler.

Kapı: her adımın eşiğini AŞAN eski satır (200 günlük sensör örneği, 400 günlük seans olayı ve ölü outbox, 4000 günlük bobin koşusu,
400 günlük adlı seans + operatörün PII onayı) GERÇEK `TreatmentHistoryDB`ye yazılır. (1) doğrudan `apply_data_retention_policy(…=0)`,
(2) operatörün arayüzde seçtiği PII süresi 0 iken çağıranın 365'i, (3) GERÇEK headless bakım turu `PEMF_RETAIN_*=0` ortamıyla —
üçünde de rapor sayaçları 0 ve satırlar yerinde. KARŞIT: aynı satırlar varsayılan sürelerle silinir/maskelenir (araç kör değil).
"""

from __future__ import annotations

import time

import pytest

GUN = 86400.0
_ENV = (
    "PEMF_RETAIN_SENSOR_DAYS",
    "PEMF_RETAIN_DOSE_DAYS",
    "PEMF_RETAIN_EVENT_DAYS",
    "PEMF_RETAIN_OUTBOX_DAYS",
    "PEMF_RETAIN_PII_DAYS",
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    for ad in _ENV:
        monkeypatch.delenv(ad, raising=False)
    d = TreatmentHistoryDB(tmp_path)
    try:
        yield d
    finally:
        d.close_connections()


def _eski_satirlar(db) -> dict:
    """Her saklama adımının eşiğini aşan birer eski satır — ürünün KENDİ yazıcılarıyla, sonra zaman damgası geriye alınır."""
    simdi = time.time()
    sid = int(db.start_session(treatment_mode="Manuel", patient_name="Pamuk Eski", operator_name="Dr Ayse"))
    db.end_session(sid, patient_notes="eski gozlem", duration_minutes=10)
    db.add_sensor_samples_batch(
        sid, [{"coil_id": "1", "sample_ts": simdi - 200 * GUN, "temperature_c": 31.0, "payload": {}}]
    )
    olay = db.record_session_event(sid, "seans_notu", {"a": 1})
    kosu = db.start_coil_run(sid, 1, frequency_hz=50.0, duty_percent=25.0, started_epoch=simdi - 4000 * GUN)
    db.end_coil_run(kosu, simdi - 4000 * GUN + 600)
    kutu = db.enqueue_outbox_message("pemf/test", "{}")
    with db._get_connection() as c:
        c.execute("UPDATE session_events SET created_at=? WHERE id=?", (simdi - 400 * GUN, olay))
        c.execute("UPDATE outbox_messages SET status='dead', available_at=? WHERE id=?", (simdi - 400 * GUN, kutu))
        eski_tarih = time.strftime("%Y-%m-%d", time.localtime(simdi - 400 * GUN))
        c.execute("UPDATE treatment_sessions SET session_date=? WHERE id=?", (eski_tarih, sid))
        c.commit()
    db.pii_onayla()  # operatör geri dönüşsüz maskelemeyi DAHA ÖNCE onaylamış — süre 0 olunca yine de maskelenmemeli
    return {"sid": sid, "olay": olay, "kosu": kosu, "kutu": kutu}


def _say(db, k: dict) -> dict:
    with db._get_connection() as c:
        return {
            "sensor": c.execute("SELECT COUNT(*) FROM sensor_samples WHERE session_id=?", (k["sid"],)).fetchone()[0],
            "olay": c.execute("SELECT COUNT(*) FROM session_events WHERE id=?", (k["olay"],)).fetchone()[0],
            "kosu": c.execute("SELECT COUNT(*) FROM session_coil_runs WHERE id=?", (k["kosu"],)).fetchone()[0],
            "kutu": c.execute("SELECT COUNT(*) FROM outbox_messages WHERE id=?", (k["kutu"],)).fetchone()[0],
            "ad": c.execute("SELECT patient_name FROM treatment_sessions WHERE id=?", (k["sid"],)).fetchone()[0],
        }


_YERINDE = {"sensor": 1, "olay": 1, "kosu": 1, "kutu": 1, "ad": "Pamuk Eski"}


def test_KRITIK_tum_sureler_SIFIR_eski_satirlar_YERINDE_sayaclar_SIFIR(db):
    """MUTASYON: `apply_data_retention_policy`deki beş `if <süre> > 0:` koşulundan herhangi biri `if True:` → KIRMIZI."""
    k = _eski_satirlar(db)
    rapor = db.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=0, dose_retain_days=0
    )
    assert _say(db, k) == _YERINDE, f"süre 0 (adım kapalı) iken eski satır silindi/maskelendi: {_say(db, k)}"
    assert all(v == 0 for v in rapor.values()), f"adım kapalıyken rapor işlem bildiriyor: {rapor}"


def test_KRITIK_operatorun_SECTIGI_pii_suresi_SIFIR_cagiranin_365ini_EZER(db):
    """Arayüzde "Kapalı" seçen klinikte (pii_retention_days=0) çağıranın 365'i maskelemeyi açmamalı."""
    k = _eski_satirlar(db)
    db.pii_suresi_yaz(0)
    rapor = db.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365, dose_retain_days=0
    )
    assert _say(db, k)["ad"] == "Pamuk Eski", "operatör maskelemeyi KAPATMIŞKEN eski seansın adı maskelendi"
    assert rapor["sessions_pii_redacted"] == 0 and rapor.get("pii_pending", 0) == 0, rapor


def test_KRITIK_GERCEK_headless_bakim_turu_PEMF_RETAIN_SIFIR_hicbir_sey_silmez(db, monkeypatch):
    """Üretimdeki asıl silici (`services/headless_db_maintenance`) ortamdaki `0`ı "adım kapalı" okumalı.
    MUTASYON: `_retain_days` 0'ı varsayılana çevirirse (`… or default`) → KIRMIZI."""
    from services.headless_db_maintenance import HeadlessDBMaintenance

    k = _eski_satirlar(db)
    for ad in _ENV:
        monkeypatch.setenv(ad, "0")
    bakim = HeadlessDBMaintenance.__new__(HeadlessDBMaintenance)  # iş parçacığı kurulmaz; GERÇEK tur gövdesi koşar
    bakim.db = db
    bakim._run_maintenance()
    assert _say(db, k) == _YERINDE, f"PEMF_RETAIN_*=0 iken headless bakım turu sildi/maskeledi: {_say(db, k)}"


def test_KARSIT_varsayilan_surelerle_ayni_eski_satirlar_SILINIR_ve_MASKELENIR(db):
    """Araç kör değil: aynı satırlar varsayılan sürelerle (90/3650/365/30/365 + onay) gerçekten gider."""
    k = _eski_satirlar(db)
    rapor = db.apply_data_retention_policy()
    son = _say(db, k)
    assert (son["sensor"], son["olay"], son["kosu"], son["kutu"]) == (0, 0, 0, 0), son
    assert son["ad"] != "Pamuk Eski", "onaylı maskeleme varsayılan sürede eski seansı maskelemedi"
    assert rapor["sensor_samples_removed"] == 1 and rapor["coil_runs_removed"] == 1, rapor
    assert rapor["session_events_removed"] == 1 and rapor["dead_outbox_removed"] == 1, rapor
