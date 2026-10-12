# -*- coding: utf-8 -*-
"""AII-2.3 (AI incelemesi, A2) — karar #4 (araştırma AI Pro'da ArUco ZORUNLU) yöntem tavanı TABLOSUNUN İÇERİĞİYLE kilitli.

KÖR KAPI [ÖLÇTÜM K1.4 + mutant K1a]: hocanın v3'ü ArUco YOKKEN de `pemf_valid=true` üretir — CST eğitim kutusu VARSAYIMI
(`pemf_source=cst_phantom_box`, eksen işareti laboratuvar #2) ya da `placement` (petri `multiwell.placement`, fantom
`origin_cabin_mm`). PEMF tüketim kapısı bunları GEÇİRİR (hocanın §3'ü: pemf_valid true). Bu sonuçların AI Pro'da sürülmemesinin
TEK nedeni `YONTEM_TAVANI` (ArUco dışı yöntem tavanı 0,25 < `MIN_GUVEN` 0,3). Mevcut kapı yalnız VARSAYILAN tavanı (`pixel`)
denetliyor: tabloya `"coil_ring": 1.0` (ya da `plate_grid`) eklemek 11 dosyalık AI Pro araştırma kümesinde YEŞİL kaldı
(149 geçti) ve CST VARSAYIMLI fantom T1 (-43,6, -15,0, -9,2) mm güven 0,9 ile LOKALİZE oldu.
Bu kapı: boru hatlarının ürettiği HER ArUco dışı yöntem tavanı eşiğin altında + kapıdan geçen (pemf_valid) ArUco'suz sonuç
sağlayıcıda LOKALİZE SAYILMAZ (uçtan uca, sahte en alt katta).
Yol: tests/test_ai_pro_arastirma_ArUco_DISI_yontem_TAVANI_kilidi_AII23.py"""

from __future__ import annotations

import numpy as np
import pytest

#: phantom_cv_v3 / petri_cv_v2 `result.method` değerleri (pipeline.py'lerde `result.method =` satırları) — ArUco dışı.
ARUCO_DISI = ("coil_ring", "phantom_layout", "phantom_length", "pixel", "plate_grid", "petri_diameter", "")


@pytest.mark.parametrize("yontem", ARUCO_DISI)
def test_KRITIK_ArUco_disi_her_yontemin_tavani_ESIGIN_altinda(yontem):
    import servers.ai_pro_hedef as hedef

    assert hedef._yontem_tavani(yontem) < hedef.MIN_GUVEN, (
        f"'{yontem}' yöntem tavanı {hedef._yontem_tavani(yontem)} ≥ MIN_GUVEN {hedef.MIN_GUVEN} — ArUco'suz (CST VARSAYIMI / "
        "placement) sonuç AI Pro'da sürülebilir (karar #4)"
    )
    assert hedef._yontem_tavani("aruco_pnp") >= hedef.MIN_GUVEN, "karşıt: ArUco kipi sürülebilir kalmalı"


class _Bolge:
    def __init__(self, mm):
        self.centroid_px, self.centroid_cabin_mm, self.organ_id, self.area_px = (100.0, 100.0), mm, 1, 400
        self.bbox_px, self.E_cancer, self.E_healthy, self.tumor_id, self.well_id = (
            (90, 90, 20, 20),
            0.9,
            0.1,
            "T1",
            "B2",
        )
        self.reliability = 0.95


class _Sonuc:
    def __init__(self, **k):
        self.success, self.error, self.mm_per_px, self.pemf_valid, self.reliable = True, None, 0.31, True, True
        self.layout, self.healthy_regions = {"mode": "register", "rms_mm": 1.2}, []
        self.tumor_regions = [_Bolge((-43.6, -15.0, -9.2))]
        self.wells = [_Bolge((-20.0, 10.0, -40.0))]
        self.phantom_detection = {"primary": {"solidity": 0.95, "n_blue_inside": 5}}
        self.plate, self.classification = {"plate_type": 24}, {"control_healthy": ["A1"], "control_cancer": ["B2"]}
        for a, v in k.items():
            setattr(self, a, v)


DURUMLAR = [
    (
        "fantom",
        dict(
            method="coil_ring",
            pemf_source="cst_phantom_box",
            coord_frame="cabin_cst_phantom_box",
            warnings=["pemf_axis_sign_assumed: fantom merkezi/eksenleri CST egitim kutusuna eslendi"],
        ),
    ),
    (
        "fantom",
        dict(method="phantom_layout", pemf_source="cst_phantom_box", coord_frame="cabin_cst_phantom_box", warnings=[]),
    ),
    ("fantom", dict(method="coil_ring", pemf_source="placement", coord_frame="cabin_placement", warnings=[])),
    ("petri", dict(method="plate_grid", coord_frame="cabin_placement", warnings=[])),
    ("petri", dict(method="petri_diameter", coord_frame="cabin_placement", warnings=[])),
]


@pytest.mark.parametrize("model,alanlar", DURUMLAR, ids=[f"{m}-{a['method']}-{a['coord_frame']}" for m, a in DURUMLAR])
def test_KRITIK_kapidan_gecen_ArUco_suz_sonuc_LOKALIZE_sayilmaz(monkeypatch, model, alanlar):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air

    from ai_hub.cv_ortak import pemf_kapisi

    sonuc = _Sonuc(**alanlar)
    assert pemf_kapisi.degerlendir(sonuc, model=model)["surulebilir"] is True, (
        "düzenek: bu sonuç PEMF kapısından GEÇMELİ"
    )

    class _Hat:
        def __init__(self, cfg, **kw):
            self._predictor, self.yolo = None, None

        def process_image(self, frame, achieved_B=None, duty_sum=None):
            return sonuc, {}

        def render_panels(self, *a, **k):
            return {}

    class _Cfg:
        class phantom:  # noqa: N801
            achieved_B, duty_sum = 0.001, 2.4

    monkeypatch.setattr(
        air,
        "_get_or_load_model",
        lambda ad, y: {"cls": _Hat, "cfg": _Cfg(), "predictor": None, "yolo": None, "yolo_path": "y.onnx"},
    )
    s = hedef.FantomSaglayici() if model == "fantom" else hedef.PetriSaglayici()
    r = s.localize(np.zeros((400, 400, 3), np.uint8), 0)
    assert r[0] is False, (
        f"{model} {alanlar['method']} / {alanlar['coord_frame']}: ArUco'suz sonuç LOKALİZE sayıldı (güven {r[4]:.2f}) — karar #4"
    )
    assert "kabin işareti" in s.ipucu(True, "Hedef"), "ipucu operatöre ArUco işaretini söylemeli"
