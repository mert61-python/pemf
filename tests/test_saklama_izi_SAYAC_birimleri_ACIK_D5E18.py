# -*- coding: utf-8 -*-
"""2-F incelemesi §10 #18 (D5 · yardımcı E · A1 K4 notları) — saklama denetim izlerinin SAYAÇ BİRİMLERİ açık: eski anahtarlar KALIR
(eski okuyucular), anlamı söyleyen yeni anahtar eklenir. Davranış (silme / maskeleme) DEĞİŞMEZ.

ÖLÇÜLEN (HEAD 9c6d4505):
  (1) `retention.olay_silindi` iz `detail.kritik_korunan` = silmeden SONRA süresi dolmuş TÜM olayların sayısı (`created_at < kesim`) —
      kritik olmayanlar az önce silindiği için bu, saklanan süresi dolmuş KRİTİK olayların BİRİKİMLİ toplamıdır; her turun izi aynı
      (büyüyen) sayıyı yeniden yazar. Ad "bu turda korunan" gibi okunuyordu (2-F A1 K4). Seans silme izlerindeki aynı adlı anahtar ise
      o silmenin koruduğu kritik olaylardır (akış) — iki anlam tek ad.
  (2) D2.58 `retention.pii_maskelendi` iz `item_count` = seans SÜTUNU maskelenen seans SATIRI; `detail.parametre` = parametre SATIRI. Operatörün
      onayladığı / ekranın "N kayıt" dediği sayı ise ETKİLENEN SEANS (`redaksiyon_bekleyen_sayisi` — seans sütunu YA DA PII parametresi):
      yalnız parametresinde PII kalan seans izde HİÇ görünmüyordu (ölçüldü: onay 2, iz 1 + parametre 1).
Düzeltme: (1) iz `detail.suresi_dolmus_kritik_toplam` (aynı sayı, birikimli olduğu adında) · (2) iz `detail.etkilenen_seans` (maskelemeden
hemen önce aynı ölçütle sayılan seans; sayılamazsa null). Kullanıcı ekranına / PDF'e GİTMEZ (yalnız `/api/audit/events`, destek paketi
yalnız tür sayar) → yeni kullanıcı metni YOK.
GERÇEK: TreatmentHistoryDB (tmp), `purge_old_session_events`, `apply_data_retention_policy`.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

import pytest

GUN = 86400.0


@pytest.fixture
def db(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    for ad in ("PEMF_RETAIN_PII_DAYS", "PEMF_MASK_HISTORY_PII", "PEMF_RETAIN_EVENT_DAYS"):
        monkeypatch.delenv(ad, raising=False)
    d = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield d
    finally:
        d.close_connections()


def _olay(db, sid, tur, onem, gun_once) -> int:
    eid = db.record_session_event(sid, tur, {"g": gun_once}, severity=onem)
    with db._get_connection() as c:
        c.execute("UPDATE session_events SET created_at=? WHERE id=?", (time.time() - gun_once * GUN, eid))
        c.commit()
    return eid


def _ayrintilar(db, tur) -> list:
    return [json.loads(e["detail"]) for e in reversed(db.denetim_oku(50, tur))]


def test_KRITIK_olay_izi_kritik_sayaci_BIRIKIMLI_oldugu_adiyla_tasinir_eski_anahtar_KALIR(db):
    sid = int(db.start_session(treatment_mode="Manuel", patient_name="Pamuk E18"))
    _olay(db, sid, "emergency_stop", "critical", 400)
    _olay(db, sid, "estop_mandali_sifirlandi", "warning", 400)
    _olay(db, sid, "seans_notu", "info", 400)
    assert db.purge_old_session_events(365) == 1
    _olay(db, sid, "seans_notu", "info", 380)  # ikinci tur: yalnız bir kritik olmayan eski olay; YENİ kritik yok
    assert db.purge_old_session_events(365) == 1
    _olay(db, sid, "emergency_stop", "critical", 370)  # üçüncü tur: bir kritik daha süresini doldurdu
    _olay(db, sid, "seans_notu", "info", 370)
    assert db.purge_old_session_events(365) == 1
    ayr = _ayrintilar(db, "retention.olay_silindi")
    assert [a.get("kritik_korunan") for a in ayr] == [2, 2, 3], (
        f"eski anahtar düştü / değeri değişti (eski okuyucular): {ayr}"
    )
    assert [a.get("suresi_dolmus_kritik_toplam") for a in ayr] == [2, 2, 3], (
        f"izde kritik sayacının BİRİKİMLİ (süresi dolmuş tüm kritikler) olduğunu söyleyen alan yok / yanlış: {ayr}"
    )


def _seans(db, ad, gun_once, operator="Dr. Test", parametreler=None):
    tarih = (datetime.now() - timedelta(days=gun_once)).strftime("%Y-%m-%d")
    with db._get_connection() as c:
        cur = c.cursor()
        cur.execute(
            "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode, patient_name, operator_name) "
            "VALUES (?,?,?,?,?)",
            (tarih, "10:00", "Manuel", ad, operator),
        )
        sid = cur.lastrowid
        for ad_, deger in (parametreler or {}).items():
            cur.execute(
                "INSERT INTO session_parameters (session_id, parameter_name, parameter_value) VALUES (?,?,?)",
                (sid, ad_, deger),
            )
        c.commit()
        return sid


def test_KRITIK_pii_izi_ETKILENEN_SEANS_onay_sayisiyla_AYNI_birimde(db):
    _seans(db, "Boncuk E18", 400)  # seans sütunu (ad + hekim)
    _seans(
        db, "[REDACTED]", 400, operator="[REDACTED]", parametreler={"patient_owner_email": "e18@ornek.com"}
    )  # yalnız parametre
    _seans(db, "Taze E18", 10)  # süresi dolmamış
    bekleyen = db.redaksiyon_bekleyen_sayisi(365)
    assert bekleyen == 2, f"aparat: bekleyen {bekleyen}"
    db.pii_onayla(gun=365, sayi=bekleyen)
    r = db.apply_data_retention_policy(
        sensor_retain_days=0, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=365
    )
    assert (r["sessions_pii_redacted"], r["parameters_pii_redacted"]) == (1, 1), f"maskeleme davranışı değişti: {r}"
    izler = db.denetim_oku(50, "retention.pii_maskelendi")
    assert len(izler) == 1 and izler[0]["item_count"] == 1, f"eski iz sayısı değişti (eski okuyucular): {izler}"
    ayr = json.loads(izler[0]["detail"])
    assert ayr.get("parametre") == 1 and ayr.get("gun") == 365, ayr
    assert ayr.get("etkilenen_seans") == bekleyen, (
        f"izde operatörün onayladığı birimde (etkilenen seans = {bekleyen}) sayı yok — yalnız parametresi maskelenen seans izde "
        f"görünmüyor: {ayr}"
    )
