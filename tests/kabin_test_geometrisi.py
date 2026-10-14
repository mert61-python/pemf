# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Test aparatı (TD4, 2026-10-14): MANTIK kapıları için SABİT test kabini — 2026-09-08 düzeni (65 × 50 × 50 cm).

NEDEN: ürün kabin YAML'ı artık SAHA ölçüsünü taşır (tezgâh Oturum 13: iç 57 × 34 × 32, kamera ve işaret YENİDEN yerleşecek →
konum alanları yine değişecek). Kabin sınırı / koordinat dönüşümü / kıskaç kapıları bant ve mutantlarını belirli bir geometride
ölçer: ör. Y49'un hedeflediği `yari = min(300, extent/2)` mutantı yarı genişlik 285 mm'de EŞDEĞER olur (kapı körleşir), i7 F-9
"kabin içi ama eğitim dışı x ∈ (300, 325]" bandı yeni kabinde hiç yoktur. Bu testler geometriyi buradan alır; ÜRÜN geometrisi
`tests/test_kabin_config_65x50x50.py` + `tests/test_TD4_kabin_ISARET_TERS_tavan_up_cabin_ve_intrinsics.py` ile denetlenir.
"""

from __future__ import annotations

#: 2026-09-08 sahip ölçüsü (kabin #6, `git show 2d28ad05:ai_hub/inference_cat_organ/cabin_config_example.yaml`).
SABIT = {
    "cabin_extent_cm": [65.0, 50.0, 50.0],
    "qr_to_origin_cm": [21.5, -14.0, -25.0],
    "fixed_position_cm": [32.5, -25.0, -25.0],
    "to_marker_cm": 83.3,
    "to_origin_cm": 48.0,
    "real_cm": 15.0,
}


def sabit_kabin(cfg):
    """`ai_hub.cv_ortak.cabin_config.CabinConfig` → sabit test kabinine çevir (yerinde) ve döndür."""
    cfg.geometry.cabin_extent_cm = list(SABIT["cabin_extent_cm"])
    cfg.geometry.qr_to_origin_cm = list(SABIT["qr_to_origin_cm"])
    cfg.camera.fixed_position_cm = list(SABIT["fixed_position_cm"])
    cfg.camera.to_marker_cm = SABIT["to_marker_cm"]
    cfg.camera.to_origin_cm = SABIT["to_origin_cm"]
    cfg.aruco.real_cm = SABIT["real_cm"]
    return cfg


def sabit_kabin_dict(cfg: dict) -> dict:
    """Kedi (`ai_hub.inference_cat_organ.lib.cabin_config`) sözlüğü → sabit test kabini (KOPYA)."""
    d = dict(cfg)
    d["geometry"] = dict(
        d.get("geometry") or {},
        cabin_extent_cm=list(SABIT["cabin_extent_cm"]),
        qr_to_origin_cm=list(SABIT["qr_to_origin_cm"]),
    )
    d["camera"] = dict(
        d.get("camera") or {},
        fixed_position_cm=list(SABIT["fixed_position_cm"]),
        to_marker_cm=SABIT["to_marker_cm"],
        to_origin_cm=SABIT["to_origin_cm"],
    )
    d["aruco"] = dict(d.get("aruco") or {}, real_cm=SABIT["real_cm"])
    return d


def kedi_yukleyicisini_sabitle(monkeypatch) -> None:
    """Ürünün kedi kabin yükleyicisi (`cc.load_cabin_config`, çağrı anında modülden okunur) sabit test kabinini döndürsün."""
    from ai_hub.inference_cat_organ.lib import cabin_config as cc

    gercek = cc.load_cabin_config
    monkeypatch.setattr(cc, "load_cabin_config", lambda *a, **k: sabit_kabin_dict(gercek(*a, **k)))
