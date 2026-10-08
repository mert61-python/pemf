# -*- coding: utf-8 -*-
"""B2B2-1 (2-B2 yeni bulgu, Y113 karşıt kolu ölçülürken) — kimlik DB'si KİLİTLİYKEN ACİL DURDUR / STOP BEKLEMEZ.

ÖLÇÜLEN KUSUR: kimlik kararları (`auth.kayitli_operator_var`, `_kayitli_operator_mu`, `cozumlenmis_operator_adi`) `async` uçlarda
(AI değerlendirmesi, AI günlüğü, AI Pro onayı, denetim izi …) OLAY DÖNGÜSÜNDE satır içi auth DB okur. `auth_users.db` başka bir
süreç tarafından kilitliyken (yedekleme aracı, ikinci bir backend, SQLite `locking_mode=EXCLUSIVE`) her okuma ~26 sn bekliyordu
(`connect(timeout=10)` + her bağlantıda `PRAGMA journal_mode=WAL` + `busy_timeout=5000`, üstelik `AuthDB._lock` altında) → döngü
donuyor, ACİL DURDUR HTTP isteği 24,4 sn bekliyordu (sonda, paylaşılan döngü: değerlendirme ve beyanlı AI günlüğü yolları).
Ö.4-Y8: ACİL DURDUR hiçbir kimlik kapısına bağlanamaz — gecikme de bağlanmadır.

DÜZELTME (en alt kat, `AuthDB`): kimlik KARARI okumaları (`kati=True`) kendi kısa zaman aşımlı bağlantısıyla, `AuthDB._lock`'u
BEKLEMEDEN (WAL okuyucuları eşzamanlı güvenlidir) okunur ve bağlantı kapatılır; kilitte hızla düşer → çağıran FAIL-CLOSED
(B2-1.1 korunur: kimliksiz istek 428 / sahipsiz).

GERÇEK: auth DB'nin kopyası İKİNCİ bir SQLite bağlantısıyla gerçekten kilitlenir (`locking_mode=EXCLUSIVE` + `BEGIN EXCLUSIVE` +
yazma); istekler TEK paylaşılan olay döngüsünden (üretimdeki uvicorn gibi) gider; kilit sürerken `AuthDB._lock`'u tutan gerçek bir
PIN doğrulaması (`/api/operators/verify`, iş parçacığında) da uçuştadır. Ölçüt: ACİL DURDUR ve STOP yanıt süresi.
"""

from __future__ import annotations

import shutil
import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
LAN = ("192.168.1.85", 52135)
SINIR_SN = 3.0  # önce: 24–85 sn; düzeltmeyle ~1,3 sn (kilitte tek katı okuma ~0,8 sn)


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as apa
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens

    o = apa.kur(monkeypatch, tmp_path)
    o.tmp = tmp_path
    o.secenek = dict(apa.ISTEMCI_SECENEKLERI)
    o.yerel = TestClient(o.api.app, client=("127.0.0.1", 52134), backend_options=o.secenek)
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


def _kilitli_kopya(o, m):
    """auth DB'nin kopyası tekile bağlanır ve ikinci bağlantıyla GERÇEKTEN kilitlenir. Dönen bağlantı kilidi tutar."""
    from database.auth_db import get_auth_db

    adb = get_auth_db()
    kopya = o.tmp / "kilitli" / "auth_users.db"
    kopya.parent.mkdir()
    shutil.copy2(adb.db_path, kopya)
    m.setattr(adb, "db_path", kopya)
    kc = sqlite3.connect(str(kopya), isolation_level=None, timeout=1)
    kc.execute("PRAGMA locking_mode=EXCLUSIVE")
    kc.execute("BEGIN EXCLUSIVE")
    kc.execute("UPDATE device_operators SET last_active = last_active")
    return kc


def _paylasilan_istemci(o, portal):
    c = TestClient(o.api.app, client=LAN)
    c.portal = portal  # tek olay döngüsü — üretimdeki uvicorn gibi
    return c


@pytest.mark.parametrize("yol", ["degerlendirme", "ai_gunlugu_beyanli"])
def test_KRITIK_kimlik_DB_KILITLIYKEN_ACIL_DURDUR_ve_STOP_BEKLEMEZ(o, monkeypatch, yol):
    from anyio.from_thread import start_blocking_portal

    r = o.yerel.post("/api/operators/enroll", json={"email": AYSE, "display_name": "A", "pin": "123456"})
    assert r.status_code == 200, r.text[:200]
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    with monkeypatch.context() as m:
        kc = _kilitli_kopya(o, m)
        try:
            with start_blocking_portal(backend="asyncio", backend_options=o.secenek) as portal:
                c = _paylasilan_istemci(o, portal)
                dur = threading.Event()
                kimlik_sonuc: list = []

                def _pin():  # AuthDB._lock'u tutan gerçek yazma yolu (iş parçacığında)
                    c.post("/api/operators/verify", json={"email": AYSE, "pin": "123456"})

                def _kimlik_yuku():  # olay döngüsünde satır içi kimlik okuyan uçlar, art arda
                    while not dur.is_set():
                        if yol == "degerlendirme":
                            rr = c.post(
                                "/api/ai/log/review", json={"analysis_id": aid, "status": "approved", "reviewed_by": ""}
                            )
                            kimlik_sonuc.append(rr.status_code)
                        else:
                            rr = c.post("/api/ai/log", json={"summary": "s", "operator_email": "x@y.com"})
                            rid = rr.json().get("id")
                            sahip = next(
                                (
                                    a.get("operator_email") or ""
                                    for a in o.db.get_ai_analyses(limit=200)
                                    if a["id"] == rid
                                ),
                                "?",
                            )
                            kimlik_sonuc.append((rr.status_code, sahip))

                tp = threading.Thread(target=_pin, daemon=True)
                tk = threading.Thread(target=_kimlik_yuku, daemon=True)
                tp.start()
                time.sleep(0.3)
                tk.start()
                time.sleep(1.0)
                t0 = time.monotonic()
                re = c.post("/api/hardware/emergency_stop")
                estop_sn = time.monotonic() - t0
                t0 = time.monotonic()
                rs = c.post("/api/session/stop", json={})
                stop_sn = time.monotonic() - t0
                dur.set()
                tk.join(90)
                tp.join(90)
        finally:
            kc.execute("ROLLBACK")
            kc.close()
    print(
        f"\nB2B2-1 {yol}: ACİL DURDUR {estop_sn:.2f} sn · STOP {stop_sn:.2f} sn · uçan kimlik isteği {len(kimlik_sonuc)}"
    )
    assert re.status_code == 200 and estop_sn < SINIR_SN, (
        f"kimlik DB kilitliyken ACİL DURDUR {estop_sn:.1f} sn bekledi ({re.status_code}) — olay döngüsü kimlik okumasında donuk"
    )
    assert rs.status_code == 200 and stop_sn < SINIR_SN, f"STOP {stop_sn:.1f} sn bekledi ({rs.status_code})"
    assert kimlik_sonuc, "aparat: kilit sürerken hiç kimlik isteği uçmadı"
    if yol == "degerlendirme":
        assert set(kimlik_sonuc) == {428}, f"kilitte kimliksiz değerlendirme FAIL-CLOSED kalmalı: {kimlik_sonuc}"
    else:
        assert all(k == (200, "") for k in kimlik_sonuc), f"kilitte beyan kimlik sayıldı (fail-open): {kimlik_sonuc}"


def test_KARSIT_kimlik_okumasi_ESZAMANLI_PIN_dogrulamasi_altinda_YANLIS_ariza_uretmez(o):
    """Kısa zaman aşımı normal yükte yanlış 'okunamıyor' üretmemeli: PIN doğrulamaları (PBKDF2 + yazma, `AuthDB._lock` altında)
    art arda koşarken katı okumalar hep kayıtlı operatörü görür."""
    from servers import auth

    r = o.yerel.post("/api/operators/enroll", json={"email": AYSE, "display_name": "A", "pin": "123456"})
    assert r.status_code == 200, r.text[:200]
    dur = threading.Event()

    def _pinler():
        while not dur.is_set():
            o.yerel.post("/api/operators/verify", json={"email": AYSE, "pin": "123456"})

    t = threading.Thread(target=_pinler, daemon=True)
    t.start()
    try:
        sonuc = [
            (auth.kayitli_operator_var(), auth._kayitli_operator_mu(AYSE), auth._kayitli_operator_mu("x@y.com"))
            for _ in range(60)
        ]
    finally:
        dur.set()
        t.join(30)
    assert set(sonuc) == {(True, True, False)}, f"normal yükte yanlış kimlik kararı: {sorted(set(sonuc))}"
