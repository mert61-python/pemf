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

    # ⚠️ DENETİM 2026-08-28 #03: bu fixture eskiden model yolu olarak `None` veriyordu ve
    # "saglam" modülün HAZIR sayılmasını bekliyordu — yani testin kendisi, kapının 12 modülde
    # hiçbir dosyaya bakmadan PASS vermesini (bulgunun ta kendisini) kilitliyordu. Artık
    # "saglam" GERÇEK bir ağırlık yolu alır; ayrık-teşhis sözleşmesi (kod ≠ model) korunur.
    from servers.ai_router import _AI_MODUL_ENVANTERI as _gercek

    # ⚠️ ÇÖZÜLEBİLEN bir ağırlık seçilir, envanterdeki İLK yol değil (CI'da ölçüldü): ağırlıkların
    # klonlanmadığı ortamda ilk yol çözülemez, "saglam" modül HAZIR olamaz ve kapı, ilgisi olmayan
    # bir sebeple kırmızı yanar. Sözleşme (kod ≠ model ayrımı) ortamdan bağımsızdır; testin onu
    # ölçebilmek için yalnızca gerçekten var olan TEK bir ağırlığa ihtiyacı vardır.
    from utils.model_downloader import find_installed_model

    gercek_model = next((m for _a, _i, m in _gercek if m and find_installed_model(m)), None)
    if gercek_model is None:
        pytest.skip("bu ortamda hiçbir model ağırlığı kurulu değil — 'saglam' senaryosu kurulamaz")
    monkeypatch.setattr(
        air,
        "_AI_MODUL_ENVANTERI",
        [
            ("saglam", "json", gercek_model),
            ("kodu_bozuk", "olmayan_paket_xyz", gercek_model),
            ("modeli_yok", "json", "ai_hub/olmayan/model.pt"),
            ("envanteri_eksik", "json", None),
        ],
    )
    r = client.get("/api/ai/hazirlik?derin=1")
    assert r.status_code == 200
    d = r.json()
    durum = {m["modul"]: m for m in d["moduller"]}

    assert durum["saglam"]["hazir"] is True
    # kod bozuk → kod alanı işaretli, model alanı SUÇLANMAZ (asıl yanlış-teşhisin panzehiri)
    assert durum["kodu_bozuk"]["hazir"] is False
    assert durum["kodu_bozuk"]["kod"] in ("kod_hatali", "kod_yok")
    assert durum["kodu_bozuk"]["model"] == "ok", "kod bozukken model haksız yere suçlanıyor"
    # model yok → kod SAĞLAM raporlanır (ayrık teşhis)
    assert durum["modeli_yok"]["hazir"] is False
    assert durum["modeli_yok"]["kod"] == "ok"
    assert durum["modeli_yok"]["model"] == "model_yok"
    # envanterde yol yoksa bu bir HATA'dır — sessiz "gomulu" PASS'ı geri gelmemeli
    assert durum["envanteri_eksik"]["hazir"] is False
    assert durum["envanteri_eksik"]["model"] == "envanter_eksik"

    assert d["hazir"] == 1 and sorted(d["eksik"]) == ["envanteri_eksik", "kodu_bozuk", "modeli_yok"]


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


# ── 4) spec: paket METADATA'sı (ölçülen kök neden) ───────────────────────────
def test_KRITIK_spec_paket_METADATASINI_topluyor():
    """ÖLÇÜLEN KÖK NEDEN (2026-08-27): frozen EXE'de scratch modülü
    `PackageNotFoundError: No package metadata was found for imageio` ile ölüyordu.

    Modül KODUNU toplamak yetmez: çalışma anında `importlib.metadata.version("X")`
    çağıran her kütüphane için X'in .dist-info'su da frozen'a KOPYALANMALI. Bu satır
    silinirse aynı sınıf arıza sessizce geri gelir (kullanıcı 'model paketi gerekli'
    görür, model kuruluyken).

    ⚠️ DENETİM 2026-08-28 #10: bu kapının ilk hali düz metin araması yapıyordu ve döngünün
    KENDİSİNİN sessizce çalışmadığını göremiyordu — `recursive=True`, ağaçtaki tek bir eksik
    dağıtımda (`opencv-python-headless`) tüm çağrıyı düşürüyor, `except` yutuyor, build yeşil
    kalıyordu. Ölçüldü: celldetection + albumentations + grad-cam metadata'sı HİÇ toplanmıyordu,
    yani 27 Ağustos arızasının önlemi kendi paketini kapsamıyordu. Toplama artık
    `_metadata_topla` fonksiyonunda (recursive → düz → kuruluysa build DURUR) ve çıpa AST'ye
    pinlendi. Derin kontroller `tests/test_calisma_ani_pip_yasagi.py`'de.
    """
    import ast
    from pathlib import Path

    yol = Path(__file__).resolve().parents[1] / "build_tools" / "PEMF_Backend_onedir.spec"
    agac = ast.parse(yol.read_text(encoding="utf-8", errors="replace"))
    cagri = next(
        (
            d
            for d in ast.walk(agac)
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "_metadata_topla" and d.args
        ),
        None,
    )
    assert cagri is not None, "metadata toplama çağrısı kayboldu"
    liste = [e.value for e in cagri.args[0].elts if isinstance(e, ast.Constant)]
    # Ölçülen arızanın paketi ADIYLA listede olmalı (liste boşalırsa kapı vacuous olur)
    for zorunlu in ("imageio", "celldetection"):
        assert zorunlu in liste, f"metadata listesinde {zorunlu} yok — ölçülen arıza geri gelebilir"


def test_KRITIK_build_betigi_AI_KAPISINI_kosuyor():
    """Kapı olmadan bozuk EXE yayına çıkar (bu arıza tam böyle çıktı). Build betiği
    üretilen EXE'de derin=1 taraması yapıp eksik modülde build'i KIRMIZI yapmalı."""
    from pathlib import Path

    ps = (Path(__file__).resolve().parents[1] / "scripts" / "build_backend_exe.ps1").read_text(
        encoding="utf-8", errors="replace"
    )
    assert "/api/ai/hazirlik?derin=1" in ps, "build kapısı derin taramayı çağırmıyor"
    assert "AI HAZIRLIK KAPISI KIRMIZI" in ps, "eksik modülde build KIRMIZI olmuyor"
    # Kapı varsayılan AÇIK olmalı (yalnız açık bayrakla atlanabilsin)
    assert "-not $SkipAiGate" in ps
