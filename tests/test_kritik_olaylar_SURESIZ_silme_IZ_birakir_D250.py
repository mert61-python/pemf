# -*- coding: utf-8 -*-
"""D2.50 (B-3.25) · A-07 — seans olaylarının saklama silmesi KRİTİK tıbbi olayları korur ve her silmeyi denetim izine yazar.

ÖLÇÜLEN KUSUR: `purge_old_session_events` tür / önem ayrımı yapmadan 365 günden eski TÜM `session_events` satırlarını iz bırakmadan
siliyordu. Seans başlığındaki "Acil Durduruldu" ve doz kaydı 3650 gün kalırken durdurmanın NEDENİ (aşırı akım, NACK, STM kopması, bekçi —
`emergency_stop` yükünde), acil durdurma kilidini kimin sıfırladığı ve AI önerisinin hekim onay/ret izi 365. günde yok oluyordu.

SAHİP KARARI A-07: kritik tıbbi olaylar SÜRESİZ saklanır; diğer seans olayları 365 gün; silme iz bırakır. Kritik = önemi `critical` /
`warning` olan HER olay + tür listesi (`emergency_stop`, `estop_mandali_sifirlandi`, `ai_proposal_approved`, `ai_proposal_rejected`,
`service_shutdown`). Üç silici de aynı işlevden geçer: doğrudan `apply_data_retention_policy`, GERÇEK headless bakım turu, GERÇEK günlük döngü.
"""

from __future__ import annotations

import json
import threading
import time

import pytest

GUN = 86400.0
KRITIK_TURLER = (
    "emergency_stop",
    "estop_mandali_sifirlandi",
    "ai_proposal_approved",
    "ai_proposal_rejected",
    "service_shutdown",
)


class _TurBitti(BaseException):
    pass


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    for ad in (
        "PEMF_RETAIN_EVENT_DAYS",
        "PEMF_RETAIN_SENSOR_DAYS",
        "PEMF_SENSOR_RETAIN_DAYS",
        "PEMF_RETAIN_DOSE_DAYS",
        "PEMF_RETAIN_OUTBOX_DAYS",
        "PEMF_RETAIN_PII_DAYS",
    ):
        monkeypatch.delenv(ad, raising=False)
    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(api, "get_patient_database", lambda: None)
    try:
        yield api, db
    finally:
        db.close_connections()


def _olay(db, sid, tur, onem, gun_once, yuk=None) -> int:
    eid = db.record_session_event(sid, tur, yuk or {"g": gun_once}, severity=onem)
    with db._get_connection() as c:
        c.execute("UPDATE session_events SET created_at=? WHERE id=?", (time.time() - gun_once * GUN, eid))
        c.commit()
    return eid


def _tohumla(db) -> dict:
    sid = int(db.start_session(treatment_mode="Manuel", patient_name="Pamuk D250"))
    k = {
        "estop": _olay(db, sid, "emergency_stop", "critical", 400, {"reason": "overcurrent", "coil_ids": [1]}),
        "mandal": _olay(db, sid, "estop_mandali_sifirlandi", "warning", 400),
        "onay": _olay(db, sid, "ai_proposal_approved", "info", 400),
        "ret": _olay(db, sid, "ai_proposal_rejected", "info", 400),
        "kapanis": _olay(db, sid, "service_shutdown", "info", 400),
        "bilinmeyen_kritik": _olay(db, sid, "yeni_alarm_turu", "critical", 400),
        "eski_not": _olay(db, sid, "seans_notu", "info", 400),
        "yeni_not": _olay(db, sid, "seans_notu", "info", 10),
    }
    return k


def _kalan(db, k) -> set:
    with db._get_connection() as c:
        var = {r[0] for r in c.execute("SELECT id FROM session_events").fetchall()}
    return {ad for ad, eid in k.items() if eid in var}


_KRITIKLER = {"estop", "mandal", "onay", "ret", "kapanis", "bilinmeyen_kritik"}


def _izler(db) -> list:
    return [e for e in db.denetim_oku(50, "retention.olay_silindi")]


def _gunluk_tur(api):
    orj = time.sleep
    durum = {"ident": None, "uyku": 0}
    hatalar: list = []

    def _sleep(s):
        if threading.get_ident() == durum["ident"]:
            durum["uyku"] += 1
            if durum["uyku"] >= 2:
                raise _TurBitti()
            return None
        return orj(s)

    def _kos():
        durum["ident"] = threading.get_ident()
        try:
            api._daily_maintenance_loop()
        except _TurBitti:
            pass
        except BaseException as e:  # noqa: BLE001
            hatalar.append(e)

    time.sleep = _sleep
    try:
        th = threading.Thread(target=_kos, daemon=True, name="bakim-d250")
        th.start()
        th.join(30)
    finally:
        time.sleep = orj
    assert not th.is_alive() and not hatalar and durum["uyku"] == 2, (th.is_alive(), durum, hatalar)


def _headless_tur(db):
    from services.headless_db_maintenance import HeadlessDBMaintenance

    b = HeadlessDBMaintenance.__new__(HeadlessDBMaintenance)
    b.db = db
    b._run_maintenance()


@pytest.mark.parametrize("silici", ["dogrudan", "headless", "gunluk_dongu"])
def test_KRITIK_kritik_olaylar_365_gunden_eski_de_KALIR_kritik_olmayan_SILINIR(ortam, silici):
    """MUTASYON: kritik dışlaması silinir → KIRMIZI (ACİL DURDUR nedeni, kilit sıfırlama, AI onay/ret izi 365. günde gider)."""
    api, db = ortam
    k = _tohumla(db)
    if silici == "dogrudan":
        db.apply_data_retention_policy()
    elif silici == "headless":
        _headless_tur(db)
    else:
        _gunluk_tur(api)
    assert _kalan(db, k) == _KRITIKLER | {"yeni_not"}, f"{silici}: kalan olaylar {_kalan(db, k)}"


def test_KRITIK_tur_listesi_ONEMDEN_bagimsiz_korur(ortam):
    """MUTASYON: yalnız önem (`critical`/`warning`) korunur, tür listesi düşer → AI onay/ret ve servis kapanışı (önemi `info`) SİLİNİR → KIRMIZI."""
    _, db = ortam
    k = _tohumla(db)
    db.purge_old_session_events(365)
    assert {"onay", "ret", "kapanis"} <= _kalan(db, k)


def test_KRITIK_onem_TUR_listesinden_bagimsiz_korur(ortam):
    """MUTASYON: yalnız tür listesi korunur → listede olmayan ama önemi `critical` olan yeni alarm türü SİLİNİR → KIRMIZI."""
    _, db = ortam
    k = _tohumla(db)
    db.purge_old_session_events(365)
    assert {"bilinmeyen_kritik", "mandal"} <= _kalan(db, k)


def test_KRITIK_silme_DENETIM_IZINE_yazilir_sayi_ve_sure_ile(ortam):
    """A-07 "silme iz bırakır". MUTASYON: denetim yazımı silinir → KIRMIZI."""
    _, db = ortam
    _tohumla(db)
    assert db.purge_old_session_events(365) == 1
    izler = _izler(db)
    assert len(izler) == 1 and izler[0]["item_count"] == 1, izler
    ayrinti = json.loads(izler[0]["detail"])
    assert ayrinti.get("gun") == 365 and ayrinti.get("kritik_korunan") == len(_KRITIKLER), ayrinti


def test_KARSIT_silinecek_olay_yoksa_IZ_yazilmaz(ortam):
    """Gürültü yok: hiçbir şey silinmeyen turda iz satırı oluşmaz (6 saatte bir boş iz birikmez)."""
    _, db = ortam
    sid = int(db.start_session(treatment_mode="Manuel", patient_name="Pamuk D250"))
    _olay(db, sid, "seans_notu", "info", 10)
    assert db.purge_old_session_events(365) == 0
    assert _izler(db) == []
