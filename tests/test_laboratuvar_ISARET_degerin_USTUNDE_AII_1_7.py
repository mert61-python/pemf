# -*- coding: utf-8 -*-
"""AII-1.7 (AI incelemesi, A1) — C8 kapısının "işaret değerin 25 satır içinde" ölçütü işareti BAŞKA değere taşımayı görmüyor (TOTOLOJİ, düşük).

ÖLÇÜLDÜ (`amut.sh a C8K …`): fantom v3 YAML'ında #2 (CST eksen işareti) uyarısı `cst_box:` bloğundan alınıp 13 satır yukarıya,
`layout_file:` değerinin ÜSTÜNE taşındı → `axis_u:` hâlâ 25 satır içinde olduğu için C8 kapısı 11/11 YEŞİL (işaret artık yanlış
değeri açıklıyor; bir sonraki kişi `layout_file`'ı "laboratuvar varsayımı", `axis_u`'yu "ölçülmüş" okur). #3'ü değerin ALTINA taşımak
kırmızı (karşıt). Kural: işaret yorum bloğundan sonraki İLK yorum-dışı satır ya anahtarın kendisi ya da anahtarı içeren bölüm başlığı.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
PETRI_YAML = KOK / "ai_hub" / "inference_petri_dish" / "petri_cv_v2" / "cabin_config_v2.yaml"
FANTOM_YAML = KOK / "ai_hub" / "inference_em_fantom" / "phantom_cv_v3" / "cabin_config_v3.yaml"
#: (madde, YAML, işaretin AÇIKLADIĞI anahtar) — beklenenler burada sabit (kaynaktan okunmaz).
MADDELER = [
    ("#1", PETRI_YAML, "a1_cabin_mm"),
    ("#2", FANTOM_YAML, "axis_u"),
    ("#3", FANTOM_YAML, "diameter_mm"),
    ("#4", PETRI_YAML, "frac"),
    ("#5", PETRI_YAML, "a1_corner"),
]


def _girinti(s: str) -> int:
    return len(s) - len(s.lstrip(" "))


@pytest.mark.parametrize("madde,yol,anahtar", MADDELER, ids=[m[0] for m in MADDELER])
def test_KRITIK_isaret_ACIKLADIGI_degerin_hemen_ustunde(madde, yol, anahtar):
    satirlar = yol.read_text(encoding="utf-8").splitlines()
    isaret = [n for n, s in enumerate(satirlar) if "LABORATUVAR" in s and f"§4 {madde}" in s]
    assert len(isaret) == 1, f"{yol.name}: §4 {madde} işareti {len(isaret)} kez (tam 1 olmalı)"
    i = isaret[0] + 1
    while i < len(satirlar) and satirlar[i].strip().startswith("#"):
        i += 1  # işaretin devam eden yorum satırları
    assert i < len(satirlar), "işaretten sonra değer yok"
    ilk = satirlar[i]
    if re.match(rf"^\s*{anahtar}:", ilk):
        return  # işaret doğrudan değerin üstünde
    # ya da işaret, anahtarı içeren bölüm başlığının üstünde (ör. `cst_box:` → `axis_u:`)
    assert re.match(r"^\s*[A-Za-z_]+:\s*(#.*)?$", ilk), (
        f"§4 {madde} işaretinden sonraki ilk satır `{ilk.strip()}` — `{anahtar}` değil ve bölüm başlığı değil (işaret başka değere taşınmış)"
    )
    g = _girinti(ilk)
    blok = []
    for s in satirlar[i + 1 :]:
        if s.strip() and not s.strip().startswith("#") and _girinti(s) <= g:
            break
        blok.append(s)
    assert any(re.match(rf"^\s*{anahtar}:", s) for s in blok), (
        f"§4 {madde} işareti `{ilk.strip()}` bölümünün üstünde ama `{anahtar}` o bölümde değil"
    )
