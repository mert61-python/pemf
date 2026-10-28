# -*- coding: utf-8 -*-
"""Y208 (S-D5.6) — operatör onaylı SÜRELİ PII maskelemesi `session_events` yüklerindeki hasta adını (`patient_name`) da maskeler; varsayılan KAPALI.

ÖLÇÜLEN (2-F incelemesi §10 #5 · A2 açık #7, D5 S-D5.6): `redact_old_session_pii` yalnız `treatment_sessions` sütunlarını ve PII
parametrelerini maskeliyordu; `SessionManager` yaşam döngüsü olayının (`session_started`) yükü `patient_name`'i düz taşıyordu (yazım anı maskesi
`PEMF_MASK_HISTORY_PII` kapalıyken) → süre dolup maskeleme onaylı koşsa da ad olay tablosunda SÜRESİZ kalıyordu. SAHİP KARARI Y208: maskeleme
açıksa olay yükündeki hasta adı da maskelenir; maskeleme varsayılan KAPALI kalır (onaysız / süre 0 → hiçbir şey değişmez).
⚠️ A-09 · D2.55: maskeleme KAPSAMI genişledi → kapsam imzası değişir → eski kapsamla verilmiş onay GEÇERSİZ (operatör yeniden onaylar).
⚠️ D2.58: ekranın "N kayıt" dediği (`redaksiyon_bekleyen_sayisi`) maskelemenin değiştirdiğiyle AYNI ölçüt — yalnız olayında ad kalan seans da sayılır.

GERÇEK: TreatmentHistoryDB (tmp; şifresiz), `record_session_event`, `redact_old_session_pii`, `apply_data_retention_policy`, denetim izi.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

AD = "Pamuk Y208"


@pytest.fixture
def db(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    for ad in ("PEMF_RETAIN_PII_DAYS", "PEMF_MASK_HISTORY_PII", "PEMF_RETAIN_EVENT_DAYS", "PEMF_ENCRYPT_AT_REST"):
        monkeypatch.delenv(ad, raising=False)
    d = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield d
    finally:
        d.close_connections()


def _seans(db, ad, gun_once, sutun_ad=None, operator="Dr Y208") -> int:
    tarih = (datetime.now() - timedelta(days=gun_once)).strftime("%Y-%m-%d")
    with db._get_connection() as c:
        cur = c.cursor()
        cur.execute(
            "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode, patient_name, operator_name) VALUES (?, ?, ?, ?, ?)",
            (tarih, f"{tarih} 10:00:00", "Manuel", sutun_ad if sutun_ad is not None else ad, operator),
        )
        c.commit()
        return int(cur.lastrowid)


def _olay(db, sid, ad, tur="session_started"):
    return db.record_session_event(
        sid,
        tur,
        {"event": tur, "session_id": sid, "patient_name": ad, "operator_name": "Dr Y208", "patient_id": "uuid-y208"},
    )


def _yuk(db, eid) -> dict:
    with db._get_connection() as c:
        return json.loads(c.execute("SELECT payload FROM session_events WHERE id = ?", (eid,)).fetchone()[0])


def test_KRITIK_suresi_dolan_seansin_OLAY_yukundeki_hasta_adi_MASKELENIR(db):
    eski = _seans(db, AD, 400)
    yeni = _seans(db, "Boncuk Y208", 10)
    e_eski = _olay(db, eski, AD)
    e_yeni = _olay(db, yeni, "Boncuk Y208")
    e_adsiz = db.record_session_event(eski, "seans_notu", {"not": "kontrol"})
    rapor = db.redact_old_session_pii(365)
    assert _yuk(db, e_eski).get("patient_name") == "[REDACTED]", (
        f"süresi dolan seansın OLAY yükünde hasta adı maskelenmedi (Y208 / S-D5.6): {_yuk(db, e_eski)}"
    )
    assert int(rapor.get("events_redacted", -1)) == 1, f"rapor olay sayısını taşımıyor / yanlış: {rapor}"
    y = _yuk(db, e_eski)
    assert y.get("patient_id") == "uuid-y208" and y.get("event") == "session_started", (
        f"maskeleme yükün geri kalanını bozdu: {y}"
    )
    assert _yuk(db, e_yeni).get("patient_name") == "Boncuk Y208", "süresi DOLMAMIŞ seansın olayı maskelendi"
    assert _yuk(db, e_adsiz) == {"not": "kontrol"}, "adı olmayan olay yükü değişti"
    # İkinci tur: maskelenecek kalmadı → sayaç 0 (D2.58 — her turda yeniden yazılmaz).
    assert int(db.redact_old_session_pii(365).get("events_redacted", -1)) == 0


def test_KRITIK_N_kayit_sayimi_YALNIZ_olayinda_ad_kalan_seansi_da_SAYAR_D258(db):
    sid = _seans(
        db, AD, 400, sutun_ad="[REDACTED]", operator="[REDACTED]"
    )  # seans sütunları zaten maskeli, olay yükünde ad DURUYOR
    assert db.redact_old_session_pii(365).get("sessions_redacted") == 0, (
        "aparat: seans sütunlarında maskelenecek alan kalmış"
    )
    _olay(db, sid, AD)
    assert db.redaksiyon_bekleyen_sayisi(365) == 1, (
        "yalnız olay yükünde ad kalan seans 'N kayıt' sayımında YOK — ekranın dediği maskelemenin değiştirdiğinden farklı (D2.58)"
    )
    db.redact_old_session_pii(365)
    assert db.redaksiyon_bekleyen_sayisi(365) == 0


def test_KRITIK_kapsam_imzasi_OLAY_alanini_icerir_ESKI_onay_GECERSIZ_A09(db):
    imza = db.pii_kapsam_imzasi()
    assert "olay:patient_name" in imza, (
        f"maskeleme kapsamı genişledi ama kapsam imzası olay alanını söylemiyor (A-09): {imza}"
    )
    eski_imza = imza.split("|olay:")[0]
    db._set_system_setting(
        db.PII_ONAY_ANAHTARI,
        json.dumps({"gun": 365, "sayi": 1, "kim": "dr@test", "zaman": "2026-10-01T10:00:00", "kapsam": eski_imza}),
        "test",
    )
    assert db.pii_onayi_var_mi(365) is False, (
        "ESKİ (olaysız) kapsamla verilmiş onay hâlâ geçerli — kapsam genişlemesi yeniden onay istemeli (A-09)"
    )
    db.pii_onayla(365, sayi=1, kim="dr@test")
    assert db.pii_onayi_var_mi(365) is True


def test_KRITIK_bakim_turu_ONAYLI_ise_olayi_maskeler_ve_IZE_olay_sayisini_yazar(db):
    sid = _seans(db, AD, 400)
    eid = _olay(db, sid, AD)
    db.pii_suresi_yaz(365)
    db.pii_onayla(365, sayi=1, kim="dr@test")
    rapor = db.apply_data_retention_policy(pii_retain_days=365)
    assert _yuk(db, eid).get("patient_name") == "[REDACTED]" and rapor.get("events_pii_redacted") == 1, rapor
    iz = db.denetim_oku(10, "retention.pii_maskelendi")
    assert len(iz) == 1 and json.loads(iz[0]["detail"]).get("olay") == 1, f"iz olay sayısını taşımıyor: {iz}"
    assert AD not in json.dumps(iz, ensure_ascii=False, default=str), "denetim izi hasta adını taşıyor"


def test_KARSIT_VARSAYILAN_KAPALI_onaysiz_ve_sure_0_iken_OLAY_DEGISMEZ(db):
    sid = _seans(db, AD, 400)
    eid = _olay(db, sid, AD)
    rapor = db.apply_data_retention_policy(pii_retain_days=365)  # onay YOK
    assert _yuk(db, eid).get("patient_name") == AD and rapor.get("pii_pending") == 1, rapor
    assert db.redact_old_session_pii(0).get("events_redacted", 0) == 0 and _yuk(db, eid).get("patient_name") == AD
