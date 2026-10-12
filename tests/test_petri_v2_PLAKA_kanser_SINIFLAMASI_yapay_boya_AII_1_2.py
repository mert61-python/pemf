# -*- coding: utf-8 -*-
"""AII-1.2 (AI incelemesi, A1) — petri v2 PLAKA kipinin kanser sınıflaması HİÇBİR kapıda ölçülmüyordu (KÖR KAPI).

ÖLÇÜLDÜ: hocanın kâhin plakalarında kanser kuyucuğu YOK (144/144 sağlıklı) → `test_petri_cv_v2_KAHIN_…` "etiket birebir"
denetimi yalnız "hepsi sağlıklı"yı görür. Mutant `organ_id = HEALTHY` (plaka kipinde sınıflama kapalı, `pipeline.py:575`)
petri boru hattına atıf yapan 42 test dosyasının HEPSİNDE yeşil (534 geçti / 0 kırmızı, gerçek ağırlıkla — `kayit/K1_M1_*`).
Kanser etiketi hedef seçimini, `organ_id`'yi, kontrol QC'sini (`control_cancer_missed` → sonuç kullanılmaz) ve AI Hub kartını
belirler.

Bu kapı hocanın sentetik doğrulamasının eşidir (README: "gerçek görüntülere yapay boya"): kâhin plakasında BİLİNEN iki kuyucuğa
(B2, C5) yapay mavi boya → yalnız o ikisi kanser; yanlış kontrol kuyucuğu (A3) → `control_cancer_missed` + tüketim kapısı keser.
Sahte EN ALT katta: YOLO kapatılır (yalnız ipucu), doz modeli çağrı sınırında sözleşmeye uyan sahte; sınıflama gerçek kod.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

KAHIN = Path(__file__).resolve().parent / "kahin" / "hoca_cv_2026_10"
_RESIMLER = sorted(p.name for p in (KAHIN / "petri").glob("WhatsApp Image *.jpeg"))
_BOYALI = ("B2", "C5")


class _SahteEM:
    def predict(self, x, y, z, organ_id, achieved_B, duty_sum):
        d = {f"D{k}": 0.5 for k in range(1, 8)}
        d.update({f"P{k}": 100.0 for k in range(1, 8)})
        d.update(result_E_healthy=0.1, result_E_cancer=0.1, result_E_avg=0.1)
        return d


def _boyali(ad):
    """Hocanın beklenen kuyucuk merkezlerine (wells.csv) yarıçapın %55'i kadar mavi boya (BGR 200,70,90; α 0,6)."""
    import cv2

    img = cv2.imdecode(np.fromfile(str(KAHIN / "petri" / ad), dtype=np.uint8), cv2.IMREAD_COLOR)
    mmpx = {
        s["image"]: float(s["mm_per_px"])
        for s in csv.DictReader(open(KAHIN / "beklenen_petri" / "summary.csv", encoding="utf-8"))
    }
    r = 0.5 * 15.6 / mmpx[ad]
    for s in csv.DictReader(open(KAHIN / "beklenen_petri" / "wells.csv", encoding="utf-8")):
        if s["image"] == ad and s["well_id"] in _BOYALI:
            m = np.zeros(img.shape[:2], np.uint8)
            cv2.circle(m, (int(float(s["cx_px"])), int(float(s["cy_px"]))), int(r * 0.55), 255, -1)
            sel = m > 0
            img[sel] = (0.6 * np.array((200, 70, 90)) + 0.4 * img[sel]).astype(np.uint8)
    return img


def _boru_hatti(tmp_path, **kw):
    from ai_hub.inference_petri_dish.petri_cv_v2 import PetriCvPipeline, load_cabin_config

    yol = tmp_path / "yolo_ipucu_yok.onnx"
    yol.write_bytes(b"")
    pl = PetriCvPipeline(load_cabin_config(None), yolo_model_path=yol, yolo_device="cpu", **kw)
    pl.yolo, pl._predictor = None, _SahteEM()
    return pl


@pytest.mark.parametrize("ad", _RESIMLER)
def test_KRITIK_boyali_kuyucuklar_KANSER_digerleri_SAGLIKLI(tmp_path, ad):
    r, _ = _boru_hatti(tmp_path).process_image(_boyali(ad))
    assert r.success and r.n_wells == 24, (r.error, r.n_wells)
    kanser = sorted(w.well_id for w in r.wells if w.label == "cancer")
    assert kanser == sorted(_BOYALI), f"{ad}: kanser={kanser} (beklenen {_BOYALI})"
    assert r.n_cancer == 2 and all(w.organ_id == 1 for w in r.wells if w.well_id in _BOYALI)


@pytest.mark.parametrize("ad", _RESIMLER[:2])
def test_KRITIK_yanlis_kontrol_kuyucugu_QC_ve_kapi_KESER(tmp_path, ad):
    from ai_hub.cv_ortak import pemf_kapisi

    r, _ = _boru_hatti(tmp_path, control_cancer=["A3"]).process_image(_boyali(ad))
    kodlar = {str(u).split(":", 1)[0] for u in r.warnings}
    assert "control_cancer_missed" in kodlar, r.warnings
    k = pemf_kapisi.degerlendir(r, model="petri")
    assert "control_cancer_missed" in k["engelleyici"] and k["surulebilir"] is False, k
