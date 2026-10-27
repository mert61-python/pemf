# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.38 (B-10.214) — scratch GPU smoke betiğinin 24H referansı, gerçek-model testinin referansıyla TEK KAYNAK.

ÖLÇÜLEN KUSUR: `scripts/ai_service_scratch_smoke_istek.py` 24H `mean_gap_um`yi SABİT 428,0 ile karşılaştırıyordu; gap ekseni
2026-09-09'da düzeltilince test referansı 240,8 µm oldu (`tests/test_scratch_gercek_model.REFERANSLAR`), betik eski değerde kaldı →
doğru çalışan GPU imajını "gap sapti" diye REDDEDERDİ (n_cells 2085 / closure 29,3 de eski paket değerleriydi).

Kapı iki dosyayı da AST ile okur (içe aktarmaz): gerçek-model testi CPN ağırlığı yoksa modül düzeyinde ATLANIR ve betik içe
aktarılınca ağ isteği atmamalı. İddialar: sabitler BİREBİR eşit · betiğin karşılaştırmaları sabitten okur (sayı sabiti yok) ·
modül düzeyinde istek YOK (iş `main()`de).
"""

from __future__ import annotations

import ast
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "ai_service_scratch_smoke_istek.py"
TEST = KOK / "tests" / "test_scratch_gercek_model.py"


def _modul_sabiti(dosya: Path, ad: str):
    for d in ast.parse(dosya.read_text(encoding="utf-8")).body:
        if isinstance(d, ast.Assign) and any(isinstance(h, ast.Name) and h.id == ad for h in d.targets):
            return ast.literal_eval(d.value)
    raise AssertionError(f"{dosya.name}: modül düzeyinde `{ad}` sabiti YOK")


def test_KRITIK_D5_38_smoke_24H_referansi_test_referansiyla_BIREBIR():
    smoke = _modul_sabiti(BETIK, "REFERANS_24H")
    test = _modul_sabiti(TEST, "REFERANSLAR")["12b_YaraKapanma_24H.tif"]
    assert smoke == test, f"smoke referansı ({smoke}) gerçek-model test referansından ({test}) AYRIŞTI — biri bayat"


def test_KRITIK_D5_38_smoke_karsilastirmalari_REFERANSTAN_okur():
    """Betiğin assert'leri sabit SAYI değil `REFERANS_24H`/`ref` alanlarını kullanır (sabit güncellenip assert eski kalmasın)."""
    agac = ast.parse(BETIK.read_text(encoding="utf-8"))
    main = next((d for d in agac.body if isinstance(d, ast.FunctionDef) and d.name == "main"), None)
    assert main is not None, "betikte main() YOK — iş modül düzeyinde koşuyor olabilir"
    asserts = [d for d in ast.walk(main) if isinstance(d, ast.Assert)]
    kullanilan = {
        s.slice.value
        for a in asserts
        for s in ast.walk(a.test)
        if isinstance(s, ast.Subscript)
        and isinstance(s.value, ast.Name)
        and s.value.id in {"ref", "REFERANS_24H"}
        and isinstance(s.slice, ast.Constant)
    }
    assert kullanilan >= {"n_cells", "closure_pct", "mean_gap_um"}, (
        f"assert'ler referans alanlarını kullanmıyor: {kullanilan}"
    )
    sabitler = [
        s.value
        for a in asserts
        for s in ast.walk(a.test)
        if isinstance(s, ast.Constant)
        and isinstance(s.value, (int, float))
        and s.value in (2085, 2083, 29.3, 29.36, 428.0, 240.8)
    ]
    assert not sabitler, f"assert'lerde referans SAYISI elle yazılmış (tek kaynak dışı): {sabitler}"


def test_KRITIK_D5_38_smoke_ICE_AKTARILINCA_istek_ATMAZ():
    """Modül düzeyinde (fonksiyon dışı, `__main__` bloğu hariç) ağ / dosya çağrısı YOK — kapı ve önsöz koşucusu güvenle okur."""
    agac = ast.parse(BETIK.read_text(encoding="utf-8"))
    ust = [
        d
        for d in agac.body
        if not isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not (isinstance(d, ast.If) and "__main__" in ast.unparse(d.test))
    ]
    cagri = [
        ast.unparse(c.func)
        for d in ust
        for c in ast.walk(d)
        if isinstance(c, ast.Call)
        and ast.unparse(c.func).split(".")[-1] in {"urlopen", "Request", "read_bytes", "load"}
    ]
    assert not cagri, f"betik modül düzeyinde iş yapıyor (içe aktarınca istek atar): {cagri}"
