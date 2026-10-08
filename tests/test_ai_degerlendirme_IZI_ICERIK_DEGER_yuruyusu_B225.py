# -*- coding: utf-8 -*-
"""B2-2.5 (2-B bağımsız inceleme · A2) — D2.19 "gerekçe METNİ ize girmez" kapısı DEĞER üzerinde ve PARÇA düzeyinde ölçülür.

ÖLÇÜLEN KÖR NOKTA: `tests/test_ai_degerlendirme_IZI_D219.py::test_KRITIK_gerekce_METNI_ize_GIRMEZ_yalniz_varligi` sızıntıyı TAM
dizenin satırın `json.dumps` METNİNDE geçip geçmediğiyle ölçüyor (tek ASCII gerekçe). Gerekçenin bir PARÇASINI ize koyan mutant
(`detail["ozet"] = note[:24]`) o kapıda YEŞİL kalıyor (ölçüldü: `kayit/k2_mutasyon.txt` k2a 11/11). Ayrıca tırnak / yeni satır
taşıyan gerçek bir gerekçe JSON kaçışıyla iki kez kaçırılır (`"` → `\\\"`, `\\n` → `\\\\n`) → tam-dize araması metinde onu da bulamaz.
Bu kapı: gerekçe Türkçe + tırnak + yeni satır; her iz satırının her alanı ve `detail` JSON'unun her DEĞERİ (özyinelemeli,
çözülmüş) gerekçenin kendisi ve her 8 karakterlik PARÇASI için aranır. Üç kimlik dalı (jeton, 428 kanıtsız beyan, 428 boş) + Kural 2.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
TEK = "tek@klinik.com"
GEREKCE = 'Lezyon "çapı" ölçümle uyuşmuyor\nikinci satır: şüpheli ödem — gizli-B225'


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens

    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    yerel = TestClient(api.app, client=("127.0.0.1", 52034))
    lan = TestClient(api.app, client=("192.168.1.85", 52035))

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


def _degerler(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield str(k)
            yield from _degerler(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _degerler(v)
    elif x is not None:
        yield str(x)


def _sizan_degerler(o):
    parcalar = {GEREKCE[i : i + 8] for i in range(len(GEREKCE) - 7)}
    bulunan = []
    for s in o.db.denetim_oku(500):
        alanlar = dict(s)
        alanlar["detail"] = json.loads(s.get("detail") or "{}")
        for d in _degerler(alanlar):
            if any(p in d for p in parcalar):
                bulunan.append((s.get("event_type"), d[:60]))
    return bulunan


def _deg(o, aid, durum, beyan, jeton=""):
    return o.lan.post(
        "/api/ai/log/review",
        json={"analysis_id": aid, "status": durum, "note": GEREKCE, "reviewed_by": beyan},
        headers={"X-PEMF-Operator": jeton} if jeton else {},
    )


def test_KRITIK_gerekce_PARCASI_hicbir_iz_DEGERINDE_yok_uc_kimlik_dali(o):
    """MUTASYON: `detail`e gerekçenin ilk 24 karakteri → KIRMIZI (D2.19 kapısı bunda yeşil)."""
    assert (
        o.yerel.post("/api/operators/enroll", json={"email": AYSE, "display_name": AYSE, "pin": "123456"}).status_code
        == 200
    )
    j = o.yerel.post("/api/operators/verify", json={"email": AYSE, "pin": "123456"}).json()["operator_token"]
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    kodlar = [
        _deg(o, aid, "rejected", AYSE, j).status_code,
        _deg(o, aid, "rejected", AYSE).status_code,
        _deg(o, aid, "corrected", "").status_code,
    ]
    assert kodlar == [200, 428, 428], kodlar
    iz = [s for s in o.db.denetim_oku(500, "ai.review") if s.get("scope") == f"ai_analiz:{aid}"]
    assert len(iz) == 3 and all(json.loads(s["detail"])["gerekce_var"] is True for s in iz), iz  # ön koşul: iz VAR
    assert _sizan_degerler(o) == [], "gerekçe metni (parçası) bir iz satırının DEĞERİNDE"


def test_KRITIK_KURAL2_gerekce_PARCASI_izde_yok(o):
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    assert _deg(o, aid, "rejected", TEK).status_code == 200
    assert [s for s in o.db.denetim_oku(500, "ai.review") if s.get("scope") == f"ai_analiz:{aid}"], "ön koşul: iz VAR"
    assert _sizan_degerler(o) == [], "gerekçe metni (parçası) bir iz satırının DEĞERİNDE"
