# -*- coding: utf-8 -*-
"""I18NI-A3.3 — fantom / petri analiz PANEL GÖRSELLERİNE yazılan metin İSTEK dilinde olmalı.

GERÇEK: `/api/ai/vision/em_fantom` + `/api/ai/vision/em_petri` uçları (TestClient, LAN — dinleyici YOK), `_IstekDiliBaglami`, `panel_yayin`,
kodlama; GPU profilinde `:8100` servisinin GERÇEK uygulaması (`ai_service.app`, TestClient — dinleyici YOK). Sahte: yalnız boru hattı
(model yok) — `render_panels(ctx, result, lang=…)` çağrısının `lang` değeri KAYDEDİLİR.

Sorun: çağrı yerleri (`ai_router` ×2, `ai_pro_hedef`, `ai_service/app.py` ×2) `render_panels(..., lang="tr")` SABİT verir; çizici
(`phantom_cv_v3/render.py`, `petri_cv_v2/render.py`) `LANG = {"tr": …, "en": …}` İKİ DİLİ de taşır. İngilizce arayüzde panel çipi adı
İngilizce (`paneller[].ad`, istek dilinde) ama görselin ÜSTÜNE yazılan başlık / not Türkçe ("01 - Giris", "olcek yok: doz hesaplanmadi",
"konum yok") → karışık dil. Başlıksız (eski APK) / `tr` istek bugünkü gibi `tr` çizmeli (TR birebir). GPU servisi katalog taşımaz (yaprak):
istek dili ona form alanı `dil` ile devredilir; alanı göndermeyen ESKİ backend → `tr` (bugünkü görünüm); bilinmeyen değer → `tr`.
Orkestratör (14): ajan sondası yalnız gömülü uçları ölçüyordu; GPU devri + `:8100` uçları eklendi.
"""

from __future__ import annotations

import capraz
import pytest

np = capraz.paket_yoksa_atla("numpy")
cv2 = capraz.paket_yoksa_atla("cv2")

import test_ai_panel_yayini as tp  # noqa: E402  (aynı dizin: tests/ — yardımcılar tek kaynaktan)
from utils.panel_yayin import PANEL_ADLARI, PETRI_PANEL_ADLARI  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from servers import api_server

    return TestClient(api_server.app, client=("127.0.0.1", 51240))


def _sahte_boru_sinifi(kayit: dict, anahtarlar, sonuc_sinifi):
    class _SahtePipeline:
        def __init__(self, cfg, **kw):
            pass

        def process_image(self, img, **kw):
            return sonuc_sinifi(), {}

        def render_panels(self, ctx, result, lang="tr"):
            kayit["lang"] = lang
            return tp._sahte_panel_seti(anahtarlar)

    return _SahtePipeline


@pytest.fixture()
def boru(monkeypatch):
    from servers import ai_router

    kayit: dict = {}

    def _kur(anahtarlar, sonuc_sinifi):
        sinif = _sahte_boru_sinifi(kayit, anahtarlar, sonuc_sinifi)
        monkeypatch.setattr(
            ai_router,
            "_get_or_load_model",
            lambda key, loader: {
                "cls": sinif,
                "cfg": object(),
                "yolo_path": "x.onnx",
                "yolo": object(),
                "predictor": object(),
            },
        )
        monkeypatch.setattr(ai_router, "ai_service_enabled", lambda: False)
        return kayit

    return _kur


UCLAR = [
    ("em_fantom", PANEL_ADLARI, "_SahteFantomSonuc", True),
    ("em_petri", PETRI_PANEL_ADLARI, "_SahtePetriSonuc", False),
]
DILLER = [({}, "tr"), ({"X-PEMF-Dil": "tr"}, "tr"), ({"X-PEMF-Dil": "en"}, "en")]


@pytest.mark.parametrize("uc,adlar,sonuc,renkli", UCLAR, ids=[u[0] for u in UCLAR])
@pytest.mark.parametrize("baslik,beklenen", DILLER, ids=["basliksiz", "tr", "en"])
def test_panel_gorseli_istek_dilinde_cizilir(client, boru, uc, adlar, sonuc, renkli, baslik, beklenen):
    import i18n_yardimci as iy

    kayit = boru(adlar, getattr(tp, sonuc))
    r = client.post(
        f"/api/ai/vision/{uc}", files={"file": ("t.jpg", tp._jpeg(renkli=renkli), "image/jpeg")}, headers=baslik
    )
    assert r.status_code == 200, r.text[:300]
    # çip adı (paneller[].ad) istek dilinde — bugün DOĞRU (karşılaştırma tabanı)
    kat = iy.katalog("sunucu", beklenen)
    for p in r.json()["paneller"]:
        assert p["ad"] == kat[adlar[p["k"]]], (uc, p["k"], p["ad"])
    # görselin İÇİNE yazılan metin de aynı dilde çizilmeli
    assert kayit.get("lang") == beklenen, (
        f"{uc}: render_panels lang={kayit.get('lang')!r} — istek dili {beklenen!r}; panel çipi {beklenen} ama görsel metni TÜRKÇE"
    )


@pytest.mark.parametrize("uc,adlar,sonuc,renkli", UCLAR, ids=[u[0] for u in UCLAR])
@pytest.mark.parametrize("baslik,beklenen", DILLER, ids=["basliksiz", "tr", "en"])
def test_GPU_profili_istek_dilini_servise_DEVREDER(client, monkeypatch, uc, adlar, sonuc, renkli, baslik, beklenen):
    from servers import ai_router

    giden: dict = {}

    async def _sahte_devret(name, label=None, **kw):
        giden.update(kw.get("data") or {})
        return {"status": "success", "image_base64": "", "paneller": []}

    monkeypatch.setattr(ai_router, "ai_service_enabled", lambda: True)
    monkeypatch.setattr(ai_router, "_kapili_devret", _sahte_devret)
    r = client.post(
        f"/api/ai/vision/{uc}", files={"file": ("t.jpg", tp._jpeg(renkli=renkli), "image/jpeg")}, headers=baslik
    )
    assert r.status_code == 200, r.text[:300]
    assert giden.get("dil") == beklenen, (
        f"{uc}: GPU servisine giden form alanı dil={giden.get('dil')!r} — istek dili {beklenen!r}"
    )


@pytest.fixture(scope="module")
def servis():
    capraz.paket_yoksa_atla("onnxruntime", sebep="ai_service :8100 calisma zamani paketi yok (CI)")
    from ai_service import app as _app

    return _app


@pytest.mark.parametrize("uc,adlar,sonuc,renkli", UCLAR, ids=[u[0] for u in UCLAR])
@pytest.mark.parametrize(
    "form,beklenen",
    [({}, "tr"), ({"dil": "tr"}, "tr"), ({"dil": "en"}, "en"), ({"dil": "xx"}, "tr")],
    ids=["alansiz-eski-backend", "tr", "en", "bilinmeyen"],
)
def test_8100_servisi_paneli_DEVREDILEN_dilde_cizer(servis, monkeypatch, uc, adlar, sonuc, renkli, form, beklenen):
    from fastapi.testclient import TestClient

    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    kayit: dict = {}
    sinif = _sahte_boru_sinifi(kayit, adlar, getattr(tp, sonuc))

    class _SahteTahminci:  # servis yanıtın `device` alanı için yalnız `session.get_providers()` okur (hata → "?")
        session = None

    paket = {"cls": sinif, "cfg": object(), "yolo_path": "x.onnx", "yolo": object(), "predictor": _SahteTahminci()}
    monkeypatch.setattr(servis.predictors, "get", lambda ad: paket)
    r = TestClient(servis.app).post(
        f"/infer/{uc}", files={"file": ("t.jpg", tp._jpeg(renkli=renkli), "image/jpeg")}, data=form
    )
    assert r.status_code == 200, r.text[:300]
    assert kayit.get("lang") == beklenen, (
        f":8100 {uc}: render_panels lang={kayit.get('lang')!r} — devredilen dil {form!r}"
    )
