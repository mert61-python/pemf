# -*- coding: utf-8 -*-
"""2-D ORTAK APARATI — cihaz taşıma / geri yükleme / dışa aktarma kapıları için (test değil, yardımcı modül).

* `cihaz_kur` bir veri kökünde GERÇEK `TreatmentHistoryDB` + `PatientDatabase` açar (şifresiz ya da GERÇEK sqlcipher3 ile şifreli).
* `uclari_bagla` `servers.api_server`ın `/api/data/*` uçlarının o cihaza bakmasını sağlar (yalnız DB getter'ları yönlendirilir; uç
  gövdeleri, şifreleme, doğrulama, iz — hepsi gerçek).
* `doldur` hasta + seans + bobin koşusu + sensör + olay + AI kaydı yazar (ürünün kendi DB yöntemleriyle).
* `istekler` tek olay döngüsünde (httpx `ASGITransport`) istek(ler) gönderir; `eszamanli=True` ise aynı anda.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

PAROLA = "klinik-yedek-2026-ikiD"


def cihaz_kur(monkeypatch, kok: Path, sifreli: bool = False, anahtar: str = "2D-aparat-anahtari"):
    from database import patient_database as pdb
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    kok.mkdir(parents=True, exist_ok=True)
    if sifreli:
        import sahte_sqlcipher

        sahte_sqlcipher.baglayici_kur("gercek", monkeypatch)
        monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
        k = anahtar
    else:
        monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
        k = ""
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **kw: k)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **kw: k)
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    tdb = thdb.TreatmentHistoryDB(kok)
    hdb = pdb.PatientDatabase(str(kok / "patients.db"))
    return tdb, hdb


def uclari_bagla(monkeypatch, tdb, hdb) -> None:
    from servers import api_server as api

    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    monkeypatch.setattr(api, "get_patient_database", lambda *a, **k: hdb)


def kapat(*dbler) -> None:
    for db in dbler:
        try:
            if hasattr(db, "close"):
                db.close()
            else:
                db._reset_thread_conn()
        except Exception:
            pass


def doldur(tdb, hdb, adlar, seans_basi: int = 2, operator: str = "", sensor: int = 2, analiz: bool = True) -> dict:
    """Her ad için hasta (hasta DB'si + tedavi DB'si ayna satırı) ve `seans_basi` tam seans. {ad: hasta_id}"""
    kimlikler = {}
    for ad in adlar:
        hid = hdb.add_patient({"name": ad, "species": "Kedi", "owner": f"{ad}-sahibi", "operator_email": operator})
        kimlikler[ad] = hid
        pid = tdb.upsert_patient({"name": ad, "patient_uuid": hid})
        for i in range(seans_basi):
            sid = tdb.start_session(treatment_mode="Manuel", patient_name=ad, operator_email=operator)
            tdb.set_session_meta(sid, patient_id=pid)
            with tdb._get_connection() as c:
                cur = c.cursor()
                cur.execute(
                    "INSERT INTO session_coil_runs (session_id, coil_id, started_epoch, ended_epoch, duration_seconds, "
                    "frequency_hz, duty_percent, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (sid, 1 + i % 7, 1000.0, 1300.0, 300.0, 50.0, 25.0, 1000.0),
                )
                for j in range(sensor):
                    cur.execute(
                        "INSERT INTO sensor_samples (session_id, coil_id, sample_ts, temperature_c, created_at) "
                        "VALUES (?,?,?,?,?)",
                        (sid, str(1 + i % 7), 1100.0 + j, 30.0 + j, 1100.0 + j),
                    )
                c.commit()
            tdb.record_session_event(sid, "session_started", payload={"hasta": ad}, severity="info")
            tdb.end_session(sid, duration_minutes=5)
        if analiz:
            tdb.add_ai_analysis(
                module_id="m", patient_name=ad, result_summary=f"{ad}-analiz", operator_email=operator, patient_uuid=hid
            )
    return kimlikler


def sayimlar(tdb, hdb) -> dict:
    with tdb._get_connection() as c:
        s = {
            t: int(c.execute(f"SELECT count(*) FROM {t}").fetchone()[0])
            for t in (
                "treatment_sessions",
                "session_coil_runs",
                "sensor_samples",
                "session_events",
                "ai_analyses",
                "patients",
            )
        }
    s["hasta_db"] = len(hdb.get_all_patients())
    return s


def istekler(app, liste, eszamanli: bool = False, client=("127.0.0.1", 50123)):
    """`liste` = [(yöntem, yol, json|None, başlıklar|None), ...] → yanıtlar (httpx.Response) aynı sırada."""
    import httpx

    async def _kos():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=client), base_url="http://cihaz", timeout=120
        ) as c:

            async def _bir(yontem, yol, govde, basliklar):
                return await c.request(yontem, yol, json=govde, headers=basliklar or {})

            if eszamanli:
                return await asyncio.gather(*[_bir(*x) for x in liste])
            return [await _bir(*x) for x in liste]

    return asyncio.run(_kos())


def disa_aktar(app, parola: str = PAROLA, client=("127.0.0.1", 50123)) -> dict:
    (r,) = istekler(app, [("POST", "/api/data/export", {"passphrase": parola}, None)], client=client)
    assert r.status_code == 200, f"aparat: dışa aktarma {r.status_code} {r.text[:300]}"
    return r.json()
