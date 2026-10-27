# -*- coding: utf-8 -*-
"""D2.71 (B-6.18 · B-6.20) arayüz kapısının girdisi — `/api/ai/log` yanıtı GERÇEK backend'den üretilir.

Arayüz yarısı `apps/ui/src/screens/__tests__/aiGecmisiHastaCipleri.D271.web.test.tsx` bu fikstürü okur (jest Python koşturamaz).
Burada `ai_log_yanitini_uret()` GERÇEK uçlarla (`POST /api/ai/log` ×5 → `GET /api/ai/log`) aynı veriyi kurar; fikstür bayatlarsa
(`/api/ai/log` biçimi ya da kayıt alanları değişirse) bu kapı KIRMIZI olur. Yenilemek: `D271_FIKSTUR_YAZ=1` ile bu dosyayı koş.

Veri (kayıtlı operatörsüz cihaz — Kural 2: beyan edilen e-posta kayıt sahibidir):
  · ev sahibi `sahip@ev.com`: aynı adlı İKİ hayvan "Mia" (kimlik M1 ×2 kayıt, M2 ×1 kayıt) + kimliksiz ESKİ "Mia" kaydı
  · başka hekim `dr.b@klinik.com`: "Pamuk" (kimlik P) — ev sahibinin kapsamında DEĞİL
Değişken alanlar (`created_at`) sabitlenir; `id` taze DB'de belirlenimcidir.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import capraz
import pytest

_KOK = Path(__file__).resolve().parents[1]
_FIKSTUR = _KOK / "apps" / "ui" / "src" / "screens" / "__tests__" / "__fixtures__" / "aiLog.D271.json"
SAHIP = "sahip@ev.com"
DR_B = "dr.b@klinik.com"
M1 = "6f1c2a90-0b3e-4d55-9a71-3c0d5e8b4a11"
M2 = "b27e9d04-5c1a-4f88-8e20-7a6b1f3c9d22"
P = "d93a7b15-2e6c-4a09-b4f3-0c8e2d5a7f33"
KAYITLAR = [
    {
        "operator_email": SAHIP,
        "patient_name": "Mia",
        "patient_id": M1,
        "summary": "FGS 2/10 (Hafif)",
        "module_id": "landmark",
    },
    {
        "operator_email": SAHIP,
        "patient_name": "Mia",
        "patient_id": M1,
        "summary": "FGS 4/10 (Orta)",
        "module_id": "landmark",
    },
    {
        "operator_email": SAHIP,
        "patient_name": "Mia",
        "patient_id": M2,
        "summary": "FGS 1/10 (Hafif)",
        "module_id": "landmark",
    },
    {
        "operator_email": SAHIP,
        "patient_name": "Mia",
        "patient_id": "",
        "summary": "FGS 3/10 (eski)",
        "module_id": "landmark",
    },
    {"operator_email": DR_B, "patient_name": "Pamuk", "patient_id": P, "summary": "FGS 0/10", "module_id": "landmark"},
]


def ai_log_yanitini_uret(tmp_path, monkeypatch) -> dict:
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from servers import api_server, operator_tokens

    kok = tmp_path / "gecmis"
    kok.mkdir()
    d = TreatmentHistoryDB(kok)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: d)
    monkeypatch.setattr(api_server, "_app_data_dir", lambda: kok)
    monkeypatch.setattr(
        api_server, "_ai_kimlik_tasindi", True
    )  # tek seferlik ad→kimlik taşıması bu verinin konusu değil
    operator_tokens.temizle_hepsi()
    c = TestClient(api_server.app, client=("127.0.0.1", 50271))
    for k in KAYITLAR:
        r = c.post(
            "/api/ai/log", json={"module": "Ağrı Analizi (FGS)", "mode": "pet_owner", "input_type": "image", **k}
        )
        assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    yanit = c.get("/api/ai/log?limit=50").json()
    for i, it in enumerate(sorted(yanit["data"], key=lambda x: x["id"])):
        it["created_at"] = f"2026-10-0{1 + i} 10:00:00"
    return yanit


def test_KRITIK_arayuz_fiksturu_GERCEK_ai_log_yanitiyla_AYNI(tmp_path, monkeypatch):
    beklenen = ai_log_yanitini_uret(tmp_path, monkeypatch)
    # Ara doğrulama: gerçek yanıt kimliği taşıyor (arayüzün kimlikle ayırması buna dayanır).
    assert sorted({it.get("patient_uuid", "∅") for it in beklenen["data"]}) == sorted({"", M1, M2, P})
    if os.environ.get("D271_FIKSTUR_YAZ") == "1":
        _FIKSTUR.parent.mkdir(parents=True, exist_ok=True)
        _FIKSTUR.write_text(json.dumps(beklenen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert _FIKSTUR.is_file(), f"arayuz fiksturu yok: {_FIKSTUR} (D271_FIKSTUR_YAZ=1 ile uret)"
    kayitli = json.loads(_FIKSTUR.read_text(encoding="utf-8"))
    assert kayitli == beklenen, (
        "arayuz fiksturu backend'in GERCEK /api/ai/log yanitindan BAYATLADI (D271_FIKSTUR_YAZ=1 ile yenile)"
    )


def test_KARSIT_fikstur_kusuru_TASIR_ayni_adli_iki_kimlik_ve_baska_hekimin_hastasi():
    """Fikstürün kendisi kusuru taşımalı (yoksa arayüz kapısı kör): aynı adlı iki kimlik + kimliksiz eski kayıt + başka hekim."""
    # D5-F: eski düz skipif — İZLENEN ağaç, ZORUNLU kipte DÜŞER
    capraz.atla_yoksa("apps/ui/src/screens/__tests__/__fixtures__/aiLog.D271.json", izlenen=True)
    veri = json.loads(_FIKSTUR.read_text(encoding="utf-8"))["data"]
    mia = {it["patient_uuid"] for it in veri if it["patient_name"] == "Mia"}
    assert mia == {M1, M2, ""}
    assert [it["operator_email"] for it in veri if it["patient_name"] == "Pamuk"] == [DR_B]
