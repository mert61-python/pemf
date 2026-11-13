# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""T3 · Y191b (sahip + Çağlar Hoca, 2026-10-24) — petri PLAKA kipinde ızgara hücresinin skoruna eşik (varsayılan 0,6), arayüzden ayarlı.

İSTEK: Çağlar Hoca (ekran görüntüsü, `Desktop\\deneme.png`, "02 – YOLO Kuyucuk Tespiti" paneli): "o üstünde yazan skora threshold
koycam … 0.6 olarak … 0.6 yaptık ama bir şey değişmedi bu analizde"; sahip: "UI'dan da ayarlanır olsun o skor".
ÖLÇÜLEN (önce, HEAD 7432f62c): plaka kipinde hücre üstündeki sayı YOLO güveni DEĞİL — `plate_grid` destek skoru (hücre maskesinde
besiyeri / boya kaplayan alan oranı; `PetriDetection.conf` alanına yazılıyor). Izgara 24 hücreyi HER ZAMAN üretir; Y191'in YOLO güveni
(0,6) yalnız ipucu tespitlerini süzer → plaka kipinde sonuç DEĞİŞMEZ (12/12 kare). `deneme.png` koşulsuz: ızgara plakadan taşıyor,
kâğıda düşen D1 0,00 · D2 0,00 · D3 0,195 · D5 0,051 · D6 0,247 de kuyu sayılıyor (24 kuyu). İyi kabin karelerinde en düşük hücre
skoru ≥ 0,785 (eleme yok).
KAPI: eşik altı hücre kuyu SAYILMAZ (ne D/P/E ne sınıflama ne AI Pro hedefi), `plate.elenen_kuyular` + `kuyu_skor_esigi:` uyarısı;
eşik = boru hattı varsayılanı 0,6 (tek kaynak) ya da istek alanı `kuyu_skor_esigi` (0 = kapalı, 0–1); PEMF kapısı: koşulluda yeniden
çekim (bobine esas alınmaz), koşulsuzda uyarı; hepsi elenirse sonuç yok (`plate_wells_below_score`).
"""

from __future__ import annotations

import inspect

import cv2
import numpy as np
import pytest
from test_em_ongorucu_SONLU_OLMAYAN_girdi_PIKSEL_kipi_ve_TOPLAM_sure import (  # noqa: F401
    _KayitciDoz,
    _renkli_kare,
    petri_hatti,
)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 1. AYAR (tek kaynak)
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_kuyu_skor_esigi_varsayilani_0_6_ve_arayuz_varsayilani_BORU_HATTINI_izler():
    from ai_hub.inference_petri_dish import petri_ayar as pa
    from ai_hub.inference_petri_dish.petri_cv_v2.pipeline import PetriCvPipeline

    vars_ = inspect.signature(PetriCvPipeline.__init__).parameters["kuyu_skor_esigi"].default
    assert vars_ == pytest.approx(0.6)
    assert pa.varsayilanlar()["kuyu_skor_esigi"] == pytest.approx(vars_)
    assert pa.SINIRLAR["kuyu_skor_esigi"] == (0.0, 1.0)


def test_KRITIK_arayuz_varsayilani_KOPYA_degil_boru_hattini_TAKIP_eder(monkeypatch):
    from ai_hub.inference_petri_dish import petri_ayar as pa
    from ai_hub.inference_petri_dish.petri_cv_v2 import pipeline as pp

    def _sahte(self, cfg=None, *, yolo_conf: float = 0.6, kuyu_skor_esigi: float = 0.33, **k):  # noqa: ARG001
        return None

    monkeypatch.setattr(pp.PetriCvPipeline, "__init__", _sahte)
    assert pa.varsayilanlar()["kuyu_skor_esigi"] == pytest.approx(0.33), (
        "varsayılan KOPYALANMIŞ (boru hattını izlemiyor)"
    )


def test_KRITIK_istek_alani_cozulur_sinir_disi_REDDEDILIR_bos_istek_varsayilanda():
    from ai_hub.inference_petri_dish import petri_ayar as pa

    assert pa.coz() == {}, "alan gönderilmeyen istek varsayılanı EZMEMELİ"
    assert pa.coz(kuyu_skor_esigi="0.4") == {"kuyu_skor_esigi": pytest.approx(0.4)}
    assert pa.coz(kuyu_skor_esigi="0") == {"kuyu_skor_esigi": 0.0}, "0 = eşik KAPALI geçerli değer"
    with pytest.raises(pa.AyarHatasi):
        pa.coz(kuyu_skor_esigi="1.5")


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 2. BORU HATTI (GERÇEK `process_image`, sahte ızgara — en alt kat)
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════

_SKORLAR = [("A1", 0.97), ("A2", 0.0), ("A3", 0.59), ("A4", 0.6)]


def _sahte_izgara():
    from ai_hub.inference_petri_dish.petri_cv_v2.petri_detector import PetriDetection
    from ai_hub.inference_petri_dish.petri_cv_v2.plate_grid import PlateGridResult

    g = PlateGridResult(True, H_img_from_plate=np.eye(3), mm_per_px=0.2)
    for j, (kid, skor) in enumerate(_SKORLAR):
        maske = np.zeros((480, 640), np.uint8)
        merkez = (100 + 140 * j, 240)
        cv2.circle(maske, merkez, 50, 255, -1)
        kont, _ = cv2.findContours(maske, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        g.detections.append(
            PetriDetection(
                bbox_xyxy=(merkez[0] - 50.0, 190.0, merkez[0] + 50.0, 290.0),
                conf=skor,
                mask=maske,
                contour=kont[0],
                centroid_px=(float(merkez[0]), 240.0),
                area_px=int((maske > 0).sum()),
                radius_px=50.0,
            )
        )
        g.well_ids.append(kid)
        g.wells_plate_mm.append((19.3 * j, 0.0))
        g.sources.append("grid")
    return g


def _plaka_kos(pp, yolo_sinifi, monkeypatch, **kw):
    monkeypatch.setattr(pp, "detect_plate_wells", lambda *a, **k: _sahte_izgara())
    monkeypatch.setattr(pp._plaus, "evaluate_plate", lambda *a, **k: (True, {"kip": "plaka"}))
    hat = pp.PetriCvPipeline(None, yolo_device="cpu", plate_type=24, **kw)
    hat.yolo = yolo_sinifi()
    hat._predictor = _KayitciDoz()
    return hat.process_image(_renkli_kare())


def test_KRITIK_esik_alti_hucre_KUYU_SAYILMAZ_elenenler_ve_uyari_gorunur(petri_hatti, monkeypatch):
    pp, _kos, _Yolo = petri_hatti
    sonuc, ctx = _plaka_kos(pp, _Yolo, monkeypatch)
    assert sonuc.success is True, (sonuc.error, sonuc.warnings)
    assert [w.well_id for w in sonuc.wells] == ["A1", "A4"], "eşik altı hücre kuyu sayıldı (0,6 eşitse KALIR)"
    assert sonuc.n_wells == 2 and len(ctx["detections"]) == 2, "panelde / hesapta elenen hücre kaldı"
    assert sonuc.plate["kuyu_skor_esigi"] == pytest.approx(0.6)
    assert sonuc.plate["elenen_kuyular"] == [{"well_id": "A2", "skor": 0.0}, {"well_id": "A3", "skor": 0.59}]
    assert any(w.startswith("kuyu_skor_esigi:") and "A2, A3" in w for w in sonuc.warnings), sonuc.warnings


def test_KARSIT_esik_0_KAPALI_tum_hucreler_kuyu_istek_esigi_GECER(petri_hatti, monkeypatch):
    pp, _kos, _Yolo = petri_hatti
    s0, _ = _plaka_kos(pp, _Yolo, monkeypatch, kuyu_skor_esigi=0.0)
    assert s0.n_wells == 4 and s0.plate["elenen_kuyular"] == []
    assert not any(w.startswith("kuyu_skor_esigi:") for w in s0.warnings)
    s1, _ = _plaka_kos(pp, _Yolo, monkeypatch, kuyu_skor_esigi=0.95)
    assert [w.well_id for w in s1.wells] == ["A1"]


def test_KRITIK_tum_hucreler_esik_altinda_ise_SONUC_YOK(petri_hatti, monkeypatch):
    pp, _kos, _Yolo = petri_hatti
    s, _ = _plaka_kos(pp, _Yolo, monkeypatch, kuyu_skor_esigi=0.99)
    assert s.success is False and s.error == "plate_wells_below_score" and s.wells == [], (s.error, s.n_wells)


def test_KARSIT_TEKIL_kipte_esik_UYGULANMAZ_YOLO_guveni_ayri(petri_hatti):
    pp, kos, _Yolo = petri_hatti
    _hat, sonuc, _ctx = kos(kuyu_skor_esigi=0.99)  # tekil kap kipi (plate_type=0): hücre skoru yok, YOLO güveni süzer
    assert sonuc.n_wells == 1 and "kuyu_skor_esigi" not in (sonuc.plate or {})


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 3. PEMF KAPISI
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_Y284_elenen_hucre_KOSULLUDA_da_SURUSU_KESMEZ_uyari_kodu_KALIR():
    """Y284 (sahip 13 Kasım 2026: "yeniden çekim sayılmasın … yarı dolu plakayla da sürüş olabilmeli koşulluda"): boş (eşik altı) hücre
    kuyu SAYILMAZ ama koşullu kipte de sürüşü KESMEZ; uyarı kodu sonuçta görünür. (Eski Y191b: koşulluda yeniden çekimdi.)"""
    from ai_hub.cv_ortak import pemf_kapisi as pk

    sonuc = {
        "success": True,
        "pemf_valid": True,
        "warnings": ["kuyu_skor_esigi: 2 hucrenin skoru 0.6 altinda - kuyu sayilmadi: D1, D2"],
    }
    k = pk.degerlendir(sonuc, model="petri")
    assert k["surulebilir"] is True and "kuyu_skor_esigi" not in k["yeniden_cekim"], k
    assert "kuyu_skor_esigi" in k["uyari_kodlari"], k
    assert "kuyu_skor_esigi" not in pk.YENIDEN_CEKIM
    k2 = pk.degerlendir(sonuc, model="petri", kosulsuz=True)
    assert k2["surulebilir"] is True, k2
    # KARŞIT: kırpık plaka (ızgara kadrajdan taştı) koşulluda YİNE yeniden çekim
    k3 = pk.degerlendir(
        {**sonuc, "warnings": sonuc["warnings"] + ["plate_cropped: plaka kenari kadraj disinda"]}, model="petri"
    )
    assert k3["surulebilir"] is False and "plate_cropped" in k3["yeniden_cekim"], k3
    k0 = pk.degerlendir({"success": True, "pemf_valid": True, "warnings": []}, model="petri")
    assert k0["surulebilir"] is True  # KARŞIT: eleme yoksa koşullu da sürülebilir
