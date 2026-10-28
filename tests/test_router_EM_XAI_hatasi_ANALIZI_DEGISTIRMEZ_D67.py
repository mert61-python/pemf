# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D67 (D5 "SONRAKİ OTURUM" devri) — GÖMÜLÜ router `/api/ai/vision/em_fantom` · `/api/ai/vision/em_petri`: XAI hatası ANALİZİ değiştirmez.

D5 C123 (`test_xai_kalan_a_grubu.py::test_KRITIK_D557_ai_service_EM_XAI_hatasi_ANALIZI_DEGISTIRMEZ`) bu sözleşmeyi YALNIZ :8100 (GPU servisi)
tarafında davranışla ölçüyordu; gömülü router tarafında (sahadaki profil) yalnız AST kapısı vardı
(`test_YAPISAL_router_fantom_ve_petri_meta_bagli`). Bu dosya aynı sözleşmeyi gömülü uçta DAVRANIŞLA ölçer:

- GERÇEK `PhantomCvPipeline` / `PetriCvPipeline` (`process_image` + `render_panels`) ve GERÇEK router ucu (süreç içi `TestClient`, port YOK);
  sahte yalnız EN ALT katta: algılama / segmentasyon / YOLO / doz öngörücüsü (`test_em_ongorucu_…` aparatı) + kabin (ArUco) pozu + açıklama
  işlevi (`xai_hizli_sensitivity`).
- Aynı girdi iki kez: (A) açıklama başarılı, (B) açıklama `RuntimeError` fırlatır. A ve B'nin analiz alanları (`tumor_regions` / `wells` …)
  BİREBİR aynı VE hattın XAI'siz ürettiği yükle (`result.to_dict()`, açıklamadan ÖNCE kopyalanır) BİREBİR; B'de `xai_error` var,
  `xaiSensitivity` yok; A'da tersi.

MUTASYON: router'ın açıklama yakalayıcısında analiz alanını boşaltmak / değiştirmek (`payload["tumor_regions"] = []`, `wells.clear()`) ya da
açıklama denemesinde bölgeyi YERİNDE değiştirmek (`_r0["centroid_cabin_mm"]` yerine) → KIRMIZI. Ürün DEĞİŞMEZ.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.encoders import jsonable_encoder
from test_em_ongorucu_SONLU_OLMAYAN_girdi_PIKSEL_kipi_ve_TOPLAM_sure import (  # noqa: F401 — aparat (fikstür + yardımcı)
    _aruco,
    _KayitciFantom,
    fantom_hatti,
    fantom_ucu,
    petri_hatti,
    petri_ucu,
)

#: uç → (analiz alanları, hattın yükündeki karşılaştırılan anahtarlar)
_UCLAR = {
    "em_fantom": (
        (
            "success",
            "method",
            "n_tumor",
            "n_healthy",
            "tumor_regions",
            "healthy_regions",
            "mm_per_px",
            "status",
            "error",
        ),
        ("tumor_regions", "healthy_regions"),
    ),
    "em_petri": (
        ("success", "method", "wells", "plausibility", "mm_per_px", "status", "error"),
        ("wells", "plausibility"),
    ),
}


def _json(x):
    """Yanıtla aynı biçime (JSON) indir — demet / numpy türü farkı kapının konusu değil."""
    return json.loads(json.dumps(jsonable_encoder(x)))


@pytest.mark.parametrize("uc", sorted(_UCLAR))
def test_KRITIK_D67_router_EM_XAI_hatasi_ANALIZI_DEGISTIRMEZ(uc, request, monkeypatch):
    from ai_hub.inference_em_fantom import inference_em_fantom as ief
    from ai_hub.inference_em_petri import inference_em_petri as iep

    alanlar, yuk_anahtarlari = _UCLAR[uc]
    if uc == "em_fantom":
        c, _ef, kutu, govde = request.getfixturevalue("fantom_ucu")
        mod = request.getfixturevalue("fantom_hatti")[0]
        sinif, xmod = mod.PhantomCvPipeline, ief
        kutu["ong"] = _KayitciFantom()
    else:
        c, _kutu, govde, _xai = request.getfixturevalue("petri_ucu")
        mod = request.getfixturevalue("petri_hatti")[0]
        sinif, xmod = mod.PetriCvPipeline, iep
    _aruco(mod, monkeypatch)  # kabin çerçevesi: sonuç SÜRÜLEBİLİR → açıklama yoluna girilir (Y144)

    tabanlar: list = []
    orj = sinif.process_image

    def _kaydeden(self, *a, **k):
        sonuc, ctx = orj(self, *a, **k)
        tabanlar.append(_json(copy.deepcopy(sonuc.to_dict())))  # açıklamadan ÖNCE — hattın XAI'siz yükü
        return sonuc, ctx

    monkeypatch.setattr(sinif, "process_image", _kaydeden)
    cagri: list = []

    def _basarili(*a, **k):
        cagri.append("A")
        return [{"feature": "duty_sum", "etki": 1.0}]

    def _patlayan(*a, **k):
        cagri.append("B")
        raise RuntimeError("D67 XAI SIMULE ARIZA")

    yanitlar = {}
    for kip, islev in (("A", _basarili), ("B", _patlayan)):
        monkeypatch.setattr(xmod, "xai_hizli_sensitivity", islev)
        r = c.post(f"/api/ai/vision/{uc}", data={"image_base64": govde})
        assert r.status_code == 200, f"{uc} ({kip}): {r.status_code} {r.text[:200]}"
        yanitlar[kip] = r.json()
    assert cagri == ["A", "B"], f"aparat: açıklama yoluna iki koşuda da girilmedi ({cagri}) — kapı vakumda"
    assert len(tabanlar) == 2, f"aparat: hat iki kez koşmadı ({len(tabanlar)})"
    a, b = yanitlar["A"], yanitlar["B"]
    assert a.get("pemf_kapisi", {}).get("surulebilir") is True, (
        f"aparat: sonuç sürülebilir değil: {a.get('pemf_kapisi')}"
    )
    assert a.get("xaiSensitivity") and "xai_error" not in a, f"aparat: başarılı koşuda açıklama yok: {sorted(a)}"
    assert b.get("xai_error") and "xaiSensitivity" not in b, f"{uc}: XAI hatası yanıtta söylenmiyor: {sorted(b)}"
    assert all(k in a for k in alanlar), (
        f"aparat: {uc} yanıtında analiz alanı eksik: {[k for k in alanlar if k not in a]}"
    )
    farkli = {k: (a.get(k), b.get(k)) for k in alanlar if a.get(k) != b.get(k)}
    assert not farkli, f"{uc}: XAI hatası ANALİZ alanlarını DEĞİŞTİRDİ (açıklama ikincil olmalı): {farkli}"
    # A ile B'yi karşılaştırmak, açıklama DENEMESİNİN kendisi analizi bozuyorsa (iki koşuda da AYNI bozulma) kördür → taban hattın yükü.
    for (kip, j), taban in zip((("A_basarili", a), ("B_hata", b)), tabanlar):
        # router `plausibility`yi `_payload.get("plausibility") or {}` ile yazar (yalnız o anahtarda boş yük → {})
        beklenen = {k: (taban.get(k) or {}) if k == "plausibility" else taban.get(k) for k in yuk_anahtarlari}
        hattan = {k: (j.get(k), beklenen[k]) for k in yuk_anahtarlari if j.get(k) != beklenen[k]}
        assert not hattan, (
            f"{uc}: açıklama denemesi ({kip}) analiz alanlarını HATTIN ürettiğinden (XAI'siz taban) FARKLI döndürdü: {hattan}"
        )
