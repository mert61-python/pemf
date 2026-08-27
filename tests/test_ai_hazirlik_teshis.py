# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI HAZIRLIK / TEŞHİS EDİLEBİLİRLİK — saha bulgusu 2026-08-27.

ÖLÇÜLEN ARIZA: klinik makinede "Yara kapanma modeli bu kurulumda hazır değil — GPU AI
servisi ya da model paketi gerekli." çıkıyordu; oysa model paketi (872 MB PT) KURULUYDU
(`ai_models/ai_hub/inference_paper_dilek_hoca/ginoro_*.pt` diskte) ve launcher paket
kaydını doğru tutuyordu. Gerçek sebep modülün bir bağımlılığının frozen EXE'de import
edilememesiydi; `except ModelKurulumEksik → 503` bloğu hatayı HİÇ LOGLAMADAN yuttuğu için
sahada teşhis imkânsızdı ve kullanıcı YANLIŞ nedeni okuyordu.

SINIF SORUNU (sahip uyarısı): her yeni AI modülünde tekrarlanabilir — model iner, kod
gelir, transitif bağımlılık frozen'a girmez, modül ölü doğar, mesaj "model paketi gerekli"
der. Kilitlenen davranışlar bu sınıfı görünür kılar:
 1) Kök-neden zinciri: sarmalanmış istisna zinciri tek satıra indirgenir (kaybolmaz).
 2) 503 yolu LOGLAR: mesaj sabit kalır ama sunucu kaydında kök neden bulunur.
 3) /api/ai/hazirlik: kod ve model AYRI raporlanır — "kod bozuk" ile "model yok" karışmaz.
 4) Uç sızıntı yapmaz (auth-muaf): dosya yolu/sistem detayı dönmez.
"""

import logging

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    import servers.api_server as apis

    return TestClient(apis.app)


# ── 1) kök-neden zinciri ─────────────────────────────────────────────────────
def test_KRITIK_kok_neden_zinciri_SARMALANMIS_hatayi_KAYBETMEZ():
    from servers.ai_router import _kok_neden_zinciri

    try:
        try:
            raise ModuleNotFoundError("No module named 'celldetection'")
        except ModuleNotFoundError as ic:
            raise RuntimeError("cell/ paketi eksik: ...") from ic
    except RuntimeError as dis:
        z = _kok_neden_zinciri(dis)

    assert "RuntimeError" in z and "cell/ paketi eksik" in z
    # ⚠️ ASIL DEĞER: dıştaki sabit metin değil, KÖK sebep görünür olmalı
    assert "celldetection" in z, f"kök neden kayboldu: {z}"
    assert "⇐" in z


def test_KARSIT_KANIT_zincirsiz_hata_da_okunur_kalir():
    from servers.ai_router import _kok_neden_zinciri

    assert "ValueError: tek" in _kok_neden_zinciri(ValueError("tek"))


# ── 2) 503 yolu artık LOGLUYOR ───────────────────────────────────────────────
def test_KRITIK_scratch_kurulum_eksigi_503_ama_LOGLANIR(client, monkeypatch, caplog):
    """Kullanıcı mesajı sade kalır; kök neden sunucu kaydına DÜŞER (eskiden hiç düşmüyordu)."""
    import ai_hub.inference_paper_dilek_hoca.inference_paper_dilek_hoca as ipd
    import servers.ai_router as air

    def _patla(*a, **k):
        try:
            raise ModuleNotFoundError("No module named 'sahte_bagimlilik'")
        except ModuleNotFoundError as ic:
            raise ipd.ModelKurulumEksik("cell/ paketi eksik: ...") from ic

    monkeypatch.setattr(ipd, "scratch_analiz", _patla)
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    # araştırma kapısı: uç `require_research` bağımlılığı taşıyor — testte serbest bırak
    import servers.api_server as apis

    apis.app.dependency_overrides[air.require_research] = lambda: True
    try:
        with caplog.at_level(logging.ERROR, logger="ai_router"):
            r = client.post(
                "/api/ai/vision/scratch",
                files={"file": ("x.png", _kucuk_png(), "image/png")},
                data={"scratch_yonu": "dikey", "pixel_mm": "0.0016"},
            )
    finally:
        apis.app.dependency_overrides.pop(air.require_research, None)

    assert r.status_code == 503
    # Kullanıcıya giden metin DEĞİŞMEZ (sade, teknik detay sızdırmaz)
    assert "hazır değil" in r.json()["detail"]
    assert "sahte_bagimlilik" not in r.text, "iç hata istemciye SIZDI"
    # ...ama sunucu kaydında kök neden VAR (saha teşhisinin tek dayanağı)
    kayit = "\n".join(caplog.messages)
    assert "sahte_bagimlilik" in kayit, f"kök neden loglanmadı: {kayit[:300]}"


def _kucuk_png() -> bytes:
    import base64

    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


# ── 3) hazırlık ucu: kod ve model AYRI ───────────────────────────────────────
def test_KRITIK_hazirlik_ucu_KOD_ve_MODEL_ayri_raporlar(client, monkeypatch):
    """Asıl yanlış-teşhisin panzehiri: modül kodu bozuksa 'model yok' DENMEZ."""
    import servers.ai_router as air

    monkeypatch.setattr(
        air,
        "_AI_MODUL_ENVANTERI",
        [
            ("saglam", "json", None),
            ("kodu_bozuk", "olmayan_paket_xyz", None),
            ("modeli_yok", "json", "ai_hub/olmayan/model.pt"),
        ],
    )
    r = client.get("/api/ai/hazirlik?derin=1")
    assert r.status_code == 200
    d = r.json()
    durum = {m["modul"]: m for m in d["moduller"]}

    assert durum["saglam"]["hazir"] is True
    # kod bozuk → kod alanı işaretli, model alanı SUÇLANMAZ
    assert durum["kodu_bozuk"]["hazir"] is False
    assert durum["kodu_bozuk"]["kod"] in ("kod_hatali", "kod_yok")
    assert durum["kodu_bozuk"]["model"] == "gomulu"
    # model yok → kod SAĞLAM raporlanır (ayrık teşhis)
    assert durum["modeli_yok"]["hazir"] is False
    assert durum["modeli_yok"]["kod"] == "ok"
    assert durum["modeli_yok"]["model"] == "model_yok"

    assert d["hazir"] == 1 and sorted(d["eksik"]) == ["kodu_bozuk", "modeli_yok"]


def test_KRITIK_hazirlik_ucu_gercek_envanterde_SCRATCH_var():
    """Envanter, sahada kırılan modülü GERÇEKTEN kapsamalı (yoksa kapı boş çalışır)."""
    from servers.ai_router import _AI_MODUL_ENVANTERI

    adlar = {ad for ad, _i, _m in _AI_MODUL_ENVANTERI}
    assert "scratch" in adlar, "saha arızasının modülü envanterde YOK"
    assert {"histopath", "kidney_ct", "cat_organ", "em_kedi"} <= adlar
    # scratch satırı model yolunu TAŞIMALI (yalnız kodu değil, PT'yi de sınasın)
    scratch = next(s for s in _AI_MODUL_ENVANTERI if s[0] == "scratch")
    assert scratch[2] and scratch[2].endswith(".pt")


def test_KARSIT_KANIT_hazirlik_ucu_yol_SIZDIRMAZ(client):
    """auth-muaf uç: mutlak yol / sürücü harfi / kullanıcı adı DÖNMEMELİ."""
    g = client.get("/api/ai/hazirlik").text
    assert "C:\\" not in g and "/Users/" not in g and "AppData" not in g
