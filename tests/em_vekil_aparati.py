# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.56 (B-10.106) aparatı — canlı E-alanı vekil modeli yüklenemediğinde ATLA ya da DÜŞ.

Eskiden kapılar `ef._predictor(...) is None` görünce "ağırlık yok" diye ATLIYORDU; oysa `efield_live._predictor` HER istisnayı
(kırık import, yanlış sınıf adı, kod hatası) aynı `None`a çeviriyordu → ağırlıklar kuruluyken ürün hatası atlamaya gizleniyordu
(mutant `PetriPredictorX` bugün SKIP). Artık neden ürünün kendisinden okunur (`efield_live.vekil_yuklenemedi_nedeni`):
  · "agirlik_yok" / "paket_yok" → ortam eksiği: ATLA (`PEMF_CAPRAZ_KAYNAK_ZORUNLU=1` → DÜŞ),
  · "hata" (ya da neden kaydı yok) → ürün hatası: DÜŞ.
"""

from __future__ import annotations

import capraz
import pytest


def vekil_gerekli(ef, *modeller) -> None:
    """`modeller`in (None = varsayılan fantom) vekili yüklenemediyse nedene göre atla ya da düş.

    ⚠️ ÖNCE HEPSİ denenir, sonra karar: ilk eksikte atlamak sonraki modelin ürün hatasını gizlerdi (ölçüldü — ağırlıksız
    ortamda fantom "agirlik_yok" ile atlarken petri'nin kırık import'u hiç sorulmuyordu)."""
    eksik = []
    for model in modeller or (None,):
        if ef._predictor(model) is None:
            eksik.append((model or "fantom", ef.vekil_yuklenemedi_nedeni(model)))
    hatali = [(m, n) for m, n in eksik if n not in ("agirlik_yok", "paket_yok")]
    if hatali:
        pytest.fail(
            f"EM vekil modeli ORTAM EKSİĞİNDEN DEĞİL yüklenemedi {hatali} — ürün hatası atlamaya gizlenmez "
            "(bkz. günlükteki 'E-alanı vekil modeli yüklenemedi' zinciri)"
        )
    if eksik:
        if capraz.ZORUNLU:
            pytest.fail(f"PEMF_CAPRAZ_KAYNAK_ZORUNLU=1 ama EM vekil modeli yok: {eksik}")
        pytest.skip(f"EM vekil ağırlıkları / paketi bu ortamda yok: {eksik}")
