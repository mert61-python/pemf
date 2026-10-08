# -*- coding: utf-8 -*-
"""D2.E11 (İG-6.59 · A-62) arayüz kapısının girdisi — `/api/patients` ve ekranların yaptığı `/api/ai/log` sorgularının yanıtları
GERÇEK backend'den üretilir.

Arayüz yarısı `apps/ui/src/screens/__tests__/sonAnalizAdYedegi.E11.A62.web.test.tsx` bu fikstürü okur (jest Python koşturamaz).
`yanitlari_uret()` GERÇEK uçlarla (hasta ekleme ×3 + `POST /api/ai/log` ×2) ADAY-DOĞRULAMA-D2 İG-6.59 verisini kurar ve ekranların
GERÇEK sorgularını (Hastalar `?limit=200`, Akıllı Teşhis şeridi `?limit=20&patient_name=…&patient_id=…`) koşar. Hasta kimlikleri
backend'in ürettiği rastgele UUID'lerdir → yer tutuculara (`kimlik-A/B/C`) normalleştirilir; `created_at` sabitlenir. Fikstür
bayatlarsa (uçların biçimi ya da ad süzgecinin davranışı değişirse — ör. D2.18) bu kapı KIRMIZI olur:
`E11_FIKSTUR_YAZ=1` ile yenile.

Veri (kayıtlı operatörsüz cihaz — Kural 2; sahip `sahip@ev.com`): A = Mia/Kedi (analizi "A-ANALIZI"), B = Mia/Köpek (analizi YOK),
C = Miami/Kedi (analizi "C-ANALIZI").
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote

_KOK = Path(__file__).resolve().parents[1]
_FIKSTUR = _KOK / "apps" / "ui" / "src" / "screens" / "__tests__" / "__fixtures__" / "sonAnaliz.E11.json"
SAHIP = "sahip@ev.com"
HASTALAR = [("A", "Mia", "Kedi"), ("B", "Mia", "Köpek"), ("C", "Miami", "Kedi")]
ANALIZ = {"A": "A-ANALIZI", "C": "C-ANALIZI"}


def _normalle(nesne, eslem: dict):
    metin = json.dumps(nesne, ensure_ascii=False)
    for gercek, yer in eslem.items():
        metin = metin.replace(gercek, yer)
    return json.loads(metin)


def yanitlari_uret(tmp_path, monkeypatch) -> dict:
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from servers import api_server, operator_tokens, patient_router

    kok = tmp_path / "gecmis"
    kok.mkdir()
    d = TreatmentHistoryDB(kok)
    hdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: d)
    monkeypatch.setattr(api_server, "_app_data_dir", lambda: kok)
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: hdb)
    monkeypatch.setattr("database.patient_database.get_patient_database", lambda: hdb)
    monkeypatch.setattr(
        api_server, "_ai_kimlik_tasindi", True
    )  # tek seferlik ad→kimlik taşıması bu verinin konusu değil
    operator_tokens.temizle_hepsi()
    c = TestClient(api_server.app, client=("127.0.0.1", 50611))
    kimlik = {}
    for harf, ad, tur in HASTALAR:
        r = c.post("/api/patients", json={"name": ad, "species": tur, "operator_email": SAHIP})
        assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
        kimlik[harf] = next(
            p["id"] for p in c.get("/api/patients").json()["data"] if p["species"] == tur and p["name"] == ad
        )
    for harf, ozet in ANALIZ.items():
        ad = next(a for h, a, _t in HASTALAR if h == harf)
        r = c.post(
            "/api/ai/log",
            json={
                "module": "Ağrı Analizi (FGS)",
                "module_id": "landmark",
                "summary": ozet,
                "patient_name": ad,
                "patient_id": kimlik[harf],
                "operator_email": SAHIP,
            },
        )
        assert r.json().get("status") == "success", r.text[:200]
    sorgular = ["/ai/log?limit=200"] + [
        f"/ai/log?limit=20&patient_name={quote(ad)}&patient_id={quote(kimlik[harf])}" for harf, ad, _t in HASTALAR
    ]
    yanitlar = {"/patients": c.get("/api/patients").json()}
    for s in sorgular:
        yanitlar[s] = c.get("/api" + s).json()
    eslem = {kimlik[h]: f"kimlik-{h}" for h in kimlik}
    sonuc = _normalle(yanitlar, eslem)
    for yanit in sonuc.values():
        for it in yanit.get("data", []):
            for alan in ("created_at", "updated_at", "last_visit"):
                if it.get(alan):
                    it[alan] = "2026-10-01 10:00:00"
    return sonuc


def test_KRITIK_arayuz_fiksturu_GERCEK_backend_yanitlariyla_AYNI(tmp_path, monkeypatch):
    beklenen = yanitlari_uret(tmp_path, monkeypatch)
    if os.environ.get("E11_FIKSTUR_YAZ") == "1":
        _FIKSTUR.parent.mkdir(parents=True, exist_ok=True)
        _FIKSTUR.write_text(json.dumps(beklenen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert _FIKSTUR.is_file(), f"arayuz fiksturu yok: {_FIKSTUR} (E11_FIKSTUR_YAZ=1 ile uret)"
    assert json.loads(_FIKSTUR.read_text(encoding="utf-8")) == beklenen, (
        "arayuz fiksturu backend'in GERCEK yanitlarindan BAYATLADI (E11_FIKSTUR_YAZ=1 ile yenile)"
    )


def test_KARSIT_fikstur_kusuru_TASIR_B_icin_sorgu_A_nin_analizini_doner():
    """Fikstür kusuru taşımalı (yoksa arayüz kapısı kör): B'nin şerit sorgusu (ad 'Mia' VEYA kimlik B) A'nın analizini döndürür —
    arayüzün ad yedeği onu B'ye bağlıyordu. Hastalar ekranının sorgusu (`?limit=200`, süzgeçsiz) A'nın kaydını HER ZAMAN taşır."""
    veri = json.loads(_FIKSTUR.read_text(encoding="utf-8"))
    tum = veri["/ai/log?limit=200"]["data"]
    assert ("kimlik-A", "Mia", "A-ANALIZI") in [
        (k["patient_uuid"], k["patient_name"], k["result_summary"]) for k in tum
    ]
    b = veri["/ai/log?limit=20&patient_name=Mia&patient_id=kimlik-B"]["data"]
    assert ("kimlik-A", "A-ANALIZI") in [(k["patient_uuid"], k["result_summary"]) for k in b]
