# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""EM doz öngörücülerinin (fantom, petri, kedi `em_kedi`) ortak GİRDİ/ÇIKTI denetimi — D1.E07 · İG-5.80 · İG-5.15.

NEDEN: öngörücüler NaN/None girdiyi reddetmiyordu; `np.asarray(None, float)` NaN olur, ölçekleyiciden geçen NaN ONNX'te
"makul görünen" sonlu bir D'ye dönüşüyor ve bobin bildirimsiz sürülüyordu (ölçüldü). Bozuk ölçekleyici (ortalama NaN)
aynı sonucu veriyordu. Bu bir doz KISKACI değildir (Ö.4-Y9): geçersiz girdi reddedilir, çağıran uç 422 döner.

Yaprak modül: yalnız numpy. `SonluOlmayanGirdi` `ValueError`dır → mevcut `except ValueError` yolları aynen yakalar.
"""

from __future__ import annotations

import numpy as np


class SonluOlmayanGirdi(ValueError):
    """Girdi ya da model çıktısı sonlu değil (NaN / ±inf / None) — uçlar 422'ye eşler."""


def sonlu_dogrula(**alanlar) -> None:
    """Her alan (skaler ya da dizi) sonlu sayı olmalı; değilse `SonluOlmayanGirdi` (hangi alan olduğu söylenir)."""
    hatali = []
    for ad, deger in alanlar.items():
        if deger is None:
            hatali.append(ad)
            continue
        try:
            dizi = np.asarray(deger, dtype=np.float64)
        except (TypeError, ValueError):
            hatali.append(ad)
            continue
        if dizi.size == 0 or not np.all(np.isfinite(dizi)):
            hatali.append(ad)
    if hatali:
        raise SonluOlmayanGirdi(f"sonlu olmayan girdi: {', '.join(hatali)}")


def sonlu_dizi_dogrula(ne: str, dizi) -> None:
    """Ara/çıktı dizisi (ölçeklenmiş girdi, model çıktısı) sonlu değilse `SonluOlmayanGirdi`."""
    if not np.all(np.isfinite(np.asarray(dizi, dtype=np.float64))):
        raise SonluOlmayanGirdi(f"sonlu olmayan {ne}")
