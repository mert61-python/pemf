# -*- coding: utf-8 -*-
"""D2.41 · B-2.3 · B-2.11 · B-2.19 · D-2.2 (+ aday İG-6.25) — KAYDA MÜHÜRLENEN HEKİM KİMLİĞİ `cozumlenmis_operator`'dan.

ÖLÇÜLEN KUSUR (DENETIM-02 + 02-2; aday İG-6.25 ayrı süreç saha kimlik kipinde): kural (`auth.cozumlenmis_operator`: jeton
varsa jetondan; jeton yok + beyan KAYITLI bir hekime aitse SAHİPSİZ; kayıtlı operatör yoksa beyan) VAR ama dört yol onu
ÇAĞIRMIYORDU — AI değerlendirmesi (`reviewed_by`), hasta ekleme (`operator_email`), seans `operator_name`, AI Pro onay/red
mührü (ve `/start`'ın mühürden okunan seans sahibi). LAN'dan jetonsuz (ya da başka hekimin jetonuyla) kayıtlı bir hekimin
adı yazılabiliyordu; tünelden ANONİM bir istek kayıtlı bir hekimin adıyla onay mührü basıp tedaviyi başlatıyordu.

⚠️ D-2.2 SAHİP KARARI: `/api/ai/pro/*` tünelden kimliksiz erişilebilir — ERİŞİM SINIFI DEĞİŞMEZ. Tünelden token'sız
approve 200 KALIR; değişen yalnız mührün İÇERİĞİ ('' olur) ve başlatma SÜRER.
⚠️ Kural 2: kayıtlı operatörü OLMAYAN tek hekimli klinikte beyan kabul edilir (her yolun karşıt kolu).

GERÇEK: uçlar (TestClient — LAN 192.168.1.50 / yerel / tünel başlıkları), `operator_tokens`, `auth_db` operatörleri, tedavi ve
hasta DB'leri (geçici), `HardwareController` (kaydedici çekirdek). Sahte: görüntü/lokalizasyon/doz (AI Pro aparatı), yayın.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
TEK = "tek@klinik.com"
LAN = ("192.168.1.50", 51235)
TUNEL_BASLIK = {"cf-ray": "8a1b2c3d4e5f-IST", "cf-connecting-ip": "203.0.113.9"}


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
    hdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: hdb)
    secenek = dict(apa.ISTEMCI_SECENEKLERI)
    o.hdb = hdb
    o.yerel = TestClient(o.api.app, client=("127.0.0.1", 51234), backend_options=secenek)
    o.lan = TestClient(o.api.app, client=LAN, backend_options=secenek)
    o.tunel = TestClient(o.api.app, client=("127.0.0.1", 51236), backend_options=secenek)
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


def _kaydet(o, eposta, ad):
    r = o.yerel.post("/api/operators/enroll", json={"email": eposta, "display_name": ad, "pin": "123456"})
    assert r.status_code == 200, r.text[:200]


def _jeton(o, eposta):
    r = o.yerel.post("/api/operators/verify", json={"email": eposta, "pin": "123456"})
    assert r.status_code == 200, r.text[:200]
    return r.json()["operator_token"]


def _iki_hekim(o):
    _kaydet(o, AYSE, "Dr. Ayşe")
    _kaydet(o, MEHMET, "Dr. Mehmet")


def _b(jeton):
    return {"X-PEMF-Operator": jeton} if jeton else {}


# ─────────────────────────── (a) AI değerlendirmesi `reviewed_by` ───────────────────────────


def _degerlendir(o, istemci, beyan, jeton=""):
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    istemci.post(
        "/api/ai/log/review", json={"analysis_id": aid, "status": "approved", "reviewed_by": beyan}, headers=_b(jeton)
    )
    return next(a for a in o.db.get_ai_analyses(limit=50) if a["id"] == aid).get("reviewed_by") or ""


def test_KRITIK_a_degerlendirme_JETONSUZ_kayitli_hekim_beyani_SAHIPSIZ(o):
    """MUTASYON: `set_ai_review`a `payload.reviewed_by`yi doğrudan geçirmek → KIRMIZI.

    ⚠️ KATMAN (Y88 sonrası): bu istek artık 428 ile durur ve kayda HİÇ yazılmaz; yukarıdaki tek mutant Y88 katmanı
    arkasında eşdeğerdir — ısırması Y88 dalı da indirilince ölçülür (tests/test_degerlendirme_KIMLIKSIZ_428_Y88.py)."""
    _iki_hekim(o)
    assert _degerlendir(o, o.lan, AYSE) == "", "jetonsuz LAN beyanı kayıtlı hekimin adıyla 'onaylandı' yazdı"


def test_KRITIK_a2_degerlendirme_JETON_SAHIBINE_yazilir_beyan_yok_sayilir(o):
    _iki_hekim(o)
    assert _degerlendir(o, o.lan, AYSE, _jeton(o, MEHMET)) == MEHMET


def test_KARSIT_a_KURAL2_operatorsuz_klinikte_beyan_kabul(o):
    assert _degerlendir(o, o.lan, TEK) == TEK


# ─────────────────────────── (b) hasta ekleme `operator_email` ───────────────────────────


def _hasta_ekle(o, istemci, beyan, jeton=""):
    r = istemci.post(
        "/api/patients", json={"name": "Boncuk", "species": "Kedi", "operator_email": beyan}, headers=_b(jeton)
    )
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    pid = r.json()["patient_id"]
    # Çapa API okuması (DB alanı `enc:` şifreli): ekranın gördüğü değer.
    hastalar = o.yerel.get("/api/patients").json()["data"]
    return next(h for h in hastalar if str(h["id"]) == str(pid)).get("operator_email") or ""


def test_KRITIK_b_hasta_JETONSUZ_kayitli_hekim_beyani_SAHIP_OLAMAZ_Y110(o):
    """Kanıtsız kayıtlı-hekim beyanı hastanın sahibi OLAMAZ. Y110'dan (A-61) beri kayıtlı operatörlü cihazda kimliksiz YENİ
    hasta hiç AÇILMAZ — 428, satır yok (önce sahipsiz açılıyor, herkesin "Benim" listesine düşüyordu)."""
    _iki_hekim(o)
    once = len(o.yerel.get("/api/patients").json()["data"])
    r = o.lan.post("/api/patients", json={"name": "Boncuk", "species": "Kedi", "operator_email": AYSE})
    assert r.status_code == 428, r.text[:200]
    assert len(o.yerel.get("/api/patients").json()["data"]) == once


def test_KRITIK_b2_hasta_JETON_SAHIBINE_yazilir(o):
    _iki_hekim(o)
    assert _hasta_ekle(o, o.lan, AYSE, _jeton(o, MEHMET)) == MEHMET


def test_KARSIT_b_KURAL2_operatorsuz_klinikte_beyan_kabul(o):
    assert _hasta_ekle(o, o.lan, TEK) == TEK


# ─────────────────────────── (c) seans `operator_name` ───────────────────────────


def _seans_baslat(o, beyan_eposta, beyan_ad, jeton=""):
    r = o.lan.post(
        "/api/session/start",
        json={
            "coil_ids": [1],
            "frequency": 100,
            "duty": 40,
            "phase": 0,
            "duration_minutes": 5,
            "mode": "Manuel",
            "operator_email": beyan_eposta,
            "operator_name": beyan_ad,
        },
        headers=_b(jeton),
    )
    assert r.status_code == 200, r.text[:300]
    satir = o.db.get_session_history(limit=5)[0]
    with o.db._get_connection() as c:
        olay = c.execute(
            "SELECT payload FROM session_events WHERE event_type='session_started' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    o.lan.post("/api/session/stop")
    yuk = json.loads(olay[0]) if olay else {}
    return (satir.get("operator_name") or "", satir.get("operator_email") or ""), (
        yuk.get("operator_name") or "",
        yuk.get("operator_email") or "",
    )


def test_KRITIK_c_seans_JETONSUZ_kayitli_hekim_ADI_kayda_ve_ize_GECMEZ(o):
    _iki_hekim(o)
    satir, olay = _seans_baslat(o, AYSE, "Dr Ayse")
    assert satir == ("", "") and olay == ("", ""), f"kanıtsız beyan seansa mühürlendi: satır={satir} olay={olay}"


def test_KRITIK_c2_seans_JETONLU_hekimin_KAYITLI_adi_yazilir(o):
    _iki_hekim(o)
    satir, olay = _seans_baslat(o, AYSE, "Dr Ayse", _jeton(o, MEHMET))
    assert satir == ("Dr. Mehmet", MEHMET) and olay == ("Dr. Mehmet", MEHMET), (satir, olay)


def test_KARSIT_c_KURAL2_operatorsuz_klinikte_beyan_kabul(o):
    satir, olay = _seans_baslat(o, TEK, "Dr Tek")
    assert satir == ("Dr Tek", TEK) and olay == ("Dr Tek", TEK), (satir, olay)


def test_KARSIT_c_KURAL2_YALNIZ_ad_gonderen_eski_istemci_adi_korunur(o):
    """Operatörsüz klinikte e-posta göndermeyen (yalnız ad) eski istemci: ad yine yazılır (Kural 2)."""
    satir, olay = _seans_baslat(o, "", "Dr Eski")
    assert satir == ("Dr Eski", "") and olay == ("Dr Eski", ""), (satir, olay)


def test_KRITIK_c3_kayitli_operatorlu_cihazda_YALNIZ_ad_beyani_YAZILMAZ(o):
    """Kayıtlı operatörlü cihazda kimliksiz ad beyanı (e-posta yok) kayda ve ize geçmez."""
    _iki_hekim(o)
    satir, olay = _seans_baslat(o, "", "Dr. Ayşe")
    assert satir == ("", "") and olay == ("", ""), (satir, olay)


# ─────────────────────────── (d) AI Pro onay/red mührü + `/start` ───────────────────────────


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


def test_KRITIK_d1_onay_muhru_ve_seans_sahibi_JETON_sahibi(o):
    """MUTASYON: approve'a `payload.operator_email`i doğrudan geçirmek → KIRMIZI."""
    _iki_hekim(o)
    assert _onayla_baslat(o, o.lan, AYSE, _jeton(o, MEHMET)) == (MEHMET, MEHMET)


def test_KRITIK_d2_JETONSUZ_kayitli_beyan_muhur_SAHIPSIZ_baslatma_SURER(o):
    _iki_hekim(o)
    assert _onayla_baslat(o, o.lan, AYSE) == ("", "")


def test_KRITIK_d3_TUNEL_anahtarsiz_onay_200_KALIR_muhur_SAHIPSIZ_baslatma_SURER(o, monkeypatch):
    """D-2.2 sahip kararı: erişim sınıfı DEĞİŞMEZ. MUTASYON: approve'u 403'e çevirmek → KIRMIZI ("200 kalmalı")."""
    from servers import auth

    _iki_hekim(o)
    monkeypatch.setattr(auth, "_require", True)  # saha kimlik kipi (PEMF_REQUIRE_AUTH=1)
    kontrol = o.tunel.post("/api/ai/log", json={"summary": "x"}, headers=TUNEL_BASLIK)
    assert kontrol.status_code == 401, f"ön koşul: tünel isteği uzak sayılmalı ({kontrol.status_code})"
    assert _onayla_baslat(o, o.tunel, AYSE, ek=TUNEL_BASLIK) == ("", "")


def test_KRITIK_d4_RED_muhru_JETON_sahibi(o):
    _iki_hekim(o)
    pid = _oneri()
    r = o.lan.post(
        "/api/ai/pro/reject",
        json={"proposal_id": pid, "operator_email": AYSE, "reason": "lokalizasyon"},
        headers=_b(_jeton(o, MEHMET)),
    )
    assert r.status_code == 200, r.text[:200]
    assert _muhur(pid) == MEHMET


def test_KARSIT_d_KURAL2_operatorsuz_klinikte_onay_beyani_kabul(o):
    assert _onayla_baslat(o, o.lan, TEK) == (TEK, TEK)
