# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI-2 C1/C2 — hocanın fantom v3'ü guii'de: KÂHİN + guii sertleştirmesi (D1.100, D1.E07, headless) + kimlik kaydı görünürlüğü.

KÂHİN (plan §3.12): hocanın 9 fantom fotoğrafı + `beklenen_sonuclar/tumors.csv` (`tests/kahin/hoca_cv_2026_10/`, KAYNAK.md).
Hocanın kabul ölçütü (`smoke_test.py`): 9/9'da `success` + `reliable` + kimlikler TAM `T1…T5` + kabin koordinatı ≤ 0,5 mm.
Ölçüldü (C0 kâhin ağacı ve guii yapılandırmasıyla): 9/9, sapma 0,0 mm, `E_cancer` farkı ≤ 1,6e-8, uyarı kodları birebir.

SERTLEŞTİRME (guii v1'deki ata → guii farkı v3'e açıkça uygulandı): ArUco kipinde geçersiz kesişim → konum / alan / doz YOK
(D1.100); piksel kipinde doz yok, fiziksel alan bilinmiyorsa None (D1.E07); manuel tıklama (cv2 penceresi) YOK (headless,
plan §3.3); PhantomPredictor paket yolundan.

KİMLİK KAYDI (ölçüldü): ArUco kipinde hocanın `_frame` ölçeği 0 → yerleşim referansına kayıt HİÇ yapılmıyor ve T1…T5 SESSİZCE
konum sıralı kalıyordu (uyarı yok). Artık `layout_unregistered` uyarısı.

⚠️ Gerçek ağırlıklı testler `golden.eser` düzenini izler (ağırlık yoksa ATLA, `PEMF_GOLDEN_REQUIRED=1`'de DÜŞ).
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

KAHIN = Path(__file__).resolve().parent / "kahin" / "hoca_cv_2026_10"
_EM = "ai_hub/inference_em_fantom/BiLSTM_XXL_Raw.onnx"
_FANTOMLAR = sorted(p.name for p in (KAHIN / "fantom").glob("*.jpeg"))
_ESKI = sorted(p.name for p in (KAHIN / "fantom_eski").glob("*.jpeg"))


def _oku(yol: Path):
    import cv2

    img = cv2.imdecode(np.fromfile(str(yol), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert img is not None, f"kâhin görüntüsü okunamadı: {yol}"
    return img


def _kod(u: str) -> str:
    return str(u).split(":", 1)[0].strip()


@pytest.fixture(scope="module")
def fantom_v3():
    from golden.eser import atla, eser_var_mi

    if not eser_var_mi(_EM):
        atla(f"fantom EM ağırlığı ürün çözücüsünde yok ({_EM})")
    from ai_hub.inference_em_fantom.phantom_cv_v3 import PhantomCvPipeline, load_cabin_config

    pl = PhantomCvPipeline(load_cabin_config(None))
    _ = pl.predictor
    return pl


def _beklenen():
    t = {
        (s["image"], s["tumor_id"]): s
        for s in csv.DictReader(open(KAHIN / "beklenen_fantom" / "tumors.csv", encoding="utf-8"))
    }
    o = {s["image"]: s for s in csv.DictReader(open(KAHIN / "beklenen_fantom" / "summary.csv", encoding="utf-8"))}
    return t, o


def test_kahin_verisi_TAM():
    t, o = _beklenen()
    assert len(_FANTOMLAR) == 9 and set(_FANTOMLAR) == set(o) and len(t) == 45 and len(_ESKI) == 4


@pytest.mark.parametrize("ad", _FANTOMLAR)
def test_KRITIK_KAHIN_T1_T5_reliable_kabin_05mm(fantom_v3, ad):
    t, o = _beklenen()
    r, _ = fantom_v3.process_image(_oku(KAHIN / "fantom" / ad), image_name=ad)
    assert r.success and r.reliable, f"{ad}: success={r.success} reliable={r.reliable} hata={r.error}"
    assert [x.tumor_id for x in r.tumor_regions] == ["T1", "T2", "T3", "T4", "T5"]
    for x in r.tumor_regions:
        b = t[(ad, x.tumor_id)]
        sap = max(abs(a - float(v)) for a, v in zip(x.centroid_cabin_mm, (b["x_mm"], b["y_mm"], b["z_mm"])))
        assert sap <= 0.5, f"{ad} {x.tumor_id}: kabin koordinatı sapması {sap:.3f} mm > 0,5 (hocanın ölçütü)"
        assert x.E_cancer is not None and abs(x.E_cancer - float(b["E_cancer"])) < 1e-6
    assert r.method == o[ad]["method"] and r.pemf_source == o[ad]["pemf_source"] == "cst_phantom_box"
    assert sorted(_kod(u) for u in r.warnings) == sorted(_kod(u) for u in o[ad]["warnings"].split(" | ") if u)
    assert "pemf_axis_sign_assumed" in {_kod(u) for u in r.warnings}, "CST kutusu VARSAYIMI uyarısı kaybolmamalı (C8)"


@pytest.mark.parametrize("ad", _ESKI)
def test_KRITIK_eski_fantom_PIKSEL_kipinde_DOZ_YOK_alan_YOK_D1E07(fantom_v3, ad):
    """Hoca: eski dağınık-leke fantomu v1 kipine düşer (2 tümör, ölçek yok). guii D1.E07: piksel farkı doz modeline mm diye
    VERİLMEZ (ölçüldü: +6,8σ eğitim dışı), E None, D boş, alan None — 0.0 "hesaplandı, sıfır" diye okunurdu."""
    r, _ = fantom_v3.process_image(_oku(KAHIN / "fantom_eski" / ad), image_name=ad)
    assert r.success and r.method == "pixel" and r.pemf_valid is False and r.n_tumor == 2
    for x in r.tumor_regions:
        assert x.E_cancer is None and x.E_healthy is None and x.D == [] and x.area_mm2 is None, x


def test_KRITIK_ArUco_GECERSIZ_kesisim_KONUM_ve_DOZ_YOK_D1100(fantom_v3, monkeypatch):
    """ArUco kipinde ışın kabin dışında kesişirse (D1.100) konum / alan / doz ÜRETİLMEZ, neden `konum_hatasi`nda."""
    from ai_hub.cv_ortak.coord_transform import KesisimGecersiz
    from ai_hub.inference_em_fantom.phantom_cv_v3 import pipeline as pp

    class _Poz:
        marker_id, reproj_error_px = 0, 0.1
        tvec = np.zeros((3, 1))

    monkeypatch.setattr(pp, "detect_aruco_marker", lambda img, cfg: type("M", (), {"corners_px": np.zeros((4, 2))})())
    monkeypatch.setattr(pp, "solve_cabin_pose", lambda *a, **k: _Poz())

    def _disari(*a, **k):
        raise KesisimGecersiz("kesisim kabin DISINDA (test)")

    monkeypatch.setattr(pp, "pixel_to_cabin_mm", _disari)
    r, _ = fantom_v3.process_image(_oku(KAHIN / "fantom" / _FANTOMLAR[0]))
    assert r.success and r.method == "aruco_pnp" and r.tumor_regions
    for x in r.tumor_regions:
        assert x.centroid_cabin_mm is None and x.centroid_cabin_cm is None and "kabin DISINDA" in (x.konum_hatasi or "")
        assert x.E_cancer is None and x.D == [] and x.area_mm2 is None


def test_KRITIK_ArUco_kipinde_KIMLIK_KAYDI_yoksa_GORUNUR_uyari(fantom_v3):
    """Sentetik ArUco (guii saha işareti hocanın 19.40.11 fotoğrafına): kayıt yapılamıyor → `layout_unregistered`."""
    import cv2

    kok = Path(__file__).resolve().parents[1]
    isaret = _oku(kok / "ai_hub" / "PEMF_ArUco_Marker_5X5_50_ID0_15cm_A4.png")
    g = cv2.cvtColor(isaret, cv2.COLOR_BGR2GRAY)
    ys, xs = np.where(g < 128)
    kirp = isaret[ys.min() - 20 : ys.max() + 21, xs.min() - 20 : xs.max() + 21]
    foto = _oku(KAHIN / "fantom" / "WhatsApp Image 2026-10-02 at 19.40.11.jpeg")
    foto[10:270, 10:270] = cv2.resize(kirp, (260, 260), interpolation=cv2.INTER_AREA)
    r, _ = fantom_v3.process_image(foto)
    assert r.method == "aruco_pnp" and r.pemf_source == "aruco"
    assert "rms_mm" not in (r.layout or {}), r.layout
    assert "layout_unregistered" in {_kod(u) for u in r.warnings}, r.warnings
    # Kâhin görüntüsünde (halka ölçeği) kayıt VAR ve uyarı YOK (karşıt):
    r2, _ = fantom_v3.process_image(_oku(KAHIN / "fantom" / "WhatsApp Image 2026-10-02 at 19.40.11.jpeg"))
    assert "rms_mm" in r2.layout and "layout_unregistered" not in {_kod(u) for u in r2.warnings}


def test_KRITIK_plaka_fotografi_FANTOM_sanilmaz(fantom_v3):
    """Hocanın 24'lük plaka fotoğrafları v3'te tümör ÜRETMEZ (v1'de de `phantom_not_detected`)."""
    for p in sorted((KAHIN / "petri").glob("WhatsApp Image *.jpeg")):
        r, _ = fantom_v3.process_image(_oku(p))
        assert not r.success and r.n_tumor == 0, f"{p.name}: {r.n_tumor} tümör"


def test_KRITIK_HEADLESS_manuel_secim_ve_pencere_YOK():
    """`manual_select` (cv2 penceresi) alınmadı; paket hiçbir pencere API'si çağırmaz; manual_fallback=True YOK SAYILIR."""
    import importlib
    import inspect
    import pkgutil

    import ai_hub.inference_em_fantom.phantom_cv_v3 as paket
    from ai_hub.inference_em_fantom.phantom_cv_v3 import PhantomCvPipeline

    adlar = {m.name for m in pkgutil.iter_modules(paket.__path__)}
    assert not adlar & {"manual_select", "api", "cli", "mqtt_publish", "coil_detect"}, adlar
    for ad in adlar:
        kaynak = inspect.getsource(importlib.import_module(f"{paket.__name__}.{ad}"))
        for yasak in ("imshow(", "namedWindow(", "waitKey(", "selectROI(", "setMouseCallback(", "VideoCapture("):
            assert yasak not in kaynak, f"{ad}: {yasak}"
    assert PhantomCvPipeline(None, manual_fallback=True).manual_fallback is False


def test_v3_EM_ongorucu_PAKET_yolundan():
    import sys

    from ai_hub.inference_em_fantom import inference_em_fantom as paket
    from ai_hub.inference_em_fantom.phantom_cv_v3 import pipeline as pp

    assert pp.PhantomPredictor is paket.PhantomPredictor
    assert not any(str(p).replace("\\", "/").rstrip("/").endswith("ai_hub/inference_em_fantom") for p in sys.path)


def test_v3_yerlesim_referansi_YAMLin_YANINDA_ve_hocaninkiyle_AYNI():
    """Paket `phantom_layout_2026-10-02.json`u YAML'ın yanında taşımalı (göreli `layout_file`); içerik hocanınkiyle aynı."""
    import json

    from ai_hub.inference_em_fantom.phantom_cv_v3 import load_cabin_config

    cfg = load_cabin_config(None)
    yol = Path(cfg.source_path).parent / cfg.phantom_v2.layout_file
    d = json.loads(yol.read_text(encoding="utf-8"))
    assert d["ids"] == ["T1", "T2", "T3", "T4", "T5"] and d["n_images"] == 8 and d["tumor_radius_mm"] == 12.05
    assert d["points_mm"][3] == [5.19, -13.451] and d["phantom_box"]["size_mm"] == [104.1, 65.0]
