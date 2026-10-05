# Author: mertaygn, cglrgrkn
"""ANA MAKİNE ISR KOŞUM TAKIMI — Python tarafı. ⚠️ pytest TOPLAMAZ (`test_` ön eki yok; `topoloji.py` deseni).

GERÇEK `firmware/stm32_pemf/Core/Src/main.c` `tests/firmware_host/isr_kosum.c` ile aynı çeviri biriminde derlenir;
TIM1 ISR'ı tick tick koşar, her BSRR yazımı (port, değer, öncesindeki NOP sayısı) sırayla kaydedilir (Dalga 1 · 1-B:
D1.21, D1.25–D1.28). Kaynağın iki satır biçimi derlemeden önce değiştirilir (anlam aynı):
    `X->BSRR = v;`              → `pemf_host_bsrr(X, v);`
    `__asm volatile("nop");`    → `pemf_host_nop();`
Dönüşüm sayıları DOĞRULANIR (sıfır dönüşüm = aparat kör → hata).

⚠️ DERLEYİCİ YOKSA KAPI SKIP ETMEZ, FAIL EDER (plan 4A-2 SKIP→FAIL; D1.26 orkestratör notu). Bulma sırası:
`PEMF_CC` ortam değişkeni (`gcc`/`cc`/`clang` ya da `cl`) → Windows: `PEMF_VCVARS` / VS Build Tools `vcvars64.bat`
(vswhere) → PATH'te gcc/cc/clang. CI'daki ubuntu gcc aynı kaynağı derler (yalnız standart C11).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
MAIN_C = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
INC = KOK / "firmware" / "stm32_pemf" / "Core" / "Inc"
TAKIM = Path(__file__).resolve().parent / "firmware_host"

_VCVARS_ADAYLARI = [
    Path(r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"),
    Path(r"C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"),
    Path(r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"),
]


def _vswhere_vcvars() -> Path | None:
    vswhere = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")
    if not vswhere.is_file():
        return None
    try:
        r = subprocess.run(
            [str(vswhere), "-latest", "-products", "*", "-find", r"VC\Auxiliary\Build\vcvars64.bat"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    yol = (r.stdout or "").strip().splitlines()
    return Path(yol[0]) if yol and Path(yol[0]).is_file() else None


def derleyici() -> tuple[str, str] | None:
    """('msvc', vcvars64.bat) | ('gcc', çalıştırılabilir) | None."""
    istek = os.environ.get("PEMF_CC", "").strip()
    if istek:
        if istek.lower() in ("cl", "msvc"):
            v = (
                os.environ.get("PEMF_VCVARS")
                or _vswhere_vcvars()
                or next((p for p in _VCVARS_ADAYLARI if p.is_file()), None)
            )
            return ("msvc", str(v)) if v else None
        yol = shutil.which(istek)
        return ("gcc", yol) if yol else None
    if sys.platform == "win32":
        v = os.environ.get("PEMF_VCVARS")
        v = Path(v) if v else (_vswhere_vcvars() or next((p for p in _VCVARS_ADAYLARI if p.is_file()), None))
        if v and Path(v).is_file():
            return ("msvc", str(v))
    for ad in ("gcc", "cc", "clang"):
        yol = shutil.which(ad)
        if yol:
            return ("gcc", yol)
    return None


def derleyici_gerekli() -> tuple[str, str]:
    import pytest

    d = derleyici()
    if d is None:
        pytest.fail(
            "C derleyicisi YOK — firmware ISR kapısı SKIP EDİLMEZ (plan 4A-2: sessiz atlama kapıyı kör bırakır). "
            "MSVC Build Tools (vcvars64.bat; PEMF_VCVARS ile yol verilebilir) ya da gcc kurun / PEMF_CC ayarlayın.",
            pytrace=False,
        )
    return d


_BSRR = re.compile(r"([A-Za-z_][\w\.\[\]]*)->BSRR\s*=\s*([^;]+);")
_NOP = '__asm volatile("nop");'


def donustur(kaynak: str) -> tuple[str, int, int]:
    """(dönüştürülmüş metin, BSRR yazımı sayısı, NOP sayısı)."""
    nop = kaynak.count(_NOP)
    metin = kaynak.replace(_NOP, "pemf_host_nop();")
    metin, bsrr = _BSRR.subn(r"pemf_host_bsrr(\1, \2);", metin)
    return metin, bsrr, nop


def derle(kaynak: str, dizin: Path) -> Path:
    """`kaynak` (main.c METNİ) için koşum takımını `dizin`de derle → exe yolu."""
    tur, arac = derleyici_gerekli()
    metin, bsrr, nop = donustur(kaynak)
    assert bsrr >= 10, f"aparat: main.c'de yalnız {bsrr} BSRR yazımı dönüştürüldü (biçim değişmiş — kenar günlüğü KÖR)"
    dizin.mkdir(parents=True, exist_ok=True)
    (dizin / "main_host.c").write_text(metin, encoding="utf-8")
    (dizin / "tu.c").write_text(
        '#define KAYNAK "main_host.c"\n#include "' + (TAKIM / "isr_kosum.c").as_posix() + '"\n', encoding="utf-8"
    )
    exe = dizin / ("isr_kosum.exe" if sys.platform == "win32" else "isr_kosum")
    stub, inc = (TAKIM / "stub").as_posix(), INC.as_posix()
    if tur == "msvc":
        # cmd /c'ye alıntılı yol geçirmek kaçış sorununa düşüyor → komutlar bir .bat dosyasından koşar.
        (dizin / "derle.bat").write_text(
            "@echo off\r\n"
            f'call "{arac}" >nul || exit /b 91\r\n'
            f'cl /nologo /std:c11 /W3 /utf-8 /wd4996 /wd4267 /wd4244 /wd4305 /I "{dizin}" /I "{stub}" /I "{inc}" '
            f"tu.c /Fe:{exe.name} /Fo:tu.obj\r\n",
            encoding="ascii",
        )
        r = subprocess.run(
            ["cmd", "/c", str(dizin / "derle.bat")], cwd=str(dizin), capture_output=True, text=True, timeout=300
        )
    else:
        r = subprocess.run(
            [arac, "-std=c11", "-O0", "-w", f"-I{dizin}", f"-I{stub}", f"-I{inc}", "tu.c", "-o", exe.name, "-lm"],
            cwd=str(dizin),
            capture_output=True,
            text=True,
            timeout=300,
        )
    assert r.returncode == 0 and exe.is_file(), (
        f"derleme başarısız ({tur}):\n{(r.stdout or '')[-2500:]}\n{(r.stderr or '')[-1500:]}"
    )
    return exe


def kos(
    exe: Path, *args, gunluk_bas: int | None = None, kip_bas: int | None = None, kip: tuple[int, int] | None = None
) -> list[str]:
    """`gunluk_bas`: "B" günlüğü bu tick'ten başlar (isr kipi; ISR yine baştan koşar — isr_kosum.c ISR_GUNLUK_BAS).
    `kip_bas`: sürüş kipi isteği (unipolar maskesi) döngüden önce · `kip=(tick, maske)`: çalışırken kip değişimi."""
    ek = {}
    if gunluk_bas is not None:
        ek["ISR_GUNLUK_BAS"] = str(int(gunluk_bas))
    if kip_bas is not None:
        ek["ISR_KIP_BAS"] = str(int(kip_bas))
    if kip is not None:
        ek["ISR_KIP_TICK"], ek["ISR_KIP_MASKE"] = str(int(kip[0])), str(int(kip[1]))
    env = {**os.environ, **ek} if ek else None
    r = subprocess.run([str(exe), *map(str, args)], capture_output=True, text=True, timeout=300, env=env)
    assert r.returncode == 0, f"koşum takımı rc={r.returncode}: {r.stderr[-800:]}"
    return r.stdout.splitlines()


def harita(exe: Path) -> tuple[dict[int, tuple[str, int, str, int]], dict[int, bool]]:
    pinler, uni = {}, {}
    for s in kos(exe, "harita"):
        p = s.split()
        if p[0] == "H":
            pinler[int(p[1])] = (p[2], int(p[3]), p[4], int(p[5]))
        elif p[0] == "K":
            uni[int(p[1])] = p[2] == "1"
    return pinler, uni


def bsrr_olaylari(satirlar: list[str]) -> list[tuple[int, str, int, int]]:
    return [(int(p[1]), p[2], int(p[3], 16), int(p[4])) for p in (s.split() for s in satirlar) if p and p[0] == "B"]


def durumlar(satirlar: list[str]) -> list[tuple[int, int, int, int, int]]:
    return [tuple(int(x) for x in p[1:6]) for p in (s.split() for s in satirlar) if p and p[0] == "S"]


def sabit(ad: str, kaynak: str | None = None) -> int:
    """main.c'deki `#define <ad> <sayı>[U]` — YORUMU SOYULMUŞ metinden (yorumdaki kopya sayılmaz)."""
    from c_soyucu import c_soy

    m = re.search(
        rf"^\s*#define\s+{ad}\s+(\d+)U?\b",
        c_soy(kaynak if kaynak is not None else MAIN_C.read_text(encoding="utf-8")),
        re.M,
    )
    assert m, f"main.c'de (yorum dışı) #define {ad} yok"
    return int(m.group(1))


def bacak_analizi(olaylar, pinler, bobinler, baslangic_tick: int = 0):
    """Her BSRR yazımından sonra bobin bacaklarının seviyesi → ihlaller ve kenarlar.

    Dönüş: {bobin: {"cakisma": [tick], "kenarlar": [(tick, bacak, yeni_seviye, onceki_nop, onceki_olay)]}}
    `onceki_olay`: aynı tick'te bu yazımdan hemen önceki yazım (port, değer) ya da None."""
    seviye = {(port, pin): 0 for (pa, ia, pb, ib) in pinler.values() for (port, pin) in ((pa, ia), (pb, ib))}
    sonuc = {i: {"cakisma": [], "kenarlar": []} for i in bobinler}
    onceki = None
    for tick, port, deger, nop in olaylar:
        set_, reset = deger & 0xFFFF, (deger >> 16) & 0xFFFF
        degisen = []
        for (p, pin), sv in list(seviye.items()):
            if p != port:
                continue
            yeni = 1 if (set_ & pin) else (0 if (reset & pin) else sv)
            if yeni != sv:
                seviye[(p, pin)] = yeni
                degisen.append((pin, yeni))
        for i in bobinler:
            pa, ia, pb, ib = pinler[i]
            for pin, yeni in degisen:
                bacak = "A" if (port, pin) == (pa, ia) else ("B" if (port, pin) == (pb, ib) else None)
                if bacak and tick >= baslangic_tick:
                    sonuc[i]["kenarlar"].append(
                        (tick, bacak, yeni, nop, onceki if onceki and onceki[0] == tick else None)
                    )
            if seviye[(pa, ia)] and seviye[(pb, ib)] and tick >= baslangic_tick:
                sonuc[i]["cakisma"].append(tick)
        onceki = (tick, port, deger)
    return sonuc
