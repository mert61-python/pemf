# -*- coding: utf-8 -*-
"""I18NI-O.2 (orkestratör, A3.3 gerçek ağırlık ölçümünde bulundu): petri MAKULLİK REDDİ iletisi İngilizce istekte TÜRKÇE.

Kaynak: denetim `ai_hub/inference_petri_dish/plausibility.py`'dedir (mikroservis yolunda da çalışsın diye; hocanın paketi, i18n yüzeyi
DEĞİL) ve kullanıcı metnini Türkçe kurar — `plate_user_message` (24'lük plaka ızgarası oturmadı) / `user_message` (ölçümlü: dairesellik,
tespit güveni, alan payı). `ai_router._petri_reject_message` bu `plausibility["message"]`ı 422 gövdesine AYNEN koyar (gömülü ve GPU
yolu). Ölçüldü: gerçek ağırlık + gerçek uç + `06_PetriKuyu.jpg`, `X-PEMF-Dil: en` → 422 "24 kuyucuklu plaka ızgarası oturmadı. …".
Kullanıcı yanlış / eğik fotoğrafta bunu SIK görür; ileti EYLEM söyler (yakından, tepeden, dik çek; doğru modül) → EN'de okunmalı.

Kapı: (1) `ai_kapi_metni.petri_ret_metni` TR çıktısı ai_hub işlevlerinin ÇIKTISIYLA bayt bayt aynı (ölçümlü / ölçümsüz / ayarlı eşik /
plaka kipi) — hoca metni değiştirirse bu kapı KIRMIZI olur ve EN çeviri birlikte güncellenir; (2) EN çıktı Türkçe değil ve ölçülen
sayıları taşır; (3) GERÇEK uç (gömülü + GPU devri) EN istekte İngilizce, başlıksız istekte bugünkü Türkçe.
"""

from __future__ import annotations

import re

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

import test_ai_panel_yayini as tp  # noqa: E402

from ai_hub.inference_petri_dish import plausibility as pl  # noqa: E402

TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")

OLCUMLU = {"circularity_med": 0.4123, "conf_med": 0.2, "max_area_frac": 0.731, "n": 3}
AYARLI = dict(OLCUMLU, thresholds={"circularity_med": 0.4, "conf_med": 0.15, "max_area_frac": 0.9})
BOZUK = {"circularity_med": "yok", "conf_med": None, "n": 0}
PLAKA = {
    "kip": "plaka",
    "measurable": True,
    "n_inliers": 0,
    "ecc_ok": True,
    "thresholds": {"min_dogrulanmis": 2, "ecc_gerekli": True},
}


def _beklenen_tr(m: dict) -> str:
    return pl.plate_user_message(m) if m.get("kip") == "plaka" else pl.user_message(m)


@pytest.mark.parametrize("m", [OLCUMLU, AYARLI, BOZUK, PLAKA], ids=["olcumlu", "ayarli-esik", "olculemeyen", "plaka"])
def test_TR_ileti_ai_hub_metniyle_BAYT_BAYT_ayni(m):
    from servers import ai_kapi_metni

    veri = dict(m, message=_beklenen_tr(m))
    # KATALOG yolu doğrudan (güvence dalı eşliği GİZLEMESİN — orkestratör mutantı: biçim .3f'e dönünce güvence yüzünden sağ kalıyordu)
    assert ai_kapi_metni.petri_ret_katalog_metni(veri, dil="tr") == veri["message"]
    assert ai_kapi_metni.petri_ret_metni(veri, dil="tr") == veri["message"]


def test_TR_GUVENCE_kaynak_metni_degisirse_kaynagin_metni_AYNEN_doner():
    from servers import ai_kapi_metni

    for m in (PLAKA, OLCUMLU):
        veri = dict(m, message="kaynak metni değişti (hoca güncellemesi)")
        assert ai_kapi_metni.petri_ret_metni(veri, dil="tr") == veri["message"]
        assert ai_kapi_metni.petri_ret_metni(veri, dil="en") != veri["message"]  # EN katalogdan


@pytest.mark.parametrize("m", [OLCUMLU, AYARLI, BOZUK, PLAKA], ids=["olcumlu", "ayarli-esik", "olculemeyen", "plaka"])
def test_EN_ileti_ingilizce_ve_olcumu_tasir(m):
    from servers import ai_kapi_metni

    en = ai_kapi_metni.petri_ret_metni(dict(m, message=_beklenen_tr(m)), dil="en")
    assert en and not TR_HARF.search(en), en
    if m is OLCUMLU:  # ölçülen dairesellik / güven / alan payı ve VARSAYILAN eşikler, kaynakla aynı yuvarlamayla
        assert re.search(r"circularity 0\.41 — expected ≥0\.\d\d;", en) and re.search(r"covers 73% of the frame", en), (
            en
        )
    if m is AYARLI:  # ayarlı (ETKİN) eşik — sabit değil
        assert "expected ≥0.40;" in en and "expected ≤90%" in en, en
    if m is BOZUK:  # ölçülemeyen değer → ölçüm parçası YOK (kaynaktaki gibi)
        assert "measured" not in en, en


def test_ileti_yoksa_katalog_yedegi():
    from servers import ai_kapi_metni
    from utils import ceviri

    for d in ("tr", "en"):
        assert ai_kapi_metni.petri_ret_metni({}, dil=d) == ceviri.t("ai.hata.petriPlakaDegil", dil=d)
        assert ai_kapi_metni.petri_ret_metni(None, dil=d) == ceviri.t("ai.hata.petriPlakaDegil", dil=d)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from servers import api_server

    return TestClient(api_server.app, client=("127.0.0.1", 51243))


DILLER = [({}, "tr"), ({"X-PEMF-Dil": "en"}, "en")]


@pytest.mark.parametrize("baslik,dil", DILLER, ids=["basliksiz", "en"])
def test_gomulu_uc_reddi_istek_dilinde(client, monkeypatch, baslik, dil):
    from servers import ai_router

    class _RetSonuc(tp._SahtePetriSonuc):
        def __init__(self):
            super().__init__()
            self.success = False
            self.error = pl.PETRI_REJECT
            self.plausibility = dict(PLAKA, message=pl.plate_user_message(PLAKA))

    class _SahtePipeline:
        def __init__(self, cfg, **kw):
            pass

        def process_image(self, img, **kw):
            return _RetSonuc(), {}

    monkeypatch.setattr(
        ai_router,
        "_get_or_load_model",
        lambda key, loader: {
            "cls": _SahtePipeline,
            "cfg": object(),
            "yolo_path": "x.onnx",
            "yolo": object(),
            "predictor": object(),
        },
    )
    monkeypatch.setattr(ai_router, "ai_service_enabled", lambda: False)
    r = client.post("/api/ai/vision/em_petri", files={"file": ("t.jpg", tp._jpeg(), "image/jpeg")}, headers=baslik)
    assert r.status_code == 422, r.text[:300]
    detay = r.json()["detail"]
    if dil == "tr":
        assert detay == pl.plate_user_message(PLAKA)  # bugünkü görünüm
    else:
        assert not TR_HARF.search(detay), detay


@pytest.mark.parametrize("baslik,dil", DILLER, ids=["basliksiz", "en"])
def test_GPU_yolu_reddi_istek_dilinde(client, monkeypatch, baslik, dil):
    from servers import ai_router

    async def _sahte_devret(name, label=None, **kw):
        return {"error": pl.PETRI_REJECT, "plausibility": dict(OLCUMLU, message=pl.user_message(OLCUMLU))}

    monkeypatch.setattr(ai_router, "ai_service_enabled", lambda: True)
    monkeypatch.setattr(ai_router, "_kapili_devret", _sahte_devret)
    r = client.post("/api/ai/vision/em_petri", files={"file": ("t.jpg", tp._jpeg(), "image/jpeg")}, headers=baslik)
    assert r.status_code == 422, r.text[:300]
    detay = r.json()["detail"]
    if dil == "tr":
        assert detay == pl.user_message(OLCUMLU)
    else:
        assert not TR_HARF.search(detay) and "0.41" in detay, detay
