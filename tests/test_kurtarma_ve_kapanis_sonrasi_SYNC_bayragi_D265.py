# -*- coding: utf-8 -*-
"""D2.65 · B-3.66 — kurtarılan seans ve kapanış sonrası not/parametre buluta GİDER; PULL yerel değişikliği bayat değerle EZMEZ.

UYKUDA (A-15: `PEMF_CLOUD_PATIENT_SYNC` varsayılan 0, launcher geçirmiyor) — bayrak açılırsa:
(1) ÖLÇÜLEN: açılış kurtarması (`recover_stale_active_sessions`) seansı `ABORTED_DUE_TO_POWER` ile kapatıyor ama `sync_status`'a
    dokunmuyordu → seans aktifken buluta gitmişse (1) kapanış HİÇ PUSH edilmez, bulut kopyası kalıcı 'active'.
(2) ÖLÇÜLEN: kapanış sonrası gözlem notu / frekans / yoğunluk (`update_session_finalized_extras`, `/api/session/notes`) `sync_status`'u
    işaretlemiyordu → buluta gitmez; aynı döngüdeki PULL bayat bulut değeriyle yerel frekansı EZİYORDU (77.0 → None).
GERÇEK: TreatmentHistoryDB (sentetik, tmp), açılış kurtarması (yeni örnek), `CloudSyncWorker._sync_sessions` (PUSH + PULL). Sahte: yalnız
bulut istemcisi (en dış sınır; PUSH ağ hatasıyla düşer — gerçekçi).
"""

from __future__ import annotations

import pytest


class _Rpc:
    def __init__(self, rows):
        self.data = rows

    def execute(self):
        return self


class _BulutPushHatali:
    """PUSH (`upsert_session`) ağ hatasıyla düşer; PULL (`resolve_sessions`) verilen (bayat) satırları döndürür."""

    def __init__(self, satirlar):
        self._satirlar = satirlar
        self.push = 0

    def rpc(self, name, params=None):
        if name == "upsert_session":
            self.push += 1
            raise RuntimeError("bulut push agi hatasi (test)")
        return _Rpc(self._satirlar if name == "resolve_sessions" else [])


def _oku(db, sid, *sutunlar):
    with db._get_connection() as c:
        c.row_factory = None
        return c.execute(f"SELECT {', '.join(sutunlar)} FROM treatment_sessions WHERE id=?", (sid,)).fetchone()


def _senkron_isaretle(db, sid):
    with db._get_connection() as c:
        c.execute("UPDATE treatment_sessions SET sync_status=1 WHERE id=?", (sid,))
        c.commit()


def _bulut_satiri(sid, **kw):
    s = {
        "id": sid,
        "session_date": "2026-08-22",
        "start_time": "2026-08-22T10:00:00",
        "end_time": "2026-08-22T10:30:00",
        "duration_minutes": 30,
        "treatment_mode": "Manual",
        "target_condition": None,
        "frequency_hz": None,
        "intensity_mt": None,
        "pulse_duration_ms": None,
        "session_status": "completed",
        "created_at": "2026-08-22T10:00:00",
    }
    s.update(kw)
    return s


def _pull(db, istemci, monkeypatch):
    from servers.sync_worker import CloudSyncWorker

    monkeypatch.setenv("PEMF_CLOUD_PATIENT_SYNC", "1")
    w = CloudSyncWorker("", "")
    w.client = istemci
    w.patient_sync_enabled = True
    w.device_id = "test-device"
    w._sync_sessions(db)


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    acik = []

    def ac():
        db = TreatmentHistoryDB(tmp_path / "gecmis")
        acik.append(db)
        return db

    try:
        yield ac
    finally:
        for db in acik:
            db.close_connections()


def test_KRITIK_acilis_kurtarmasi_kapanisi_PUSH_icin_ISARETLER(ortam):
    """Plan kapısı (1): seans aktifken buluta gitti (sync_status=1), cihaz çöktü → GERÇEK açılış kurtarması (yeni örnek) seansı
    kapatır VE `sync_status=0` yapar (kapanış bir sonraki PUSH'ta gider). MUTASYON: kurtarma UPDATE'inden sync_status=0 → KIRMIZI."""
    db = ortam()
    sid = db.start_session("Manual", operator_name="Vet", patient_name="Pamuk")
    _senkron_isaretle(db, sid)
    db.close_connections()
    db2 = ortam()  # açılış: __init__ → recover_stale_active_sessions
    durum, sync = _oku(db2, sid, "session_status", "sync_status")
    assert durum == "ABORTED_DUE_TO_POWER", f"aparat: açılış kurtarması seansı kapatmadı ({durum})"
    assert sync == 0, "kurtarılan kapanış PUSH için işaretlenmedi — bulut kopyası kalıcı 'active' kalır (B-3.66)"


def test_KRITIK_kapanis_sonrasi_not_ve_parametre_PUSH_icin_ISARETLER(ortam):
    db = ortam()
    sid = db.start_session("Manual", operator_name="Vet", patient_name="Pamuk")
    db.end_session(sid, duration_minutes=30, session_status="completed")
    _senkron_isaretle(db, sid)  # kapanış buluta gitti
    db.update_session_finalized_extras(sid, notes="gozlem notu", frequency_hz=77.0, intensity_mt=3.5)
    assert _oku(db, sid, "sync_status")[0] == 0, (
        "kapanış sonrası not/parametre buluta gitmez (sync_status işaretlenmedi)"
    )


def test_KRITIK_PULL_PUSH_bekleyen_yerel_frekansi_bayat_bulut_degeriyle_EZMEZ(ortam, monkeypatch):
    """Plan kapısı (2): kapanış PUSH'u sonrası not + frekans yazılır, PUSH ağ hatasıyla düşer, aynı döngüdeki GERÇEK PULL bayat bulut
    kopyasını (frekans None) getirir → yerel frekans/yoğunluk KORUNUR ve PUSH bayrağı (0) silinmez. MUTASYON: PULL'un koşulsuz
    `frequency_hz=excluded.frequency_hz`'ına dönmek → KIRMIZI."""
    db = ortam()
    sid = db.start_session("Manual", operator_name="Vet", patient_name="Pamuk")
    db.end_session(sid, duration_minutes=30, session_status="completed")
    _senkron_isaretle(db, sid)
    db.update_session_finalized_extras(sid, frequency_hz=77.0, intensity_mt=3.5)
    bulut = _BulutPushHatali([_bulut_satiri(sid, frequency_hz=None, intensity_mt=None)])
    _pull(db, bulut, monkeypatch)
    assert bulut.push >= 1, "aparat: PUSH denenmedi (sync_status işaretlenmemiş olabilir)"
    f, i, sync = _oku(db, sid, "frequency_hz", "intensity_mt", "sync_status")
    assert (f, i) == (77.0, 3.5), f"PULL PUSH bekleyen yerel değeri bayat bulut değeriyle EZDİ: {(f, i)}"
    assert sync == 0, "PULL PUSH bekleyen değişikliğin bayrağını sildi — değişiklik buluta HİÇ gitmez"


def test_KARSIT_senkron_satirda_bulut_degeri_UYGULANIR(ortam, monkeypatch):
    """Koruma aşırı geniş değil: yerel satır SENKRON (1) ise buluttaki yeni frekans uygulanır."""
    db = ortam()
    sid = db.start_session("Manual", operator_name="Vet", patient_name="Pamuk")
    db.end_session(sid, duration_minutes=30, session_status="completed")
    _senkron_isaretle(db, sid)
    _pull(db, _BulutPushHatali([_bulut_satiri(sid, frequency_hz=42.0)]), monkeypatch)
    assert _oku(db, sid, "frequency_hz", "sync_status") == (42.0, 1)
