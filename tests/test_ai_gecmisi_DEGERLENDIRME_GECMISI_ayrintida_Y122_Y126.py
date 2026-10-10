# -*- coding: utf-8 -*-
"""Y122 (S-C.4) + Y126 (S-A2.3) — AI değerlendirme GEÇMİŞİNİN METİNLERİ listede değil, kayıt AYRINTISINDA.

Y126: jetonsuz LAN AI geçmişi listesi (A-02) değerlendirme geçmişinin METİNLERİNİ taşımaz, yalnız SAYISINI; hangi kayıtların listelendiği
DEĞİŞMEZ (A-02 aynen). Y122: geçmiş AI Geçmişi kaydının ayrıntısında "Önceki değerlendirmeler" (karar, metin, hekim, zaman) olarak kaydı
görebilen hekime gösterilir; PDF raporuna GİRMEZ.
ÖLÇÜLEN KUSUR: `GET /api/ai/log` (LAN'dan jetonsuz) her kaydın önceki red gerekçelerini / düzeltilmiş teşhis METİNLERİNİ taşıyordu;
ayrıntı ucu yoktu.
Ayrıntı ucunun kimlik kuralı (silme/değerlendirme ile aynı): cihazda kayıtlı operatör VARSA kimlik yalnız operatör jetonundan (kimliksiz →
428); kayıtlı operatör YOKSA (Kural 2, tek hekimli klinik) serbest. Tünel/uzak kuralı değişmez.
GERÇEK: `/api/ai/log/review`, `GET /api/ai/log`, `GET /api/ai/log/{id}`, operatör kaydı/jetonu, `TreatmentHistoryDB` (tmp), PDF ögeleri.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
GEREKCE = "Lezyon sinirlari yanlis-Y122-gizli-gerekce"
FIKSTUR_DIZIN = Path(__file__).resolve().parents[1] / "apps" / "ui" / "src" / "screens" / "__tests__" / "__fixtures__"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens

    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    yerel = TestClient(api.app, client=("127.0.0.1", 51236))
    lan = TestClient(api.app, client=("192.168.1.50", 51237))

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


def _jeton(o, e=AYSE):
    assert (
        o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": e, "pin": "123456"}).status_code == 200
    )
    return o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]


def _iki_degerlendirmeli_kayit(o, jeton="", beyan=""):
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    h = {"X-PEMF-Operator": jeton} if jeton else {}
    for durum, not_ in (("rejected", GEREKCE), ("approved", "")):
        r = o.lan.post(
            "/api/ai/log/review",
            json={"analysis_id": aid, "status": durum, "note": not_, "reviewed_by": beyan},
            headers=h,
        )
        assert r.status_code == 200, r.text[:200]
    return aid


def test_KRITIK_Y126_jetonsuz_LAN_listesi_gecmis_METNI_tasimaz_SAYISINI_tasir(o):
    """MUTASYON: liste ucu geçmişi yeniden taşır → KIRMIZI."""
    aid = _iki_degerlendirmeli_kayit(o, jeton=_jeton(o))
    diger = o.db.add_ai_analysis(module_id="m", patient_name="Q", result_summary="ozet2")
    r = o.lan.get("/api/ai/log", params={"limit": 50})
    assert r.status_code == 200, "A-02: liste LAN'dan jetonsuz OLMALI"
    ham = r.text
    assert GEREKCE not in ham and "Y122-gizli" not in ham, (
        "jetonsuz LAN listesi önceki değerlendirme METNİNİ taşıyor (Y126)"
    )
    k = {x["id"]: x for x in r.json()["data"]}
    assert set(k) == {aid, diger}, "A-02: listelenen kayıtlar değişti"
    assert k[aid]["review_history_count"] == 1 and "review_history" not in k[aid], k[aid]
    assert k[diger]["review_history_count"] == 0


def test_KRITIK_Y122_ayrinti_ucu_metinleri_TASIR_kayitli_klinikte_JETONLA(o):
    j = _jeton(o)
    aid = _iki_degerlendirmeli_kayit(o, jeton=j)
    r = o.lan.get(f"/api/ai/log/{aid}", headers={"X-PEMF-Operator": j})
    assert r.status_code == 200, r.text[:200]
    gecmis = r.json()["data"]["review_history"]
    assert [(g["status"], g["note"], g["reviewed_by"]) for g in gecmis] == [("rejected", GEREKCE, AYSE)], gecmis
    assert gecmis[0]["reviewed_at"], "zaman yok"


def test_KRITIK_Y122_kayitli_klinikte_KIMLIKSIZ_ayrinti_428_metin_YOK(o):
    """MUTASYON: kimlik kapısı kaldırılır → KIRMIZI."""
    aid = _iki_degerlendirmeli_kayit(o, jeton=_jeton(o))
    r = o.lan.get(f"/api/ai/log/{aid}")
    assert r.status_code == 428, f"kayıtlı operatörlü klinikte kimliksiz ayrıntı açıldı: {r.status_code}"
    assert GEREKCE not in r.text


def test_KARSIT_Kural2_operatorsuz_klinikte_ayrinti_SERBEST(o):
    aid = _iki_degerlendirmeli_kayit(o, beyan="tek@klinik.com")
    r = o.lan.get(f"/api/ai/log/{aid}")
    assert r.status_code == 200 and [g["note"] for g in r.json()["data"]["review_history"]] == [GEREKCE]


def test_KARSIT_olmayan_kayit_404(o):
    assert o.lan.get("/api/ai/log/987654").status_code == 404


def test_KRITIK_Y122_PDF_ogeleri_onceki_degerlendirmeleri_ICERMEZ(o):
    """Y122: geçmiş PDF raporuna GİRMEZ — ayrıntı ucunun (metinli) kaydıyla PDF ögeleri kurulsa bile."""
    from utils.ai_rapor_ogeleri import analiz_pdf_ogeleri

    aid = _iki_degerlendirmeli_kayit(o, beyan="tek@klinik.com")
    kayit = o.lan.get(f"/api/ai/log/{aid}").json()["data"]
    assert kayit["review_history"], "aparat: geçmiş yok"
    assert GEREKCE not in json.dumps(analiz_pdf_ogeleri(kayit), ensure_ascii=False, default=str), (
        "önceki değerlendirme PDF'e girdi"
    )


def test_KRITIK_arayuz_fikstürleri_GERCEK_yanitlarla_AYNI(o):
    """Arayüz yarısı (`screens/__tests__/aiGecmisiOncekiDegerlendirmeler.Y122.web.test.tsx`) bu GERÇEK yanıtları okur: liste (sayı) +
    ayrıntı (metinler). Bayatlarsa KIRMIZI; yenilemek: `Y122_FIKSTUR_YAZ=1` (S-A2.5)."""
    aid = _iki_degerlendirmeli_kayit(o, beyan="tek@klinik.com")
    liste = o.lan.get("/api/ai/log", params={"limit": 50})
    ayrinti = o.lan.get(f"/api/ai/log/{aid}")

    def _sabitle(v):
        # zaman damgaları koşudan koşuya değişir → sabit değer (yapı ve metin karşılaştırılır)
        if isinstance(v, dict):
            return {
                k: ("<zaman>" if k in ("created_at", "reviewed_at") and v[k] else _sabitle(x)) for k, x in v.items()
            }
        if isinstance(v, list):
            return [_sabitle(x) for x in v]
        return v

    beklenen = {
        "liste": {"durum": liste.status_code, "govde": _sabitle(liste.json())},
        "ayrinti": {"durum": ayrinti.status_code, "govde": _sabitle(ayrinti.json())},
    }
    f = FIKSTUR_DIZIN / "aiGecmisiOnceki.Y122.json"
    if os.environ.get("Y122_FIKSTUR_YAZ") == "1":
        f.write_text(json.dumps(beklenen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert f.exists(), "arayüz fikstürü yok (Y122_FIKSTUR_YAZ=1 ile üret)"
    assert json.loads(f.read_text(encoding="utf-8")) == beklenen, "arayüz fikstürü GERÇEK yanıttan BAYATLADI"
