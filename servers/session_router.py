# Author: mertaygn, cglrgrkn
"""Seans (session) uclari (refactor B1 Faz B: api_server.py'den ayrildi — modular router).

Davranis BIREBIR korunur. Paylasilan runtime durumu (_active_session, _session_lock,
_sensor_sample_buffer(_lock), _app_data_dir) cagri-zamani lazy import ile servers.api_server'dan
okunur (circular yok). Yollar birebir korunur. GUVENLIK: /api/session/active salt-okunur
(global _active_session'i MUTATE ETMEZ) — watchdog STOP'unu bastirma riski yok.

NOT: /api/session/start + /api/session/stop (bobin-suren, safety-kritik) BURADA DEGIL —
human-review batch'inde ayrica ele alinacak.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
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
    operator_email: str = ""  # klinik-içi sahiplik (fallback start_session için)


@router.get("/api/session/active")
def get_active_session():
    """Return current active session state."""
    import time

    from servers import api_server as _api

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
def save_session_notes(payload: SessionNotesPayload, request: Request):
    from servers.auth import cozumlenmis_operator

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
            already_final = bool(_api._active_session.get("db_finalized"))

        if existing_sid:
            if already_final:
                # DENETIM P1: /api/session/stop GERCEK sureyi (now - started_epoch) + end_time'i
                # zaten yazdi ve db_finalized bayragini dikti. Burada end_session'i TEKRAR
                # cagirmak o alanlari EZIYORDU: istemci PLANLANAN sureyi gonderdiginde 4 dk'lik
                # seans 20 dk gorunuyor; alan hic gelmezse (0 → None) end_session sureyi
                # `now - start` ile yeniden hesapliyor → notu 45 dk sonra yazan operatorde
                # 65 dk cikiyordu. db_finalized tam bunun icin yaziliyordu ama HIC OKUNMUYORDU.
                # Artik yalniz not + parametre guncellenir; zaman/durum alanlarina dokunulmaz.
                db.update_session_finalized_extras(
                    existing_sid,
                    notes=(payload.notes or None),
                    frequency_hz=(payload.frequency or None),
                    intensity_mt=(payload.intensity or None),
                )
                return {
                    "status": "success",
                    "session_id": existing_sid,
                    "sensor_samples": 0,
                    "updated": True,
                    "durationPreserved": True,
                }
            # Seans DB'de henuz kapatilmamis (ör. /stop hic cagrilmadi) → normal finalize.
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
            # ⚠️ 2026-08-09 (Tier 1): sahibi sunucu belirler (bkz. auth.cozumlenmis_operator).
            operator_email=cozumlenmis_operator(request, payload.operator_email) or None,
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
