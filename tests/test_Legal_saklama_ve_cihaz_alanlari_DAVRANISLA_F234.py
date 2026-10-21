# -*- coding: utf-8 -*-
"""F2-3.4 (2-F incelemesi A3, K2 · D2.06 / A-38) — Legal §6 süreleri ve §5.1 cihaz alanları DAVRANIŞLA kod ile aynı.

D2.06 kapısı (`test_kvkk_transfer_claims`) sayıları KAYNAKTAN, belirli AST noktalarından okur: headless `_run_maintenance`'taki
`_retain_days("X", <sabit>)` literalleri, `ESIK_GUN` sabiti, `_publish_device_registry` içindeki SÖZLÜK DEĞİŞMEZLERİ. Davranışı değiştiren ama
o literalleri değiştirmeyen değişiklikler (ölçüldü — 179 testlik saklama/KVKK/kayıt kümesi YEŞİL): günlük döngünün olay varsayılanı 180,
günlük döngünün anonimleştirme eşiği 730, silicide `min(süre, 30)`, RPC'ye alt simge atamasıyla / `out.update` ile yeni alan.
Bu kapı Legal'deki sayıyı OKUR ve GERÇEK iki siliciyi (headless tur + günlük döngü bir tur), GERÇEK anonimleştirme yolunu (günlük döngü →
kvkk turu) ve GERÇEK cihaz kaydı yayınını (bulut istemcisi en dış sınırda sahte) koşar.
"""

from __future__ import annotations

import re
import time
import types
from datetime import datetime, timedelta

import pytest
import test_kvkk_transfer_claims as kt
from test_bakim_TEK_silici_sensor_sozlesmesi_D244 import _ENV, _gunluk_bakim_tek_tur, _headless_tur

GUN = 86400.0


def _legal_gunleri() -> dict:
    m = kt._saklama_maddeleri(kt.gorunen_legal())
    out = {}
    for k in ("sensor", "doz", "olay", "anonim"):
        g = re.search(r"(\d+)\s*gün", m[k])
        assert g, f"aparat: Legal §6 '{k}' maddesinde gün sayısı yok: {m[k]!r}"
        out[k] = int(g.group(1))
    return out


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    for ad in _ENV:
        monkeypatch.delenv(ad, raising=False)
    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    db = TreatmentHistoryDB(tmp_path / "gecmis")
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(api, "get_patient_database", lambda: pdb)
    try:
        yield types.SimpleNamespace(api=api, db=db, pdb=pdb)
    finally:
        db.close_connections()


def test_KRITIK_iki_silici_birlikte_Legal_SURELERINDE_siler(ortam):
    """Sensör / doz / olay: Legal'deki N gün için N-2 günlük kayıt KALIR, N+2 günlük kayıt GİDER — GERÇEK headless tur + GERÇEK günlük
    döngü bir tur (ikisi de üretimde koşar). MUTASYON: günlük döngü olay varsayılanı 180 / silicide min(süre, 30) → KIRMIZI."""
    o, n = ortam, _legal_gunleri()
    simdi = time.time()
    sid = int(o.db.start_session(treatment_mode="Manuel", patient_name="Saklama F234"))
    o.db.add_sensor_samples_batch(
        sid,
        [
            {"coil_id": "1", "sample_ts": simdi - g * GUN, "temperature_c": 30.0, "payload": {}}
            for g in (n["sensor"] - 2, n["sensor"] + 2)
        ],
    )
    for g in (n["doz"] - 2, n["doz"] + 2):
        assert o.db.start_coil_run(sid, 1, started_epoch=simdi - g * GUN, frequency_hz=10.0)
    for g in (n["olay"] - 2, n["olay"] + 2):
        eid = o.db.record_session_event(sid, "seans_notu", {"g": g})
        with o.db._get_connection() as c:
            c.execute("UPDATE session_events SET created_at=? WHERE id=?", (simdi - g * GUN, eid))
            c.commit()

    def _say():
        with o.db._get_connection() as c:
            s = sorted(
                round((simdi - r[0]) / GUN)
                for r in c.execute("SELECT sample_ts FROM sensor_samples WHERE session_id=?", (sid,))
            )
            d = sorted(
                round((simdi - r[0]) / GUN)
                for r in c.execute("SELECT started_epoch FROM session_coil_runs WHERE session_id=?", (sid,))
            )
            e = sorted(
                round((simdi - r[0]) / GUN)
                for r in c.execute(
                    "SELECT created_at FROM session_events WHERE session_id=? AND event_type='seans_notu'", (sid,)
                )
            )
        return {"sensor": s, "doz": d, "olay": e}

    once = _say()
    assert once == {k: [n[k] - 2, n[k] + 2] for k in once}, f"aparat: tohum {once}"
    _headless_tur(o.db)
    _gunluk_bakim_tek_tur(o.api)
    sonra = _say()
    beklenen = {k: [n[k] - 2] for k in sonra}
    assert sonra == beklenen, (
        f"Legal §6 süreleri ({n}) ile iki silicinin davranışı farklı: önce {once} → sonra {sonra}, beklenen {beklenen}"
    )


def test_KRITIK_anonimlestirme_GUNLUK_DONGUDE_Legal_esiginde_onayla_UYGULANIR(ortam):
    """Legal 'anonim' N gün + klinik ONAYI (ekranın yazdığı biçimde: ESIK_GUN'e) → GERÇEK günlük döngü bir tur: N+30 gün inaktif hasta
    anonimleşir, N-30 gün inaktif kalır. MUTASYON: döngü `tur(_pdb, db, 730)` → onay eşiği tutmaz, hiçbir şey anonimleşmez → KIRMIZI."""
    from services import kvkk_anonimlestirme as kv

    o, n = ortam, _legal_gunleri()
    kimlik = {}
    for ad, gun in (("Eski F234", n["anonim"] + 30), ("Yeni F234", n["anonim"] - 30)):
        pid = o.pdb.add_patient({"name": ad, "owner": "Sahip F234"})
        with o.pdb._get_connection() as c:
            c.execute(
                "UPDATE patients SET last_treatment_at=? WHERE id=?",
                ((datetime.now() - timedelta(days=gun)).isoformat(), pid),
            )
            c.commit()
        kimlik[ad] = pid
    o.db.anonim_onayi_yaz(
        gun=kv.ESIK_GUN, sayi=1, kim="dr@klinik.test"
    )  # /api/settings/retention anonymize_acknowledge'ın yazdığı
    _gunluk_bakim_tek_tur(o.api)
    adlar = {ad: o.pdb.get_patient(pid)["name"] for ad, pid in kimlik.items()}
    assert adlar == {"Eski F234": "[ANONIM]", "Yeni F234": "Yeni F234"}, (
        f"Legal 'anonim' {n['anonim']} gün + onay → günlük döngü sonrası adlar {adlar}"
    )


def test_KRITIK_buluta_GERCEKTEN_giden_cihaz_alanlari_Legalde(monkeypatch):
    """GERÇEK `_publish_device_registry` bir yayın; bulut istemcisi en dış sınırda sahte (RPC parametrelerini kaydeder). Giden HER alan
    `_CIHAZ_KARSILIK`ta ve Legal §5.1 maddesinde. MUTASYON: RPC'ye alt simge atamasıyla / `_surum_alanlari`na `out.update` ile alan → KIRMIZI."""
    import database.treatment_history_db as tdbm
    from servers.sync_worker import CloudSyncWorker

    monkeypatch.setenv("PEMF_LAUNCHER_VERSION", "9.9.9")
    monkeypatch.setenv("PEMF_BASE_SHA", "abc123")
    monkeypatch.setattr(tdbm, "get_treatment_db", lambda *a, **k: types.SimpleNamespace(at_rest_encrypted=True))
    cagrilar: list = []

    class _Istemci:
        def rpc(self, ad, params=None):
            cagrilar.append((ad, dict(params or {})))
            return types.SimpleNamespace(execute=lambda: types.SimpleNamespace(data=[]))

    w = CloudSyncWorker("https://ornek.supabase.co", "anon")
    w.client = _Istemci()
    w._reg_secret = "sir-f234"
    w._publish_device_registry()
    kayit = [p for ad, p in cagrilar if ad == "upsert_device"]
    assert kayit, f"aparat: upsert_device çağrılmadı {cagrilar}"
    giden = {k[2:] if k.startswith("p_") else k for p in kayit for k in p}
    assert {"device_id", "secret", "app_version", "launcher_version", "at_rest_encrypted"} <= giden, (
        f"aparat kör: {sorted(giden)}"
    )
    eslemesiz = sorted(giden - set(kt._CIHAZ_KARSILIK))
    assert not eslemesiz, f"buluta GERÇEKTEN giden ama aydınlatma eşlemesinde olmayan alan: {eslemesiz} (A-38)"
    madde = kt._cihaz_maddesi(kt.gorunen_legal()).lower()
    eksik = sorted(a for a in giden if kt._CIHAZ_KARSILIK[a].lower() not in madde)
    assert not eksik, f"giden ama Legal §5.1'de anlatılmayan: {eksik}"
