# -*- coding: utf-8 -*-
"""Y204 (S-D5.5) — sensör örneği ve ölü-outbox SAKLAMA silmeleri denetim izine TEK satır yazar: sayı + süre, İÇERİK YOK.

ÖLÇÜLEN (2-F incelemesi §10 #1, D5 S-D5.5): `purge_old_sensor_samples` ve `purge_old_dead_outbox` satır siliyor ama denetim izine
(`audit_events`, ekleme-only) hiçbir şey yazmıyordu; aynı bakım turundaki olay (`retention.olay_silindi`) ve doz
(`retention.doz_silindi`) silmeleri yazıyordu → asimetri. SAHİP KARARI Y204: tek iz satırı, yalnız silinen satır SAYISI ve saklama SÜRESİ
(gün); silinen verinin İÇERİĞİ (sensör değeri, outbox yükü, hasta adı) ize GİRMEZ. Yalnız gerçekten silinen turda (boş turlar iz biriktirmez).
Kullanıcı ekranına / PDF'e gitmez (yalnız `/api/audit/events`) → yeni kullanıcı metni YOK.

GERÇEK: TreatmentHistoryDB (tmp), `purge_old_sensor_samples`, `purge_old_dead_outbox`, `apply_data_retention_policy`.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest

GUN = 86400.0
_ICERIK = "Pamuk-Y204-gizli-icerik"


@pytest.fixture
def db(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    for ad in ("PEMF_RETAIN_PII_DAYS", "PEMF_MASK_HISTORY_PII", "PEMF_RETAIN_EVENT_DAYS", "PEMF_RETAIN_SENSOR_DAYS"):
        monkeypatch.delenv(ad, raising=False)
    d = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield d
    finally:
        d.close_connections()


def _sensor(db, sid, gun_once, n=1):
    ts = time.time() - gun_once * GUN
    with db._get_connection() as c:
        for _ in range(n):
            c.execute(
                "INSERT INTO sensor_samples (session_id, coil_id, sample_ts, temperature_c, magnetic_field_mt, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sid, "1", ts, 36.6, 1.25, json.dumps({"hasta": _ICERIK}), ts),
            )
        c.commit()


def _olu(db, gun_once, n=1, durum="dead"):
    ts = time.time() - gun_once * GUN
    with db._get_connection() as c:
        for _ in range(n):
            c.execute(
                "INSERT INTO outbox_messages (message_uuid, topic, payload, status, available_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), "pemf/test", json.dumps({"hasta": _ICERIK}), durum, ts, ts),
            )
        c.commit()


def _izler(db, tur) -> list:
    return list(reversed(db.denetim_oku(50, tur)))


def _say(db, tablo) -> int:
    with db._get_connection() as c:
        return int(c.execute(f"SELECT COUNT(*) FROM {tablo}").fetchone()[0])


def test_KRITIK_sensor_saklama_silmesi_TEK_iz_satiri_sayi_ve_sure_ICERIK_yok(db):
    sid = int(db.start_session(treatment_mode="Manuel", patient_name="Pamuk Y204"))
    _sensor(db, sid, 120, n=3)
    _sensor(db, sid, 10, n=2)  # süresi DOLMAMIŞ — kalır
    assert db.purge_old_sensor_samples(90) == 3 and _say(db, "sensor_samples") == 2
    iz = _izler(db, "retention.sensor_silindi")
    assert len(iz) == 1, f"sensör saklama silmesi denetim izine TEK satır yazmalı (Y204 / S-D5.5): {iz}"
    assert int(iz[0]["item_count"]) == 3 and iz[0]["scope"] == "otomatik", iz[0]
    assert json.loads(iz[0]["detail"]) == {"gun": 90}, (
        f"iz yalnız saklama süresini taşımalı (içerik YOK): {iz[0]['detail']}"
    )
    assert _ICERIK not in json.dumps(iz, ensure_ascii=False, default=str), "silinen verinin İÇERİĞİ ize sızdı"


def test_KRITIK_olu_outbox_saklama_silmesi_TEK_iz_satiri_sayi_ve_sure_ICERIK_yok(db):
    _olu(db, 45, n=2)
    _olu(db, 5, n=1)  # süresi dolmamış ölü — kalır
    _olu(db, 45, n=1, durum="pending")  # ölü DEĞİL — kalır
    assert db.purge_old_dead_outbox(30) == 2 and _say(db, "outbox_messages") == 2
    iz = _izler(db, "retention.olu_outbox_silindi")
    assert len(iz) == 1, f"ölü-outbox saklama silmesi denetim izine TEK satır yazmalı (Y204 / S-D5.5): {iz}"
    assert int(iz[0]["item_count"]) == 2 and iz[0]["scope"] == "otomatik", iz[0]
    assert json.loads(iz[0]["detail"]) == {"gun": 30}, (
        f"iz yalnız saklama süresini taşımalı (içerik YOK): {iz[0]['detail']}"
    )
    assert _ICERIK not in json.dumps(iz, ensure_ascii=False, default=str), "silinen outbox YÜKÜ ize sızdı"


def test_KARSIT_silinecek_yoksa_ve_sure_0_iken_IZ_YAZILMAZ(db):
    sid = int(db.start_session(treatment_mode="Manuel", patient_name="Bos Y204"))
    _sensor(db, sid, 10)
    _olu(db, 5)
    assert db.purge_old_sensor_samples(90) == 0 and db.purge_old_dead_outbox(30) == 0
    assert db.purge_old_sensor_samples(0) == 0 and db.purge_old_dead_outbox(0) == 0  # D2.49: 0 = adım kapalı
    assert _izler(db, "retention.sensor_silindi") == [] and _izler(db, "retention.olu_outbox_silindi") == [], (
        "boş tur / kapalı adım iz satırı biriktirdi"
    )


def test_bakim_turu_apply_data_retention_policy_iki_izi_de_yazar(db):
    """Günlük bakımın kendisi (aynı çağrı zinciri): sensör + ölü-outbox adımı birlikte koşunca iki iz de VAR, olay / doz izleri AYNI kalır."""
    sid = int(db.start_session(treatment_mode="Manuel", patient_name="Bakim Y204"))
    _sensor(db, sid, 200, n=4)
    _olu(db, 200, n=3)
    rapor = db.apply_data_retention_policy(sensor_retain_days=90, dead_outbox_retain_days=30)
    assert rapor.get("sensor_samples_removed") == 4 and rapor.get("dead_outbox_removed") == 3, rapor
    s, o = _izler(db, "retention.sensor_silindi"), _izler(db, "retention.olu_outbox_silindi")
    assert [int(x["item_count"]) for x in s] == [4] and [int(x["item_count"]) for x in o] == [3], (s, o)
