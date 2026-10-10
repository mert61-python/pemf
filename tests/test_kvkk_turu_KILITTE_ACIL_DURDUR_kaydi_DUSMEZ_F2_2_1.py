# -*- coding: utf-8 -*-
"""F2-2.1 (2-F incelemesi A2) — günlük bakımın KVKK anonimleştirme turu (D2.54 · Y125) AKTİF SEANS sürerken tedavi DB'sinin yazım
kilidini busy_timeout'tan (5 sn) uzun TUTMAZ; o sırada basılan ACİL DURDUR'un KRİTİK olayı (A-07) ve seans kapanışı DÜŞMEZ.

KUSUR (ölçüldü): `thdb_pii._ai_kayitlarini_anonimlestir` HER hasta için tablodaki TÜM kimliksiz AI kayıtlarını (özet + ayrıntı +
gerekçe + geçmiş metinleriyle) çekip Python'da ada göre süzüyor — O(hasta × kimliksiz kayıt), ilk UPDATE'ten SONRA (yazım kilidi
alınmış) tek işlemde. Günlük döngü bu turu seans denetimi YAPMADAN koşar (VACUUM'un aksine). 300 hasta × 5000 kimliksiz kayıtta
kilit ~13 sn tutuluyor; eşzamanlı her kayıt yazımı 5,5 sn bekleyip "database is locked" ile DÜŞÜYOR.
ÖLÇÜM: GERÇEK `_daily_maintenance_loop` TEK tur (yalnız döngü iş parçacığının `sleep`i yönlendirilir; öteki iş parçacıkları gerçek
`sleep`), GERÇEK `PatientDatabase` + `TreatmentHistoryDB` (geçici dizin), GERÇEK `HardwareController`; ACİL DURDUR tek PAYLAŞILAN olay
döngüsünden (httpx ASGITransport), kilit GERÇEKTEN tutulurken (ayrı bağlantıdan `BEGIN IMMEDIATE` yoklayıcısı) gönderilir.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from datetime import datetime, timedelta

import ai_pro_aparati as ap
import pytest

N_HASTA = 300
M_KIMLIKSIZ = 5000


class _TurBitti(BaseException):
    pass


@pytest.fixture
def o(monkeypatch, tmp_path):
    from database import patient_database as pmod
    from kayitci_donanim import gercek_hc

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            ns.pdb = pmod.PatientDatabase(str(tmp_path / "patients.db"))
            monkeypatch.setattr(ns.api, "get_patient_database", lambda *a, **k: ns.pdb)
            monkeypatch.setattr(pmod, "get_patient_database", lambda *a, **k: ns.pdb)
            yield ns
    finally:
        ns.geri()


def _yuk_kur(o, n_hasta, m_kimliksiz):
    from services import kvkk_anonimlestirme as kv

    eski = (datetime.now() - timedelta(days=2200)).isoformat()
    pids = [
        o.pdb.add_patient(
            {"name": f"Pamuk Sonda-{7731 + i}", "owner": f"Sahip Sonda-{i}", "owner_email": f"s{i}@ornek.com"}
        )
        for i in range(n_hasta)
    ]
    with o.pdb._get_connection() as c:
        c.executemany("UPDATE patients SET last_treatment_at=? WHERE id=?", [(eski, p) for p in pids])
        c.commit()
    for i, pid in enumerate(pids):
        o.db.upsert_patient({"name": f"Pamuk Sonda-{7731 + i}", "patient_uuid": pid})
    ayrinti = '{"bulgu": "' + ("x" * 1500) + '"}'
    with o.db._get_connection() as c:
        c.executemany(
            "INSERT INTO ai_analyses (created_at, module_id, patient_name, patient_uuid, operator_email, result_summary, "
            "result_detail) VALUES (?,?,?,?,?,?,?)",
            [
                (eski, "kalca", f"Eski Hasta {j % 700}", "", "dr@klinik.com", "ozet " + "y" * 120, ayrinti)
                for j in range(m_kimliksiz)
            ],
        )
        c.commit()
    o.db.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=n_hasta, kim="")
    return pids


def _aktif_seans(o):
    sid = int(o.db.start_session(treatment_mode="Manuel", patient_name="Seans Hasta"))
    with o.api._session_lock:
        o.api._active_session.update(
            {
                "is_active": True,
                "db_session_id": sid,
                "started_epoch": time.time(),
                "start_mono": time.monotonic(),
                "coil_ids": [1, 2, 3],
                "mode": "Manuel",
            }
        )
    return sid


class _Yoklayici:
    """Ayrı bağlantıdan 50 ms'de bir `BEGIN IMMEDIATE` (zaman aşımı 20 ms): yazım kilidinin kesintisiz tutulduğu en uzun süre."""

    def __init__(self, yol):
        self.yol = str(yol)
        self.dur = threading.Event()
        self.azami = 0.0
        self.simdi_tutuluyor = 0.0
        self.th = threading.Thread(target=self._kos, daemon=True)

    def _kos(self):
        c = sqlite3.connect(self.yol, timeout=0.02, isolation_level=None)
        bas = None
        try:
            while not self.dur.is_set():
                try:
                    c.execute("BEGIN IMMEDIATE")
                    c.execute("ROLLBACK")
                    bas = None
                    self.simdi_tutuluyor = 0.0
                except sqlite3.OperationalError:
                    t = time.monotonic()
                    bas = bas or t
                    self.simdi_tutuluyor = t - bas
                    self.azami = max(self.azami, self.simdi_tutuluyor)
                self.dur.wait(0.05)
        finally:
            c.close()


def _tek_tur_arka_planda(api):
    orj = time.sleep
    durum = {"ident": None, "uyku": 0, "hata": None}

    def _sleep(s):
        if threading.get_ident() == durum["ident"]:
            durum["uyku"] += 1
            if durum["uyku"] >= 2:
                raise _TurBitti()
            return None
        return orj(s)

    def _kos():
        durum["ident"] = threading.get_ident()
        try:
            api._daily_maintenance_loop()
        except _TurBitti:
            pass
        except BaseException as e:  # noqa: BLE001
            durum["hata"] = e

    time.sleep = _sleep
    th = threading.Thread(target=_kos, daemon=True, name="bakim-f2-2-1")
    th.start()
    return th, durum, lambda: setattr(time, "sleep", orj)


def _istemci(o):
    import httpx

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=o.api.app, client=("127.0.0.1", 50132)), base_url="http://cihaz", timeout=60
    )


def _olc(o, n_hasta, m_kimliksiz):
    from utils import dongu_disi_yazim

    _yuk_kur(o, n_hasta, m_kimliksiz)
    sid = _aktif_seans(o)
    yok = _Yoklayici(o.db.db_path)
    yok.th.start()
    th, durum, geri = _tek_tur_arka_planda(o.api)
    try:
        # Kilit kesintisiz 0,5 sn tutulana dek (ya da tur bitene dek) bekle → ACİL DURDUR kilit SÜRERKEN gönderilir.
        son = time.monotonic() + 60
        while th.is_alive() and yok.simdi_tutuluyor < 0.5 and time.monotonic() < son:
            time.sleep(0.02)
        kilitteydi = yok.simdi_tutuluyor >= 0.5

        async def _acil():
            async with _istemci(o) as c:
                cagri = o.hc.stop_all_cagri
                t0 = time.monotonic()
                r = await c.post("/api/hardware/emergency_stop")
                return r, time.monotonic() - t0, o.hc.stop_all_cagri - cagri

        r, sure, stop = asyncio.run(_acil())
        th.join(120)
    finally:
        geri()
        yok.dur.set()
        yok.th.join(5)
    assert not th.is_alive() and durum["hata"] is None and durum["uyku"] == 2, f"ölçüm aracı: tur koşmadı {durum}"
    assert dongu_disi_yazim.bosalt(30), "aparat: kayıt kuyruğu boşalmadı"
    with o.db._get_connection() as c:
        olay = c.execute(
            "SELECT COUNT(*) FROM session_events WHERE session_id=? AND event_type='emergency_stop'", (sid,)
        ).fetchone()[0]
        durum_s = c.execute("SELECT session_status FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]
        anonim = c.execute("SELECT COUNT(*) FROM patients WHERE name='[ANONIM]'").fetchone()[0]
    return {
        "kilitteydi": kilitteydi,
        "yanit": r.status_code,
        "sure": sure,
        "stop": stop,
        "olay": olay,
        "seans": durum_s,
        "anonim": anonim,
        "azami_kilit": yok.azami,
    }


def test_KRITIK_KVKK_turu_SEANS_surerken_kilidi_uzun_tutmaz_ACIL_DURDUR_kritik_olayi_ve_seans_kapanisi_DUSMEZ(o):
    """MUTASYON / HEAD: kimliksiz AI kayıtları hasta başına yeniden taranır → kilit ~13 sn, olay ve kapanış DÜŞER → KIRMIZI."""
    s = _olc(o, N_HASTA, M_KIMLIKSIZ)
    assert s["anonim"] == N_HASTA, f"aparat: tur anonimleştirmedi {s}"
    assert s["yanit"] == 200 and s["stop"] >= 1 and s["sure"] < 2.0, f"ACİL DURDUR yanıtı/STOP: {s}"
    assert s["azami_kilit"] < 2.0, (
        f"KVKK turu tedavi DB yazım kilidini {s['azami_kilit']:.1f} sn KESİNTİSİZ tuttu (seans sürerken): {s}"
    )
    assert s["olay"] >= 1, f"KVKK turu kilitteyken basılan ACİL DURDUR'un kritik olayı (A-07) YAZILMADI: {s}"
    assert s["seans"] == "EMERGENCY_STOPPED", f"ACİL DURDUR seans kaydını kapatamadı (kayıt düştü): {s}"


def test_KARSIT_yuksuz_turda_ACIL_DURDUR_olayi_ve_kapanisi_yazilir(o):
    """Araç kör değil: aynı zincir küçük yükte (kilit kısa) olay + kapanış yazılır."""
    s = _olc(o, 3, 0)
    assert s["anonim"] == 3 and s["olay"] >= 1 and s["seans"] == "EMERGENCY_STOPPED" and s["azami_kilit"] < 2.0, s
