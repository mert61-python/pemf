# -*- coding: utf-8 -*-
"""Y88 (sahip kararı · S6 · İG-6.26 · D2.42) — cihazda kayıtlı operatör VARKEN kimliği çözülemeyen AI değerlendirmesi
arka uçta REDDEDİLİR: 428 "Operatör seçin".

ÖLÇÜLEN KUSUR (ADAY-DOGRULAMA-D2 İG-6.26 V1): iki operatör kayıtlı, kimse seçili değil → jetonsuz `reviewed_by: ""` ile
`/api/ai/log/review` 200 dönüyor, kayıt `approved / ''` (imzasız "Hekim onayladı"). D2.41'in `cozumlenmis_operator`
yaması bu kolu KAPATMAZ (sahipsiz yazar, yine 200) — ölçüldü.

Kural: kimlik çözülemedi + kayıtlı operatör var → 428, kayıt DEĞİŞMEZ, deneme izde `reddedildi` (sinyal kaybolmaz).
Karşıt kollar: jetonlu LAN isteği (A-01: LAN erişim sınıfı değişmez) → 200 jeton sahibine; Kural 2: kayıtlı operatörü
OLMAYAN tek hekimli klinik → beyanla (boş beyan dahil) 200, kilitlenmez. Gerçek uçlar (TestClient), gerçek DB (geçici).
"""

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
TEK = "tek@klinik.com"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens

    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    yerel = TestClient(api.app, client=("127.0.0.1", 51334))
    lan = TestClient(api.app, client=("192.168.1.60", 51335))

    def _sil():
        for op in yerel.get("/api/operators").json().get("data", []):
            yerel.post("/api/operators/remove", json={"email": op["email"]})

    operator_tokens.temizle_hepsi()
    _sil()
    try:
        yield type("O", (), {"db": db, "yerel": yerel, "lan": lan})
    finally:
        operator_tokens.temizle_hepsi()
        _sil()
        db.close_connections()


def _iki_hekim(o):
    jetonlar = {}
    for e in (AYSE, MEHMET):
        r = o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"})
        assert r.status_code == 200, r.text[:200]
        jetonlar[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return jetonlar


def _degerlendir(o, istemci, beyan, jeton="", durum="approved", not_=""):
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    r = istemci.post(
        "/api/ai/log/review",
        json={"analysis_id": aid, "status": durum, "note": not_, "reviewed_by": beyan},
        headers={"X-PEMF-Operator": jeton} if jeton else {},
    )
    kayit = next(a for a in o.db.get_ai_analyses(limit=50) if a["id"] == aid)
    iz = [
        dict(s, detail=json.loads(s["detail"] or "{}"))
        for s in o.db.denetim_oku(200, "ai.review")
        if s.get("scope") == f"ai_analiz:{aid}"
    ]
    return r, kayit, iz


@pytest.mark.parametrize("beyan", ["", AYSE], ids=["bos_beyan", "kanitsiz_kayitli_hekim_beyani"])
def test_KRITIK_kayitli_operator_varken_KIMLIKSIZ_degerlendirme_428_ve_kayit_DEGISMEZ(o, beyan):
    """MUTASYON: Y88 dalını kaldırmak → 200 + `approved` → KIRMIZI."""
    _iki_hekim(o)
    r, kayit, iz = _degerlendir(o, o.lan, beyan)
    assert r.status_code == 428, f"kimliksiz değerlendirme kabul edildi: {r.status_code} {r.text[:200]}"
    assert "Operatör seçin" in r.json().get("detail", ""), r.text[:200]
    assert (kayit.get("review_status") or "", kayit.get("reviewed_by") or "") == ("", ""), (
        f"reddedilen değerlendirme kayda yazıldı: {kayit}"
    )
    # Deneme izde KALIR (sinyal), sahipsiz ve 'reddedildi'.
    assert [(s["operator_email"], s["outcome"], s["detail"].get("kimlik_kaynagi")) for s in iz] == [
        ("", "reddedildi", "yok")
    ], iz


def test_KRITIK_yerel_istemci_de_KIMLIKSIZSE_428(o):
    """Kapı istemcinin konumuna bakmaz (masaüstü/loopback da kimlik ister) — kimlik kuralıdır, erişim sınıfı değil."""
    _iki_hekim(o)
    r, kayit, _ = _degerlendir(o, o.yerel, "")
    assert r.status_code == 428 and not kayit.get("review_status"), (r.status_code, kayit)


def test_KRITIK_operator_listesi_OKUNAMAZSA_FAIL_CLOSED_428(o, monkeypatch):
    """Bilemiyorsak kimliksiz isteği operatörsüz klinik sanıp kabul ETMEYİZ. MUTASYON: hata dalında False → KIRMIZI."""
    from database import auth_db

    class _Bozuk:
        def list_operators(self):
            raise RuntimeError("auth db okunamadi (taklit)")

        def operator_exists(self, _e):
            raise RuntimeError("auth db okunamadi (taklit)")

    # Yama BU blokta kalır: fikstür yıkımı (operatör temizliği) gerçek auth DB'sine erişebilmeli.
    with monkeypatch.context() as m:
        m.setattr(auth_db, "get_auth_db", lambda: _Bozuk())
        r, kayit, _ = _degerlendir(o, o.lan, "")
    assert r.status_code == 428 and not kayit.get("review_status"), (r.status_code, kayit)


def test_KARSIT_A01_jetonlu_LAN_istegi_200_jeton_SAHIBINE(o):
    j = _iki_hekim(o)
    r, kayit, iz = _degerlendir(o, o.lan, AYSE, j[MEHMET], durum="rejected", not_="uyusmuyor")
    assert r.status_code == 200, r.text[:200]
    assert (kayit["review_status"], kayit["reviewed_by"]) == ("rejected", MEHMET)
    assert [(s["operator_email"], s["outcome"]) for s in iz] == [(MEHMET, "ok")], iz


@pytest.mark.parametrize("beyan", [TEK, ""], ids=["beyanli", "bos_beyan_eski_istemci"])
def test_KARSIT_KURAL2_operatorsuz_tek_hekimli_klinik_KILITLENMEZ(o, beyan):
    r, kayit, _ = _degerlendir(o, o.lan, beyan)
    assert r.status_code == 200, f"Kural 2 ihlali: operatörsüz klinik kilitlendi: {r.status_code} {r.text[:200]}"
    assert (kayit["review_status"], kayit["reviewed_by"] or "") == ("approved", beyan)
