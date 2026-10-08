# -*- coding: utf-8 -*-
"""Y109 (S-B2.1 · B2-2.2 = B2-3.3, 2-B incelemesi) — kayıtlı operatörlü cihazda JETONSUZ her e-posta beyanı SAHİPSİZ.

ÖLÇÜLEN KUSUR (2-B incelemesi, A2 + A3 + orkestratör zinciri Z3a): `auth.cozumlenmis_operator` kural (2)'yi yorumundaki gibi
uygulamıyordu ("jeton yok VE cihazda kayıtlı operatör YOK → beyan"); yalnız beyan KAYITLI bir hekime aitse reddediyordu.
Kayıtlı operatörlü cihazda KAYITSIZ bir adres (paylaşılan giriş e-postası, uydurma, kayıtlı adrese GÖRÜNMEZ karakterle
GÖRSEL EŞ adres) jetonsuz kimlik sayılıyordu: değerlendirme 200 ile o adrese imzalanıyor (Y88 baypası), hasta / AI günlüğü /
seans sahibi doğrulanmamış adres, tünelden anonim AI Pro onay mührü ekranda Ayşe'nin adresi gibi görünen dizeyle basılıyordu.

SAHİP KARARI Y109: kayıtlı operatörlü cihazda jetonsuz HER beyan sahipsizdir — işlem DURMAZ, kayıt sahipsiz yazılır;
değerlendirme ve silme 428 (Y88, A-10). Operatörsüz klinik (Kural 2) aynen. Tünelden AI Pro erişimi (D-2.2, 07-01) değişmez:
onay 200, mühür '', başlatma sürer. ACİL DURDUR ve STOP hiçbir kimlik kapısından geçmez (Ö.4-Y8).

GERÇEK: uçlar (TestClient — LAN / yerel / tünel başlıkları), `operator_tokens`, `auth_db` operatörleri, tedavi + hasta DB'leri
(geçici), `HardwareController` (kaydedici çekirdek). Sahte: görüntü/lokalizasyon/doz (AI Pro aparatı), yayın. Ölçüt ham SQL /
ürünün okuyucusu.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
ORTAK = "klinik@ortak-giris.com"  # operatörler kurulmadan önceki paylaşılan giriş / eski APK oturumu
UYDURMA = "yeni.hekim@baska-klinik.com"
GORSEL_ES = AYSE + "​"  # sıfır genişlikli boşluk: ekranda Ayşe'nin adresi
GORSEL_ES_IC = "dr.ay­se@klinik.com"  # yumuşak tire: ekranda görünmez
TEK = "tek@klinik.com"
LAN = ("192.168.1.83", 51935)
TUNEL_BASLIK = {"cf-ray": "8a1b2c3d4e5f-IST", "cf-connecting-ip": "203.0.113.9"}
KAYITSIZ = [ORTAK, UYDURMA, GORSEL_ES, GORSEL_ES_IC]
KAYITSIZ_ID = ["ortak_giris", "uydurma", "gorsel_es_zwsp", "gorsel_es_shy"]


def _operatorleri_sil(c):
    for op in c.get("/api/operators").json().get("data", []):
        c.post("/api/operators/remove", json={"email": op["email"]})


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as apa
    from database.patient_database import PatientDatabase
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens, patient_router

    o = apa.kur(monkeypatch, tmp_path)
    o.hdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: o.hdb)
    secenek = dict(apa.ISTEMCI_SECENEKLERI)
    o.yerel = TestClient(o.api.app, client=("127.0.0.1", 51934), backend_options=secenek)
    o.lan = TestClient(o.api.app, client=LAN, backend_options=secenek)
    o.tunel = TestClient(o.api.app, client=("127.0.0.1", 51936), backend_options=secenek)
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
        operator_tokens.temizle_hepsi()
        _operatorleri_sil(o.yerel)
        o.geri()


def _iki_hekim(o):
    j = {}
    for e, ad in ((AYSE, "Dr. Ayşe"), (MEHMET, "Dr. Mehmet")):
        r = o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": ad, "pin": "123456"})
        assert r.status_code == 200, r.text[:200]
        j[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return j


def _b(jeton):
    return {"X-PEMF-Operator": jeton} if jeton else {}


def _degerlendir(o, beyan, jeton=""):
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    r = o.lan.post(
        "/api/ai/log/review",
        json={"analysis_id": aid, "status": "approved", "reviewed_by": beyan},
        headers=_b(jeton),
    )
    kayit = next(a for a in o.db.get_ai_analyses(limit=50) if a["id"] == aid)
    iz = [
        (s["operator_email"], s["outcome"], json.loads(s["detail"] or "{}").get("kimlik_kaynagi"))
        for s in o.db.denetim_oku(200, "ai.review")
        if s.get("scope") == f"ai_analiz:{aid}"
    ]
    return r.status_code, kayit.get("review_status") or "", kayit.get("reviewed_by") or "", iz


def _ai_say(o, sahip):
    with o.db._get_connection() as c:
        return c.execute("SELECT COUNT(*) FROM ai_analyses WHERE operator_email = ?", (sahip,)).fetchone()[0]


def _ai_yaz(o, sahip, n=1):
    ids = []
    for i in range(n):
        ids.append(
            o.db.add_ai_analysis(module_id="m", patient_name=f"eski-{i}", result_summary="x", operator_email=sahip)
        )
    return ids


# ─────────────────────────── değerlendirme ve silme → 428 ───────────────────────────


@pytest.mark.parametrize("beyan", KAYITSIZ, ids=KAYITSIZ_ID)
def test_KRITIK_degerlendirme_KAYITSIZ_beyanla_428_imzalanmaz(o, beyan):
    _iki_hekim(o)
    kod, durum, kim, iz = _degerlendir(o, beyan)
    assert (kod, durum, kim) == (428, "", ""), f"Y88 baypası: kayıtsız beyan kimlik sayıldı → {kod} {durum!r} {kim!r}"
    assert iz == [("", "reddedildi", "yok")], iz


@pytest.mark.parametrize("beyan", [ORTAK, GORSEL_ES], ids=["ortak_giris", "gorsel_es"])
def test_KRITIK_AI_kendi_toplu_silme_KAYITSIZ_beyanla_428_hicbir_sey_silinmez(o, beyan):
    _iki_hekim(o)
    _ai_yaz(o, beyan, 3)
    _ai_yaz(o, AYSE, 2)
    r = o.yerel.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "operator_email": beyan})
    assert (r.status_code, _ai_say(o, beyan), _ai_say(o, AYSE)) == (428, 3, 2), (r.status_code, r.text[:200])


def test_KRITIK_AI_tekil_silme_KAYITSIZ_beyanla_428_kayit_durur(o):
    _iki_hekim(o)
    (aid,) = _ai_yaz(o, ORTAK)
    r = o.yerel.post("/api/ai/log/delete", json={"id": aid, "operator_email": ORTAK})
    assert (r.status_code, _ai_say(o, ORTAK)) == (428, 1), (r.status_code, r.text[:200])


# ─────────────────────────── yazma yolları → sahipsiz, işlem DURMAZ ───────────────────────────


@pytest.mark.parametrize("beyan", [ORTAK, GORSEL_ES], ids=["ortak_giris", "gorsel_es"])
def test_KRITIK_AI_gunlugu_sahibi_KAYITSIZ_beyan_OLMAZ_kayit_yazilir(o, beyan):
    _iki_hekim(o)
    r = o.lan.post("/api/ai/log", json={"summary": "s", "operator_email": beyan, "patient_name": "Q"})
    assert r.status_code == 200, r.text[:200]
    rid = r.json()["id"]
    assert (next(a for a in o.db.get_ai_analyses(limit=50) if a["id"] == rid).get("operator_email") or "") == ""


@pytest.mark.parametrize("beyan", [ORTAK, GORSEL_ES], ids=["ortak_giris", "gorsel_es"])
def test_KRITIK_hasta_sahibi_KAYITSIZ_beyan_OLMAZ(o, beyan):
    """Y109: kayıtsız / görsel-eş beyan hastanın sahibi OLAMAZ. Y110'dan (A-61) beri kimliksiz YENİ hasta hiç açılmaz (428)."""
    _iki_hekim(o)
    once = len(o.hdb.get_all_patients())
    r = o.lan.post("/api/patients", json={"name": "Boncuk", "species": "Kedi", "operator_email": beyan})
    sahipler = [h.get("operator_email") or "" for h in o.hdb.get_all_patients()]
    assert beyan not in sahipler, f"kayıtlı operatörlü cihazda doğrulanmamış beyan hasta sahibi oldu: {beyan!r}"
    assert (r.status_code, len(sahipler)) == (428, once), r.text[:200]


def test_KRITIK_seans_KAYITSIZ_beyanla_BASLAR_sahipsiz_yazilir(o):
    _iki_hekim(o)
    r = o.lan.post(
        "/api/session/start",
        json={
            "coil_ids": [1],
            "frequency": 100,
            "duty": 40,
            "phase": 0,
            "duration_minutes": 5,
            "mode": "Manuel",
            "operator_email": ORTAK,
            "operator_name": "Dr. Ayşe",
        },
    )
    assert r.status_code == 200, f"kimlik kuralı tedaviyi durdurmamalı: {r.status_code} {r.text[:200]}"
    satir = o.db.get_session_history(limit=5)[0]
    o.lan.post("/api/session/stop")
    assert ((satir.get("operator_email") or ""), (satir.get("operator_name") or "")) == ("", "")


def _oneri():
    from servers import ai_approval

    return ai_approval.create("ai_pro", {"organ_id": 0, "duration_minutes": 5, "model": "kedi"})["id"]


def _muhur(pid):
    from servers import ai_approval

    return ai_approval.get(pid).get("operator") or ""


def _onayla_baslat(o, istemci, beyan, jeton="", ek=None):
    pid = _oneri()
    r = istemci.post(
        "/api/ai/pro/approve", json={"proposal_id": pid, "operator_email": beyan}, headers={**_b(jeton), **(ek or {})}
    )
    assert r.status_code == 200, f"onay ucu: {r.status_code} {r.text[:200]}"
    muhur = _muhur(pid)
    r = istemci.post("/api/ai/pro/start", json={"proposal_id": pid}, headers=ek or {})
    assert r.status_code == 200, f"başlatma: {r.status_code} {r.text[:200]}"
    sahip = o.db.get_session_history(limit=5)[0].get("operator_email") or ""
    istemci.post("/api/ai/pro/stop", headers=ek or {})
    return muhur, sahip


@pytest.mark.parametrize("beyan", [GORSEL_ES, ORTAK], ids=["gorsel_es", "ortak_giris"])
def test_KRITIK_D22_TUNEL_onay_200_KALIR_muhur_ve_seans_sahibi_SAHIPSIZ(o, monkeypatch, beyan):
    """D-2.2 (sahip kararı 07-01): tünelden kimliksiz AI Pro erişimi DEĞİŞMEZ — onay 200, başlatma sürer; mühür ''."""
    from servers import auth

    _iki_hekim(o)
    monkeypatch.setattr(auth, "_require", True)  # saha kimlik kipi (PEMF_REQUIRE_AUTH=1)
    kontrol = o.tunel.post("/api/ai/log", json={"summary": "x"}, headers=TUNEL_BASLIK)
    assert kontrol.status_code == 401, f"ön koşul: tünel isteği uzak sayılmalı ({kontrol.status_code})"
    assert _onayla_baslat(o, o.tunel, beyan, ek=TUNEL_BASLIK) == ("", ""), (
        "tünelden anonim mühür kayıtsız beyanla basıldı"
    )


def test_KRITIK_AI_Pro_RED_muhru_KAYITSIZ_beyanla_SAHIPSIZ(o):
    _iki_hekim(o)
    pid = _oneri()
    r = o.lan.post("/api/ai/pro/reject", json={"proposal_id": pid, "operator_email": GORSEL_ES, "reason": "x"})
    assert r.status_code == 200, r.text[:200]
    assert _muhur(pid) == ""


# ─────────────────────────── karşıtlar ───────────────────────────


def test_KARSIT_jetonlu_istek_jeton_SAHIBINE_beyan_yok_sayilir(o):
    j = _iki_hekim(o)
    assert _degerlendir(o, ORTAK, j[MEHMET]) == (200, "approved", MEHMET, [(MEHMET, "ok", "jeton")])
    assert _onayla_baslat(o, o.lan, GORSEL_ES, j[AYSE]) == (AYSE, AYSE)


@pytest.mark.parametrize("beyan", [TEK, ORTAK], ids=["tek", "ortak"])
def test_KARSIT_KURAL2_operatorsuz_klinikte_beyan_KABUL(o, beyan):
    """Kural 2: kayıtlı operatörü OLMAYAN tek hekimli klinik kilitlenmez — beyan kimlik sayılır (taklit edilecek kimse yok)."""
    assert _degerlendir(o, beyan) == (200, "approved", beyan, [(beyan, "ok", "beyan")])
    r = o.lan.post("/api/patients", json={"name": "Tekir", "species": "Kedi", "operator_email": beyan})
    pid = r.json()["patient_id"]
    assert next(h.get("operator_email") for h in o.hdb.get_all_patients() if str(h["id"]) == str(pid)) == beyan
    rid = o.lan.post("/api/ai/log", json={"summary": "s", "operator_email": beyan}).json()["id"]
    assert next(a for a in o.db.get_ai_analyses(limit=50) if a["id"] == rid).get("operator_email") == beyan
    assert _onayla_baslat(o, o.lan, beyan) == (beyan, beyan)


def test_KARSIT_KURAL2_AI_kendi_silme_beyanla_SILER(o):
    _ai_yaz(o, TEK, 2)
    r = o.yerel.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "operator_email": TEK})
    assert (r.status_code, _ai_say(o, TEK)) == (200, 0), r.text[:200]


def test_KARSIT_ACIL_DURDUR_ve_STOP_kimlik_kapisindan_GECMEZ(o):
    """Ö.4-Y8: kayıtlı operatörlü cihazda jetonsuz, kayıtsız beyanlı istemci de durdurur."""
    _iki_hekim(o)
    r = o.lan.post(
        "/api/session/start",
        json={"coil_ids": [1], "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 5, "mode": "Manuel"},
    )
    assert r.status_code == 200, r.text[:200]
    assert o.lan.post("/api/session/stop", json={"operator_email": ORTAK}).status_code == 200
    assert o.lan.post("/api/hardware/emergency_stop", json={"operator_email": GORSEL_ES}).status_code == 200
