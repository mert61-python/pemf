# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.21 (B-10.4) — tests/ altında AYNI ADLI iki test işlevi YOK (ikincisi ilkini sessizce siler).

ÖLÇÜLEN KUSUR: `test_olculen_yogunluk.py` iki `test_KRITIK_seans_YOKKEN_olcum_YAZILMAZ` tanımlıyordu (:51 ve :206). Python modül
ad alanında ikinci tanım ilkini EZER → pytest yalnız sonuncuyu toplar; ilk test (iki argümanlı çağrı + `ls` fikstürü) HİÇ koşmamıştı.
ruff'ın F811'i (yeniden tanım) `tests/*` için `pyproject.toml`da susturulmuş (fikstür gölgelemesi yüzünden) — bu yüzden kural AST
kapısıyla ayrıca kilitlenir: modül düzeyinde ve sınıf gövdesinde yinelenen `test*` adı → KIRMIZI.
"""

from __future__ import annotations

import ast
import collections
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]


def _test_dosyalari() -> list[Path]:
    """pytest'in topladığı TÜM test modülleri (`test_*.py`, alt dizinler dahil; izlenmeyen yeni dosya da)."""
    return sorted(p for p in (_KOK / "tests").rglob("test_*.py") if "__pycache__" not in p.parts)


def yinelenen_test_adlari(kaynak: str, ad: str = "<kaynak>") -> list[str]:
    """Modül gövdesinde ve her sınıf gövdesinde birden çok tanımlanan `test*` işlevleri."""
    agac = ast.parse(kaynak)
    sonuc = []

    def tara(govde, kapsam: str):
        sayac = collections.Counter(
            d.name
            for d in govde
            if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name.startswith("test")
        )
        sonuc.extend(f"{ad}:{kapsam}{n} ×{k}" for n, k in sorted(sayac.items()) if k > 1)
        for d in govde:
            if isinstance(d, ast.ClassDef):
                tara(d.body, f"{kapsam}{d.name}.")

    tara(agac.body, "")
    return sonuc


def test_KRITIK_D5_21_tests_altinda_YINELENEN_test_adi_YOK():
    dosyalar = _test_dosyalari()
    assert len(dosyalar) >= 500, f"VAKUM: yalniz {len(dosyalar)} test dosyasi tarandi"
    yinelenen, cozulemeyen = [], []
    for p in dosyalar:
        try:
            yinelenen += yinelenen_test_adlari(p.read_text(encoding="utf-8"), p.relative_to(_KOK).as_posix())
        except (SyntaxError, UnicodeDecodeError) as e:
            cozulemeyen.append(f"{p.relative_to(_KOK).as_posix()}: {type(e).__name__}")
    assert not cozulemeyen, f"ayristirilamayan test dosyasi (olculmedi): {cozulemeyen}"
    assert not yinelenen, f"yinelenen test adi — ikinci tanim ilkini SESSIZCE siler, ilk test hic kosmaz: {yinelenen}"


@pytest.mark.parametrize(
    ("kaynak", "beklenen"),
    [
        ("def test_a():\n    pass\n\n\ndef test_a(x):\n    pass\n", 1),
        ("async def test_a():\n    pass\n\n\ndef test_a():\n    pass\n", 1),
        ("class TestX:\n    def test_a(self):\n        pass\n\n    def test_a(self):\n        pass\n", 1),
        ("def test_a():\n    pass\n\n\nclass TestX:\n    def test_a(self):\n        pass\n", 0),
        ("def yardimci():\n    pass\n\n\ndef yardimci():\n    pass\n", 0),
        ("# def test_a(): yorum\ndef test_a():\n    pass\n", 0),
    ],
    ids=["modul", "async_karisik", "sinif_ici", "farkli_kapsam", "test_disi_ad", "yorum"],
)
def test_KARSIT_KANIT_D5_21_tarayici(kaynak, beklenen):
    assert len(yinelenen_test_adlari(kaynak)) == beklenen
