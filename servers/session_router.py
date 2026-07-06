"""Seans (session) uclari (refactor B1 Faz B: api_server.py'den ayrildi — modular router).

Davranis BIREBIR korunur. Paylasilan runtime durumu (_active_session, _session_lock,
_sensor_sample_buffer(_lock), _app_data_dir) cagri-zamani lazy import ile servers.api_server'dan
okunur (circular yok). Yollar birebir korunur. GUVENLIK: /api/session/active salt-okunur
(global _active_session'i MUTATE ETMEZ) — watchdog STOP'unu bastirma riski yok.

NOT: /api/session/start + /api/session/stop (bobin-suren, safety-kritik) BURADA DEGIL —
human-review batch'inde ayrica ele alinacak.
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["session"])


class SessionNotesPayload(BaseModel):
    notes: str = ""
    patient_name: str = ""
    mode: str = "Manuel"
    target_condition: str = ""
    frequency: float = 0.0
    intensity: float = 0.0
    duration_minutes: int = 0


@router.get("/api/session/active")
async def get_active_session():
    """Return current active session state."""
    from servers import api_server as _api
    import time
    with _api._session_lock:
        sess = dict(_api._active_session)
    if sess.get("is_active"):
        elapsed = int(time.time() - sess.get("start_time", time.time()))
        total = sess.get("duration_minutes", 0) * 60
        remaining = max(0, total - elapsed)
        sess["elapsed_sec"] = elapsed
        sess["remaining_sec"] = remaining
        sess["remaining_min"] = remaining // 60
        # Süre dolduysa yalnız YANITTA göster — GLOBAL _api._active_session'ı MUTATE ETME. GET salt-okunur
        # olmalı; aksi halde watchdog STOP'unu bastırıp bobinler fiziksel açık kalabilir (gerçek
        # durdurma _session_duration_watchdog'un işi).
        if remaining == 0 and total > 0:
            sess["is_active"] = False
    return sess


@router.post("/api/session/notes")
async def save_session_notes(payload: SessionNotesPayload):
    """Seans-sonrası gözlem notu + seansı history'ye yaz (PyQt observation_notes karşılığı).

    Asama-2 (1c): seans BASINDA gercek db_session_id olustuysa ARTIK YENI satir ACMAZ →
    o satiri GUNCELLER (notlar + parametreler). Sensor buffer zaten /api/session/stop'ta
    flush edildiginden burada tekrar flush ETMEZ (cift-kayit onlenir). db_session_id yoksa
    eski start_session+end_session fallback'i korunur (geriye uyumlu)."""
    from servers import api_server as _api
    try:
        from database.treatment_history_db import get_treatment_db

        app_data = _api._app_data_dir()
        db = get_treatment_db(app_data)

        # Aktif seansin DB durumunu al (varsa).
        with _api._session_lock:
            existing_sid = _api._active_session.get("db_session_id")

        if existing_sid:
            # Var olan seans satirini GUNCELLE (yeni satir acma → cift-kayit yok).
            db.end_session(
                existing_sid,
                parameters={"frequency_hz": payload.frequency, "intensity_mt": payload.intensity},
                patient_notes=payload.notes or None,
                duration_minutes=(int(payload.duration_minutes) if payload.duration_minutes else None),
            )
            # Buffer zaten /stop'ta flush edildi; tekrar flush etme (idempotent).
            return {"status": "success", "session_id": existing_sid, "sensor_samples": 0, "updated": True}

        # Eski yol (db_session_id yok): tek-seferlik start+end fallback'i.
        sid = db.start_session(
            treatment_mode=payload.mode,
            target_condition=payload.target_condition or None,
            patient_name=payload.patient_name or None,
        )
        db.end_session(
            sid,
            parameters={"frequency_hz": payload.frequency, "intensity_mt": payload.intensity},
            patient_notes=payload.notes or None,
            duration_minutes=int(payload.duration_minutes),
        )
        # Seans boyunca toplanan sensör örneklerini gerçek session_id ile kalıcı kaydet.
        pending_count = 0
        try:
            with _api._sensor_sample_buffer_lock:
                pending = list(_api._sensor_sample_buffer)
                _api._sensor_sample_buffer.clear()
            if pending:
                pending_count = db.add_sensor_samples_batch(sid, pending)
                logging.info("Sensör örnekleri kaydedildi: %d satır (session_id=%s)", pending_count, sid)
        except Exception:
            logging.exception("Sensör örnekleri kaydedilemedi")
        return {"status": "success", "session_id": sid, "sensor_samples": pending_count}
    except Exception:
        # B3 güvenlik-fix: ham str(e) SIZMAZ (zaten loglanıyor) — generic detail.
        logging.exception("save_session_notes failed")
        raise HTTPException(status_code=500, detail="Not kaydedilemedi")
