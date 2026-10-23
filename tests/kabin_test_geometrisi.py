# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Test aparatı (TD4, 2026-10-14): MANTIK kapıları için SABİT test kabini — 2026-09-08 düzeni (65 × 50 × 50 cm).

NEDEN: ürün kabin YAML'ı SAHA ölçüsünü taşır (tezgâh Oturum 13: iç 57 × 34 × 32 → T2B 2026-10-23: 55,5 × 35 × 40,5, işaret
TABANDA, kamera tavanda; yerleşim yine değişebilir). T3 (2026-10-23): yönelim alanları (işaret normali, `up_cabin`, hedef düzlemi) da
sabitlenir — işaret tabana inince ürün YAML'ından gelen normal / up bu düzenin arka duvar işaretiyle ÇELİŞİYORDU (D1.100 "kameranın
arkasında kesişen ışın" aparatı pikseli bulamadı, marker→kabin rotasyon kapısı taban dönüşümünü gördü). Kabin sınırı / koordinat dönüşümü / kıskaç kapıları bant ve mutantlarını belirli bir geometride
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
    # T3: yönelim (2026-09-08 düzeni = arka duvar işareti, yüzü öne; üst kenarı tavana; hedef düzlemi Y = -20 cm).
    "normal_axis_in_cabin": "-Z",
    "up_cabin": [0.0, 1.0, 0.0],
    "hedef_duzlem_eksen": "Y",
    "hedef_duzlem_cm": -20.0,
}

#: TD4 DUVAR DÜZENİ (tezgâh Oturum 13, 2026-10-14 saha ölçüsü; T2B'ye dek ürün YAML'ıydı): arka duvar işareti — `isaret_ters_mi`
#: (ters kâğıt) mekanizması YALNIZ duvar işaretinde karar verir; ürün kabini T2B'den beri TABAN işareti (karar vermez — T2B B3).
TD4_DUVAR = {
    "cabin_extent_cm": [57.0, 34.0, 32.0],
    "qr_to_origin_cm": [1.5, -1.5, -16.0],
    "fixed_position_cm": [-20.5, -15.0, -8.0],
    "to_marker_cm": 34.8,
    "to_origin_cm": 26.6,
    "real_cm": 10.0,
    "normal_axis_in_cabin": "-Z",
    "up_cabin": [0.0, 1.0, 0.0],
    "hedef_duzlem_eksen": "Y",
    "hedef_duzlem_cm": -20.0,
}


def _uygula(cfg, g):
    cfg.geometry.cabin_extent_cm = list(g["cabin_extent_cm"])
    cfg.geometry.qr_to_origin_cm = list(g["qr_to_origin_cm"])
    cfg.camera.fixed_position_cm = list(g["fixed_position_cm"])
    cfg.camera.to_marker_cm = g["to_marker_cm"]
    cfg.camera.to_origin_cm = g["to_origin_cm"]
    cfg.camera.up_cabin = list(g["up_cabin"])
    cfg.aruco.real_cm = g["real_cm"]
    cfg.aruco.normal_axis_in_cabin = g["normal_axis_in_cabin"]
    cfg.phantom_plate.hedef_duzlem_eksen = g["hedef_duzlem_eksen"]
    cfg.phantom_plate.hedef_duzlem_cm = g["hedef_duzlem_cm"]
    return cfg


def sabit_kabin(cfg):
    """`ai_hub.cv_ortak.cabin_config.CabinConfig` → sabit test kabinine çevir (yerinde) ve döndür."""
    return _uygula(cfg, SABIT)


def td4_duvar_kabini(cfg):
    """`CabinConfig` → TD4 duvar düzenine çevir (yerinde) ve döndür (ters işaret kapıları)."""
    return _uygula(cfg, TD4_DUVAR)


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
        up_cabin=list(SABIT["up_cabin"]),
    )
    d["aruco"] = dict(
        d.get("aruco") or {}, real_cm=SABIT["real_cm"], normal_axis_in_cabin=SABIT["normal_axis_in_cabin"]
    )
    return d


def kedi_yukleyicisini_sabitle(monkeypatch) -> None:
    """Ürünün kedi kabin yükleyicisi (`cc.load_cabin_config`, çağrı anında modülden okunur) sabit test kabinini döndürsün."""
    from ai_hub.inference_cat_organ.lib import cabin_config as cc

    gercek = cc.load_cabin_config
    monkeypatch.setattr(cc, "load_cabin_config", lambda *a, **k: sabit_kabin_dict(gercek(*a, **k)))
