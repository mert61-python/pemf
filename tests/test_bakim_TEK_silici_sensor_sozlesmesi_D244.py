# -*- coding: utf-8 -*-
"""D2.44 (B-4.18) + O-B2.1 — sensör telemetrisi saklamasında TEK silici, TEK sözleşme (`PEMF_RETAIN_SENSOR_DAYS`, 0 = adım kapalı).

ÖLÇÜLEN KUSUR: üretimde iki zamanlayıcı birlikte koşuyor. Asıl silici `services/headless_db_maintenance` `PEMF_RETAIN_SENSOR_DAYS`'i
okur (vars. 90, 0 → adım kapalı). `api_server._daily_maintenance_loop` ise sensör örneklerini hiçbir yerde belgelenmemiş
`PEMF_SENSOR_RETAIN_DAYS` (vars. 90) ile ve `max(1, …)` ile siliyordu → dağıtım dosyasında (A-33) "sensör verisini silme" (0) diyen
klinikte telemetri yine 90 günde gidiyor; eski ada 0 yazılırsa 1 GÜNDEN eski tüm telemetri siliniyordu (O-B2.1: çift-yazıcı ad çelişkisi).

Düzeltme: günlük döngü sensör SİLMEZ (tek silici headless); eski ad YALNIZ yeni ad ayarlanmamışsa takma ad olarak uygulanır ve WARNING
yazılır ("0 = sakla" yazmış operatörün niyeti sessizce ezilmesin). Ölçüm aracı: GERÇEK döngü ayrı iş parçacığında BİR tur
(`time.sleep` yaması yalnız o iş parçacığında); GERÇEK headless tur gövdesi (`_run_maintenance`) gerçek DB'de.
"""

from __future__ import annotations

import logging
import threading
import time

import pytest

GUN = 86400.0
_ENV = (
    "PEMF_RETAIN_SENSOR_DAYS",
    "PEMF_SENSOR_RETAIN_DAYS",
    "PEMF_RETAIN_EVENT_DAYS",
    "PEMF_RETAIN_DOSE_DAYS",
    "PEMF_RETAIN_OUTBOX_DAYS",
    "PEMF_RETAIN_PII_DAYS",
)


class _TurBitti(BaseException):
    """Döngünün ikinci `sleep`i → bir tur tamam. BaseException: döngünün `except Exception`'ı yutmasın."""


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    for ad in _ENV:
        monkeypatch.delenv(ad, raising=False)
    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(api, "get_patient_database", lambda: None)
    try:
        yield api, db
    finally:
        db.close_connections()


def _tohumla(db) -> int:
    """2 / 100 / 400 gün önceki birer sensör örneği ve birer (kritik olmayan) seans olayı — ürünün yazıcılarıyla."""
    simdi = time.time()
    sid = int(db.start_session(treatment_mode="Manuel", patient_name="Pamuk D244"))
    db.add_sensor_samples_batch(
        sid,
        [{"coil_id": "1", "sample_ts": simdi - g * GUN, "temperature_c": 30.0, "payload": {}} for g in (2, 100, 400)],
    )
    for g in (2, 100, 400):
        eid = db.record_session_event(sid, "seans_notu", {"g": g})
        with db._get_connection() as c:
            c.execute("UPDATE session_events SET created_at=? WHERE id=?", (simdi - g * GUN, eid))
            c.commit()
    return sid


def _say(db, sid: int) -> tuple:
    with db._get_connection() as c:
        s = c.execute("SELECT COUNT(*) FROM sensor_samples WHERE session_id=?", (sid,)).fetchone()[0]
        e = c.execute(
            "SELECT COUNT(*) FROM session_events WHERE session_id=? AND event_type='seans_notu'", (sid,)
        ).fetchone()[0]
    return s, e


def _gunluk_bakim_tek_tur(api):
    orj_sleep = time.sleep
    durum = {"ident": None, "uyku": 0}
    hatalar: list = []

    def _sleep(s):
        if threading.get_ident() == durum["ident"]:
            durum["uyku"] += 1
            if durum["uyku"] >= 2:
                raise _TurBitti()
            return None
        return orj_sleep(s)

    def _kos():
        durum["ident"] = threading.get_ident()
        try:
            api._daily_maintenance_loop()
        except _TurBitti:
            pass
        except BaseException as e:  # noqa: BLE001
            hatalar.append(e)

    time.sleep = _sleep
    try:
        th = threading.Thread(target=_kos, daemon=True, name="bakim-d244")
        th.start()
        th.join(30)
    finally:
        time.sleep = orj_sleep
    assert not th.is_alive() and not hatalar and durum["uyku"] == 2, (
        f"ölçüm aracı: döngü tek tur koşmadı (canlı={th.is_alive()}, uyku={durum['uyku']}, hata={hatalar})"
    )


def _headless_tur(db):
    from services.headless_db_maintenance import HeadlessDBMaintenance

    bakim = HeadlessDBMaintenance.__new__(HeadlessDBMaintenance)
    bakim.db = db
    bakim._run_maintenance()


def test_KRITIK_gunluk_dongu_PEMF_RETAIN_SIFIR_iken_hicbir_sensor_ve_olay_SILMEZ(ortam, monkeypatch):
    """Plan kapısı: `PEMF_RETAIN_SENSOR_DAYS=0` ve `PEMF_RETAIN_EVENT_DAYS=0` → bir tur sonra (3, 3)."""
    api, db = ortam
    monkeypatch.setenv("PEMF_RETAIN_SENSOR_DAYS", "0")
    monkeypatch.setenv("PEMF_RETAIN_EVENT_DAYS", "0")
    sid = _tohumla(db)
    _gunluk_bakim_tek_tur(api)
    assert _say(db, sid) == (3, 3), f"saklama 0 (kapalı) iken günlük döngü sildi: {_say(db, sid)}"


def test_KRITIK_eski_ad_SIFIR_iken_gunluk_dongu_1_GUNLUK_silmeye_DUSMEZ(ortam, monkeypatch):
    """MUTASYON: döngüye `purge_old_sensor_samples(PEMF_SENSOR_RETAIN_DAYS)` geri konur (`max(1, 0)` = 1 gün) → KIRMIZI."""
    api, db = ortam
    monkeypatch.setenv("PEMF_SENSOR_RETAIN_DAYS", "0")
    sid = _tohumla(db)
    _gunluk_bakim_tek_tur(api)
    assert _say(db, sid)[0] == 3, f"eski ada 0 yazan klinikte günlük döngü telemetriyi sildi: {_say(db, sid)}"


def test_KRITIK_gunluk_dongu_sensor_SILMEZ_tek_silici_headless(ortam):
    """Tek silici: ayar yokken de günlük döngü sensör örneğine dokunmaz (silme headless bakımın işi)."""
    api, db = ortam
    sid = _tohumla(db)
    _gunluk_bakim_tek_tur(api)
    assert _say(db, sid)[0] == 3, f"günlük döngü sensör sildi (ikinci silici): {_say(db, sid)}"


def test_KRITIK_headless_eski_adi_YENI_AD_YOKKEN_takma_ad_olarak_UYGULAR_ve_UYARIR(ortam, monkeypatch, caplog):
    """O-B2.1: eski ada 0 yazmış klinikte (yeni ad yok) headless bakım SİLMEZ ve yeniden adlandırmayı söyler.
    MUTASYON: takma ad kaldırılır (eski ad yok sayılır → 90 gün) → KIRMIZI."""
    _, db = ortam
    monkeypatch.setenv("PEMF_SENSOR_RETAIN_DAYS", "0")
    sid = _tohumla(db)
    with caplog.at_level(logging.WARNING, logger="services.headless_db_maintenance"):
        _headless_tur(db)
    assert _say(db, sid)[0] == 3, f"eski ada 0 yazılmışken headless bakım telemetriyi sildi: {_say(db, sid)}"
    uyari = [r.getMessage() for r in caplog.records if "PEMF_SENSOR_RETAIN_DAYS" in r.getMessage()]
    assert uyari and "PEMF_RETAIN_SENSOR_DAYS" in uyari[0], f"eski ad için yeniden adlandırma uyarısı yok: {uyari}"


def test_KRITIK_iki_ad_birden_varsa_YENI_AD_kazanir(ortam, monkeypatch):
    """MUTASYON: öncelik ters (eski ad yeni adı ezer) → KIRMIZI."""
    _, db = ortam
    monkeypatch.setenv("PEMF_RETAIN_SENSOR_DAYS", "30")
    monkeypatch.setenv("PEMF_SENSOR_RETAIN_DAYS", "0")
    sid = _tohumla(db)
    _headless_tur(db)
    assert _say(db, sid)[0] == 1, f"yeni ad (30 gün) uygulanmadı: {_say(db, sid)}"


def test_KRITIK_A33_device_env_saklama_sureleri_BACKEND_varsayilanlariyla_AYNI():
    """A-33: saklama süreleri dağıtım dosyasından yönetilir — `deploy/device.env` her `PEMF_RETAIN_*` anahtarını backend'in GERÇEKTEN
    uyguladığı varsayılanla (yorum satırı) belgeler. Etkin satır DEĞİL: launcher bu anahtarları henüz geçirmiyor (Rust kapısı).
    MUTASYON: headless varsayılanı değişir ya da belge satırı silinir → KIRMIZI."""
    import ast
    import re
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1]
    agac = ast.parse((kok / "apps" / "backend" / "services" / "headless_db_maintenance.py").read_text(encoding="utf-8"))
    tur = [n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef) and n.name == "_run_maintenance"]
    assert len(tur) == 1
    kod = {
        d.args[0].value: int(d.args[1].value)
        for d in ast.walk(tur[0])
        if isinstance(d, ast.Call)
        and getattr(d.func, "attr", "") == "_retain_days"
        and len(d.args) == 2
        and isinstance(d.args[0], ast.Constant)
        and isinstance(d.args[1], ast.Constant)
    }
    assert len(kod) == 5, f"araç: headless saklama çağrıları okunamadı: {kod}"
    metin = (kok / "deploy" / "device.env").read_text(encoding="utf-8")
    belge = {a: int(v) for a, v in re.findall(r"^#\s*(PEMF_RETAIN_[A-Z_]+)=(\d+)\s*$", metin, re.M)}
    etkin = re.findall(r"^\s*PEMF_RETAIN_[A-Z_]+\s*=", metin, re.M)
    assert belge == kod, f"device.env saklama belgesi backend varsayılanlarıyla AYNI değil: belge={belge} kod={kod}"
    assert not etkin, f"device.env'de ETKİN PEMF_RETAIN_* satırı var ama launcher geçirmiyor: {etkin}"


def test_KARSIT_headless_varsayilan_90_gun_eskiyi_SILER_yeniyi_TUTAR(ortam):
    """Silme yeteneği kaybolmaz: ayar yokken headless bakım 90 günden eski telemetriyi siler."""
    _, db = ortam
    sid = _tohumla(db)
    _headless_tur(db)
    assert _say(db, sid)[0] == 1, f"headless bakım varsayılan 90 günde eski telemetriyi silmedi: {_say(db, sid)}"
