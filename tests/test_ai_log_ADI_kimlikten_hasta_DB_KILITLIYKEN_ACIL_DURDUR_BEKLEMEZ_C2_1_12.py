# -*- coding: utf-8 -*-
"""C2-1.12 (2-C inceleme, A1) — KÖR KAPI: D2.69'un hasta defteri okuması (`_hasta_adi_kimlikten`) async `/api/ai/log` ucunda
olay döngüsünü BLOKLAMAMALI (Ö.4-Y8: ACİL DURDUR gecikmesi de kapılanmadır).

HEAD'de okuma `asyncio.to_thread` ile — doğru. Ama hiçbir kapı bunu ölçmüyor: A1 mutantı k8m2 (`to_thread` kaldırılır, okuma olay
döngüsünde senkron) D2.69 kapısında YEŞİL kalır. Hasta DB'si kilitliyken (yedekleme aracı, ikinci backend) senkron okuma bağlantı
zaman aşımı + `busy_timeout` boyunca döngüyü dondurur → aynı döngüdeki ACİL DURDUR HTTP isteği bekler.
GERÇEK: hasta DB dosyası İKİNCİ bir SQLite bağlantısıyla kilitlenir; istekler TEK paylaşılan olay döngüsünden (üretimdeki uvicorn
gibi); kilit sürerken ad doldurmayı tetikleyen `/api/ai/log` istekleri (kimlik var, ad boş) bir iş parçacığında uçuşta.
Ölçüt: ACİL DURDUR yanıt süresi.
"""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient

SINIR_SN = 3.0


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from database.patient_database import PatientDatabase
    from kayitci_donanim import gercek_hc

    o = ap.kur(monkeypatch, tmp_path)
    o.pdb_yol = tmp_path / "patients.db"
    o.pdb = PatientDatabase(str(o.pdb_yol))
    monkeypatch.setattr("database.patient_database.get_patient_database", lambda *a, **k: o.pdb)
    monkeypatch.setattr(o.api, "_ai_kimlik_tasindi", True)
    o.secenek = dict(ap.ISTEMCI_SECENEKLERI)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            yield o
    finally:
        o.geri()


def test_KRITIK_C2_1_12_hasta_DB_KILITLIYKEN_ad_doldurma_ACIL_DURDURU_bekletmez(o):
    from anyio.from_thread import start_blocking_portal

    hid = o.pdb.add_patient({"name": "Mia", "species": "Kedi"})
    o.pdb._reset_thread_conn()
    kc = sqlite3.connect(str(o.pdb_yol), isolation_level=None, timeout=5)
    kc.execute("PRAGMA locking_mode=EXCLUSIVE")
    kc.execute("BEGIN EXCLUSIVE")
    kc.execute("UPDATE patients SET name = name")
    yuk: list = []
    try:
        with start_blocking_portal(backend="asyncio", backend_options=o.secenek) as portal:
            c = TestClient(o.api.app, client=("192.168.1.95", 53001))
            c.portal = portal
            dur = threading.Event()

            def _yuk():
                while not dur.is_set():
                    r = c.post(
                        "/api/ai/log", json={"module": "m", "summary": "s", "patient_id": hid, "patient_name": ""}
                    )
                    yuk.append(r.status_code)

            t = threading.Thread(target=_yuk, daemon=True)
            t.start()
            time.sleep(1.0)
            t0 = time.monotonic()
            re = c.post("/api/hardware/emergency_stop")
            estop_sn = time.monotonic() - t0
            dur.set()
            t.join(120)
    finally:
        kc.execute("ROLLBACK")
        kc.close()
        o.c.post("/api/hardware/estop_mandali/sifirla", json={"onay": True})
    print(f"\nC2-1.12: ACİL DURDUR {re.status_code} {estop_sn:.2f} sn · uçan /ai/log {yuk[:3]}")
    assert yuk, "aparat: kilit sürerken /ai/log isteği uçmadı"
    assert re.status_code == 200 and estop_sn < SINIR_SN, (
        f"hasta DB kilitliyken ad doldurma ACİL DURDUR'u {estop_sn:.1f} sn bekletti — okuma olay döngüsünde senkron"
    )
