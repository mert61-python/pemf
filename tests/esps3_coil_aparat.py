# Author: mertaygn, cglrgrkn
"""ESP32-S3 `CoilController` ANA MAKİNE aparatı (1-G · D1.102). ⚠️ pytest TOPLAMAZ (`test_` ön eki yok).

GERÇEK `firmware/esps3_pemf_coil/CoilController.cpp` + `CoilController.h` + `SharedDefs.h` derleme dizinine BAYT BAYT
kopyalanır (sha256 doğrulanır — firmware kaynağı değişmeden koşar) ve `tests/firmware_host/esps3/` taklitleriyle
derlenir. Koşum takımı (`s3_kosum.cpp`) AYRI çeviri birimidir: kaynağa yalnız public API (`handleCommand` …) ve taklit
tabloya kaydedilen ISR işaretçileriyle dokunur; senkron girişi GPIO7 SEVİYESİ sürülerek verilir. Senaryo dili ve çıktı
biçimi: `s3_kosum.cpp` başlığı.

⚠️ Gerçek `Secrets.h` KOPYALANMAZ, OKUNMAZ, DERLENMEZ (sır içerebilir — skip-worktree): derleme dizinine
`Secrets_taklit.h` `Secrets.h` adıyla konur (yalnız NVS anahtar adı) ve içeriği taklitle bayt bayt eşit olmalı.
⚠️ Derleyici yoksa FAIL (SKIP değil) — `firmware_host_aparat.derleyici_gerekli` (MSVC ya da gcc → g++).
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
FW = KOK / "firmware" / "esps3_pemf_coil"
TAKIM = Path(__file__).resolve().parent / "firmware_host" / "esps3"
_KOPYALAR = ("CoilController.cpp", "CoilController.h", "SharedDefs.h")
_METIN = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace"}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def derle(dizin: Path) -> Path:
    """GERÇEK CoilController (ayrı çeviri birimi) + koşum takımı → s3_kosum."""
    from firmware_host_aparat import derleyici_gerekli

    tur, arac = derleyici_gerekli()
    dizin.mkdir(parents=True, exist_ok=True)
    for k in _KOPYALAR:
        shutil.copyfile(FW / k, dizin / k)
        assert _sha(dizin / k) == _sha(FW / k), f"aparat: {k} kopyası kaynakla AYNI değil"
    taklit = TAKIM / "Secrets_taklit.h"
    shutil.copyfile(taklit, dizin / "Secrets.h")
    assert (dizin / "Secrets.h").read_bytes() == taklit.read_bytes(), (
        "aparat: derleme dizinindeki Secrets.h TAKLİT değil"
    )
    assert sorted(p.name for p in dizin.glob("*.h")) == sorted(["CoilController.h", "SharedDefs.h", "Secrets.h"]), (
        "aparat: derleme dizininde beklenmeyen başlık var"
    )
    kaynaklar = ["CoilController.cpp", (TAKIM / "s3_kosum.cpp").as_posix()]
    exe = dizin / ("s3_kosum.exe" if sys.platform == "win32" else "s3_kosum")
    if tur == "msvc":
        kaynak_satiri = " ".join(f'"{k}"' for k in kaynaklar)
        (dizin / "derle_s3_kosum.bat").write_text(
            "@echo off\r\n"
            f'call "{arac}" >nul || exit /b 91\r\n'
            f'cl /nologo /std:c++17 /EHsc /O2 /W3 /utf-8 /wd4244 /wd4305 /wd4996 /I "{TAKIM}" /I "{dizin}" '
            f"{kaynak_satiri} /Fe:{exe.name}\r\n",
            encoding="ascii",
        )
        r = subprocess.run(["cmd", "/c", str(dizin / "derle_s3_kosum.bat")], cwd=str(dizin), timeout=300, **_METIN)
    else:
        gpp = shutil.which("g++") or shutil.which("clang++")
        assert gpp, "aparat: C++ derleyicisi (g++/clang++) yok"
        r = subprocess.run(
            [gpp, "-std=c++17", "-O2", "-w", f"-I{TAKIM}", f"-I{dizin}", *kaynaklar, "-o", exe.name],
            cwd=str(dizin),
            timeout=300,
            **_METIN,
        )
    # ⚠️ derleyici çıktısı yalnız hata hâlinde ve yalnız SON kısmı (kaynaklar sırsız: CoilController / taklitler).
    assert r.returncode == 0 and exe.is_file(), f"derleme başarısız ({tur}):\n{(r.stdout or '')[-2500:]}"
    return exe


def kos(exe: Path, senaryo: str, dizin: Path, ad: str) -> dict:
    """→ {"kurulum": {...}, "kenarlar": [(t_us, a, b, deneme)], "denemeler": {kimlik: {"durum": {...}, "komut": [...]}}}"""
    yol = dizin / f"{ad}.txt"
    yol.write_text(senaryo, encoding="ascii")
    r = subprocess.run([str(exe), str(yol)], timeout=900, **_METIN)
    assert r.returncode == 0, f"koşum takımı rc={r.returncode}: {r.stderr[-800:]}"
    kurulum, son, deneme = None, False, None
    kenarlar: list[tuple[int, int, int, int | None]] = []
    denemeler: dict[int, dict] = {}
    for s in r.stdout.splitlines():
        p = s.split()
        if not p:
            continue
        if p[0] == "K":
            kenarlar.append((int(p[1]), int(p[2]), int(p[3]), deneme))
        elif p[0] == "T":
            deneme = int(p[1])
            denemeler[deneme] = {"durum": None, "komut": []}
        elif p[0] == "C" and deneme is not None:
            denemeler[deneme]["komut"].append((p[1], p[2] == "1"))
        elif p[0] == "S" and deneme is not None:
            denemeler[deneme]["durum"] = {
                "sync_disabled": p[1] == "1",
                "sync_ignored": int(p[2]),
                "aktif": p[3] == "1",
                "efektif_duty": int(p[4]),
            }
        elif p[0] == "KURULUM":
            kurulum = {"dds_us": int(p[1]), "senkron_pin": int(p[2]), "senkron_kip": int(p[3]), "oto": p[4] == "1"}
        elif p[0] == "SON":
            son = True
    assert kurulum and son, f"aparat: KURULUM/SON satırı yok (çöktü?): {r.stdout[-500:]}"
    return {"kurulum": kurulum, "kenarlar": kenarlar, "denemeler": denemeler}


def zit_acilislar(kenarlar) -> list[tuple[int | None, int, int, int | None]]:
    """Her bacak AÇILIŞI → (deneme, t_us, bacak 0=A/1=B, boşluk_us | None).

    boşluk = açılış anı − KARŞI bacağın son HIGH→LOW anı; yalnız bir önceki AÇILAN bacak karşı bacaksa (zıt geçiş)
    hesaplanır, aynı bacağın yeniden açılışı None. Karşı bacak o an hâlâ HIGH ise boşluk −1 (iki bacak birden HIGH)."""
    seviye = [0, 0]
    son_dusus: list[int | None] = [None, None]
    son_acilan: int | None = None
    sonuc = []
    for t, a, b, deneme in kenarlar:
        yeni = (a, b)
        for bacak in (0, 1):
            if seviye[bacak] == 1 and yeni[bacak] == 0:
                son_dusus[bacak] = t
        for bacak in (0, 1):
            if seviye[bacak] == 0 and yeni[bacak] == 1:
                karsi = 1 - bacak
                bosluk = None
                if son_acilan == karsi:
                    bosluk = -1 if yeni[karsi] == 1 else t - son_dusus[karsi]
                sonuc.append((deneme, t, bacak, bosluk))
                son_acilan = bacak
        seviye = list(yeni)
    return sonuc


def yuksek_araliklar(kenarlar, bacak: int) -> list[tuple[int, int]]:
    """Bacağın HIGH aralıkları [yükseliş_us, düşüş_us) — kenar sırasıyla."""
    araliklar, bas, onceki = [], None, 0
    for t, a, b, _ in kenarlar:
        v = (a, b)[bacak]
        if onceki == 0 and v == 1:
            bas = t
        elif onceki == 1 and v == 0 and bas is not None:
            araliklar.append((bas, t))
            bas = None
        onceki = v
    return araliklar
