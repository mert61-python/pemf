# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""İG-5.75 · ArUco (perspektif PnP) kipinde fantom / petri analiz PANELİ "Olcek: 0.000 mm/px" YAZMAZ (D67, 2026-10-28).

🔴 ÖLÇÜLEN DURUM (HEAD ebf1c3fe, sonda `_inceleme/IG-5.75`; sentetik kabin işareti DICT_5X5_50 hocanın gerçek fantom / petri
fotoğrafına yapıştırıldı + izli `06b_PetriKuyu_aruco.jpg`; gömülü uç ve :8100 TestClient): ArUco kipinde `method="aruco_pnp"`,
`mm_per_px = 0.0` (fantom `phantom_cv_v3/pipeline.py:350`; petri aynı) — perspektif izdüşümde TEK bir mm/px YOK. Alan artık
ölçülmüş-sıfır DEĞİL (`area_mm2 = None`, D1.E07 / D1.100 — o kol KAPALI). Ama panel görseli (`render.py` `panel_02_*`) ölçeği
`"Olcek: {s:.3f} mm/px"` ile 0 → "Olcek: 0.000 mm/px" çiziyor = "ölçek ölçüldü, sıfır" (yanlış ölçüm gösterimi).
KAPI: çizici `_put_text`e giden metin KAYDEDİLİR (sahte EN ALT katta: yalnız metin çizimi); ölçek ≤ 0 / sonlu değil → "0.000 mm/px"
YOK + "perspektif" notu VAR (TR ve EN, fantom ve petri); karşıt-kanıt: pozitif ölçek (halka / uzunluk kipi) aynen yazılır.
"""

from __future__ import annotations

import capraz
import pytest

np = capraz.paket_yoksa_atla("numpy")
cv2 = capraz.paket_yoksa_atla("cv2")

_FANTOM = "ai_hub.inference_em_fantom.phantom_cv_v3.render"
_PETRI = "ai_hub.inference_petri_dish.petri_cv_v2.render"

#: Pinli beklenen metinler (üründen OKUNMAZ) — cv2 Hershey yazı tipi ASCII dışını çizemez.
BEKLENEN_YOK = {"tr": "Olcek: perspektif (ArUco), tek mm/px yok", "en": "Scale: perspective (ArUco), no single mm/px"}


def _kayitli_metinler(monkeypatch, modul_adi: str, mm_per_px, lang: str) -> list[str]:
    import importlib

    m = importlib.import_module(modul_adi)
    kayit: list[str] = []
    asil = m._put_text

    def _casus(img, text, *a, **k):
        kayit.append(str(text))
        return asil(img, text, *a, **k)

    monkeypatch.setattr(m, "_put_text", _casus)
    img = np.full((480, 640, 3), 90, np.uint8)
    kontur = np.array([[[200, 150]], [[440, 150]], [[440, 330]], [[200, 330]]], np.int32)
    if modul_adi == _FANTOM:
        from types import SimpleNamespace

        ph = SimpleNamespace(contour_px=kontur, centroid_px=(320.0, 240.0), area_px=43200)
        m.panel_02_phantom(img, [ph], "aruco_pnp" if not mm_per_px else "coil_ring", mm_per_px, lang=lang)
    else:
        from types import SimpleNamespace

        det = SimpleNamespace(contour=kontur, bbox_xyxy=(200, 150, 440, 330), centroid_px=(320.0, 240.0), conf=0.9)
        well = SimpleNamespace(organ_id=0, well_id="A1")
        m.panel_02_yolo(img, [det], [well], "aruco_pnp" if not mm_per_px else "petri_diameter", mm_per_px, lang=lang)
    return kayit


@pytest.mark.parametrize("modul_adi", [_FANTOM, _PETRI])
@pytest.mark.parametrize("lang", ["tr", "en"])
@pytest.mark.parametrize("olcek", [0.0, None, float("nan")])
def test_KRITIK_ArUco_kipinde_panel_SIFIR_olcek_YAZMAZ(monkeypatch, modul_adi, lang, olcek):
    metinler = _kayitli_metinler(monkeypatch, modul_adi, olcek, lang)
    sifir = [t for t in metinler if "mm/px" in t and any(s in t for s in ("0.000", "nan", "None"))]
    assert not sifir, f"{modul_adi.split('.')[-2]} [{lang}] ölçek={olcek}: panel ölçülmüş-sıfır ölçek yazıyor: {sifir}"
    assert BEKLENEN_YOK[lang] in metinler, (
        f"{modul_adi.split('.')[-2]} [{lang}]: perspektif kipinin notu panelde yok ({BEKLENEN_YOK[lang]!r}); yazılanlar: {metinler}"
    )


@pytest.mark.parametrize("modul_adi", [_FANTOM, _PETRI])
@pytest.mark.parametrize("lang,beklenen", [("tr", "Olcek: 0.315 mm/px"), ("en", "Scale: 0.315 mm/px")])
def test_KARSIT_KANIT_pozitif_olcek_AYNEN_yazilir(monkeypatch, modul_adi, lang, beklenen):
    metinler = _kayitli_metinler(monkeypatch, modul_adi, 0.3146, lang)
    assert beklenen in metinler, f"pozitif ölçek yazılmıyor: {metinler}"
    assert BEKLENEN_YOK[lang] not in metinler
