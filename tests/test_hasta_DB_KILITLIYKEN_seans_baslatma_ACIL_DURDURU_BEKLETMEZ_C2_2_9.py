# -*- coding: utf-8 -*-
"""C2-2.9 (2-C inceleme A2 · Ö.4-Y8) — hasta DB'si kilitliyken uçuştaki `/api/session/start` (hasta kimlikli) olay döngüsünü
BLOKLAMAZ; ACİL DURDUR beklemez.

ÖLÇÜLEN (HEAD 1cd770c, `_inceleme/kayit/sonda_k5.txt` [K5c], paylaşılan TEK olay döngüsü): `async def start_session` hasta DB'sini
OLAY DÖNGÜSÜNDE senkron okur/yazar — `_lookup_owner_email` → `PatientDatabase.get_patient` (`self.lock`) ve `touch_last_treatment`
(`self.lock` + UPDATE, `busy_timeout` 5 sn) (`api_server.py:3952-3961`; sürüşten sonra `:4349-4352` bir `get_patient` daha). Hasta DB'si
ikinci bağlantıyla yazma kilidindeyken (WAL; yedekleme / ikinci süreç) başlatma uçuştayken basılan ACİL DURDUR **5,12 sn**; GERÇEK
`/api/patients/delete_all` (D2.57 — DELETE kilitte beklerken `PatientDatabase.lock`'u tutar) de uçuştayken **10,08 sn** — bu sürede
ACİL DURDUR isteği İŞLENEMİYOR, donanım STOP'u da o kadar gecikiyor. Kilitsizken 0,02 sn.
DÜZELTME: başlatmadaki hasta DB işleri (`_lookup_owner_email` + `touch_last_treatment`, sürüş sonrası özet okuması) `to_thread`'e.
GERÇEK: uçlar (TestClient + `start_blocking_portal`), `PatientDatabase` (geçici, şifresiz), `HardwareController` (`gercek_hc`; donanım
kuyruğu damgalı), tedavi DB'si; kilit ikinci SQLite bağlantısı.
"""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient

LAN = ("192.168.1.85", 52135)
SINIR_SN = 3.0


def _hdb(tmp_path, monkeypatch):
    import database.patient_database as pdb

    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    return pdb.PatientDatabase(str(tmp_path / "patients.db"))


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as apa
    from kayitci_donanim import gercek_hc
    from servers import patient_router

    o = apa.kur(monkeypatch, tmp_path)
    o.secenek = dict(apa.ISTEMCI_SECENEKLERI)
    o.pdb = _hdb(tmp_path, monkeypatch)
    o.pid = o.pdb.add_patient({"name": "Mia", "owner": "S", "species": "Kedi", "owner_email": "sahip@x.com"})
    monkeypatch.setattr(o.api, "get_patient_database", lambda *a, **k: o.pdb)
    monkeypatch.setattr(patient_router, "get_patient_database", lambda *a, **k: o.pdb)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            o.hc = hc
            kuyruk = hc.core._hw_send_queue
            o.paket_zaman: list = []
            _orj = kuyruk.put_nowait

            def _damgali(pkt):
                o.paket_zaman.append(time.monotonic())
                return _orj(pkt)

            kuyruk.put_nowait = _damgali
            yield o
            o.c.post("/api/session/stop")
    finally:
        o.air._ai_loop_active = False
        o.geri()


def _baslat_govde(o):
    return {
        "coil_ids": [1],
        "frequency": 100,
        "duty": 40,
        "phase": 0,
        "intensity": 0,
        "duration_minutes": 5,
        "mode": "Manuel",
        "patient_name": "Mia",
        "patient_id": o.pid,
    }


@pytest.mark.parametrize("ariza", ["hasta_db_yazma_kilidi", "toplu_silme_ucusta", "tedavi_db_yazma_kilidi"])
def test_KRITIK_hasta_DB_kilitliyken_baslatma_ucusta_ACIL_DURDUR_ve_donanim_STOPu_BEKLEMEZ(o, ariza):
    from anyio.from_thread import start_blocking_portal

    kc = sqlite3.connect(
        str(o.db.db_path if ariza == "tedavi_db_yazma_kilidi" else o.pdb.db_file), isolation_level=None, timeout=1
    )
    kc.execute("BEGIN EXCLUSIVE")
    kc.execute("UPDATE patients SET name = name")
    try:
        with start_blocking_portal(backend="asyncio", backend_options=o.secenek) as portal:
            c = TestClient(o.api.app, client=LAN)
            c.portal = portal
            yerel = TestClient(o.api.app, client=("127.0.0.1", 51999))
            yerel.portal = portal
            ipler = []
            if ariza == "toplu_silme_ucusta":
                ipler.append(
                    threading.Thread(
                        target=lambda: yerel.post("/api/patients/delete_all", json={"confirm": "DELETE_ALL"}),
                        daemon=True,
                    )
                )
                ipler[-1].start()
                time.sleep(0.5)
            ipler.append(
                threading.Thread(target=lambda: c.post("/api/session/start", json=_baslat_govde(o)), daemon=True)
            )
            ipler[-1].start()
            time.sleep(0.5)
            once = len(o.paket_zaman)
            t0 = time.monotonic()
            r = c.post("/api/hardware/emergency_stop")
            sn = time.monotonic() - t0
            ilk = (o.paket_zaman[once] - t0) if len(o.paket_zaman) > once else None
            for t in ipler:
                t.join(60)
    finally:
        kc.execute("ROLLBACK")
        kc.close()
    print(f"\nC2-2.9 {ariza}: ACİL DURDUR {sn:.2f} sn · ilk donanım paketi {ilk}")
    assert r.status_code == 200, r.text[:200]
    assert ilk is not None and ilk < 1.0, f"donanım STOP'u {ilk} sn sonra (olay döngüsü hasta DB'sinde bloklu)"
    assert sn < SINIR_SN, (
        f"hasta DB kilitliyken ACİL DURDUR {sn:.1f} sn bekledi — olay döngüsü senkron hasta DB G/Ç'sinde"
    )


def test_KARSIT_kilitsiz_baslatma_SAHIP_epostasi_ve_SON_TEDAVI_damgasini_yazar(o):
    r = o.c.post("/api/session/start", json=_baslat_govde(o))
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    with o.api._session_lock:
        sid = o.api._active_session.get("db_session_id")
    with o.db._get_connection() as c:
        c.row_factory = None
        sahip = c.execute(
            "SELECT parameter_value FROM session_parameters WHERE session_id = ? AND parameter_name = "
            "'patient_owner_email'",
            (sid,),
        ).fetchone()
    assert sahip and sahip[0] == "sahip@x.com", sahip
    assert (o.pdb.get_patient(o.pid) or {}).get("last_treatment_at"), "son tedavi damgası yazılmadı"
