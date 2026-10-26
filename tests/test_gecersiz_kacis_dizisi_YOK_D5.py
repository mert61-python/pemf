# -*- coding: utf-8 -*-
"""D5 devri (DUZELTME-D4A-INCELEME §10 #4) — izlenen hiçbir Python dosyasında GEÇERSİZ KAÇIŞ DİZİSİ (`"\\P"`, `"\\s"` …) yok.

Python 3.10/3.11 bunu `DeprecationWarning`, 3.12+ `SyntaxWarning` olarak bildirir; ileride sözdizimi hatası olacak. Kapı yokken uyarılar
birikti (D4A incelemesi 3 test dosyası saydı; k5 HEAD `5bc99be1`'de 4 test + `build_tools/_static_password.example.py`). Onarım değeri
korur (ters bölü ikilendi — `ast.dump` önce = sonra). Kapı `git ls-files` ile İZLENEN tüm `.py` dosyalarını DERLER (çalıştırmaz).
"""

from __future__ import annotations

import subprocess
import warnings
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
_ASGARI_DOSYA = (
    1000  # vakum bekçisi: taranan izlenen .py sayısı bunun altına düşerse tarama kırılmıştır (HEAD'de ~2 000)
)


def _izlenen_py() -> list[Path]:
    cikti = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "-z", "--", "*.py"], cwd=KOK, capture_output=True, check=True
    ).stdout
    return [KOK / ad for ad in cikti.decode("utf-8").split("\0") if ad]


def _gecersiz_kacislar(kaynak: bytes, ad: str) -> list[str]:
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        compile(kaynak, ad, "exec", dont_inherit=True)
    return [f"{ad}:{x.lineno} {x.message}" for x in w if "invalid escape sequence" in str(x.message)]


def test_KARSIT_tarayici_gecersiz_kacisi_GORUR():
    kotu = ("x = " + '"' + "a" + chr(92) + "P" + '"' + "\n").encode()
    iyi = ("x = " + '"' + "a" + chr(92) + chr(92) + "P" + '"' + "\n").encode()
    assert _gecersiz_kacislar(kotu, "kotu.py"), "tarayıcı geçersiz kaçışı görmüyor (kapı kör)"
    assert _gecersiz_kacislar(iyi, "iyi.py") == []


def test_KRITIK_izlenen_py_dosyalarinda_GECERSIZ_KACIS_YOK():
    dosyalar = [p for p in _izlenen_py() if p.is_file()]
    assert len(dosyalar) >= _ASGARI_DOSYA, f"vakum: yalnız {len(dosyalar)} izlenen .py tarandı"
    bulunan = []
    for p in dosyalar:
        try:
            bulunan += _gecersiz_kacislar(p.read_bytes(), str(p.relative_to(KOK)))
        except SyntaxError as e:  # sözdizimi bozuk dosya ayrı kapıların konusu; burada gizlenmez
            bulunan.append(f"{p.relative_to(KOK)}: SyntaxError {e}")
    assert not bulunan, (
        "geçersiz kaçış dizisi (ters bölüyü ikile ya da ham dize kullan; değer AYNI kalmalı):\n" + "\n".join(bulunan)
    )
