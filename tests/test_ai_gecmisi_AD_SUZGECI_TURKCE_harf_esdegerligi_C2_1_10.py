# -*- coding: utf-8 -*-
"""C2-1.10 (2-C inceleme, A1) — D2.18 ad süzgecinin "TAM ad" eşitliği, aynı ürünün iki öteki kuralıyla ÇELİŞİYOR.

`get_ai_analyses` ad dalı `TRIM(patient_name) = ?` (ikili, harf duyarlı). Aynı kimliksiz eski kaydı:
  · D2.22 taşıması `arama_katla` (Türkçe-doğru küçültme + NFC + boşluk) ile hastaya BAĞLAR,
  · arayüz anahtarı `adAnahtari` (`aramaNormalize`: toLocaleLowerCase('tr') + NFC) ile AYNI hasta sayar (AI Geçmişi çipi,
    kimliksiz hastanın kartı),
  · ama sunucu ad süzgeci (ev sahibi şeridi kimliksiz hastada, eski APK'nın yalnız-ad sorgusu, kimlik+ad'ın eski-kayıt kolu)
    "mia"/"ışık"/"ipek" yazımlı kaydı DÜŞÜRÜR. D2.18 ÖNCESİ `LIKE %ad%` ASCII harf farkını (mia/MIA) yakalıyordu.
Ölçüldü (`kayit/k5_sonda_turkce.txt`). Kapı GERÇEK `TreatmentHistoryDB` + GERÇEK `/api/ai/log`. Eşdeğerlik ölçütü ürünün
KENDİ taşıma kuralı (`utils.turkce_metin.arama_katla`); "Miami" (alt-dize) ve "MIA" (Türkçe'de "mıa") HARİÇ kalmalı (D2.18).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

ESKI = ["Mia", "mia", "MIA", " Mia ", "Işık", "ışık", "IŞIK", "İpek", "ipek", "Miami"]


def _kur(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api

    db = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    for ad in ESKI:
        db.add_ai_analysis(module_id="m", patient_name=ad, result_summary=f"ESKI[{ad}]")
    return api, db


def _ozet(kayitlar):
    return sorted(k["result_summary"] for k in kayitlar)


def test_KRITIK_C2_1_10_ad_suzgeci_TASIMA_ve_ARAYUZ_ile_ayni_esdegerlikte(tmp_path, monkeypatch):
    from utils.turkce_metin import arama_katla

    _api, db = _kur(tmp_path, monkeypatch)
    try:
        for q in ("Mia", "Işık", "İpek"):
            beklenen = sorted(f"ESKI[{a}]" for a in ESKI if arama_katla(a) == arama_katla(q))
            assert _ozet(db.get_ai_analyses(limit=100, patient_name=q)) == beklenen, q
            assert _ozet(db.get_ai_analyses(limit=100, patient_name=q, patient_uuid="u-x")) == beklenen, q
    finally:
        db.close_connections()


def test_KRITIK_C2_1_10_GERCEK_uc_yalniz_ad_sorgusu_harf_farkli_eski_kaydi_dusurmez(tmp_path, monkeypatch):
    api, db = _kur(tmp_path, monkeypatch)
    try:
        y = TestClient(api.app, client=("192.168.1.50", 51011)).get("/api/ai/log?limit=100&patient_name=Mia").json()
        assert _ozet(y["data"]) == ["ESKI[ Mia ]", "ESKI[Mia]", "ESKI[mia]"]
    finally:
        db.close_connections()


def test_KARSIT_C2_1_10_alt_dize_ve_TURKCE_ayri_harf_HARIC(tmp_path, monkeypatch):
    _api, db = _kur(tmp_path, monkeypatch)
    try:
        got = _ozet(db.get_ai_analyses(limit=100, patient_name="Mia"))
        assert "ESKI[Miami]" not in got and "ESKI[MIA]" not in got
    finally:
        db.close_connections()
