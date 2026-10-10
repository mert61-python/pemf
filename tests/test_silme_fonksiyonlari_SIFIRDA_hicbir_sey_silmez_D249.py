# -*- coding: utf-8 -*-
"""D2.49 (B-3.1) — saklama silmesi operatörün KAPATTIĞI ya da UZATTIĞI süreyi ezmez; "0 = adım kapalı" EN ALT katta da geçerli.

Döngü düzeyi: `api_server._daily_maintenance_loop` olay silmesini `PEMF_RETAIN_EVENT_DAYS`'e (0 = silme) B2-1.6 ile bağladı; sensör silmesi
D2.44 ile kalktı (tek silici headless). Bu kapı kalan kök nedeni kilitler: silme fonksiyonlarının KENDİSİ (`purge_old_sensor_samples`,
`purge_old_session_events`, `purge_old_coil_runs`, `purge_old_dead_outbox`) `max(1, retain_days)` ile 0'ı 1 GÜNE çeviriyordu — çağıran
"0 = kapalı" kuralını bir kez unutursa (2026-08-17 doz olayında ve B2-1.6'da iki kez oldu) bir günden eski TÜM telemetri, seans olayları
(ACİL DURDUR kanıtı dahil), UYGULANAN DOZ ve ölü outbox geri dönüşsüz gidiyordu. Artık süre <= 0 → HİÇBİR şey silinmez, 0 döner.
"""

from __future__ import annotations

import time

import pytest

GUN = 86400.0


@pytest.fixture
def db(tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(tmp_path)
    try:
        yield d
    finally:
        d.close_connections()


def _eski_satirlar(db) -> dict:
    simdi = time.time()
    sid = int(db.start_session(treatment_mode="Manuel", patient_name="Pamuk D249"))
    db.add_sensor_samples_batch(
        sid, [{"coil_id": "1", "sample_ts": simdi - 30 * GUN, "temperature_c": 30.0, "payload": {}}]
    )
    olay = db.record_session_event(sid, "seans_notu", {"a": 1})
    kosu = db.start_coil_run(sid, 1, frequency_hz=50.0, duty_percent=25.0, started_epoch=simdi - 30 * GUN)
    kutu = db.enqueue_outbox_message("pemf/test", "{}")
    with db._get_connection() as c:
        c.execute("UPDATE session_events SET created_at=? WHERE id=?", (simdi - 30 * GUN, olay))
        c.execute("UPDATE outbox_messages SET status='dead', available_at=? WHERE id=?", (simdi - 30 * GUN, kutu))
        c.commit()
    return {"sid": sid, "olay": olay, "kosu": kosu, "kutu": kutu}


def _say(db, k) -> dict:
    with db._get_connection() as c:
        return {
            "sensor": c.execute("SELECT COUNT(*) FROM sensor_samples WHERE session_id=?", (k["sid"],)).fetchone()[0],
            "olay": c.execute("SELECT COUNT(*) FROM session_events WHERE id=?", (k["olay"],)).fetchone()[0],
            "kosu": c.execute("SELECT COUNT(*) FROM session_coil_runs WHERE id=?", (k["kosu"],)).fetchone()[0],
            "kutu": c.execute("SELECT COUNT(*) FROM outbox_messages WHERE id=?", (k["kutu"],)).fetchone()[0],
        }


_ISLEV = {
    "sensor": "purge_old_sensor_samples",
    "olay": "purge_old_session_events",
    "kosu": "purge_old_coil_runs",
    "kutu": "purge_old_dead_outbox",
}


@pytest.mark.parametrize("sure", [0, -5], ids=["sifir", "negatif"])
@pytest.mark.parametrize("adim", sorted(_ISLEV))
def test_KRITIK_silme_islevi_SIFIR_ya_da_NEGATIF_surede_hicbir_sey_SILMEZ(db, adim, sure):
    """MUTASYON: herhangi bir silme işlevine `max(1, …)` geri konur (0 → 1 günlük silme) → o işlevin kolu KIRMIZI."""
    k = _eski_satirlar(db)
    silinen = getattr(db, _ISLEV[adim])(sure)
    assert silinen == 0 and _say(db, k)[adim] == 1, (
        f"{_ISLEV[adim]}({sure}) 30 günlük satırı sildi (silinen={silinen}) — süre <= 0 'adım kapalı' demek, 1 günlük silme DEĞİL"
    )


@pytest.mark.parametrize("adim", sorted(_ISLEV))
def test_KARSIT_pozitif_surede_eski_satir_SILINIR(db, adim):
    """Araç kör değil: 7 günlük süre 30 günlük satırı siler."""
    k = _eski_satirlar(db)
    assert getattr(db, _ISLEV[adim])(7) >= 1 and _say(db, k)[adim] == 0
