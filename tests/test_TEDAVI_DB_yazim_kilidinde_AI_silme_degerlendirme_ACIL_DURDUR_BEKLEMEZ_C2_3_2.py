# -*- coding: utf-8 -*-
"""C2-3.2 (2-C incelemesi A3 · 2-B2 §6 madde 7 "aynı sınıf, başka DB — ÖLÇÜLMEDİ") — tedavi DB'si YAZIM KİLİDİNDEYKEN AI
geçmişi silme / değerlendirme uçlarının kimlik reddi (428) ACİL DURDUR'u BEKLETMEZ.

ÖLÇÜLEN KUSUR: `/api/ai/log/delete_all` (Y112 · Y105 · Y113), `/api/ai/log/delete` (Y83 · Y113), `/api/ai/log/review` (Y88 · Y113)
`async` uçlardır ve 428 dalında denetim izini (`audit_log.kimlikli_yaz` → `TreatmentHistoryDB.denetim_yaz`: `_lock` + tedavi DB'sine
INSERT, `busy_timeout` 5 sn) OLAY DÖNGÜSÜNDE satır içi yazar. Tedavi DB'si başka bir bağlantının yazım kilidindeyken (kendi "Tüm
Klinik" silmesinin VACUUM'u, uzun yazma, ikinci backend) her red döngüyü ~5,4 sn dondurur. Ölçüldü (paylaşılan döngü, cihaz token'lı
LAN istemcisi, jetonsuz): TEK istemcide ACİL DURDUR 9,2–10,2 sn, STOP 5,5 sn; ÜÇ istemcide ACİL DURDUR 14,6–32,1 sn, STOP 16,4 sn.
Kilit yokken ve istek yokken ACİL DURDUR 0,00 sn (ACİL DURDUR'un kendisi tedavi DB'si beklemez). Ö.4-Y8: gecikme de bağlanmadır.

GERÇEK: tedavi DB'sine ürünün kendi bağlantı havuzundan (ayrı iş parçacığı = ayrı bağlantı) `BEGIN IMMEDIATE` + `INSERT` ile gerçek
SQLite yazım kilidi; istekler tek paylaşılan olay döngüsünden; kayıtlı operatörlü klinik; kimlik reddi 428 (fail-closed korunur).
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
LAN = ("192.168.1.88", 52175)
TOKEN = {"X-API-Key": "DOGRU-TOKEN"}
SINIR_SN = 3.0


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as apa
    from kayitci_donanim import gercek_hc
    from servers import auth, operator_tokens

    o = apa.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(auth, "check_token", lambda t: t == "DOGRU-TOKEN")
    o.secenek = dict(apa.ISTEMCI_SECENEKLERI)
    o.yerel = TestClient(o.api.app, client=("127.0.0.1", 52174), backend_options=o.secenek)
    operator_tokens.temizle_hepsi()
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            yield o
    finally:
        operator_tokens.temizle_hepsi()
        for op in o.yerel.get("/api/operators").json().get("data", []):
            o.yerel.post("/api/operators/remove", json={"email": op["email"]})
        o.geri()


class _TedaviYazimKilidi:
    """Tedavi DB'sine GERÇEK yazım kilidi (VACUUM / uzun yazma eşdeğeri): ürün havuzundan ayrı bağlantı, BEGIN IMMEDIATE + INSERT."""

    def __init__(self, db):
        self.db, self.hazir, self.birak, self.hata = db, threading.Event(), threading.Event(), None

    def _calis(self):
        try:
            with self.db._get_connection() as c:
                c.execute("BEGIN IMMEDIATE")
                c.execute("INSERT INTO audit_events (ts_utc, event_type) VALUES ('2000-01-01', 'c232_kilit')")
                self.hazir.set()
                self.birak.wait(180)
                c.execute("ROLLBACK")
        except Exception as e:  # pragma: no cover - aparat
            self.hata = repr(e)
            self.hazir.set()

    def __enter__(self):
        self.t = threading.Thread(target=self._calis, daemon=True)
        self.t.start()
        assert self.hazir.wait(10) and self.hata is None, f"aparat: tedavi DB kilidi kurulamadı: {self.hata}"
        return self

    def __exit__(self, *a):
        self.birak.set()
        self.t.join(30)
        return False


def _aparat_kilit_gercek_mi(o):
    """Aparat kanıtı: kilit sürerken ayrı bir bağlantı tedavi DB'sine YAZAMAZ (denetim_yaz False döner)."""
    sonuc = {}

    def _yaz():
        t0 = time.monotonic()
        sonuc["ok"] = o.db.denetim_yaz("c232_aparat")
        sonuc["sn"] = time.monotonic() - t0

    t = threading.Thread(target=_yaz)
    t.start()
    t.join(30)
    return sonuc


@pytest.mark.parametrize("istemci", [1, 3])
def test_KRITIK_tedavi_DB_yazim_kilidinde_kimliksiz_AI_silme_ve_degerlendirme_ACIL_DURDUR_ve_STOP_BEKLEMEZ(o, istemci):
    from anyio.from_thread import start_blocking_portal

    r = o.yerel.post("/api/operators/enroll", json={"email": AYSE, "display_name": "A", "pin": "123456"})
    assert r.status_code == 200, r.text[:200]
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet", operator_email=AYSE)
    yukler = [
        ("/api/ai/log/delete_all", {"confirm": "DELETE_ALL"}),
        ("/api/ai/log/delete", {"id": aid}),
        ("/api/ai/log/review", {"analysis_id": aid, "status": "approved", "reviewed_by": ""}),
    ][:istemci]
    with start_blocking_portal(backend="asyncio", backend_options=o.secenek) as portal:
        c = TestClient(o.api.app, client=LAN)
        c.portal = portal  # tek olay döngüsü — üretimdeki uvicorn gibi
        with _TedaviYazimKilidi(o.db):
            kanit = _aparat_kilit_gercek_mi(o)
            assert kanit["ok"] is False and kanit["sn"] > 1.0, f"aparat: tedavi DB kilidi gerçek değil: {kanit}"
            dur, sonuc = threading.Event(), []

            def _dongu(yol, govde):
                while not dur.is_set():
                    sonuc.append((yol, c.post(yol, json=govde, headers=TOKEN).status_code))

            ts = [threading.Thread(target=_dongu, args=y, daemon=True) for y in yukler]
            for t in ts:
                t.start()
            time.sleep(1.0)
            estop = []
            for _ in range(4):
                time.sleep(0.5)
                t0 = time.monotonic()
                re = c.post("/api/hardware/emergency_stop")
                estop.append((round(time.monotonic() - t0, 2), re.status_code))
            t0 = time.monotonic()
            rs = c.post("/api/session/stop", json={})
            stop = (round(time.monotonic() - t0, 2), rs.status_code)
            dur.set()
        for t in ts:
            t.join(90)
    en_kotu = max(s for s, _ in estop)
    print(f"\nC2-3.2 istemci={istemci}: ACİL DURDUR {estop} · STOP {stop} · uçan red {len(sonuc)} {sorted(set(sonuc))}")
    assert all(k == 200 for _, k in estop) and en_kotu < SINIR_SN, (
        f"tedavi DB yazım kilidindeyken kimlik reddi (428) izi ACİL DURDUR'u {en_kotu:.1f} sn bekletti: {estop}"
    )
    assert stop[1] == 200 and stop[0] < SINIR_SN, f"STOP {stop[0]:.1f} sn bekledi ({stop[1]})"
    assert sonuc and {k for _, k in sonuc} == {428}, (
        f"kimliksiz istekler FAIL-CLOSED (428) kalmalı: {sorted(set(sonuc))}"
    )
    with o.db._get_connection() as cc:
        assert (
            cc.execute("SELECT COUNT(*) FROM ai_analyses WHERE id=?", (aid,)).fetchone()[0] == 1
        )  # hiçbir şey silinmedi
