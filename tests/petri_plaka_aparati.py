# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODD B-5 test aparatı: ODAK plaka ızgarasına OTURAN sahte petri adayları (24 kuyu, A1 istenen noktada).

Koşulsuz kipte plaka artık ODAK ızgara oturtmasıyla doğrulanır (`PetriSaglayici._plaka_engeli`); tek sahte kuyuyla "koşulsuz kip
sürer" diyen kapılar gerçek bir plaka vermelidir. Konumlar `test_ODK_odak_alan_ve_oneri._plaka` ile aynı geometriden (ölçüm
çerçevesinde merkez + yön, aralık 19,3 mm) → backend çerçevesi; bütün plaka KATI kaydırılarak A1 istenen noktaya getirilir (oturtma
korunur). A1 sonlu değilse (NaN / inf kapıları) A1 o değeri taşır, öteki kuyular varsayılan konumda kalır (ızgara yine oturur)."""

from __future__ import annotations

import math


def plaka_adaylari(a1=(10.0, 20.0, 30.0), onek: str = "Kuyu", eksik=()) -> list:
    from test_ODK_odak_alan_ve_oneri import _plaka

    kuyular = _plaka()
    p_a1 = kuyular[0]["P"]
    sonlu = all(isinstance(v, (int, float)) and math.isfinite(v) for v in a1)
    kayma = [a1[i] - p_a1[i] for i in range(3)] if sonlu else [0.0, 0.0, 0.0]
    out = []
    for k in kuyular:
        if k["etiket"] in eksik:
            continue
        ilk = k["etiket"] == "A1"
        P = list(a1) if (ilk and not sonlu) else [k["P"][i] + kayma[i] for i in range(3)]
        u, v = k["px"]
        out.append(
            {
                "px": (float(u), float(v)),
                "bbox": (u - 10, v - 10, u + 10, v + 10),
                "x": P[0],
                "y": P[1],
                "z": P[2],
                "organ_id": 1,
                "reliability": 0.9,
                "oncelik": 1.0 if ilk else 0.5,
                "label": f"{onek} {k['etiket']}",
                "id": 0,
            }
        )
    return out
