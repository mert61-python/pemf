# -*- coding: utf-8 -*-
"""S-F2-1.5 (2-F incelemesi A1 · Y123 önerilen) — `PEMF_RETAIN_*` geçersiz ya da BOŞ değer geri dönüşsüz adımı KAPATIR (+ WARNING).

ÖLÇÜLEN: bugüne dek geçersiz / boş değer WARNING + VARSAYILAN süreye düşüyordu → silme sürüyordu; hiçbir kapı boş dizenin anlamını
sabitlemiyordu (A1 k4_m2 mutantı yeşil). Örn. dağıtım dosyasında `PEMF_RETAIN_DOSE_DAYS=` ("silme" niyetiyle boş bırakılmış) → uygulanan doz
kaydı 10 yılda yine silinir. Güvenli yön: niyeti okunamayan geri dönüşsüz silme YAPILMAZ. Ekran (`/api/settings/retention`) aynı okuyucuyu
kullanır → "Maskeleme KAPALI" der (tur ile ekran tutarlı). Günlük döngünün olay silmesi de aynı okuyucuyu kullanır (eskiden kendi `int()`'i
geçersizde 365'e düşüyordu).
GERÇEK headless tur gövdesi + GERÇEK günlük döngü bir tur (D2.44 aparatı) + GERÇEK uç; geçici DB.
"""

from __future__ import annotations

import logging
import time

import pytest
from test_bakim_TEK_silici_sensor_sozlesmesi_D244 import _ENV, _gunluk_bakim_tek_tur, _headless_tur

GUN = 86400.0


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    for ad in _ENV:
        monkeypatch.delenv(ad, raising=False)
    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(api, "get_patient_database", lambda: None)
    try:
        yield api, db
    finally:
        db.close_connections()


def _tohumla(db) -> int:
    """Her türden 4000 gün önceki birer kayıt (her varsayılan sürenin dışında) — ürünün yazıcılarıyla."""
    simdi = time.time()
    sid = int(db.start_session(treatment_mode="Manuel", patient_name="Eski SF215"))
    db.end_session(sid, duration_minutes=5)
    db.add_sensor_samples_batch(
        sid, [{"coil_id": "1", "sample_ts": simdi - 4000 * GUN, "temperature_c": 30.0, "payload": {}}]
    )
    assert db.start_coil_run(sid, 1, started_epoch=simdi - 4000 * GUN, frequency_hz=10.0)
    eid = db.record_session_event(sid, "seans_notu", {"g": 4000})
    with db._get_connection() as c:
        c.execute("UPDATE session_events SET created_at=? WHERE id=?", (simdi - 4000 * GUN, eid))
        c.commit()
    return sid


def _say(db, sid) -> dict:
    with db._get_connection() as c:
        return {
            "sensor": c.execute("SELECT COUNT(*) FROM sensor_samples WHERE session_id=?", (sid,)).fetchone()[0],
            "doz": c.execute("SELECT COUNT(*) FROM session_coil_runs WHERE session_id=?", (sid,)).fetchone()[0],
            "olay": c.execute(
                "SELECT COUNT(*) FROM session_events WHERE session_id=? AND event_type='seans_notu'", (sid,)
            ).fetchone()[0],
        }


@pytest.mark.parametrize("deger", ["", "abc", " "])
def test_KRITIK_gecersiz_ya_da_bos_deger_SILMEZ_ve_UYARIR(ortam, monkeypatch, caplog, deger):
    """MUTASYON: `_retain_days` geçersizde VARSAYILANA düşer (eski davranış) → doz / sensör / olay silinir → KIRMIZI."""
    api, db = ortam
    for ad in ("PEMF_RETAIN_SENSOR_DAYS", "PEMF_RETAIN_DOSE_DAYS", "PEMF_RETAIN_EVENT_DAYS"):
        monkeypatch.setenv(ad, deger)
    sid = _tohumla(db)
    assert _say(db, sid) == {"sensor": 1, "doz": 1, "olay": 1}, "aparat"
    with caplog.at_level(logging.WARNING):
        _headless_tur(db)
        _gunluk_bakim_tek_tur(api)
    assert _say(db, sid) == {"sensor": 1, "doz": 1, "olay": 1}, (
        f"geçersiz / boş saklama değeri ({deger!r}) VARSAYILAN süreyle silmeyi sürdürdü: {_say(db, sid)}"
    )
    uyarilar = " ".join(r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)
    assert "PEMF_RETAIN_DOSE_DAYS" in uyarilar and "KAPALI" in uyarilar, f"geçersiz değer SESSİZ: {uyarilar[:400]}"


def test_KRITIK_gecersiz_PII_suresi_ekranda_KAPALI_ve_turda_maskelenmez(ortam, monkeypatch):
    """Ekran ve tur aynı okuyucu: geçersiz `PEMF_RETAIN_PII_DAYS` → ekran 0 gün (Maskeleme KAPALI), bekleyen yok, onay sorulmaz."""
    from fastapi.testclient import TestClient
    from servers import system_router as sr

    api, db = ortam
    monkeypatch.setattr(sr, "_pii_ayar_db", lambda: db)
    monkeypatch.setenv("PEMF_RETAIN_PII_DAYS", "bir yil")
    durum = TestClient(api.app, client=("127.0.0.1", 51957)).get("/api/settings/retention").json()
    assert (durum["days"], durum["pending"]) == (0, 0), f"geçersiz PII süresi ekranda kapalı görünmüyor: {durum}"


def test_KARSIT_gecerli_deger_UYGULANIR(ortam, monkeypatch):
    api, db = ortam
    for ad in ("PEMF_RETAIN_SENSOR_DAYS", "PEMF_RETAIN_DOSE_DAYS", "PEMF_RETAIN_EVENT_DAYS"):
        monkeypatch.setenv(ad, "30")
    sid = _tohumla(db)
    _headless_tur(db)
    _gunluk_bakim_tek_tur(api)
    assert _say(db, sid) == {"sensor": 0, "doz": 0, "olay": 0}, f"araç kör: geçerli 30 gün uygulanmadı {_say(db, sid)}"
