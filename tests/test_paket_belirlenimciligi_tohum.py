# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""PAKET BELIRLENIMCILIGI — `PYTHONHASHSEED` kapisi (2026-08-21, olculerek bulundu).

OLCULEN ARIZA. 1.9.18 paketleri kurulunca `base-deps.zip` sha'si degisti — ama BOYUT bayti
bayti aynidiy. Yayindaki paketin merkezi dizini HTTP Range ile cekilip karsilastirildi:
6154 dosyanin 6153'u BIREBIR ayni, yalniz `_internal/base_library.zip` farkli. Onun da ici
acildi: 151 kayittan yalniz `_collections_abc.pyc` (ayni boyut, farkli CRC). Bayt farki
20 bayt ve .pyc BASLIGINDA degil, marshal edilmis KOD govdesinde.

KOK NEDEN. `marshal`, `frozenset` sabitlerini KUMENIN YINELEME SIRASINA gore yazar. O sira
string hash'lerine, yani `PYTHONHASHSEED`e baglidir. `_collections_abc.py` boyle bir sabit
tasir. PyInstaller stdlib .pyc'lerini build surecinde derledigi icin her build farkli bir
`base_library.zip` uretiyordu.

SONUC (neden onemli). `base-deps.zip` ~1,4 GB'dir ve katmanli paketin TEK amaci "bagimlilik
degismediyse klinik onu tekrar indirmesin"dir. Bu tohum yuzunden HICBIR bagimlilik degismedigi
hâlde her yayin her klinige 1,4 GB indiriyordu.

KANIT (bu turda kosuldu): ayni kaynagi rastgele tohumla 5 kez derlemek 5 FARKLI marshal
ciktisi verdi; `PYTHONHASHSEED=0` ile 3/3 BIREBIR ayni.

Bu dosya iki sey kilitler: (1) mekanizmanin hâlâ gecerli oldugu (tohum degisince cikti degisir),
(2) build betiginin tohumu SABITLEDIGI. (2) olmadan (1) sessiz bir regresyona doner.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

_KOK = Path(__file__).resolve().parents[1]

# `_collections_abc.py`deki desenin aynisi: kod govdesine gomulen sabit bir frozenset.
_KAYNAK = "def f(x):\n    return x in {'a','bb','ccc','dddd','ee','fff','g','hh','iii','jjjj','k','ll'}\n"
_KOD = (
    "import hashlib,marshal,sys;"
    "c=compile(sys.argv[1],'t.py','exec',dont_inherit=True);"
    "print(hashlib.sha256(marshal.dumps(c)).hexdigest())"
)


def _derle(tohum: str) -> str:
    ortam = dict(os.environ)
    ortam["PYTHONHASHSEED"] = tohum
    r = subprocess.run([sys.executable, "-c", _KOD, _KAYNAK], capture_output=True, text=True, env=ortam, timeout=120)
    assert r.returncode == 0, f"derleme basarisiz: {r.stderr[:200]}"
    return r.stdout.strip()


def test_KRITIK_build_betigi_PYTHONHASHSEED_i_SABITLER():
    """Kapinin kendisi. Bu satir kalkarsa her yayin kliniklere gereksiz 1,4 GB indirir."""
    betik = (_KOK / "scripts" / "build_backend_exe.ps1").read_text(encoding="utf-8", errors="replace")
    assert '$env:PYTHONHASHSEED   = "0"' in betik or '$env:PYTHONHASHSEED = "0"' in betik, (
        "build_backend_exe.ps1 PYTHONHASHSEED'i sabitlemiyor → base_library.zip her build'de "
        "farkli cikar → base-deps.zip sha'si bosuna degisir → her klinik 1,4 GB yeniden indirir"
    )


def test_KRITIK_sabit_tohum_AYNI_bytecode_uretir():
    """Duzeltmenin GERCEKTEN ise yaradigi: sabit tohumla tekrar tekrar ayni cikti."""
    ciktilar = {_derle("0") for _ in range(3)}
    assert len(ciktilar) == 1, (
        f"PYTHONHASHSEED=0 oldugu hâlde bytecode degisiyor ({len(ciktilar)} farkli cikti) — "
        "belirlenimcilik baska bir kaynaktan bozuluyor, tohum tek basina yetmiyor"
    )


def test_KARSIT_KANIT_mekanizma_HALA_GECERLI():
    """⚠️ Asiri-genisleme/koru-kapi korumasi. Yukaridaki test, Python ileride marshal'i
    belirlenimci yapsa da GECERDI — yani kapi sessizce anlamsizlasirdi. Bu test tohumun
    GERCEKTEN fark yarattigini dogrular; yaratmiyorsa kapi artik gereksizdir ve BU test
    kirilarak bunu bildirir (kaldirilmasi bilincli bir karar olsun diye)."""
    ciktilar = {_derle(str(t)) for t in (1, 2, 3, 4, 5, 6, 7, 8)}
    assert len(ciktilar) > 1, (
        "farkli PYTHONHASHSEED degerleri AYNI bytecode veriyor — marshal artik belirlenimci "
        "olabilir. Bu iyi haber; ama kapinin gerekcesi degismis demektir, gozden gecirin."
    )
