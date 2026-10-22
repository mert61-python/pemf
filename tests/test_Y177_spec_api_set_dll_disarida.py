# -*- coding: utf-8 -*-
"""Y177 (S-YH.11) — paketteki Windows Kits `api-ms-win-*.dll` "API set" saplamaları spec süzgeciyle DIŞLANIR.

ÖLÇÜLEN DURUM (YH D5, gerçek derleme 2026-10-22): `PEMF_Backend` paketinde 40 `api-ms-win-*.dll` vardı; 40'ının da kaynağı
`C:\\Program Files (x86)\\Windows Kits\\10\\…` (PyInstaller'ın ikili bağımlılık çözümü derleme makinesinin SDK / UCRT redist kurulumundan
topluyor) → paket derleme makinesine bağlı. Windows 10 / 11'de UCRT ve API set şeması işletim sisteminde. Sahip kararı Y177: 1.9.51'de
paketten çıkar (deps katmanı bu yayında zaten değişiyor).

KAPI: spec'in süzgeç deyimleri AST ile alınır ve SAHTE bir `a` (Analysis) nesnesinin `binaries` listesi üzerinde KOŞAR (davranış: hangi
adlar düşer, hangileri kalır; aynı liste nesnesi mi); konum denetimi: süzgeç `a = Analysis(...)`'ten SONRA, `COLLECT(...)`'ten ÖNCE ve
COLLECT `a.binaries`'i alır. Gerçek derlemedeki sayım (pakette 0) §8 derleme ölçümünde yapılır.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
SPEC = KOK / "build_tools" / "PEMF_Backend_onedir.spec"


def _agac():
    kaynak = SPEC.read_text(encoding="utf-8")
    return kaynak, ast.parse(kaynak)


def _suzgec_deyimleri():
    """`def _api_set_saplamasi_mi` + onu kullanan `a.binaries` deyimleri (sıralı)."""
    _, agac = _agac()
    govde = agac.body
    fn = [i for i, d in enumerate(govde) if isinstance(d, ast.FunctionDef) and d.name == "_api_set_saplamasi_mi"]
    assert len(fn) == 1, "Y177 süzgeç yüklemi `_api_set_saplamasi_mi` spec'te TEK kez tanımlı olmalı"
    kullanan = [
        i
        for i, d in enumerate(govde)
        if i > fn[0] and "_api_set_saplamasi_mi" in ast.unparse(d) and "binaries" in ast.unparse(d)
    ]
    assert kullanan, "süzgeç yüklemi tanımlı ama a.binaries'e UYGULANMIYOR"
    return govde, fn[0], kullanan


class _SahteAnaliz:
    def __init__(self, ikililer):
        self.binaries = ikililer


ORNEK = [
    (
        "api-ms-win-core-file-l1-2-0.dll",
        r"C:\Program Files (x86)\Windows Kits\10\Redist\ucrt\DLLs\x64\api-ms-win-core-file-l1-2-0.dll",
        "BINARY",
    ),
    (
        "API-MS-WIN-CRT-RUNTIME-L1-1-0.DLL",
        r"C:\Program Files (x86)\Windows Kits\10\Redist\ucrt\DLLs\x64\API-MS-WIN-CRT-RUNTIME-L1-1-0.DLL",
        "BINARY",
    ),
    ("torch/lib/api-ms-win-crt-heap-l1-1-0.dll", r"C:\x\torch\lib\api-ms-win-crt-heap-l1-1-0.dll", "BINARY"),
    ("ucrtbase.dll", r"C:\Windows\System32\ucrtbase.dll", "BINARY"),
    ("vcruntime140.dll", r"C:\py\vcruntime140.dll", "BINARY"),
    ("api-ms-win-ozel.pyd", r"C:\x\api-ms-win-ozel.pyd", "EXTENSION"),
    ("cv2/opencv_world.dll", r"C:\x\cv2\opencv_world.dll", "BINARY"),
    ("my-api-ms-win-core.dll", r"C:\x\my-api-ms-win-core.dll", "BINARY"),
]


def _kos(ikililer):
    govde, fi, kullanan = _suzgec_deyimleri()
    a = _SahteAnaliz(list(ikililer))
    kimlik = id(a.binaries)
    ad_alani = {"os": os, "a": a, "print": lambda *x, **k: None}
    modul = ast.Module(body=[govde[fi]] + [govde[i] for i in kullanan], type_ignores=[])
    exec(compile(modul, str(SPEC), "exec"), ad_alani)  # noqa: S102 — yalnız spec'in kendi süzgeç deyimleri, sahte nesneyle
    return a, kimlik


def test_KRITIK_Y177_api_set_saplamalari_DUSER_digerleri_KALIR():
    a, _ = _kos(ORNEK)
    kalan = [x[0] for x in a.binaries]
    assert kalan == [
        "ucrtbase.dll",
        "vcruntime140.dll",
        "api-ms-win-ozel.pyd",
        "cv2/opencv_world.dll",
        "my-api-ms-win-core.dll",
    ], kalan


def test_KRITIK_Y177_suzgec_YERINDE_ayni_liste_COLLECTe_gider():
    a, kimlik = _kos(ORNEK)
    assert id(a.binaries) == kimlik, "süzgeç a.binaries'i YENİDEN bağladı — yerinde (dilim) atama bekleniyor"


def test_KRITIK_Y177_suzgec_Analysisten_SONRA_COLLECTten_ONCE_ve_COLLECT_a_binaries_alir():
    kaynak, agac = _agac()
    govde, _, kullanan = _suzgec_deyimleri()
    analiz = [
        i
        for i, d in enumerate(govde)
        if isinstance(d, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "a" for t in d.targets)
        and isinstance(d.value, ast.Call)
        and getattr(d.value.func, "id", "") == "Analysis"
    ]
    collect = [
        i
        for i, d in enumerate(govde)
        if isinstance(d, ast.Assign) and isinstance(d.value, ast.Call) and getattr(d.value.func, "id", "") == "COLLECT"
    ]
    assert len(analiz) == 1 and len(collect) == 1, (analiz, collect)
    assert all(analiz[0] < i < collect[0] for i in kullanan), (
        f"süzgeç Analysis {analiz} ile COLLECT {collect} ARASINDA değil: {kullanan}"
    )
    arglar = [ast.unparse(x) for x in govde[collect[0]].value.args]
    assert "a.binaries" in arglar, f"COLLECT süzülmüş a.binaries'i ALMIYOR: {arglar}"


def test_KARSIT_Y177_ornek_listede_api_set_GERCEKTEN_var():
    """Ölçücü kör değil: örnekte 3 api-ms-win-*.dll var, süzgeçsiz kalan sayısı 8 olurdu."""
    assert (
        sum(
            1
            for x in ORNEK
            if os.path.basename(x[0].replace("\\", "/")).lower().startswith("api-ms-win-")
            and x[0].lower().endswith(".dll")
        )
        == 3
    )
