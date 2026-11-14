# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AP · B5 + B2 (istem 48, tezgâh 13 Kasım 2026 16:3x) — ORTAK KÖK.

B5: petri kuyusu seçilirken "Organ değiştirilemedi — Hedef 11 'Kedi Organ' için desteklenmiyor (geçerli: 0–6)". `/ai/pro/stop` etkin modeli
KEDİ'ye döndürür (eski APK / mobil kare yolu için); seans bitince panel petride kalır ve kuyu seçimi `/organ` etkin (kedi) sağlayıcıyla
doğrulanıp 422 alır.
B2: aynı ret panelde seçimi GERİ alır (otomatik = 0) → hazırlık otomatik hedefle başlar → öneri "Otomatik seçim … «Kuyu C2»" (C6 seçilmişti).
DÜZELTME: BOŞTA (döngü / hazırlık / mühürlü seans YOK) `/organ` İSTENEN modelin hedef kümesiyle doğrular ve seçimi kabul eder; etkin model
ve küresel hedef DEĞİŞMEZ (hazırlık kendi gövdesindeki model + hedefle kurar — seçim oraya taşınır). Seans / hazırlık sürerken eski kural
(başka model 422). Durum ucu son lokalizasyonun modelini (`targetsModel`) verir — panel başka modelin bayat adaylarını göstermez.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def ortam(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    adlar = (
        "_ai_hedef_modeli",
        "_ai_organ_id",
        "_ai_loop_active",
        "_ai_hazirlik_active",
        "_ai_owner_client",
        "_ai_relocalize",
    )
    snap = {a: getattr(air, a) for a in adlar}
    snap_cache = dict(air._ai_organ_cache)
    with apis._session_lock:
        sess = dict(apis._active_session)
        apis._active_session.clear()
        apis._active_session.update({"is_active": False, "mode": "Sistem Hazır"})
    air._ai_hedef_modeli = "kedi"  # /ai/pro/stop sonrası
    air._ai_organ_id = 0
    air._ai_loop_active = False
    air._ai_hazirlik_active = False
    air._ai_owner_client = ""
    yield air, TestClient(apis.app)
    for a, v in snap.items():
        setattr(air, a, v)
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap_cache)
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update(sess)


def test_KRITIK_B5_bosta_kuyu_secimi_ISTENEN_modelle_dogrulanir(ortam):
    air, c = ortam
    r = c.post("/api/ai/pro/organ", json={"organ_id": 11, "model": "petri", "client_id": "panel"})
    assert r.status_code == 200, r.text  # önce: 422 "Hedef 11 'Kedi Organ' için desteklenmiyor (geçerli: 0, 1, …, 6)"
    j = r.json()
    assert j["organId"] == 11 and j["model"] == "petri"
    # Etkin model ve küresel hedef DEĞİŞMEZ (başka istemcinin kedi kareleri etkilenmez); seçim hazırlık gövdesiyle kurulur.
    assert air._ai_hedef_modeli == "kedi"
    assert air._ai_organ_id == 0


def test_KRITIK_B2_bosta_secilen_kuyu_HAZIRLIGA_tasinir_otomatige_DUSMEZ(ortam, monkeypatch):
    air, c = ortam
    assert c.post("/api/ai/pro/organ", json={"organ_id": 11, "model": "petri", "client_id": "panel"}).status_code == 200
    monkeypatch.setattr(air.kabin_kamerasi, "secili_kamera", lambda: {"indeks": 0, "kaynak": "ayar"})
    monkeypatch.setattr(air, "_ai_hazirlik_loop", lambda: None)  # kamera / model açılmaz
    r = c.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 11, "model": "petri", "client_id": "panel"})
    assert r.status_code == 200, r.text
    assert air._ai_hedef_modeli == "petri"
    assert air._ai_organ_id == 11, "elle seçilen kuyu hazırlıkta otomatik (0) hedefe düştü (B2)"
    air._ai_hazirlik_active = False


def test_hazirlik_SURERKEN_baska_modele_secim_REDDEDILIR(ortam):
    air, c = ortam
    air._ai_hazirlik_active = True  # kedi önizlemesi sürüyor
    try:
        r = c.post("/api/ai/pro/organ", json={"organ_id": 11, "model": "petri", "client_id": "panel"})
        assert r.status_code == 422
        assert air._ai_organ_id == 0
    finally:
        air._ai_hazirlik_active = False


def test_seans_SURERKEN_baska_modele_secim_REDDEDILIR(ortam):
    air, c = ortam
    air._ai_loop_active = True
    try:
        assert c.post("/api/ai/pro/organ", json={"organ_id": 11, "model": "petri"}).status_code == 422
    finally:
        air._ai_loop_active = False


def test_modelsiz_ESKI_istemci_davranisi_AYNI(ortam):
    _air, c = ortam
    r = c.post("/api/ai/pro/organ", json={"organ_id": 11})
    assert r.status_code == 422  # etkin (kedi) hedef kümesi 0–6


def test_bosta_gecersiz_hedef_ISTENEN_modelin_adiyla_reddedilir(ortam):
    _air, c = ortam
    r = c.post("/api/ai/pro/organ", json={"organ_id": -3, "model": "petri"})
    assert r.status_code == 422
    assert "Kedi" not in r.json()["detail"]


def test_durum_ucu_HEDEF_ADAYLARININ_modelini_verir(ortam):
    air, c = ortam
    air._ai_organ_cache["model"] = "petri"
    j = c.get("/api/ai/pro/status").json()
    assert j["targetsModel"] == "petri"
    assert j["model"] == "kedi"  # etkin sağlayıcı (durdurma sonrası) — ikisi ayrı bilgi
