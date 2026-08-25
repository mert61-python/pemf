# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""BULUT PULL, KAPANMIS SEANSI BAYAT 'active' ILE GERI ACAMAZ (eksik-taramasi P2, 2026-08-22).

OLCULEN DURUM (latent — PEMF_CLOUD_PATIENT_SYNC varsayilan KAPALI): `_sync_sessions` PULL
upsert'i `end_time=excluded.end_time, duration_minutes=excluded.duration_minutes,
session_status=excluded.session_status` yazar — KOSULSUZ. Bulut kopyasi bayat-"active" ise
(PUSH'tan once kosulan PULL, ya da baska cihazin gec PUSH'u), YEREL olarak KAPANMIS seansin
end_time/duration'i NULL'a ezilir ve status yeniden "active" olur.

Bu bir DOZ BELGESI bozulmasidir: "seans ne zaman bitti, kac dakika surdu" bilgisi kaybolur ve
seans arayuzde/raporda yeniden acik gorunur. Bayrak bugun kapali oldugu icin canli zarar yok;
acildigi gun ilk sync cakismasinda patlardi.

SOZLESME (monotonik kapanis): KAPANIS GERI ALINAMAZ. Yerel satirin end_time'i doluyken buluttan
end_time'i NULL bir kopya gelirse kapanis kolonlari (end_time/duration_minutes/session_status)
KORUNUR; diger kolonlar normal guncellenir. Bulut GERCEK bir kapanis tasiyorsa (end_time dolu)
o kazanir — baska cihazda kapatilan seans yerelde de kapanmali (karsi-kanit testi)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _FakeRpc:
    def __init__(self, rows):
        self.data = rows

    def execute(self):
        return self


class _FakeSupabase:
    """resolve_sessions → verilen satirlar; diger RPC'ler (upsert_session) → no-op."""

    def __init__(self, resolve_rows):
        self._resolve = resolve_rows

    def rpc(self, name, params=None):
        return _FakeRpc(self._resolve if name == "resolve_sessions" else [])


def _kapali_seans_kur(temp_app_data):
    from database.treatment_history_db import get_treatment_db

    db = get_treatment_db(temp_app_data)
    sid = db.start_session("Manual", operator_name="Vet", patient_name="Boncuk")
    db.end_session(sid, duration_minutes=30, session_status="completed")
    return db, sid


def _seans_oku(db, sid):
    with db._get_connection() as c:
        c.row_factory = None
        row = c.execute(
            "SELECT end_time, duration_minutes, session_status FROM treatment_sessions WHERE id=?",
            (sid,),
        ).fetchone()
    return {"end_time": row[0], "duration_minutes": row[1], "session_status": row[2]}


def _pull_kos(db, satirlar, monkeypatch):
    from servers.sync_worker import CloudSyncWorker

    monkeypatch.setenv("PEMF_CLOUD_PATIENT_SYNC", "1")
    w = CloudSyncWorker("", "")
    w.client = _FakeSupabase(satirlar)
    w.patient_sync_enabled = True
    w.device_id = "test-device"
    w._sync_sessions(db)


def test_KRITIK_bayat_active_kapanisi_GERI_ACAMAZ(temp_app_data, monkeypatch):
    db, sid = _kapali_seans_kur(temp_app_data)
    once = _seans_oku(db, sid)
    assert once["end_time"], "onkosul: seans kapali olmali"

    bayat = {
        "id": sid,
        "session_date": "2026-08-22",
        "start_time": "2026-08-22T10:00:00",
        "end_time": None,  # bayat-acik bulut kopyasi
        "duration_minutes": None,
        "treatment_mode": "Manual",
        "target_condition": None,
        "frequency_hz": 42.0,  # sync-sahibi kolon: guncellenmesi MESRU
        "intensity_mt": None,
        "pulse_duration_ms": None,
        "session_status": "active",
        "created_at": "2026-08-22T10:00:00",
    }
    _pull_kos(db, [bayat], monkeypatch)

    sonra = _seans_oku(db, sid)
    assert sonra["end_time"] == once["end_time"], (
        "bulut PULL kapanmis seansin end_time'ini NULL'a ezdi — doz belgesi bozuldu "
        "(seans 'ne zaman bitti' cevabi kayboldu)"
    )
    assert sonra["duration_minutes"] == once["duration_minutes"], "sure kaydi bayat kopyayla silindi"
    assert sonra["session_status"] == once["session_status"], (
        f"kapanmis seans yeniden {sonra['session_status']!r} oldu — arayuzde acik gorunur"
    )
    # Kapanis-DISI kolon normal guncellenmeli (koruma asiri genislemesin):
    with db._get_connection() as c:
        c.row_factory = None
        f = c.execute("SELECT frequency_hz FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]
    assert f == 42.0, "koruma asiri genis: kapanis-disi kolonlar da guncellenmez oldu"


def _sync_status_oku(db, sid):
    with db._get_connection() as c:
        c.row_factory = None
        return c.execute("SELECT sync_status FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]


def test_KRITIK_D1_kapanis_sync_status_SIFIRLAR(temp_app_data):
    """🔴 D1 (denetim 2026-08-24): seans AKTİFKEN buluta push edilmiş olabilir (worker 60 sn
    interval → 1 dk'dan uzun HER seans; yerel sync_status=1). Kapanış `sync_status`'u 0'a
    ÇEKMEZSE bir sonraki PUSH ('WHERE sync_status=0') kapanışı HİÇ görmez → bulut kopyası SONSUZA
    DEK 'active' kalır (diğer cihazlarda/raporlarda seans hep açık, end_time/duration bulutta hiç
    oluşmaz). Kapanış senkronlanmayı İŞARETLEMELİ."""
    from database.treatment_history_db import get_treatment_db

    db = get_treatment_db(temp_app_data)
    sid = db.start_session("Manual", operator_name="Vet", patient_name="Boncuk")
    # Seans aktifken buluta push edildi → sync_status=1 (worker'ın yaptığı).
    with db._get_connection() as c:
        c.execute("UPDATE treatment_sessions SET sync_status=1 WHERE id=?", (sid,))
        c.commit()
    db.end_session(sid, duration_minutes=30, session_status="completed")
    assert _sync_status_oku(db, sid) == 0, (
        "kapanış sync_status'u 0'a çekmedi — bir sonraki PUSH ('WHERE sync_status=0') kapanışı "
        "görmez, bulut kopyası sonsuza dek 'active' kalır (D1 kök nedeni)"
    )


class _PushHatali(_FakeSupabase):
    """PUSH (upsert_session) AĞ HATASIYLA düşer; PULL (resolve_sessions) çalışır. Gerçekçi: bulut
    push'u ağ hatasıyla başarısız olur (sık), o döngüde PULL yine de bayat-active getirir."""

    def rpc(self, name, params=None):
        if name == "upsert_session":
            raise RuntimeError("bulut push agi hatasi (test)")
        return _FakeRpc(self._resolve if name == "resolve_sessions" else [])


def test_KRITIK_D1_bayat_active_PULL_PUSH_bayragini_SILMEZ(temp_app_data, monkeypatch):
    """🔴 D1 (denetim 2026-08-24): PUSH başarısızken (sync_status=0 KALIR) gelen bayat-active PULL,
    korunan kapanışın bekleyen PUSH bayrağını KOŞULSUZ `sync_status=1` ile silmemeli — yoksa
    kapanış CASE ile korunsa bile bir daha ASLA PUSH edilmez ve bulut sonsuza dek 'active' kalır.
    Kapanış korunuyorsa sync_status da korunur (aynı CASE koşulu)."""
    from servers.sync_worker import CloudSyncWorker

    db, sid = _kapali_seans_kur(temp_app_data)
    assert _sync_status_oku(db, sid) == 0, "önkoşul: kapanış PUSH bekliyor (sync_status=0)"

    bayat = {
        "id": sid,
        "session_date": "2026-08-22",
        "start_time": "2026-08-22T10:00:00",
        "end_time": None,  # bayat-açık bulut kopyası
        "duration_minutes": None,
        "treatment_mode": "Manual",
        "target_condition": None,
        "frequency_hz": 42.0,
        "intensity_mt": None,
        "pulse_duration_ms": None,
        "session_status": "active",
        "created_at": "2026-08-22T10:00:00",
    }
    # PUSH ağ hatasıyla düşer → kapanış sync_status=0 KALIR; aynı döngüde PULL bayat-active gelir.
    monkeypatch.setenv("PEMF_CLOUD_PATIENT_SYNC", "1")
    w = CloudSyncWorker("", "")
    w.client = _PushHatali([bayat])
    w.patient_sync_enabled = True
    w.device_id = "test-device"
    w._sync_sessions(db)

    assert _sync_status_oku(db, sid) == 0, (
        "PUSH başarısızken bayat-active PULL, korunan kapanışın PUSH bayrağını (sync_status 0→1) "
        "SİLDİ → kapanış bir daha ASLA PUSH edilmez, bulut kopyası sonsuza dek 'active' (D1)"
    )
    # Kapanış üçlüsü de korunmalı (mevcut monotonik-kapanış koruması bozulmasın):
    sonra = _seans_oku(db, sid)
    assert sonra["end_time"] and sonra["session_status"] != "active", "kapanış PULL'da bayat-active ile ezildi"


def test_KARSIT_KANIT_gercek_kapanis_bulutttan_UYGULANIR(temp_app_data, monkeypatch):
    """Baska cihazda kapatilan seansin kapanisi yerelde de gorunmeli — koruma yalniz
    'dolu → NULL' yonunu keser, 'NULL/eski → dolu' yonunu DEGIL."""
    from database.treatment_history_db import get_treatment_db

    db = get_treatment_db(temp_app_data)
    sid = db.start_session("Manual", operator_name="Vet", patient_name="Pamuk")  # ACIK birakildi

    kapali_bulut = {
        "id": sid,
        "session_date": "2026-08-22",
        "start_time": "2026-08-22T10:00:00",
        "end_time": "2026-08-22T10:45:00",
        "duration_minutes": 45,
        "treatment_mode": "Manual",
        "target_condition": None,
        "frequency_hz": None,
        "intensity_mt": None,
        "pulse_duration_ms": None,
        "session_status": "completed",
        "created_at": "2026-08-22T10:00:00",
    }
    _pull_kos(db, [kapali_bulut], monkeypatch)

    sonra = _seans_oku(db, sid)
    assert sonra["end_time"] == "2026-08-22T10:45:00", "buluttaki GERCEK kapanis yerel acik seansa uygulanmadi"
    assert sonra["duration_minutes"] == 45
    assert sonra["session_status"] == "completed"
