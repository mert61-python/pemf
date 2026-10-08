# -*- coding: utf-8 -*-
"""D2.18 (B-3.32) — AI geçmişinin hasta süzgecinde AD dalı yalnız KİMLİKSİZ kayıtları ve TAM ad eşleşmesini kapsar.

ÖLÇÜLEN KUSUR: `get_ai_analyses(patient_uuid=A, patient_name='Mia')` → `(patient_uuid = A OR patient_name LIKE '%Mia%')` —
başka bir hayvanın (B, aynı ad) kimlikli kaydı ve "Miami" de geliyordu (alt-dize) → "kaldığın yerden" şeridi / hasta süzgeci
yanlış hastanın analizini gösteriyordu (2-C E11 fikstüründe ÖLÇÜLDÜ: Mia/Köpek'in sorgusu Mia/Kedi'nin VE Miami'nin
analizini döndürüyordu). Sahada (1.9.50) kusur daha güçlü: kimlik sütunu yok, süzme yalnız `LIKE` (plan C3 notu).
Satırlar ürün okuyucusuyla DEĞİL, GERÇEK uçtan (`GET /api/ai/log`) ve DB metodundan; DB'ye ürünün yazma yoluyla yazılır.
Karşıtlar: yalnız ad verilen (eski istemci) sorgu TAM adla tüm kayıtları bulur (alt-dize değil); yalnız kimlik verilen sorgu
yalnız o hastanın kayıtları; A-01/A-02 LAN istemcisi aynı yanıtı alır.
"""

from __future__ import annotations

import pytest

A, B, C = "kimlik-A-mia-kedi", "kimlik-B-mia-kopek", "kimlik-C-miami"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from servers import api_server

    kok = tmp_path / "gecmis"
    kok.mkdir()
    d = TreatmentHistoryDB(kok)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: d)
    monkeypatch.setattr(api_server, "_app_data_dir", lambda: kok)
    for ad, kimlik, ozet in (
        ("Mia", A, "A1"),
        ("Mia", B, "B1"),
        ("Miami", C, "C1"),
        ("Mia", "", "ESKI"),
        (" Mia ", "", "BOSLUKLU"),
    ):
        d.add_ai_analysis(module_id="landmark", patient_name=ad, result_summary=ozet, patient_uuid=kimlik)
    yerel = TestClient(api_server.app, client=("127.0.0.1", 50218))
    lan = TestClient(api_server.app, client=("192.168.1.66", 50219))
    return d, yerel, lan


def _ozetler(kayitlar) -> list:
    return sorted(k["result_summary"] for k in kayitlar)


def test_KRITIK_kimlik_ve_ad_birlikte_YALNIZ_kendi_ve_kimliksiz_TAM_ad(o):
    d, _y, _l = o
    assert _ozetler(d.get_ai_analyses(limit=50, patient_uuid=A, patient_name="Mia")) == ["A1", "BOSLUKLU", "ESKI"]


def test_KRITIK_GERCEK_uc_sorgusu_baska_hayvani_ve_alt_dizeyi_DONDURMEZ(o):
    _d, yerel, _l = o
    r = yerel.get("/api/ai/log", params={"limit": 20, "patient_name": "Mia", "patient_id": B})
    assert r.status_code == 200
    assert _ozetler(r.json()["data"]) == ["B1", "BOSLUKLU", "ESKI"], (
        "B'nin sorgusu başka hayvanı (A) ya da Miami'yi döndürüyor"
    )


def test_KRITIK_yalniz_ad_TAM_eslesme_alt_dize_HARIC_kimlikli_kayitlar_dahil(o):
    d, _y, _l = o
    assert _ozetler(d.get_ai_analyses(limit=50, patient_name="Mia")) == ["A1", "B1", "BOSLUKLU", "ESKI"]


def test_KARSIT_yalniz_kimlik_YALNIZ_o_hasta(o):
    d, _y, _l = o
    assert _ozetler(d.get_ai_analyses(limit=50, patient_uuid=C)) == ["C1"]


def test_KARSIT_A01_LAN_istemcisi_ayni_yaniti_alir(o):
    _d, yerel, lan = o
    p = {"limit": 20, "patient_name": "Miami", "patient_id": C}
    assert lan.get("/api/ai/log", params=p).json() == yerel.get("/api/ai/log", params=p).json()
    assert _ozetler(lan.get("/api/ai/log", params=p).json()["data"]) == ["C1"]
