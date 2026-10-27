# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.17 (B-10.84) — `test_pdf_turkce_karakter.py`'nin fitz'e BAĞLI OLMAYAN kapıları PyMuPDF'siz ortamda (CI) da koşar.

ÖLÇÜLEN KÖRLÜK: dosyanın başındaki modül düzeyi `pytest.importorskip("fitz")` fitz'siz CI'da dosyanın TAMAMINI atlatıyordu →
stil sayfası (Type1 kalmadı), dört yüz, yedek yüz ve kaynak çıpası kapıları hiç koşmuyordu; `_setup_custom_styles` sonundaki
`self._stilleri_unicode_yap()` çağrısını silen mutant (sahibin bildirdiği siyah kutucuk arızası) orada YEŞİLDİ.
Bu kapı AYRI dosyadadır: modül düzeyindeki bir `pytestmark = skipif(...)` ölçülen dosyayla birlikte kendisini de atlatamasın.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

_HEDEF = Path(__file__).resolve().parent / "test_pdf_turkce_karakter.py"


def test_KRITIK_D5_17_modul_duzeyinde_ATLAMA_yok():
    """Modül düzeyinde (fonksiyon dışı) hiçbir `importorskip` / `skip` / `skipif` çağrısı ve `pytestmark` YOK (AST; yorum ve
    docstring sayılmaz). fitz yalnız PDF metni / font çıkarımı yapan testlerin İÇİNDE (`_fitz()`) istenir."""
    agac = ast.parse(_HEDEF.read_text(encoding="utf-8"))
    ust = [d for d in agac.body if not isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    atlama = [
        f"satir {c.lineno}: {ast.unparse(c)[:80]}"
        for d in ust
        for c in ast.walk(d)
        if isinstance(c, ast.Call)
        and isinstance(c.func, ast.Attribute)
        and c.func.attr in {"importorskip", "skip", "skipif"}
    ]
    atlama += [
        f"pytestmark satir {d.lineno}" for d in ust if isinstance(d, ast.Assign) and "pytestmark" in ast.unparse(d)
    ]
    assert not atlama, f"modul duzeyinde atlama dosyanin TAMAMINI atlar (fitz'siz CI'da kapilar kor): {atlama}"


def test_KRITIK_D5_17_fitz_KURULUYSA_metin_kapilari_ATLANMAZ():
    """`_fitz()` yardımcısı fitz kuruluyken modülü DÖNDÜRÜR (koşulsuz atlama PDF metni kapılarını sessizce kapatırdı)."""
    if importlib.util.find_spec("fitz") is None:
        pytest.skip("PyMuPDF yok — bu kol fitz kurulu ortamda olculur")
    spec = importlib.util.spec_from_file_location("pdf_tr_d517", _HEDEF)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    try:
        fitz = mod._fitz()
    except pytest.skip.Exception as e:  # atlama burada SUSTURULMAZ — fitz varken atlamak kapıyı kör eder
        pytest.fail(f"fitz kurulu ama _fitz() ATLATTI ({e}) — PDF metni / gomulu font kapilari kosmuyor")
    assert hasattr(fitz, "open"), f"_fitz() PyMuPDF modulunu dondurmedi: {fitz!r}"
