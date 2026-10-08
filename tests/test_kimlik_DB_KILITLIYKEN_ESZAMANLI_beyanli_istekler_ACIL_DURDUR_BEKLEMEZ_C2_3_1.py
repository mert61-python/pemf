# -*- coding: utf-8 -*-
"""C2-3.1 (2-C incelemesi A3 · 2-B2 B2B2-1'in kör kalan yarısı) — kimlik DB'si KİLİTLİYKEN eşzamanlı (eski APK gövdeli) kimlik
istekleri ACİL DURDUR'u BEKLETMEZ.

ÖLÇÜLEN KUSUR: B2B2-1 (`1d54383`) kimlik KARARI okumasını kısa zaman aşımına bağladı (okuma başına ~0,7 sn kilitte) ama kararlar hâlâ
`async` uçlarda OLAY DÖNGÜSÜNDE satır içi ve istek başına okuma sayısı ile eşzamanlı istek sayısı ÇARPILIYOR: beyanlı (eski APK:
`reviewed_by` dolu, jeton yok) değerlendirme 3 katı okuma yapar (`cozumlenmis_operator` → `_kayitli_operator_mu`, `kayitli_operator_var`,
`kimlikli_yaz` → yine `_kayitli_operator_mu`) → istek başına ~2,1 sn döngü donar. Ölçüldü (paylaşılan döngü): TEK istemcide ACİL
DURDUR 2,7–3,6 sn, ÜÇ istemcide 7,9–12,2 sn. B2B2-1 kapısı yalnız `reviewed_by: ""` (1 okuma) + tek istemci ölçtüğü için yeşil
(1,3 sn). Ö.4-Y8: ACİL DURDUR hiçbir kimlik kapısına bağlanamaz — gecikme de bağlanmadır.

GERÇEK: auth DB kopyası ikinci SQLite bağlantısıyla gerçekten kilitlenir (`locking_mode=EXCLUSIVE` + `BEGIN EXCLUSIVE` + yazma);
istekler TEK paylaşılan olay döngüsünden; üç istemci iş parçacığı eşzamanlı. Ölçüt: ACİL DURDUR ve STOP yanıt süresi (en kötü).
KARŞIT: kilit KALKINCA kimlik kararları kısa sürede yine DOĞRU (arıza mandallanmaz) · kilitsiz aynı yükte ACİL DURDUR beklemez ·
kilitte kararlar FAIL-CLOSED (değerlendirme 428, AI günlüğü sahipsiz, silme 428).
"""

from __future__ import annotations

import shutil
import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
ESKI_APK = "eski.apk@klinik.com"  # jetonsuz gövde beyanı (eski APK)
LAN = ("192.168.1.86", 52155)
TOKEN = {"X-API-Key": "DOGRU-TOKEN"}  # eşleştirilmiş LAN istemcisinin cihaz token'ı (A-01)
SINIR_SN = 3.0


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as apa
    from kayitci_donanim import gercek_hc
    from servers import auth, operator_tokens

    o = apa.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(auth, "check_token", lambda t: t == "DOGRU-TOKEN")
    o.tmp = tmp_path
    o.secenek = dict(apa.ISTEMCI_SECENEKLERI)
    o.yerel = TestClient(o.api.app, client=("127.0.0.1", 52154), backend_options=o.secenek)
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


class _Kilit:
    """auth DB'nin kopyası tekile bağlanır ve ikinci bağlantıyla GERÇEKTEN kilitlenir; `birak()` kilidi kaldırır (yol kopyada kalır)."""

    def __init__(self, o, m):
        from database.auth_db import get_auth_db

        adb = get_auth_db()
        self.kopya = o.tmp / "kilitli" / "auth_users.db"
        self.kopya.parent.mkdir()
        shutil.copy2(adb.db_path, self.kopya)
        m.setattr(adb, "db_path", self.kopya)
        self.kc = sqlite3.connect(str(self.kopya), isolation_level=None, timeout=1)
        self.kc.execute("PRAGMA locking_mode=EXCLUSIVE")
        self.kc.execute("BEGIN EXCLUSIVE")
        self.kc.execute("UPDATE device_operators SET last_active = last_active")

    def birak(self):
        if self.kc is not None:
            self.kc.execute("ROLLBACK")
            self.kc.close()
            self.kc = None


def _yukler(aid, yuk):
    deg = ("/api/ai/log/review", {"analysis_id": aid, "status": "approved", "reviewed_by": ESKI_APK}, {})
    if yuk == "degerlendirme_beyanli_x3":
        return [deg] * 3
    if yuk == "ai_gunlugu_beyanli_x5":  # istek başına TEK katı okuma — çarpan yalnız eşzamanlılık
        return [("/api/ai/log", {"summary": "s", "operator_email": ESKI_APK}, {})] * 5
    return [
        deg,
        ("/api/ai/log", {"summary": "s", "operator_email": ESKI_APK}, {}),
        ("/api/ai/log/delete_all", {"confirm": "DELETE_ALL", "operator_email": ESKI_APK}, TOKEN),
    ]


def _yuk_altinda_olc(o, c, yukler):
    dur, sonuc = threading.Event(), []

    def _dongu(yol, govde, bas):
        while not dur.is_set():
            r = c.post(yol, json=govde, headers=bas)
            sonuc.append((yol, r.status_code, (r.json() if r.status_code == 200 else {}).get("id")))

    ts = [threading.Thread(target=_dongu, args=y, daemon=True) for y in yukler]
    for t in ts:
        t.start()
    time.sleep(1.0)
    estop = []
    for _ in range(4):
        time.sleep(0.5)
        t0 = time.monotonic()
        r = c.post("/api/hardware/emergency_stop")
        estop.append((round(time.monotonic() - t0, 2), r.status_code))
    t0 = time.monotonic()
    rs = c.post("/api/session/stop", json={})
    stop = (round(time.monotonic() - t0, 2), rs.status_code)
    dur.set()
    for t in ts:
        t.join(90)
    return estop, stop, sonuc


def _enroll(o):
    r = o.yerel.post("/api/operators/enroll", json={"email": AYSE, "display_name": "A", "pin": "123456"})
    assert r.status_code == 200, r.text[:200]


@pytest.mark.parametrize("yuk", ["degerlendirme_beyanli_x3", "karisik_x3", "ai_gunlugu_beyanli_x5"])
def test_KRITIK_kimlik_DB_KILITLIYKEN_ESZAMANLI_beyanli_istekler_ACIL_DURDUR_ve_STOP_BEKLEMEZ(o, monkeypatch, yuk):
    from anyio.from_thread import start_blocking_portal

    _enroll(o)
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    with monkeypatch.context() as m:
        k = _Kilit(o, m)
        try:
            with start_blocking_portal(backend="asyncio", backend_options=o.secenek) as portal:
                c = TestClient(o.api.app, client=LAN)
                c.portal = portal  # tek olay döngüsü — üretimdeki uvicorn gibi
                estop, stop, sonuc = _yuk_altinda_olc(o, c, _yukler(aid, yuk))
        finally:
            k.birak()
    en_kotu = max(s for s, _ in estop)
    print(f"\nC2-3.1 {yuk}: ACİL DURDUR {estop} · STOP {stop} · uçan kimlik isteği {len(sonuc)}")
    assert all(kod == 200 for _, kod in estop) and en_kotu < SINIR_SN, (
        f"kimlik DB kilitliyken eşzamanlı beyanlı istekler ACİL DURDUR'u {en_kotu:.1f} sn bekletti: {estop}"
    )
    assert stop[1] == 200 and stop[0] < SINIR_SN, f"STOP {stop[0]:.1f} sn bekledi ({stop[1]})"
    assert sonuc, "aparat: kilit sürerken hiç kimlik isteği uçmadı"
    # kilitte kararlar FAIL-CLOSED kalır (B2-1.1 / Y109)
    assert {kod for yol, kod, _ in sonuc if yol == "/api/ai/log/review"} <= {428}, sonuc[:5]
    assert {kod for yol, kod, _ in sonuc if yol == "/api/ai/log/delete_all"} <= {428}, sonuc[:5]
    gunluk = [rid for yol, kod, rid in sonuc if yol == "/api/ai/log" and kod == 200]
    # 2-C incelemesi: `get_ai_analyses` en çok 500 satır döner — uçan kayıt 500'ü aşınca (569, birleşik kümede ölçüldü) eksik satır
    # `None` → sahte "fail-open" kırmızısı. Satırlar SQL ile (sınırsız) okunur; yazılan her kayıt okunmalı.
    with o.db._get_connection() as conn:
        sahipler = {
            int(r[0]): r[1] or "" for r in conn.execute("SELECT id, operator_email FROM ai_analyses").fetchall()
        }
    assert all(rid in sahipler for rid in gunluk), "aparat: kilitte yazılan AI kaydı geri okunamadı"
    assert all(sahipler[rid] == "" for rid in gunluk), "kilitte beyan kimlik sayıldı (fail-open)"


def test_KARSIT_kilit_KALKINCA_kimlik_kararlari_kisa_surede_DOGRU_ariza_mandallanmaz(o, monkeypatch):
    from servers import auth

    _enroll(o)
    with monkeypatch.context() as m:
        k = _Kilit(o, m)
        try:
            assert auth.kayitli_operator_epostalari() is None  # aparat: kilit gerçekten okunamaz yaptı
            assert auth._kayitli_operator_mu("x@y.com") is True  # fail-closed
        finally:
            k.birak()
        t0 = time.monotonic()
        dogru = None
        while time.monotonic() - t0 < 3.0:
            dogru = (
                auth.kayitli_operator_epostalari(),
                auth._kayitli_operator_mu("x@y.com"),
                auth.kayitli_operator_var(),
            )
            if dogru == (frozenset({AYSE}), False, True):
                break
            time.sleep(0.05)
        sure = time.monotonic() - t0
    print(f"\nC2-3.1 karşıt: kilit kalktıktan {sure:.2f} sn sonra karar {dogru}")
    assert dogru == (frozenset({AYSE}), False, True), f"kilit kalktı ama kimlik kararı 3 sn'de düzelmedi: {dogru}"


def test_KARSIT_KILITSIZ_ayni_yukte_ACIL_DURDUR_beklemez(o):
    from anyio.from_thread import start_blocking_portal

    _enroll(o)
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    with start_blocking_portal(backend="asyncio", backend_options=o.secenek) as portal:
        c = TestClient(o.api.app, client=LAN)
        c.portal = portal
        estop, stop, sonuc = _yuk_altinda_olc(o, c, _yukler(aid, "karisik_x3"))
    print(f"\nC2-3.1 karşıt kilitsiz: ACİL DURDUR {estop} · STOP {stop} · istek {len(sonuc)}")
    assert max(s for s, _ in estop) < 1.0 and stop[0] < 1.0, (estop, stop)
    assert {kod for yol, kod, _ in sonuc if yol == "/api/ai/log/review"} == {428}  # sağlam DB'de de kimliksiz 428 (Y88)
