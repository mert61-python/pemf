# -*- coding: utf-8 -*-
"""D6.41 (B-11.12 · Y27) — F5 (`tools/` üçe bölünmesi) iki belgede TEK anlamda: İPTAL (sahip kararı Y27).

ÖLÇÜLEN DURUM (HEAD ebf1c3fe, 2026-10-28):
  · `docs/ARIZA-LISTESI.md:206` "~~F5 `tools/`~~ | ✅ KAPANDI 2026-09-21" — oysa `tools/build`, `tools/gates`, `tools/ops` YOK;
    o gün kapatılan iş F5 değil, belge bağlantı onarımıydı (aynı satırın gövdesi bunu söylüyor).
  · `docs/KLASOR-YAPISI-PLANI.md:6` "KALAN: … F5 (`tools/` üçe bölünmesi)" ve `:175` faz tablosunda F5 açık.
  → İki belge aynı fazı biri KAPANDI, öteki KALAN diyordu. Sahip kararı Y27: "F5 İPTAL; plan 'iptal' der, 'KAPANDI' satırı düzeltilir".

Kapı faz durumunu iki belgeden ÇAPRAZ okur ve F5 için gerçek dizin durumunu ölçer. Üstü çizili (`~~…~~`) metin tarihçedir, sayılmaz.
"""

from __future__ import annotations

import re
from pathlib import Path

from utils.path_utils import kaynak_kokunu_bul

KOK = Path(kaynak_kokunu_bul(__file__))
ARIZA = KOK / "docs" / "ARIZA-LISTESI.md"
PLAN = KOK / "docs" / "KLASOR-YAPISI-PLANI.md"
F5_DIZINLERI = ("tools/build", "tools/gates", "tools/ops")


def _cizgisiz(md: str) -> str:
    return re.sub(r"~~.*?~~", " ", md, flags=re.S)


def _oku(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _ariza_faz_satiri(faz: str) -> str:
    s = [x for x in _oku(ARIZA).splitlines() if re.match(r"^>\s*\|\s*(~~)?" + faz + r"\b", x)]
    assert len(s) == 1, f"ARIZA-LISTESI '{faz}' faz satırı tek olmalı ({len(s)})"
    return s[0]


def _plan_kalan() -> str:
    m = re.search(r"\*\*KALAN:\*\*(.*?)(\n>?\s*\n|\n[^>])", _oku(PLAN), re.S)
    assert m, "KLASOR-YAPISI-PLANI başlık 'KALAN:' paragrafı bulunamadı"
    return _cizgisiz(m.group(1))


def test_F5_dizinleri_YOK_olculdu():
    var = [d for d in F5_DIZINLERI if (KOK / d).exists()]
    assert not var, f"F5 dizinleri VAR ({var}) — F5 uygulanmış; Y27 (İPTAL) anlatımını bilinçli güncelleyin"


def test_ARIZA_F5_KAPANDI_demez_IPTAL_Y27_der():
    s = _cizgisiz(_ariza_faz_satiri("F5"))
    assert not re.search(r"KAPANDI|BİTTİ", s), "ARIZA-LISTESI F5: dizinler yokken 'KAPANDI' (çizgisiz) — Y27: F5 İPTAL"
    assert "İPTAL" in s and "Y27" in s, "ARIZA-LISTESI F5 satırı 'İPTAL' ve 'Y27' anmalı"


def test_KLASOR_PLANI_F5_KALAN_degil_IPTAL():
    assert "F5" not in _plan_kalan(), "KLASOR-YAPISI-PLANI 'KALAN:' F5'i hâlâ sayıyor — Y27: İPTAL"
    satir = [x for x in _oku(PLAN).splitlines() if re.match(r"^\|\s*(~~)?\*\*F5\*\*", x)]
    assert len(satir) == 1 and "İPTAL" in satir[0] and "Y27" in satir[0], (
        f"faz tablosu F5 satırı 'İPTAL — Y27' demeli: {satir}"
    )


def test_capraz_faz_durumu_TEK_anlam():
    """Planın 'KALAN' saydığı faz ARIZA'da çizgisiz KAPANDI/BİTTİ olamaz; ARIZA'da BİTTİ olan faz KALAN'da olamaz."""
    kalan = set(re.findall(r"\bF(\d)\b", _plan_kalan()))
    celiski = []
    for n in ("2", "3", "4", "5", "6"):
        satirlar = [x for x in _oku(ARIZA).splitlines() if re.match(r"^>\s*\|\s*(~~)?F" + n + r"\b", x)]
        for s in satirlar:
            bitti = bool(re.search(r"KAPANDI|BİTTİ", _cizgisiz(s)))
            if bitti and n in kalan:
                celiski.append(f"F{n}: ARIZA bitti diyor, plan KALAN diyor")
    assert not celiski, "; ".join(celiski)
