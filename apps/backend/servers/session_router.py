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
    # DENETIM 2. TUR [2.1] (2026-08-20): bobinler SEANSSIZ da calisir (CoilParameterPanel →
    # /api/coil/{id}/control _active_session'a dokunmaz). APK kurulumunun tibbi-guvenlik kapisi
    # (useApkGuncelleme) cihaza yalniz is_active'i soruyordu → seanssiz calisan bobinlerde Android
    # yukleyicisi kontrol ekraninin ustune ACILIYORDU. Canli-durumdan turetilen iki alan HER yanitta
    # tasinir; istemci `is_active || hardware_running`a bakar. SALT-OKUNUR (yukaridaki kural aynen):
    # yalniz snapshot okunur, ne canli-durum ne seans MUTATE edilir. Eski istemci alanlari yok sayar.
    with _api._live_state_lock:
        # ⚠️ `coils` LISTE DEGIL, 0..7 anahtarli SOZLUK (live_state.py:129) → indeksle erisilir.
        _coils = _api._live_state["coils"]
        _calisanlar = [int(_coils[i].get("id", i + 1)) for i in range(8) if _coils[i].get("running")]
    sess["hardware_running"] = bool(_calisanlar)
    sess["running_coil_ids"] = _calisanlar
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


class ParametreGuncellePayload(BaseModel):
    """Seans ORTASINDA uygulanan parametre değişikliği (sahip isteği 2026-09-11).

    Sahip: "100 Hz ile başlattım 20 dk, 10. dakikada 150 Hz yapmak istiyorum; hem toplu
    hem tek bobin için, faz/duty/süre hepsi için değişiklik yapma özgürlüğü istiyorum."

    ⚠️ BU UÇ DONANIMA DOKUNMAZ. Bobinlere yeni parametreyi `/api/coil/batch` (ya da tek
    bobin için `/api/coil/{id}/control`) gönderir; burası YALNIZ KAYIT ve GÖRÜNÜRLÜK
    tarafını düzeltir. Sebep: donanım sürüş mantığı TEK YERDE kalsın — ikinci bir sürüş
    yolu açmak, güvenlik değişmezlerini (STM kopuk kapısı, duty klempi, jeton kapısı)
    ikinci kez uygulamayı gerektirirdi ve o kopya kaçınılmaz olarak ayrışırdı.
    """

    frequency: float | None = None
    duty: float | None = None
    phase: float | None = None
    duration_minutes: int | None = None
    coil_ids: list[int] = []


@router.post("/api/session/parametre_guncelle")
def parametre_guncelle(payload: ParametreGuncellePayload):
    """Aktif seansın ÖZET KARTINI ve DOZ KAYDINI, ortada değişen parametreye göre tazeler.

    ⚠️ NEDEN GEREKLİ — KART YALAN SÖYLERDİ:
    Bobinlere yeni frekans gönderildiğinde bobin kartları ACK üzerinden kendiliğinden
    güncelleniyor (`update_live_coil_from_stm`), ama üstteki AKTİF SEANS kartı seans
    başındaki değeri göstermeye devam ediyordu. Operatör 150 Hz'e geçtikten sonra ekranda
    hâlâ "100 Hz" görürdü — uygulanan doz ile gösterilen doz AYRIŞIRDI.

    ⚠️ DOZ KAYDI DA TAZELENİR: `session_parameters`e değişiklik işlenir. Seans satırındaki
    `frequency_hz` seans BAŞINDAKİ reçetedir ve öyle KALIR (geçmişteki karşılaştırmaları
    bozmamak için); değişiklikler ayrı parametre satırları olarak birikir, böylece
    "bu seansta ne uygulandı" sorusu kaydın kendisinden cevaplanabilir.

    Seans yoksa 409: ortada olmayan bir seansın parametresi güncellenemez (donanım
    sürüşü ayrı bir yoldan zaten yapılabilir).
    """
    from servers import api_server as _api

    with _api._session_lock:
        aktif = bool(_api._active_session.get("is_active"))
        sid = _api._active_session.get("db_session_id")
    if not aktif:
        raise HTTPException(status_code=409, detail="Aktif seans yok — güncellenecek parametre yok.")

    # ── 1) Aktif seans kartı (arayüzün üstünde duran özet) ──────────────────────────
    # ⚠️ YALNIZ `frequencyHz`: seans özet kartı duty GÖSTERMEZ (alanları için bkz.
    # live_state `activeTreatment`). Gösterilmeyen bir alanı doldurmak, sözleşmeye
    # okunmayan veri eklemek olurdu; duty zaten bobin kartlarında ACK'ten geliyor.
    with _api._live_state_lock:
        at = _api._live_state["activeTreatment"]
        if payload.frequency is not None:
            at["frequencyHz"] = float(payload.frequency)
        anlik = dict(at)
    _api.live_state._ws_broadcast_sync({"type": "session_update", "data": anlik})

    # ── 2) Doz kaydı (best-effort: DB hatası sürüşü/seansı DURDURMAZ) ───────────────
    yazildi = False
    if sid:
        try:
            from database.treatment_history_db import get_treatment_db

            db = get_treatment_db(_api._app_data_dir())
            # ⚠️ ARTAN ANAHTAR: her değişiklik AYRI satır olarak birikir. Tek bir
            # "guncel_frekans" anahtarını üzerine yazmak, seans içindeki değişim
            # GEÇMİŞİNİ siler — "10. dakikada 150'ye çıktık" bilgisi kaybolurdu.
            import time as _t

            damga = int(_t.time())
            for ad, deger, birim in (
                ("degisiklik_frekans_hz", payload.frequency, "Hz"),
                ("degisiklik_duty_yuzde", payload.duty, "%"),
                ("degisiklik_faz_derece", payload.phase, "°"),
                ("degisiklik_sure_dk", payload.duration_minutes, "dk"),
            ):
                if deger is not None:
                    db.set_session_parameter(sid, f"{ad}@{damga}", str(deger), birim)
            if payload.coil_ids:
                db.set_session_parameter(
                    sid, f"degisiklik_bobinler@{damga}", ",".join(str(c) for c in payload.coil_ids), ""
                )
            yazildi = True
        except Exception:
            logging.exception("parametre degisikligi kayda yazilamadi (surus ETKILENMEDI)")

    return {
        "status": "success",
        "session_id": sid,
        "kayda_yazildi": yazildi,
        "frequencyHz": anlik.get("frequencyHz"),
    }
