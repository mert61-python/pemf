# -*- coding: utf-8 -*-
"""D2.19 · B-3.37 — hekimin AI değerlendirmesi kimliği jetondan alır (jetonsuzda "doğrulanmamış beyan" işaretiyle) ve
ÖNCEKİ değerlendirmeyi ezmeden DENETİM İZİNE yazar.

ÖLÇÜLEN KUSUR (DENETIM-03): `set_ai_review` kaydın değerlendirme alanlarını ÜZERİNE yazıyordu ve iz yoktu → bir AI çıktısı
başka bir hekimin adıyla "onaylandı" gösterilebiliyor, önceki red ya da düzeltme iz bırakmadan siliniyordu (klinik
sorumluluk zinciri). Kimlik yarısı D2.41'de (`cozumlenmis_operator`); bu kapı İZ yarısını ve kimlik KAYNAĞI işaretini ölçer.

Kural: her değerlendirme `audit_events`e `ai.review` olarak EKLENİR (append-only): karar, kimlik kaynağı
(jeton / beyan = doğrulanmamış / yok), gerekçenin VARLIĞI. ⚠️ İÇERİK YAZILMAZ: gerekçe METNİ ize girmez (denetim izi,
verinin ikinci kopyası olamaz — `audit_log` ilkesi). Gerçek uçlar (TestClient), gerçek DB (geçici).
"""

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
TEK = "tek@klinik.com"
GEREKCE = "Klinik bulgularla UYUSMUYOR-gizli-gerekce-D219"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens

    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    yerel = TestClient(api.app, client=("127.0.0.1", 51234))
    lan = TestClient(api.app, client=("192.168.1.50", 51235))

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


def _hekimler_ve_jetonlar(o):
    jetonlar = {}
    for e in (AYSE, MEHMET):
        assert (
            o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"}).status_code
            == 200
        )
        jetonlar[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return jetonlar


def _degerlendir(o, aid, durum, beyan, jeton="", not_=""):
    return o.lan.post(
        "/api/ai/log/review",
        json={"analysis_id": aid, "status": durum, "note": not_, "reviewed_by": beyan},
        headers={"X-PEMF-Operator": jeton} if jeton else {},
    )


def _iz(o, aid):
    """Bu analizin `ai.review` olayları, ESKİDEN YENİYE."""
    satirlar = [s for s in o.db.denetim_oku(200, "ai.review") if s.get("scope") == f"ai_analiz:{aid}"]
    return [dict(s, detail=json.loads(s["detail"] or "{}")) for s in reversed(satirlar)]


def test_KRITIK_ikinci_degerlendirme_ILKINI_izden_SILMEZ(o):
    """MUTASYON: değerlendirme ucundan denetim yazımını kaldırmak → KIRMIZI."""
    j = _hekimler_ve_jetonlar(o)
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    assert _degerlendir(o, aid, "approved", AYSE, j[AYSE]).status_code == 200
    assert _degerlendir(o, aid, "rejected", MEHMET, j[MEHMET], GEREKCE).status_code == 200
    iz = _iz(o, aid)
    assert [(s["operator_email"], s["detail"].get("status"), s["detail"].get("kimlik_kaynagi")) for s in iz] == [
        (AYSE, "approved", "jeton"),
        (MEHMET, "rejected", "jeton"),
    ], f"değerlendirme geçmişi izde yok ya da ezildi: {iz}"
    kayit = next(a for a in o.db.get_ai_analyses(limit=10) if a["id"] == aid)
    assert (kayit["review_status"], kayit["reviewed_by"]) == ("rejected", MEHMET)


def test_KRITIK_gerekce_METNI_ize_GIRMEZ_yalniz_varligi(o):
    """İÇERİK YAZILMAZ. MUTASYON: `detail`e notun kendisini koymak → KIRMIZI."""
    j = _hekimler_ve_jetonlar(o)
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    _degerlendir(o, aid, "rejected", MEHMET, j[MEHMET], GEREKCE)
    iz = _iz(o, aid)
    assert iz and iz[-1]["detail"].get("gerekce_var") is True, iz
    assert all(GEREKCE not in json.dumps(s, ensure_ascii=False) for s in o.db.denetim_oku(200)), (
        "gerekçe METNİ ize girdi"
    )


def test_KRITIK_jetonsuz_kayitli_hekim_beyani_izde_SAHIPSIZ_ve_KANITSIZ_isaretli(o):
    # Y88 sonrası bu deneme 428 alır (kayda yazılmaz) — iz yine yazılır (`reddedildi`): kimlik kuralı aynı.
    _hekimler_ve_jetonlar(o)
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    _degerlendir(o, aid, "approved", AYSE)
    iz = _iz(o, aid)
    assert iz, "ön koşul: kanıtsız değerlendirme de izde görünmeli (sinyal kaybolmasın)"
    for s in iz:
        assert s["operator_email"] == "", f"kanıtsız beyan izde hekim adıyla: {s}"
        assert s["detail"].get("kimlik_kaynagi") == "yok" and s["detail"].get("kanitsiz_beyan") == AYSE, s
    assert all(s["operator_email"] != AYSE for s in o.db.denetim_oku(200, "ai.review"))


def test_KARSIT_KURAL2_operatorsuz_klinikte_beyan_DOGRULANMAMIS_diye_isaretli(o):
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    assert _degerlendir(o, aid, "approved", TEK).status_code == 200
    iz = _iz(o, aid)
    assert [(s["operator_email"], s["detail"].get("kimlik_kaynagi")) for s in iz] == [(TEK, "beyan")], iz
