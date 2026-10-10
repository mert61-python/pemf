# -*- coding: utf-8 -*-
"""F2-1.2 (2-F incelemesi · A1) · A-73 — saat İLERİ sıçrarsa ya da GERİDE kalırsa tek bir tur geri dönüşsüz işlem (anonimleştirme, PII
maskeleme, doz / sensör / olay silmesi) YAPMAZ; operatör saati onaylayana dek o adımlar bekler.

ÖLÇÜLEN KUSUR (`_inceleme\\K1\\sonda_saat_A73.py`, süreç içi saat yaması — sistem saatine dokunulmadı):
- İLERİ (+10 yıl, RTC arızası): 1 hastalık onay + 365 gün PII onayı varken TEK tur → 4/4 hasta (10 gün önce tedavi gören dahil)
  anonimleşti, tüm seanslar maskelendi, TÜM doz kayıtları (bobin koşuları) ve sensör örnekleri silindi (iz: `retention.doz_silindi`).
- GERİ (BIOS 2000-01-01): saat gerideyken yapılan tedavi (`touch_last_treatment` + seans + doz 2000 damgalı) → saat düzelince ilk tur o
  hastayı (bugün tedavi gördü) anonimleştirdi, dozunu ve sensör kaydını sildi, seansını maskeledi.
A-73: "saat kayması İKİ YÖNDE ele alınır". Zaman sahtesi EN ALT katta: ürün modüllerinin `datetime` adı (+ headless `time`).
"""

from __future__ import annotations

import datetime as _dt
import time as _time
import types

import pytest

GERCEK = _dt.datetime


class _Saat:
    kayma = _dt.timedelta(0)


class _SahteDatetime(GERCEK):
    @classmethod
    def now(cls, tz=None):
        return GERCEK.now(tz) + _Saat.kayma


_ENV = (
    "PEMF_RETAIN_SENSOR_DAYS",
    "PEMF_RETAIN_DOSE_DAYS",
    "PEMF_RETAIN_EVENT_DAYS",
    "PEMF_RETAIN_OUTBOX_DAYS",
    "PEMF_RETAIN_PII_DAYS",
    "PEMF_SENSOR_RETAIN_DAYS",
)


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database import patient_database as m_pdb
    from database import thdb_ai_gecmisi, thdb_bakim, thdb_outbox, thdb_pii, thdb_seans, thdb_telemetri
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from services import headless_db_maintenance as m_hl

    for ad in ("PEMF_MASK_HISTORY_PII", "PEMF_ENCRYPT_AT_REST", *_ENV):
        monkeypatch.delenv(ad, raising=False)
    _Saat.kayma = _dt.timedelta(0)
    for m in (m_pdb, thdb_pii, thdb_seans, thdb_ai_gecmisi, thdb_telemetri, thdb_outbox, thdb_bakim, m_hl):
        monkeypatch.setattr(m, "datetime", _SahteDatetime, raising=False)
    monkeypatch.setattr(
        m_hl,
        "time",
        types.SimpleNamespace(
            time=lambda: _time.time() + _Saat.kayma.total_seconds(),
            monotonic=_time.monotonic,
            sleep=_time.sleep,
            strftime=_time.strftime,
            localtime=_time.localtime,
        ),
    )
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield pdb, tdb
    finally:
        _Saat.kayma = _dt.timedelta(0)
        tdb.close_connections()


def _hasta(pdb, ad, gun_once):
    pid = pdb.add_patient({"name": ad, "owner": f"Sahip {ad}", "owner_email": f"{ad.lower()}@ornek.com"})
    with pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((_SahteDatetime.now() - _dt.timedelta(days=gun_once)).isoformat(), pid),
        )
        c.commit()
    return pid


def _tedavi(tdb, ad, pid):
    """Ürün yazıcılarıyla seans + olay + doz (bobin koşusu) + sensör örneği — o anki ('şimdi') saatle."""
    tpid = tdb.upsert_patient({"name": ad, "patient_uuid": pid})
    sid = int(tdb.start_session(treatment_mode="Manuel", patient_name=ad, operator_name="Dr Saat"))
    tdb.set_session_meta(sid, patient_id=tpid)
    tdb.end_session(sid, patient_notes=f"{ad} not", duration_minutes=10)
    simdi = _time.time() + _Saat.kayma.total_seconds()
    tdb.add_sensor_samples_batch(sid, [{"coil_id": "1", "sample_ts": simdi, "temperature_c": 31.0, "payload": {}}])
    tdb.record_session_event(sid, "seans_notu", {"a": 1})
    kosu = tdb.start_coil_run(sid, 1, frequency_hz=50.0, duty_percent=25.0, started_epoch=simdi)
    tdb.end_coil_run(kosu, simdi + 600)


def _say(tdb):
    with tdb._get_connection() as c:
        return {
            "adli_seans": c.execute(
                "SELECT COUNT(*) FROM treatment_sessions WHERE patient_name NOT IN ('[REDACTED]','[ANONIM]')"
            ).fetchone()[0],
            "olay": c.execute("SELECT COUNT(*) FROM session_events").fetchone()[0],
            "doz": c.execute("SELECT COUNT(*) FROM session_coil_runs").fetchone()[0],
            "sensor": c.execute("SELECT COUNT(*) FROM sensor_samples").fetchone()[0],
        }


def _turlar(pdb, tdb):
    """Üretimdeki iki geri dönüşsüz tur: günlük döngünün KVKK turu + headless bakım turu (GERÇEK gövde)."""
    from services import headless_db_maintenance as m_hl
    from services import kvkk_anonimlestirme as kv

    kv.tur(pdb, tdb)
    h = m_hl.HeadlessDBMaintenance.__new__(m_hl.HeadlessDBMaintenance)
    h.db = tdb
    h._run_maintenance()


def _onaylar(pdb, tdb):
    from services import kvkk_anonimlestirme as kv

    tdb.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=kv.bekleyen_sayisi(pdb), kim="dr@klinik.vet")
    tdb.pii_onayla(gun=365, sayi=tdb.redaksiyon_bekleyen_sayisi(365) or 0, kim="dr@klinik.vet")


def test_KRITIK_ILERI_sicrama_10_yil_tek_tur_GERI_DONUSSUZ_hicbir_sey_yapmaz(o):
    """MUTASYON: saat denetimi `True` döner → KIRMIZI (tüm hastalar anonim, tüm doz silinir)."""
    pdb, tdb = o
    aktif = {ad: _hasta(pdb, ad, g) for ad, g in (("Aktif10", 10), ("Aktif100", 100))}
    for ad, pid in aktif.items():
        _tedavi(tdb, ad, pid)
    _onaylar(pdb, tdb)
    _turlar(pdb, tdb)  # olağan tur (saat doğru)
    once = _say(tdb)
    assert once == {"adli_seans": 2, "olay": 2, "doz": 2, "sensor": 2}, f"aparat: {once}"
    _Saat.kayma = _dt.timedelta(days=3650)
    _turlar(pdb, tdb)
    assert [pdb.get_patient(p)["name"] for p in aktif.values()] == list(aktif), (
        "saat +10 yıl sıçradı: AKTİF hastalar anonimleşti"
    )
    assert _say(tdb) == once, f"saat +10 yıl sıçradı: geri dönüşsüz silme/maskeleme yapıldı {once} → {_say(tdb)}"
    # Günlük döngü (`api_server._daily_maintenance_loop`) seans olaylarını headless turundan AYRI, doğrudan siler:
    assert tdb.purge_old_session_events(365) == 0 and _say(tdb) == once, (
        "günlük döngünün olay silmesi saat sıçramasında koştu"
    )


def test_KRITIK_GERI_saat_iken_yapilan_tedavi_saat_DUZELINCE_silinmez_anonimlesmez(o):
    """BIOS 2000: tedavi kayıtları 2000 damgalı yazılır; saat düzelince ilk tur onları 26 yıllık sayıp siliyordu / anonimleştiriyordu."""
    pdb, tdb = o
    pid = _hasta(pdb, "Gunluk", 30)
    _onaylar(pdb, tdb)
    _turlar(pdb, tdb)  # saat doğru — tavan
    _Saat.kayma = GERCEK(2000, 1, 1, 9, 0, 0) - GERCEK.now()
    pdb.touch_last_treatment(pid)
    _tedavi(tdb, "Gunluk", pid)
    _turlar(pdb, tdb)  # saat gerideyken (açılış turu)
    _Saat.kayma = _dt.timedelta(0)
    once = _say(tdb)
    _turlar(pdb, tdb)
    assert pdb.get_patient(pid)["name"] == "Gunluk", "saat gerideyken tedavi gören hasta saat düzelince ANONİMLEŞTİ"
    assert _say(tdb) == once, (
        f"saat gerideyken yazılan doz / sensör / seans saat düzelince silindi/maskelendi: {once} → {_say(tdb)}"
    )


def test_KRITIK_operator_saati_ONAYLAYINCA_saklama_devam_eder(o):
    """Koruma sonsuz durdurmaz: saat (NTP ile) düzelir, operatör onaylar → olağan tur 5 yıl inaktif hastayı anonimleştirir."""
    pdb, tdb = o
    eski = _hasta(pdb, "Inaktif", 2200)
    _turlar(pdb, tdb)  # onaysız tavan turu
    _onaylar(pdb, tdb)
    _Saat.kayma = _dt.timedelta(days=3650)
    _turlar(pdb, tdb)  # şüphe
    _Saat.kayma = _dt.timedelta(0)
    _turlar(pdb, tdb)
    assert pdb.get_patient(eski)["name"] == "Inaktif", "onaylanmamış saat şüphesi varken anonimleştirme yapıldı"
    tdb.saat_onayla()
    _turlar(pdb, tdb)
    assert pdb.get_patient(eski)["name"] == "[ANONIM]", "saat onaylandıktan sonra olağan anonimleştirme DURDU"


def test_KARSIT_olagan_ilerleme_1_gun_saklama_ve_anonimlestirme_CALISIR(o):
    pdb, tdb = o
    eski = _hasta(pdb, "Inaktif", 2200)
    _onaylar(pdb, tdb)
    _turlar(pdb, tdb)
    _Saat.kayma = _dt.timedelta(days=1)
    pid = _hasta(pdb, "Yeni", 0)
    _tedavi(tdb, "Yeni", pid)
    with tdb._get_connection() as c:
        c.execute("UPDATE session_coil_runs SET started_epoch = started_epoch - 4000*86400")
        c.commit()
    _turlar(pdb, tdb)
    assert pdb.get_patient(eski)["name"] == "[ANONIM]"
    assert _say(tdb)["doz"] == 0, "araç kör: olağan saatte 4000 günlük doz kaydı silinmedi"


@pytest.fixture
def api(o, monkeypatch):
    from database import patient_database as pmod
    from fastapi.testclient import TestClient
    from servers import api_server as api_mod
    from servers import system_router as sr

    pdb, tdb = o
    monkeypatch.setattr(sr, "_pii_ayar_db", lambda: tdb)
    monkeypatch.setattr(pmod, "get_patient_database", lambda *a, **k: pdb)
    monkeypatch.setattr(api_mod, "_get_treatment_db", lambda: tdb)
    return TestClient(api_mod.app, client=("127.0.0.1", 51938))


def test_KRITIK_API_saat_suphesi_EKRANA_gelir_operator_ONAYI_kaldirir_ve_IZ_birakir(o, api):
    """Ayarlar → Veri Saklama şüpheyi `clockSuspect` (neden metni) ile görür; `clock_confirm` şüpheyi kaldırır, onay denetim izine geçer
    (orkestratör eki — arayüz yarısı `screens/__tests__/veriSaklamaSaat.F212.web.test.tsx`).
    MUTASYON: GET alanı göstermez / POST onayı uygulamaz → KIRMIZI."""
    import json

    pdb, tdb = o
    _turlar(pdb, tdb)  # olağan tur — tavan
    assert api.get("/api/settings/retention").json()["clockSuspect"] is None
    _Saat.kayma = _dt.timedelta(days=3650)
    _turlar(pdb, tdb)
    _Saat.kayma = _dt.timedelta(0)
    neden = api.get("/api/settings/retention").json()["clockSuspect"]
    assert isinstance(neden, str) and neden.startswith("ileri"), f"saat şüphesi ekrana gelmiyor: {neden!r}"
    assert api.post("/api/settings/retention", json={"clock_confirm": True}).status_code == 200
    assert api.get("/api/settings/retention").json()["clockSuspect"] is None, "operatör onayı şüpheyi kaldırmadı"
    iz = tdb.denetim_oku(10, "retention.saat_onay")
    assert iz and json.loads(iz[0]["detail"])["suphe"] == neden, iz
