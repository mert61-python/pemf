# -*- coding: utf-8 -*-
"""B2-1.1 = B2-2.1 = B2-3.2 (2-B bağımsız incelemesi — A1, A2, A3 ve orkestratör DÖRT ayrı arıza biçimiyle ölçtü: dosya
kilidi, var olmayan yol, bozuk dosya, Windows ACL reddi) — operatör kimlik kapıları GERÇEK auth DB arızasında FAIL-CLOSED kalır.

ÖLÇÜLEN KUSUR: `auth.kayitli_operator_var()` ve `auth._kayitli_operator_mu()` "hata halinde FAIL-CLOSED (True)" diyor; ama
çağırdıkları `AuthDB.list_operators()` / `AuthDB.operator_exists()` her DB hatasını KENDİLERİ yutup `[]` / `False` döndürüyor
(`get_auth_db()` süreç-tekil → kurucusu bir kez geçtikten sonra auth.py'deki `except` dalına HİÇ ulaşılmaz). auth DB okunamaz
olunca (ACL reddi, kilit zaman aşımı, bozuk dosya) kayıtlı operatörlü klinik sessizce "operatörsüz klinik" (Kural 2) sayılıyordu:
jetonsuz LAN isteği başka hekimin hastasını/seansını SİLİYOR, kayıtlı hekimin beyanı kabul ediliyor (değerlendirme, hasta, seans
adı), tünelden anonim AI Pro onayı kayıtlı hekimin mührünü basıyordu (sonda: `_inceleme/B2-2.1/sonda_failopen.py`).
2-B'nin Y88 fail-closed kolu `get_auth_db`'yi istisna atan bir SAHTEYLE değiştirdiği için bunu göremiyordu (sahte yanlış katta).

Arıza EN ALT katta: tekil `AuthDB` örneğinin `db_path`'i var olmayan dizine (sqlite3 "unable to open database file") ya da
SQLite olmayan dosyaya ("file is not a database") çevrilir; `AuthDB`'nin kendi kodu koşar.
KARŞIT: arıza sürerken arıza ÖNCESİ alınmış jeton yine sahibine yazar ve sahibi kendi kaydını siler; ACİL DURDUR etkilenmez
(Ö.4-Y8); sağlam DB'de operatörsüz klinik (Kural 2) kilitlenmez. D-2.2: tünelden onay 200 KALIR (yalnız mühür '').
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
TEK = "tek@klinik.com"
LAN = ("192.168.1.80", 51535)
TUNEL_BASLIK = {"cf-ray": "8a1b2c3d4e5f-IST", "cf-connecting-ip": "203.0.113.9"}
ARIZA_KIPLERI = ["yol_yok", "bozuk_dosya"]


def _operatorleri_sil(c):
    for op in c.get("/api/operators").json().get("data", []):
        c.post("/api/operators/remove", json={"email": op["email"]})


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as apa
    from database.patient_database import PatientDatabase
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens, patient_router
    from servers.history_router import get_db

    o = apa.kur(monkeypatch, tmp_path)
    hdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: hdb)
    o.api.app.dependency_overrides[get_db] = lambda: o.db
    secenek = dict(apa.ISTEMCI_SECENEKLERI)
    o.hdb = hdb
    o.tmp = tmp_path
    o.yerel = TestClient(o.api.app, client=("127.0.0.1", 51534), backend_options=secenek)
    o.lan = TestClient(o.api.app, client=LAN, backend_options=secenek)
    o.tunel = TestClient(o.api.app, client=("127.0.0.1", 51536), backend_options=secenek)
    operator_tokens.temizle_hepsi()
    _operatorleri_sil(o.yerel)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            o.hc = hc
            yield o
            o.lan.post("/api/session/stop")
            o.lan.post("/api/ai/pro/stop")
    finally:
        o.api.app.dependency_overrides.pop(get_db, None)
        operator_tokens.temizle_hepsi()
        _operatorleri_sil(o.yerel)
        o.geri()


def _iki_hekim_jetonlar(o):
    j = {}
    for e, ad in ((AYSE, "Dr. Ayşe"), (MEHMET, "Dr. Mehmet")):
        r = o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": ad, "pin": "123456"})
        assert r.status_code == 200, r.text[:200]
        j[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return j


class _Ariza:
    """auth DB'yi EN ALT katta bozar; blok çıkışında geri alır (fikstür yıkımı operatörleri gerçek DB'den silebilsin)."""

    def __init__(self, monkeypatch, tmp_path, kip):
        self.mp, self.tmp, self.kip = monkeypatch, tmp_path, kip

    def __enter__(self):
        from database.auth_db import get_auth_db

        self.ctx = self.mp.context()
        m = self.ctx.__enter__()
        adb = get_auth_db()
        if self.kip == "yol_yok":
            m.setattr(adb, "db_path", self.tmp / "yok_dizin" / "auth_users.db")
        else:
            f = self.tmp / "bozuk_auth_users.db"
            f.write_bytes(b"BU BIR SQLITE DOSYASI DEGIL " * 400)
            m.setattr(adb, "db_path", f)
        self.m = m
        return m

    def __exit__(self, *a):
        self.ctx.__exit__(*a)
        return False


def _b(jeton):
    return {"X-PEMF-Operator": jeton} if jeton else {}


def _hasta_say(o, pid):
    with o.hdb._get_connection() as c:
        return c.execute("SELECT COUNT(*) FROM patients WHERE id=?", (pid,)).fetchone()[0]


def _seans_say(o, sid):
    with o.db._get_connection() as c:
        return c.execute("SELECT COUNT(*) FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]


@pytest.mark.parametrize("kip", ARIZA_KIPLERI)
def test_KRITIK_auth_DB_okunamazken_kayitli_operator_VAR_sayilir(o, monkeypatch, kip):
    """MUTASYON: `AuthDB.list_operators`/`operator_exists` hatayı yutsun (bugünkü hâl) → KIRMIZI."""
    from servers import auth

    _iki_hekim_jetonlar(o)
    with _Ariza(monkeypatch, o.tmp, kip):
        assert auth.kayitli_operator_var() is True, (
            "auth DB okunamazken cihaz OPERATÖRSÜZ (Kural 2) sayıldı — fail-OPEN"
        )
        assert auth._kayitli_operator_mu(AYSE) is True, "auth DB okunamazken kayıtlı hekimin beyanı KABUL edilecek"


@pytest.mark.parametrize("kip", ARIZA_KIPLERI)
def test_KRITIK_auth_DB_okunamazken_JETONSUZ_silme_baskasinin_kaydini_SILEMEZ(o, monkeypatch, kip):
    j = _iki_hekim_jetonlar(o)
    r = o.lan.post("/api/patients", json={"name": "Mehmet-Hasta", "species": "Kedi"}, headers=_b(j[MEHMET]))
    hasta = r.json()["patient_id"]
    seans = int(o.db.start_session(treatment_mode="Manuel", patient_name="S-M", operator_email=MEHMET))
    with _Ariza(monkeypatch, o.tmp, kip):
        r1 = o.lan.delete(f"/api/patients/{hasta}")
        r2 = o.yerel.post("/api/history/delete", json={"session_id": seans})
    assert (_hasta_say(o, hasta), _seans_say(o, seans)) == (1, 1), (
        f"auth DB okunamazken jetonsuz istek Mehmet'in kaydını SİLDİ: hasta {r1.status_code}, seans {r2.status_code}"
    )
    assert (r1.status_code, r2.status_code) == (428, 428), (r1.text[:200], r2.text[:200])


@pytest.mark.parametrize("kip", ARIZA_KIPLERI)
def test_KRITIK_auth_DB_okunamazken_kayitli_hekim_BEYANI_kayda_GECMEZ(o, monkeypatch, kip):
    """Değerlendirme 428 (Y88), hasta sahibi '', seans adı/e-postası '' — kanıtsız kayıtlı-hekim beyanı."""
    _iki_hekim_jetonlar(o)
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    with _Ariza(monkeypatch, o.tmp, kip):
        rd = o.lan.post("/api/ai/log/review", json={"analysis_id": aid, "status": "approved", "reviewed_by": AYSE})
        rh = o.lan.post("/api/patients", json={"name": "Boncuk", "species": "Kedi", "operator_email": AYSE})
        rs = o.lan.post(
            "/api/session/start",
            json={
                "coil_ids": [1],
                "frequency": 100,
                "duty": 40,
                "phase": 0,
                "duration_minutes": 5,
                "mode": "Manuel",
                "operator_email": AYSE,
                "operator_name": "Dr. Ayşe",
            },
        )
        satir = o.db.get_session_history(limit=5)[0]
        o.lan.post("/api/session/stop")
    kayit = next(a for a in o.db.get_ai_analyses(limit=50) if a["id"] == aid)
    assert rd.status_code == 428 and (kayit.get("reviewed_by") or "") == "", (rd.status_code, kayit.get("reviewed_by"))
    # Y110 (A-61): kayıtlı operatörlü cihazda (arızada fail-closed) kimliksiz YENİ hasta hiç AÇILMAZ — 428 (önce sahipsiz açılıyordu).
    assert rh.status_code == 428, rh.text[:200]
    assert all((h.get("operator_email") or "") != AYSE for h in o.hdb.get_all_patients()), (
        "hasta kanıtsız beyanla açıldı"
    )
    assert rs.status_code == 200, rs.text[:200]
    assert ((satir.get("operator_name") or ""), (satir.get("operator_email") or "")) == ("", ""), satir


@pytest.mark.parametrize("kip", ARIZA_KIPLERI)
def test_KRITIK_auth_DB_okunamazken_TUNEL_anonim_onay_200_KALIR_muhur_SAHIPSIZ(o, monkeypatch, kip):
    """D-2.2: erişim sınıfı değişmez (onay + başlatma 200); mühür ve seans sahibi kayıtlı hekim OLAMAZ."""
    from servers import ai_approval, auth

    _iki_hekim_jetonlar(o)
    pid = ai_approval.create("ai_pro", {"organ_id": 0, "duration_minutes": 5, "model": "kedi"})["id"]
    with _Ariza(monkeypatch, o.tmp, kip) as m:
        m.setattr(auth, "_require", True)
        r = o.tunel.post("/api/ai/pro/approve", json={"proposal_id": pid, "operator_email": AYSE}, headers=TUNEL_BASLIK)
        r2 = o.tunel.post("/api/ai/pro/start", json={"proposal_id": pid}, headers=TUNEL_BASLIK)
        sahip = o.db.get_session_history(limit=5)[0].get("operator_email")
        o.tunel.post("/api/ai/pro/stop", headers=TUNEL_BASLIK)
    assert (r.status_code, r2.status_code) == (200, 200), "D-2.2: tünel onayı/başlatma 200 kalmalı"
    assert ((ai_approval.get(pid).get("operator") or ""), (sahip or "")) == ("", ""), (
        "auth DB okunamazken tünelden ANONİM istek kayıtlı hekimin mührünü bastı"
    )


@pytest.mark.parametrize("kip", ARIZA_KIPLERI)
def test_KARSIT_auth_DB_okunamazken_JETON_sahibine_yazar_ve_KENDI_kaydini_siler(o, monkeypatch, kip):
    j = _iki_hekim_jetonlar(o)
    r = o.lan.post("/api/patients", json={"name": "Mehmet-Hasta", "species": "Kedi"}, headers=_b(j[MEHMET]))
    hasta = r.json()["patient_id"]
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    with _Ariza(monkeypatch, o.tmp, kip):
        rd = o.lan.post(
            "/api/ai/log/review",
            json={"analysis_id": aid, "status": "approved", "reviewed_by": AYSE},
            headers=_b(j[MEHMET]),
        )
        rs = o.lan.delete(f"/api/patients/{hasta}", headers=_b(j[MEHMET]))
    kayit = next(a for a in o.db.get_ai_analyses(limit=50) if a["id"] == aid)
    assert (rd.status_code, kayit.get("reviewed_by")) == (200, MEHMET), (rd.status_code, rd.text[:200])
    assert rs.status_code == 200 and _hasta_say(o, hasta) == 0, rs.text[:200]


@pytest.mark.parametrize("kip", ARIZA_KIPLERI)
def test_KARSIT_auth_DB_okunamazken_ACIL_DURDUR_kapilanmaz(o, monkeypatch, kip):
    """Ö.4-Y8: ACİL DURDUR hiçbir kimlik kapısına bağlanmaz."""
    _iki_hekim_jetonlar(o)
    with _Ariza(monkeypatch, o.tmp, kip):
        r = o.lan.post("/api/hardware/emergency_stop")
    assert r.status_code == 200, r.text[:200]


def test_KARSIT_KURAL2_saglam_DB_operatorsuz_klinik_KILITLENMEZ(o):
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    rd = o.lan.post("/api/ai/log/review", json={"analysis_id": aid, "status": "approved", "reviewed_by": TEK})
    r = o.lan.post("/api/patients", json={"name": "Tek", "species": "Kedi", "operator_email": TEK})
    pid = r.json()["patient_id"]
    rs = o.lan.delete(f"/api/patients/{pid}")
    assert rd.status_code == 200 and rs.status_code == 200 and _hasta_say(o, pid) == 0, (rd.text[:200], rs.text[:200])
    assert (
        json.dumps(next(a for a in o.db.get_ai_analyses(limit=50) if a["id"] == aid).get("reviewed_by")) == f'"{TEK}"'
    )


@pytest.mark.parametrize("kip", ARIZA_KIPLERI)
def test_KRITIK_auth_DB_okunamazken_operator_LISTESI_503_bos_liste_DEGIL(o, monkeypatch, kip):
    """Boş liste "operatörsüz klinik" (Kural 2) demektir: okunamayan liste 200 `[]` dönerse arayüz de Kural 2'ye düşer
    (B2-3.1). MUTASYON: uç okuma hatasını yutup 200 `[]` dönsün → KIRMIZI."""
    _iki_hekim_jetonlar(o)
    with _Ariza(monkeypatch, o.tmp, kip):
        r = o.lan.get("/api/operators")
    assert r.status_code == 503, (
        f"auth DB okunamazken operatör listesi {r.status_code} {r.text[:120]} — boş liste 'operatörsüz klinik' sanılır"
    )


def test_KARSIT_saglam_DB_operator_LISTESI_200(o):
    _iki_hekim_jetonlar(o)
    r = o.lan.get("/api/operators")
    assert r.status_code == 200 and sorted(x["email"] for x in r.json()["data"]) == sorted([AYSE, MEHMET]), r.text[:200]
