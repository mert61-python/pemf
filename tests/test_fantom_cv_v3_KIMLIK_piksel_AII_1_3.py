# -*- coding: utf-8 -*-
"""AII-1.3 (AI incelemesi, A1) — fantom v3 kâhin kapısı KİMLİK ATAMASINI görüntü tarafında ölçmüyordu (TOTOLOJİ).

ÖLÇÜLDÜ: CST kipinde (kâhinin 9/9 kipi) tümörün kabin koordinatı yerleşim REFERANSINDAN kimliğe göre okunur
(`phantom_cv_v3/pipeline.py` `lay_uv[tid] = layout.to_uv(layout.points_mm[k])`) — "9/9 sapma 0,0000 mm" ve E farkı ≤ 1,6e-8 bu yüzden
yapısal olarak garantidir; görüntüdeki tümör yalnız KİMLİK ATAMASINI (kayıt) belirler. Kimlik takası mutantı
(`id_map` içinde T2↔T3) fantoma atıf yapan 38 test dosyasında YEŞİL (471 geçti / 0 kırmızı, gerçek ağırlık). Takasın etkisi:
"Tümör T2" etiketi görüntüde FİZİKSEL T3 lekesinin üstünde (piksel merkezi, alan), ama kabin koordinatı / doz T2 referansından →
AI Hub kartı ve AI Pro onay ekranı operatöre bir lekeyi gösterip bobini başka tümörün koordinatına götürür.

Kapı: hocanın `tumors.csv`'sindeki piksel merkezi (cx_px, cy_px) ve alan (area_px) kimliğe göre karşılaştırılır (ölçülen fark
≤ 0,062 px, alan birebir; komşu tümörler ≥ 45 px ayrık → 2 px tolerans kimliği kesin ayırır).
Sahte EN ALT katta: doz modeli çağrı sınırında sözleşmeye uyan sahte (geometri / kimlik doz modelinden bağımsız).
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
import pytest

KAHIN = Path(__file__).resolve().parent / "kahin" / "hoca_cv_2026_10"
_FOTOLAR = sorted(p.name for p in (KAHIN / "fantom").glob("*.jpeg"))


class _SahteEM:
    def predict(self, x, y, z, organ_id, achieved_B, duty_sum):
        d = {f"D{k}": 0.5 for k in range(1, 8)}
        d.update({f"P{k}": 100.0 for k in range(1, 8)})
        d.update(result_E_healthy=0.1, result_E_cancer=0.1, result_E_avg=0.1)
        return d


@pytest.fixture(scope="module")
def fantom():
    from ai_hub.inference_em_fantom.phantom_cv_v3 import PhantomCvPipeline, load_cabin_config

    pl = PhantomCvPipeline(load_cabin_config(None), manual_fallback=False)
    pl._predictor = _SahteEM()
    return pl


def _beklenen():
    b: dict[str, dict[str, dict]] = {}
    for s in csv.DictReader(open(KAHIN / "beklenen_fantom" / "tumors.csv", encoding="utf-8")):
        b.setdefault(s["image"], {})[s["tumor_id"]] = s
    return b


def test_vakum_9_fotograf_45_tumor():
    b = _beklenen()
    assert len(_FOTOLAR) == 9 and set(_FOTOLAR) == set(b) and sum(len(v) for v in b.values()) == 45


@pytest.mark.parametrize("ad", _FOTOLAR)
def test_KRITIK_T1_T5_kimligi_GORUNTUDEKI_lekeyle_eslesir(fantom, ad):
    import cv2

    img = cv2.imdecode(np.fromfile(str(KAHIN / "fantom" / ad), dtype=np.uint8), cv2.IMREAD_COLOR)
    r, _ = fantom.process_image(img, image_name=ad)
    b = _beklenen()[ad]
    assert r.success and [x.tumor_id for x in r.tumor_regions] == ["T1", "T2", "T3", "T4", "T5"], r.error
    for x in r.tumor_regions:
        e = b[x.tumor_id]
        d = math.hypot(x.centroid_px[0] - float(e["cx_px"]), x.centroid_px[1] - float(e["cy_px"]))
        assert d <= 2.0, f"{ad} {x.tumor_id}: lekenin piksel merkezi hocanınkinden {d:.1f} px uzak (kimlik takası?)"
        assert abs(x.area_px - float(e["area_px"])) <= 0.01 * float(e["area_px"]), (
            ad,
            x.tumor_id,
            x.area_px,
            e["area_px"],
        )
        assert x.area_mm2 is not None and abs(x.area_mm2 - float(e["area_mm2"])) <= 0.01 * float(e["area_mm2"]), (
            ad,
            x.tumor_id,
            x.area_mm2,
            e["area_mm2"],
        )
