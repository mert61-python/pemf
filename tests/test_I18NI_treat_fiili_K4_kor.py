# -*- coding: utf-8 -*-
"""I18NI-A1.6 — "Seans → Session, treatment / therapy YOK" (K-4, 2026-08-08 "tedavi → seans" kararı) EN'de fiil biçimiyle delinmiş:
site ana sayfası "Klinik Güvenlik" kartı TR "seans, UYGULANACAK bölge güvenle tespit edilmeden başlamaz" → EN "until the area to be TREATED has
been safely detected" (ürün TR'de tedavi iddiası yapmıyor; EN yapıyor). K-4 yasak deseni `\\btreatment|\\btherap` yalnız ADI yakalar —
"treat / treated / treating" kör (HEAD'de K-4 YEŞİL).

Kapı: (1) hiçbir yüzeyin EN değerinde `treat` fiili, TR'sinde "tedavi / terapi" yokken geçmez; (2) K-4'ün kendi `ihlaller` işlevi fiil biçimini
YAKALAR (sözlük deseni genişletilince). Bugün ikisi KIRMIZI.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
for p in (KOK, KOK / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from scripts.i18n import ortak  # noqa: E402

FIIL = re.compile(r"\btreat(?:s|ed|ing)?\b", re.I)
TR_TEDAVI = re.compile(r"tedavi|terapi", re.I)


def test_EN_treat_fiili_TR_tedavi_yokken_gecmez():
    sorun = []
    for yuzey in ortak.KATALOGLAR:
        tr = ortak.duzlestir(ortak.katalog_yukle(yuzey, "tr"))
        en = ortak.duzlestir(ortak.katalog_yukle(yuzey, "en"))
        for k, v in en.items():
            if FIIL.search(str(v)) and not TR_TEDAVI.search(str(tr.get(k, ""))):
                sorun.append(f"{yuzey}:{k}: TR {tr.get(k)!r} → EN {v!r}")
    assert not sorun, "EN 'treat' fiili (TR'de tedavi yok):\n" + "\n".join(sorun)


def test_K4_sozlugu_treat_fiilini_YAKALAR():
    import test_i18n_terim_K4 as k4

    sozluk = json.loads((KOK / "i18n" / "terimler.json").read_text(encoding="utf-8"))
    tr = {"a": "Acil durdurma düğmesi ve hedef kontrolü: seans, uygulanacak bölge güvenle tespit edilmeden başlamaz."}
    en = {
        "a": "Emergency stop button and target check: a session does not start until the area to be treated has been safely detected."
    }
    s = "\n".join(k4.ihlaller(tr, en, "site", sozluk))
    assert "site:a" in s, "K-4 'treated' (TR'de tedavi yok) biçimini YAKALAMIYOR"
