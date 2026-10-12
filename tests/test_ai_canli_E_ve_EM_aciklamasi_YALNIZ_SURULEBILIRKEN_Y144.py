# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y144 (S-AII.7, sahip 2026-10-13) — canlı E barı ve EM "dozu en çok belirleyen" açıklaması YALNIZ sonuç SÜRÜLEBİLİRKEN kurulur.

ÖLÇÜLEN DURUM (AI incelemesi A2 K2 gözlemi): AI-2 C7 (S-AI2.5) bağlamı / açıklamayı yalnız `pemf_valid`e bağlamıştı. Kabin
konumu geçerli (`pemf_valid` true) ama fantom tespiti GÜVENİLMEZ (`reliable=false`), yerleşim referansla UYUŞMUYOR
(`layout_mismatch`) ya da sonucu kullanılamaz / yeniden çekim isteyen uyarı varken (`control_*`, `oblique_view`, `ring_partial`,
`plate_cropped`, `few_candidates` …) canlı E bağlamı bu konumdan KURULUYOR ve "dozu belirleyen" açıklaması ÜRETİLİYORDU —
bobin sürüşüne esas alınamayan sonuç seans boyunca "canlı" görünüyordu.

SÖZLEŞME (Y144): bağlam ve açıklama `pemf_kapisi.surulebilir` (TEK KAYNAK `ai_hub/cv_ortak/pemf_kapisi.py`: kabin konumu geçerli +
fantom güvenilir + engelleyen / yeniden çekim uyarısı yok) iken kurulur; değilse kurulmaz ve ÖNCEKİ bağlam KALMAZ. D / P / E yine
gösterilir (eylem metniyle — C4). GPU servisi (`ai_service`) açıklamada aynı kuralı uygular. Arayüz neden gösterilmediğini söyler
(jest: `PemfKapisiKutusu.Y144`).

KAPI: GERÇEK `PhantomCvPipeline` / `PetriCvPipeline` + render (sahte: ArUco pozu, YOLO, doz modeli — `test_em_ongorucu_…` aparatı),
kabin (ArUco) çerçevesinde; ölçülen 1–2 alan GERÇEK sonuç nesnesine enjekte edilir (`process_image` sarılır).
"""

from __future__ import annotations

import pytest
from test_em_ongorucu_SONLU_OLMAYAN_girdi_PIKSEL_kipi_ve_TOPLAM_sure import (  # noqa: F401 — aparat (fikstür + yardımcı)
    _aruco,
    _govde,
    _KayitciFantom,
    _servis_cagir,
    fantom_hatti,
    fantom_ucu,
    petri_hatti,
    petri_ucu,
    servis_cv,
)

#: (ad, enjeksiyon) — `reliable` doğrudan; `uyari` gerçek uyarı listesine EKLENİR (hocanın `kod: açıklama` biçimi).
FANTOM_ENGELLER = [
    ("guvenilir_degil", {"reliable": False}),
    ("layout_mismatch", {"uyari": "layout_mismatch: yerleşim referansla uyuşmuyor (rms 14,2 mm)"}),
    ("ring_partial", {"uyari": "ring_unavailable: ring_partial: halkanın %31'i kadrajda"}),
    ("oblique_view", {"uyari": "oblique_view: kamera fantoma dik değil"}),
]
PETRI_ENGELLER = [
    ("control_healthy_flagged", {"uyari": "control_healthy_flagged: A1 kanser işaretlendi"}),
    ("plate_cropped", {"uyari": "plate_cropped: plakanın bir kısmı kadraj dışında"}),
    ("few_candidates", {"uyari": "few_candidates: doğrulanmış aday 1"}),
]


def _enjekte(sinif, monkeypatch, alan: dict):
    """GERÇEK `process_image`in sonucuna ölçülen alanı ekler (sonuç nesnesi gerçek kalır)."""
    orj = sinif.process_image

    def _sar(self, *a, **k):
        sonuc, ctx = orj(self, *a, **k)
        if "reliable" in alan:
            sonuc.reliable = alan["reliable"]
        if "uyari" in alan:
            sonuc.warnings = list(getattr(sonuc, "warnings", None) or []) + [alan["uyari"]]
        return sonuc, ctx

    monkeypatch.setattr(sinif, "process_image", _sar)


@pytest.mark.parametrize("ad,alan", FANTOM_ENGELLER, ids=[a for a, _ in FANTOM_ENGELLER])
def test_KRITIK_Y144_fantom_KABIN_cercevesi_gecerli_ama_SURULEMEZ_baglam_ve_aciklama_KURULMAZ(
    fantom_ucu, fantom_hatti, monkeypatch, ad, alan
):
    c, ef, kutu, govde = fantom_ucu
    pl = fantom_hatti[0]
    _aruco(pl, monkeypatch)
    _enjekte(pl.PhantomCvPipeline, monkeypatch, alan)
    kutu["ong"] = _KayitciFantom()
    ef.set_context([{"centroid_cabin_mm": [99.0, 99.0, 99.0], "organ_id": 1}])  # önceki analizin bağlamı
    r = c.post("/api/ai/vision/em_fantom", data={"image_base64": govde})
    j = r.json()
    assert r.status_code == 200 and j["method"] == "aruco_pnp" and j["pemf_valid"] is True, r.text[:200]
    assert j["pemf_kapisi"]["surulebilir"] is False and ad in j["pemf_kapisi"]["nedenler"], j["pemf_kapisi"]
    assert ef.get_context() is None, (
        f"sürülemez sonuçta ({ad}) canlı E bağlamı kuruldu / eski bağlam kaldı: {ef.get_context()}"
    )
    assert kutu["xai"] == [] and "xaiSensitivity" not in j, (
        f"sürülemez sonuçta ({ad}) 'dozu belirleyen' açıklaması üretildi"
    )
    assert j["tumor_regions"][0]["D"], "aparat: D / P / E yine HESAPLANIR (eylem metniyle gösterilir — C4)"


def test_KARSIT_Y144_fantom_SURULEBILIR_sonucta_baglam_ve_aciklama_KURULUR(fantom_ucu, fantom_hatti, monkeypatch):
    c, ef, kutu, govde = fantom_ucu
    _aruco(fantom_hatti[0], monkeypatch)
    kutu["ong"] = _KayitciFantom()
    r = c.post("/api/ai/vision/em_fantom", data={"image_base64": govde})
    j = r.json()
    assert r.status_code == 200 and j["pemf_kapisi"]["surulebilir"] is True, (r.text[:200], j.get("pemf_kapisi"))
    assert ef.get_context() is not None and kutu["xai"] and "xaiSensitivity" in j


@pytest.mark.parametrize("ad,alan", PETRI_ENGELLER, ids=[a for a, _ in PETRI_ENGELLER])
def test_KRITIK_Y144_petri_KABIN_cercevesi_gecerli_ama_SURULEMEZ_aciklama_URETILMEZ(
    petri_ucu, petri_hatti, monkeypatch, ad, alan
):
    c, kutu, govde, xai = petri_ucu
    pp = petri_hatti[0]
    _aruco(pp, monkeypatch)
    _enjekte(pp.PetriCvPipeline, monkeypatch, alan)
    r = c.post("/api/ai/vision/em_petri", data={"image_base64": govde})
    j = r.json()
    assert r.status_code == 200 and j["method"] == "aruco_pnp" and j["pemf_valid"] is True, r.text[:200]
    assert j["pemf_kapisi"]["surulebilir"] is False and ad in j["pemf_kapisi"]["nedenler"], j["pemf_kapisi"]
    assert xai == [] and "xaiSensitivity" not in j, f"sürülemez petri sonucunda ({ad}) açıklama üretildi"


@pytest.mark.parametrize(
    "uc,ad,alan",
    [("em_fantom", a, al) for a, al in FANTOM_ENGELLER] + [("em_petri", a, al) for a, al in PETRI_ENGELLER],
    ids=[f"fantom-{a}" for a, _ in FANTOM_ENGELLER] + [f"petri-{a}" for a, _ in PETRI_ENGELLER],
)
def test_KRITIK_Y144_GPU_servisi_PARITESI_surulemez_sonucta_aciklama_URETMEZ(
    servis_cv, fantom_hatti, petri_hatti, monkeypatch, uc, ad, alan
):
    a, _kutu, xai = servis_cv
    mod = fantom_hatti[0] if uc == "em_fantom" else petri_hatti[0]
    _aruco(mod, monkeypatch)
    _enjekte(mod.PhantomCvPipeline if uc == "em_fantom" else mod.PetriCvPipeline, monkeypatch, alan)
    kod, j = _govde(_servis_cagir(a, uc))
    assert kod == 200 and j.get("pemf_valid") is True and j["pemf_kapisi"]["surulebilir"] is False, (kod, str(j)[:200])
    assert xai == [] and "xaiSensitivity" not in j, f"GPU servisi ({uc}, {ad}) sürülemez sonuçta açıklama üretti"


@pytest.mark.parametrize("uc", ["em_fantom", "em_petri"])
def test_KARSIT_Y144_GPU_servisi_SURULEBILIR_sonucta_aciklama_URETIR(
    servis_cv, fantom_hatti, petri_hatti, monkeypatch, uc
):
    a, _kutu, xai = servis_cv
    _aruco(fantom_hatti[0] if uc == "em_fantom" else petri_hatti[0], monkeypatch)
    kod, j = _govde(_servis_cagir(a, uc))
    assert kod == 200 and j["pemf_kapisi"]["surulebilir"] is True and xai and "xaiSensitivity" in j, (kod, str(j)[:200])
