# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""1-C §9 #10 O-1 (D1.100 kapsamı) — kedi-organ hattında perspektif çözümü YOKKEN kabin koordinatı ÜRETİLMEZ.

KUSUR (1-C i7 O-1; bu kapı ölçer): `estimate_organs_pnp` perspektif (marker pozu + kedi PnP) başarısız olup ArUco yine de
bulunduğunda "zayıf-perspektif yedek yolu"na düşüyordu: `coord_cabin_cm = (piksel − QR merkezi) × cm/px + qr_to_origin`,
derinlik = gövde modelinin göreli z'si. Görüntü eksenleri kabin eksenleri sayılıyor (görüntüde y AŞAĞI), marker→orijin
ofseti ÇIKARILACAĞINA EKLENİYORDU → çerçeve doğrulanamaz; buna rağmen `calibrated=True` ve güven TAVANSIZ.

DÜZELTME BEKLENTİSİ: perspektif kabin çözümü yoksa organ KALİBRASYONSUZ (`calibrated=False`, mevcut tek formülün 0,25
tavanı, kabin koordinatı yok) → AI Pro hedefi sürülemez. ⚠️ Gerçek kabinde doğrulama TEZGÂHTA (Oturum 13) — ölçüm
uydurulmaz. YÖNTEM: D1.E08'in GERÇEK öngörücü aparatı (yalnız ONNX koşucuları sahte); perspektif hatası yamayla verilir.
"""

from __future__ import annotations

import pytest
from test_kedi_organ_KABIN_yapilandirmasi_YUKLENEMEZSE_kalibrasyonsuz import IMG, ongorucu  # noqa: F401 — aparat


def _perspektifi_boz(monkeypatch):
    from ai_hub.inference_cat_organ.lib import pipeline as lp

    monkeypatch.setattr(lp, "_run_perspective_pipeline", lambda **k: {"error": "marker_detect: test (perspektif yok)"})


def test_KRITIK_O1_perspektif_YOKKEN_kabin_koordinati_YOK_kalibrasyonsuz_tavanli(ongorucu, monkeypatch):
    p = ongorucu("var")
    _perspektifi_boz(monkeypatch)
    r = p.predict(IMG, render=False)
    org = r.get("organs") or {}
    assert org, "aparat: öngörücü organ üretmedi"
    assert (r.get("kabin_yapilandirmasi") or {}).get("yuklendi") is True, "aparat: YAML yüklenmeliydi"
    sahte = {oid: (o.get("coord_cabin_cm"), o.get("cabin_origin")) for oid, o in org.items() if o.get("coord_cabin_cm")}
    assert not sahte, f"perspektif yokken doğrulanamayan çerçeveden kabin koordinatı üretildi: {sahte}"
    assert {o.get("calibrated") for o in org.values()} == {False}, "perspektif yokken organ 'kalibre' sayıldı"
    rels = [float(o.get("reliability") or 0.0) for o in org.values()]
    assert max(rels) <= 0.25 + 1e-9, f"kalibrasyonsuz güven tavanı uygulanmadı: max {max(rels):.3f}"


def test_KRITIK_O1_AI_Pro_hedefi_perspektif_YOKKEN_SURULEMEZ(ongorucu, monkeypatch):
    from servers import ai_router as air

    p = ongorucu("var")
    _perspektifi_boz(monkeypatch)
    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: p)
    import cv2

    kare = cv2.imread(IMG)
    sonuc = air._localize_organ_cpu(kare, 2)
    assert sonuc[0] is False, f"perspektif yokken AI Pro hedefi SÜRÜLEBİLİR döndü: {sonuc[:5]}"


def test_KARSIT_O1_perspektif_VARKEN_kalibre_ve_kaynak_PERSPEKTIF(ongorucu):
    p = ongorucu("var")
    r = p.predict(IMG, render=False)
    org = r.get("organs") or {}
    assert {o.get("calibrated") for o in org.values()} == {True}, "aparat: perspektifli görüntü kalibre olmalı"
    kaynak = {o.get("cabin_origin") for o in org.values()}
    assert kaynak == {"perspective_solvePnP"}, f"kabin koordinatı perspektiften gelmiyor: {kaynak}"
