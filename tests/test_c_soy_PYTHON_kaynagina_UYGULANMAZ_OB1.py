# -*- coding: utf-8 -*-
"""O-B.1 (2-B açık madde) — C yorum sökücüsü `c_soyucu.c_soy` Python kaynağına UYGULANMAZ.

NEDEN: `c_soy` C/C++ sözdizimini bilir; Python'da `'`/`"` paritesi (Türkçe kesme işareti) ve docstring'deki `/*` onu
şaşırtır. ÖLÇÜLDÜ (2026-10-08, 2-C): `ai_router.py` docstring'indeki `/api/ai/pro/*` blok yorum başlatıyor → `c_soy`
dosyanın 2254. satırından SONUNU (2190 satır) boşaltıyordu; `backend_service.py`'de `librosa/*/__pycache__` 758'den sonunu
(492 satır). `test_ai_donanim_rozeti_gurultusu` "`hw_status = "idle"` YALNIZ BİR KEZ atanır" kapısı ikinci atamayı dosyanın
yarısında GÖREMİYORDU (sahte yeşil); `test_goc_yarim_kalirsa_db_kaybolmaz` alt-dizeyi Python yorumunda da buluyordu.
Python kaynağını okuyan kapı AST (ya da ham metin) kullanır — hafıza "c_soy Python'da tırnak paritesi".

Kapı YAPISAL ve araç kanıtlıdır: her `tests/*.py` AST ile taranır; şu biçimler İHLALDİR:
  (a) `c_soy(...)` argümanında `.py` ile biten dize sabiti ya da modül düzeyinde `.py` yoluna atanmış bir ad;
  (b) gövdesinde `c_soy(...)` çağıran bir yardımcıya `.py` ile biten dize sabitiyle çağrı.
Ölçüm aracı ayrıca çalışma zamanı izcisiyle çapraz doğrulandı (2-C: `c_soy` 43 test dosyasında 434 kez çağrıldı; girdiler
depo dosyalarıyla SHA-256 eşlendi → Python'a giden tam bu iki yer).
"""

from __future__ import annotations

import ast
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
TESTLER = KOK / "tests"
HARIC = {"c_soyucu.py", Path(__file__).name}


def _py_sabiti(d) -> bool:
    return isinstance(d, ast.Constant) and isinstance(d.value, str) and d.value.endswith(".py")


def _c_soy_cagrisi_mi(d) -> bool:
    if not isinstance(d, ast.Call):
        return False
    f = d.func
    return (isinstance(f, ast.Name) and f.id == "c_soy") or (isinstance(f, ast.Attribute) and f.attr == "c_soy")


def ihlaller(kaynak: str, ad: str) -> list[str]:
    agac = ast.parse(kaynak)
    py_adlari = set()
    for d in agac.body:
        if isinstance(d, (ast.Assign, ast.AnnAssign)) and d.value is not None:
            if any(_py_sabiti(x) for x in ast.walk(d.value)):
                for h in d.targets if isinstance(d, ast.Assign) else [d.target]:
                    if isinstance(h, ast.Name):
                        py_adlari.add(h.id)
    saranlar = set()
    for fn in ast.walk(agac):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(_c_soy_cagrisi_mi(x) for x in ast.walk(fn)):
            saranlar.add(fn.name)
    bulgu = []
    for d in ast.walk(agac):
        if _c_soy_cagrisi_mi(d):
            for x in ast.walk(d):
                if _py_sabiti(x) or (isinstance(x, ast.Name) and x.id in py_adlari):
                    bulgu.append(f"{ad}:{d.lineno} c_soy(<Python kaynağı>)")
                    break
        elif isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id in saranlar:
            if any(_py_sabiti(a) for a in d.args):
                bulgu.append(f"{ad}:{d.lineno} {d.func.id}(<.py>) → c_soy")
    return sorted(set(bulgu))


def test_KRITIK_hicbir_test_c_soy_u_PYTHON_kaynagina_uygulamaz():
    taranan = 0
    bulgu = []
    for f in sorted(TESTLER.glob("*.py")):
        if f.name in HARIC:
            continue
        metin = f.read_text(encoding="utf-8", errors="replace")
        if "c_soy" not in metin:
            continue
        taranan += 1
        bulgu += ihlaller(metin, f.name)
    assert taranan >= 30, f"araç KÖR: c_soy kullanan test dosyası yalnız {taranan} (2-C ölçümü: 43)"
    assert bulgu == [], "C yorum sökücüsü Python kaynağına uygulanıyor (parite/`/*` dosyayı boşaltır):\n" + "\n".join(
        bulgu
    )


def test_KARSIT_arac_iki_bicimi_de_BULUR_C_kaynagina_dokunmaz():
    """Araç kanıtı: bilinen iki ihlal biçimi bulunur; C/TS yolu ve ham okuma ihlal sayılmaz."""
    ornek = (
        "from pathlib import Path\n"
        "from c_soyucu import c_soy\n"
        "KOK = Path('.')\n"
        "_ROUTER = KOK / 'apps' / 'backend' / 'servers' / 'ai_router.py'\n"
        "_EKRAN = KOK / 'apps' / 'ui' / 'x.tsx'\n"
        "def _kaynak(bagil):\n"
        "    return c_soy((KOK / bagil).read_text())\n"
        "def t1():\n"
        "    return c_soy(_ROUTER.read_text())\n"
        "def t2():\n"
        "    return _kaynak('apps/backend/backend_service.py')\n"
        "def t3():\n"
        "    return c_soy(_EKRAN.read_text()) + _kaynak('firmware/main.c') + _ROUTER.read_text()\n"
    )
    assert ihlaller(ornek, "ornek.py") == [
        "ornek.py:11 _kaynak(<.py>) → c_soy",
        "ornek.py:9 c_soy(<Python kaynağı>)",
    ]
