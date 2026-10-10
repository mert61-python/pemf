# -*- coding: utf-8 -*-
"""B2-1.6 (2-B bağımsız incelemesi · A1 bulgusu · kapı orkestratörce yeniden yazıldı) — günlük bakım döngüsü seans olaylarını
(ACİL DURDUR kanıtı dahil) operatörün saklama ayarına (`PEMF_RETAIN_EVENT_DAYS`, 0 = silme) göre siler; sabit 365 gün ZORLAMAZ.

ÖLÇÜLEN KUSUR: iki zamanlayıcı var. `services/headless_db_maintenance` `PEMF_RETAIN_EVENT_DAYS`'e uyar (vars. 365, 0 → adım
kapalı). `api_server._daily_maintenance_loop` ise `purge_old_session_events(365)` SABİT çağırıyordu → dağıtım dosyası (A-33)
"seans olaylarını silme" (0) ya da "500 gün sakla" dese bile 365 günden eski `emergency_stop` olayları her gün siliniyordu.
Doz kaydı için aynı çift-yazıcı çelişkisi 2026-08-17'de bu döngüden çıkarılarak giderilmişti.

Ölçüm aracı: döngü AYRI iş parçacığında koşar; `time.sleep` yaması YALNIZ o iş parçacığında etkilidir (ilk uyku = açılış
beklemesi atlanır, ikinci uyku = tur sonu → durur). ⚠️ A1'in ilk sürümü yamayı SÜREÇ GENELİ kuruyordu: conftest'in uyku
nöbetçisini öldürüyor (D1.41) ve tur sayacına nöbetçinin uykularını katıyordu (ölçüldü: 2 yerine 3, teardown ERROR).
"""

from __future__ import annotations

import threading
import time

import pytest


class _TurBitti(BaseException):
    """Döngünün ikinci `sleep`i → bir tur tamam. BaseException: döngünün `except Exception`'ı yutmasın."""


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(api, "get_patient_database", lambda: None)
    try:
        yield api, db
    finally:
        db.close_connections()


def _olaylar(db, gun_once):
    """400 / 10 gün önceki iki ACİL DURDUR olayı (ürünün yazıcısıyla) — kimlikleri döner."""
    sid = int(db.start_session(treatment_mode="Manuel", patient_name="Pamuk"))
    ids = []
    for g in gun_once:
        eid = db.record_session_event(sid, "emergency_stop", {"reason": "manual"}, severity="critical")
        with db._get_connection() as c:
            c.execute("UPDATE session_events SET created_at=? WHERE id=?", (time.time() - g * 86400, eid))
            c.commit()
        ids.append(eid)
    return ids


def _var(db, eid):
    with db._get_connection() as c:
        return c.execute("SELECT COUNT(*) FROM session_events WHERE id=?", (eid,)).fetchone()[0]


def _gunluk_bakim_tek_tur(api):
    """`_daily_maintenance_loop`un gövdesini TAM BİR tur koşturur; uyku yaması yalnız döngünün iş parçacığında."""
    orj_sleep = time.sleep
    durum = {"ident": None, "uyku": 0}
    hatalar: list[BaseException] = []

    def _sleep(s):
        if threading.get_ident() == durum["ident"]:
            durum["uyku"] += 1
            if durum["uyku"] >= 2:
                raise _TurBitti()
            return None  # açılış beklemesi (60 sn) atlanır
        return orj_sleep(s)

    def _kos():
        durum["ident"] = threading.get_ident()
        try:
            api._daily_maintenance_loop()
        except _TurBitti:
            pass
        except BaseException as e:  # noqa: BLE001 — aşağıda iddia edilir
            hatalar.append(e)

    time.sleep = _sleep
    try:
        th = threading.Thread(target=_kos, daemon=True, name="bakim-tek-tur")
        th.start()
        th.join(30)
    finally:
        time.sleep = orj_sleep
    assert not th.is_alive() and not hatalar and durum["uyku"] == 2, (
        f"ölçüm aracı: döngü tek tur koşmadı (canlı={th.is_alive()}, uyku={durum['uyku']}, hata={hatalar})"
    )


@pytest.mark.parametrize("ayar", ["0", "500"], ids=["silme_kapali_0", "500_gun_sakla"])
def test_KRITIK_gunluk_bakim_saklama_AYARINA_uyar_eski_ACIL_DURDUR_olayi_KALIR(ortam, monkeypatch, ayar):
    """MUTASYON: döngüde sabit `purge_old_session_events(365)` → KIRMIZI."""
    api, db = ortam
    monkeypatch.setenv("PEMF_RETAIN_EVENT_DAYS", ayar)
    eski, yeni = _olaylar(db, (400, 10))
    _gunluk_bakim_tek_tur(api)
    assert (_var(db, eski), _var(db, yeni)) == (1, 1), (
        f"PEMF_RETAIN_EVENT_DAYS={ayar} iken günlük bakım 400 günlük ACİL DURDUR olayını sildi"
    )


def test_KARSIT_varsayilan_365_gun_eski_olay_silinir_yeni_kalir(ortam, monkeypatch):
    """Ayar yoksa 365 gün (headless bakımla aynı varsayılan): KRİTİK OLMAYAN eski olay silinir, yenisi kalır.

    ⚠️ D2.50 · A-07 (2026-10-10): bu kol eskiden 400 günlük `emergency_stop` (severity=critical) olayının SİLİNMESİNİ iddia ediyordu —
    sahip kararı A-07 "kritik tıbbi olaylar SÜRESİZ saklanır" ile çelişiyordu. Artık kritik ACİL DURDUR olayı KALIR (ayrıntılı kapı:
    tests/test_kritik_olaylar_SURESIZ_silme_IZ_birakir_D250.py); günlük döngünün silme yeteneği kritik olmayan olayla kanıtlanır."""
    api, db = ortam
    monkeypatch.delenv("PEMF_RETAIN_EVENT_DAYS", raising=False)
    eski, yeni = _olaylar(db, (400, 10))
    sid = int(db.start_session(treatment_mode="Manuel", patient_name="Pamuk"))
    kritik_olmayan = db.record_session_event(sid, "seans_notu", {"a": 1})
    with db._get_connection() as c:
        c.execute("UPDATE session_events SET created_at=? WHERE id=?", (time.time() - 400 * 86400, kritik_olmayan))
        c.commit()
    _gunluk_bakim_tek_tur(api)
    assert (_var(db, eski), _var(db, yeni), _var(db, kritik_olmayan)) == (1, 1, 0)
