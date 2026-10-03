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
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["session"])


class SessionNotesPayload(BaseModel):
    notes: str = ""
    patient_name: str = ""
    mode: str = "Manuel"
    target_condition: str = ""
    frequency: float = 0.0
    intensity: float = 0.0
    duration_minutes: int = 0
    operator_email: str = ""  # klinik-içi sahiplik (eski alan; D1.78'den beri yeni satır AÇILMAZ)
    #: D1.66 (B-1.2): notun yazılacağı seansın DB kimliği (`/api/session/start` yanıtı `session.db_session_id`).
    #: Eski istemci (APK 2.3.34) göndermez → geriye uyum dalı (`_not_hedefi`).
    session_id: int | None = None


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
        # D1.70 (Y5): seans ortası süre değişikliği kesin bitiş anını yazar — kalan süre ondan (bekçiyle AYNI ölçüt).
        if sess.get("bitis_mono") is not None:
            remaining = max(0, int(float(sess["bitis_mono"]) - time.monotonic()))
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


def _not_hedefi(payload: "SessionNotesPayload", db, bellek: dict) -> tuple[int, str]:
    """D1.66 · D1.78: gözlem notunun yazılacağı seans → (db kimliği, yol). Bulunamazsa HTTPException; YENİ satır AÇILMAZ.

    Eskiden hedef süreçteki SON `db_session_id`'ydi: A'nın notu arada başlamış B'nin satırına düşüyor (B sürerken onu
    `end_session` ile KAPATIYORDU), bellekte seans yoksa (yeniden başlatma) her çağrı YENİ bir 'completed' satır açıyordu.
      1) İstemci kimliği verdiyse (yeni istemci) YALNIZ o satır; yoksa 404.
      2) Kimliksiz (eski istemci, APK 2.3.34): bellekteki seans BİTMİŞSE ve hastası aynıysa o (bugünkü akış).
      3) Değilse bu hastanın SON BİTMİŞ seansı (12 sa) — süren seans başka hastanındır, kurtarılmış satır dahil.
      4) Hiçbiri yoksa 409: not kaydedilmez (istemci notu tutar, operatör görür)."""
    if payload.session_id is not None:
        ozet = db.seans_ozeti(int(payload.session_id))
        if not ozet:
            raise HTTPException(status_code=404, detail="Seans kaydı bulunamadı — not kaydedilmedi.")
        return int(payload.session_id), "kimlik"
    b_sid = bellek.get("db_session_id")
    b_hasta = (bellek.get("patient_name") or "").strip()
    p_hasta = (payload.patient_name or "").strip()
    if b_sid and not bellek.get("is_active") and (not p_hasta or not b_hasta or p_hasta == b_hasta):
        return int(b_sid), "bellek"
    sid = db.son_biten_seans_kimligi(p_hasta)
    if sid:
        return int(sid), "hasta"
    raise HTTPException(
        status_code=409,
        detail="Notun ait olduğu seans belirlenemedi — not kaydedilmedi (yeni seans kaydı AÇILMAZ).",
    )


@router.post("/api/session/notes")
def save_session_notes(payload: SessionNotesPayload, request: Request):
    """Seans-sonrası gözlem notu + not ekranındaki doz parametreleri → seansın KENDİ satırına (yeni satır AÇILMAZ).

    Hedef: `_not_hedefi` (D1.66 · D1.78). Seans DB'de zaten kapandıysa (stop / bekçi / E-stop / kurtarma) YALNIZ not ve
    parametre güncellenir — gerçek süre ve durum EZİLMEZ (DENETİM P1). Bellekteki BİTMİŞ seans DB'de henüz kapanmadıysa
    (eski akış: `/stop` hiç çağrılmadı) normal finalize. SÜREN seansa not yazılır ama seans KAPATILMAZ.
    Sensör tamponu `/api/session/stop`'ta flush edilir; burada tekrar flush edilmez."""
    from servers import api_server as _api

    db = _api._get_treatment_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Tedavi kaydı veritabanı hazır değil — not kaydedilmedi.")
    with _api._session_lock:
        bellek = dict(_api._active_session)
    sid, yol = _not_hedefi(payload, db, bellek)
    try:
        bellek_bu = bellek.get("db_session_id") == sid
        ozet = db.seans_ozeti(sid) or {}
        if (
            bellek_bu
            and not bellek.get("is_active")
            and not bellek.get("db_finalized")
            and ozet.get("session_status") == "active"
        ):
            # Seans bellekte bitti ama DB'de kapanmadı (ör. /stop hiç çağrılmadı) → normal finalize.
            db.end_session(
                sid,
                parameters={"frequency_hz": payload.frequency, "intensity_mt": payload.intensity},
                patient_notes=payload.notes or None,
                duration_minutes=(int(payload.duration_minutes) if payload.duration_minutes else None),
            )
            return {"status": "success", "session_id": sid, "sensor_samples": 0, "updated": True, "hedef": yol}
        # DENETIM P1: kapanmış seansta end_session TEKRAR çağrılmaz (gerçek süreyi planlananla ezerdi); süren seans da
        # burada kapatılmaz. Yalnız not + parametre.
        db.update_session_finalized_extras(
            sid,
            notes=(payload.notes or None),
            frequency_hz=(payload.frequency or None),
            intensity_mt=(payload.intensity or None),
        )
        return {
            "status": "success",
            "session_id": sid,
            "sensor_samples": 0,
            "updated": True,
            "durationPreserved": True,
            "hedef": yol,
        }
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

    # D1.99 (S-1.6): NaN/Infinity 422 — kart ve doz kaydına sonlu olmayan değer girmesin (WS/JSON bozulur).
    model_config = ConfigDict(allow_inf_nan=False)

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
        seans_bobinleri = list(_api._active_session.get("coil_ids") or [])
        seans_kimligi = _api._active_session.get("session_id")
        _seans_anlik = dict(_api._active_session)
    if not aktif:
        raise HTTPException(status_code=409, detail="Aktif seans yok — güncellenecek parametre yok.")

    # ── D1.70 (B-1.8 · sahip kararı Y5): girilen süre KALAN süredir (şimdiden itibaren) ───────────────────────
    # Arayüz yeni süreyi bobinlere "şimdiden itibaren" gönderir (`/coil/batch` duration = dk × 60). Eskiden burada
    # yalnız parametre satırı yazılıp "success" dönülüyordu; seansın süresine ve süre bekçisine İŞLENMİYORDU:
    # kısaltmada bobinler yeni sürede durup seans eski sürede "completed 20" kapanıyor, uzatmada bekçi seansı eski
    # sürede kesiyordu. Kayda GERÇEK sürüş süresi yazılır (bekçi/durdurma `_kayit_suresi_dk` — monotonik geçen süre).
    if payload.duration_minutes is not None:
        if int(payload.duration_minutes) <= 0:
            raise HTTPException(
                status_code=422, detail="Kalan süre en az 1 dakika olmalı — süre değişikliği UYGULANMADI."
            )
        from servers.ai_router import _ai_seansi_mi

        if _ai_seansi_mi(_seans_anlik):
            raise HTTPException(
                status_code=409,
                detail="AI seansının süresi hekim onayının mührüdür — buradan DEĞİŞTİRİLMEDİ (yeni öneri/onay gerekir).",
            )
        import math as _m
        import time as _tm

        with _api._session_lock:
            s = _api._active_session
            if not (s.get("is_active") and s.get("session_id") == seans_kimligi):
                raise HTTPException(status_code=409, detail="Seans bu sırada değişti — süre değişikliği UYGULANMADI.")
            _simdi = _tm.monotonic()
            _kalan_s = int(payload.duration_minutes) * 60
            s["bitis_mono"] = _simdi + _kalan_s
            _sm = s.get("start_mono")
            _gecen = (_simdi - _sm) if _sm is not None else 0.0
            # Planlanan TOPLAM (gösterim): geçen + kalan, dakikaya yukarı yuvarlı. Bekçi `bitis_mono`yu esas alır.
            s["duration_minutes"] = int(_m.ceil((_gecen + _kalan_s) / 60.0))
            s["girilen_kalan_dk"] = int(payload.duration_minutes)

    # ── D1.99 (B-1.9 · S-1.2): kart ve doz kaydı donanıma GİDEN (normalize) değeri yazar ─────────────────
    # Bobinlere yeni parametre `/api/coil/batch`la gider ve orada protokol sınırından (Ö.4-Y9 — taşıyıcı,
    # KALDIRILMAZ) geçer: 30000 Hz → 25000 (STM), 0,5 Hz → 1, duty −50 → 0. Kayıt ham isteği yazarsa
    # "kaydedilen ≠ uygulanan" olur. STM bobini hedefteyse STM sınırı, yalnız ESP ise ESP sınırı uygulanır.
    from utils.stm32_protocol_limits import (
        duty_percent_to_ratio,
        normalize_esp_frequency_hz,
        normalize_frequency_hz,
        normalize_phase_deg,
    )

    _hedef = [int(c) for c in (payload.coil_ids or seans_bobinleri)] or list(_api.STM_COIL_IDS)
    _stm_hedef = any(c in _api.STM_COIL_IDS for c in _hedef)
    _f_norm = normalize_frequency_hz if _stm_hedef else normalize_esp_frequency_hz
    frekans = None if payload.frequency is None else float(_f_norm(payload.frequency))
    duty = None if payload.duty is None else float(duty_percent_to_ratio(payload.duty) * 100.0)
    faz = None if payload.phase is None else float(normalize_phase_deg(payload.phase))

    # ── 1) Aktif seans kartı (arayüzün üstünde duran özet) ──────────────────────────
    # ⚠️ YALNIZ `frequencyHz`: seans özet kartı duty GÖSTERMEZ (alanları için bkz.
    # live_state `activeTreatment`). Gösterilmeyen bir alanı doldurmak, sözleşmeye
    # okunmayan veri eklemek olurdu; duty zaten bobin kartlarında ACK'ten geliyor.
    with _api._live_state_lock:
        at = _api._live_state["activeTreatment"]
        if frekans is not None:
            at["frequencyHz"] = frekans
        anlik = dict(at)
    _api.live_state._ws_broadcast_sync({"type": "session_update", "data": anlik})

    # ── 2) Doz kaydı (best-effort: DB hatası sürüşü/seansı DURDURMAZ) ───────────────
    yazildi = False
    if sid:
        try:
            db = _api._get_treatment_db()  # seans yaşam döngüsüyle AYNI erişim (eskiden ayrı `get_treatment_db` yolu)
            # ⚠️ ARTAN ANAHTAR: her değişiklik AYRI satır olarak birikir. Tek bir
            # "guncel_frekans" anahtarını üzerine yazmak, seans içindeki değişim
            # GEÇMİŞİNİ siler — "10. dakikada 150'ye çıktık" bilgisi kaybolurdu.
            import time as _t

            damga = int(_t.time())
            for ad, deger, birim in (
                ("degisiklik_frekans_hz", frekans, "Hz"),
                ("degisiklik_duty_yuzde", duty, "%"),
                ("degisiklik_faz_derece", faz, "°"),
                # Süre: Y5 — girilen değer KALAN süredir (yukarıda seansa işlendi); girilen değer de saklanır.
                ("degisiklik_sure_dk", payload.duration_minutes, "dk (kalan)"),
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
