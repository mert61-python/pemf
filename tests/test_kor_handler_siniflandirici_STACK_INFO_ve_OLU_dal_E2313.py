# -*- coding: utf-8 -*-
"""E2-3.13 (2-E incelemesi A3) — D2.37 ile sıkılaşan `kor_mu` sınıflandırıcısının kalan YANLIŞ NEGATİFLERİ.

`_zincir_basar` `stack_info=True`yu "zincir basar" sayıyor — `stack_info` ÇAĞRI yığınını basar, yakalanan istisnanın zincirini DEĞİL
(A9'un ölçülen zararı tam bu zincirin görünmemesiydi); `exc_info=(None, None, None)` de zincir basmaz. `_yeniden_firlatir` `if TYPE_CHECKING:`
(çalışmada hep False) / `if not True:` ölü dallarını ve handler İÇİNDE tanımlanan iç fonksiyonun `raise`ini "yeniden fırlatır" sayıyor.
Ölçüldü (2-E incelemesi A3 2-E incelemesi kaydı, `k5kor_mutasyon.txt`): GERÇEK A9 handler'ı (`backend_service._start_ai_warmup_safe.
_calistir`) `logger.info(..., stack_info=True)` ya da `exc_info=(None, None, None)` yapılınca kod tabanı taraması (`test_KRITIK_alt_sistem_acan_
yolda_KOR_handler_YOK`) ve "düzeltilen dört yer" kapısı YEŞİL kaldı; yalnız D237 dönüşüm testi ÇAPA bulamayıp `StopIteration` ile düştü (aparat
kırmızısı — sınıflandırıcı görmedi).
Kapı: sınıflandırıcının KENDİSİ (deponun kapı modülünden adıyla) + GERÇEK A9 `try`ının AST kopyası dönüştürülür (kaynak dosyaya dokunulmaz).
"""

from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest
from test_loglayan_ama_KOR_handler_YOK import kor_mu

KOK = Path(__file__).resolve().parents[1]


def _try(govde: str) -> ast.Try:
    kaynak = "try:\n    import x\nexcept Exception as e:\n" + "".join("    " + s + "\n" for s in govde.splitlines())
    return ast.parse(kaynak).body[0]


@pytest.mark.parametrize(
    "govde",
    [
        'logger.info("x %s", e, stack_info=True)',
        'logger.info("x %s", e, exc_info=(None, None, None))',
        'logger.info("x %s", e)\nif TYPE_CHECKING:\n    raise',
        'logger.info("x %s", e)\nif not True:\n    raise',
        'logger.info("x %s", e)\ndef _ic():\n    raise ValueError',
    ],
    ids=["stack_info", "exc_info_none_uclu", "type_checking_olu_dal", "not_true_olu_dal", "ic_fonksiyon_raise"],
)
def test_KRITIK_kacis_bicimi_KOR_sayilir_E2313(govde):
    assert kor_mu(_try(govde)) is True, f"kör handler KÖR sayılmadı:\n{govde}"


@pytest.mark.parametrize(
    "govde",
    [
        'logger.info("x %s", e, exc_info=True)',
        'logger.info("x %s", e, exc_info=e)',
        'logger.info("x %s", e, stack_info=True, exc_info=True)',
        'logger.info("x %s", e)\nif kati:\n    raise',
        'logger.info("x %s", e)\nraise',
    ],
    ids=["exc_info_true", "exc_info_degisken", "stack_ve_exc", "kosullu_raise", "duz_raise"],
)
def test_KARSIT_zincir_basan_ya_da_firlatan_KOR_DEGIL_E2313(govde):
    assert kor_mu(_try(govde)) is False, govde


def _a9_try() -> ast.Try:
    agac = ast.parse((KOK / "apps" / "backend" / "backend_service.py").read_text(encoding="utf-8"))
    for d in ast.walk(agac):
        if isinstance(d, ast.FunctionDef) and d.name == "_calistir":
            for t in ast.walk(d):
                if isinstance(t, ast.Try) and any(
                    isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "warning"
                    for h in t.handlers
                    for c in ast.walk(h)
                ):
                    return t
    raise AssertionError("aparat: A9 handler'ı (backend_service._calistir) bulunamadı")


@pytest.mark.parametrize("anahtar", ["stack_info", "exc_info_none_uclu"])
def test_KRITIK_GERCEK_A9_handleri_STACK_INFOya_cevrilince_KOR_sayilir_E2313(anahtar):
    t = copy.deepcopy(_a9_try())
    assert kor_mu(t) is False, "aparat: gerçek A9 handler'ı bugün KÖR DEĞİL olmalı"
    for h in t.handlers:
        for c in ast.walk(h):
            if isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "warning":
                c.func.attr = "info"
                for k in c.keywords:
                    if k.arg == "exc_info":
                        if anahtar == "stack_info":
                            k.arg = "stack_info"
                        else:
                            k.value = ast.Tuple(elts=[ast.Constant(None)] * 3, ctx=ast.Load())
    assert kor_mu(t) is True, f"gerçek A9 handler'ı info + {anahtar} (zincir YOK) yapılınca KÖR sayılmadı"
