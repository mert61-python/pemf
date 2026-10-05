# Author: mertaygn, cglrgrkn
"""ESP8266 SensorManager ANA MAKİNE aparatı (1-G · D1.62). ⚠️ pytest TOPLAMAZ (`test_` ön eki yok).

GERÇEK `firmware/esp8266_pemf_coil/SensorManager.cpp` + `SensorManager.h` + `SharedDefs.h` (ve `JsonSayi.h`) derleme
dizinine BAYT BAYT kopyalanır (sha256 doğrulanır — firmware kaynağı değişmeden koşar) ve `tests/firmware_host/esp8266/`
taklitleriyle (Arduino çekirdeği, Wire, MLX kütüphaneleri, yerine-geçen `NetworkManager.h`) derlenir. Senaryo/model:
`tests/firmware_host/esp8266/sensor_kosum.cpp` başlığı.

⚠️ `Secrets.h` ve gerçek `NetworkManager.cpp`/`.h` DERLENMEZ, OKUNMAZ (sır içerebilir — Ö.4-Y6; skip-worktree).
⚠️ Derleyici yoksa FAIL (SKIP değil) — `firmware_host_aparat.derleyici_gerekli` (MSVC ya da gcc → g++).
"""

from __future__ import annotations

import hashlib
import math
import shutil
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
FW = KOK / "firmware" / "esp8266_pemf_coil"
TAKIM = Path(__file__).resolve().parent / "firmware_host" / "esp8266"
_YASAK = ("NetworkManager.h", "Secrets.h", "NetworkManager.cpp")
_METIN = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace"}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _derle(dizin: Path, kopyalar: tuple, kaynaklar: list[str], ad: str) -> Path:
    from firmware_host_aparat import derleyici_gerekli

    tur, arac = derleyici_gerekli()
    dizin.mkdir(parents=True, exist_ok=True)
    for k in kopyalar:
        shutil.copyfile(FW / k, dizin / k)
        assert _sha(dizin / k) == _sha(FW / k), f"aparat: {k} kopyası kaynakla AYNI değil"
    for yasak in _YASAK:
        assert not (dizin / yasak).exists(), f"aparat: {yasak} derleme dizinine girmemeli"
    exe = dizin / (f"{ad}.exe" if sys.platform == "win32" else ad)
    if tur == "msvc":
        kaynak_satiri = " ".join(f'"{k}"' for k in kaynaklar)
        (dizin / f"derle_{ad}.bat").write_text(
            "@echo off\r\n"
            f'call "{arac}" >nul || exit /b 91\r\n'
            f'cl /nologo /std:c++17 /EHsc /W3 /utf-8 /wd4244 /wd4305 /wd4996 /I "{TAKIM}" /I "{dizin}" '
            f"{kaynak_satiri} /Fe:{exe.name}\r\n",
            encoding="ascii",
        )
        r = subprocess.run(["cmd", "/c", str(dizin / f"derle_{ad}.bat")], cwd=str(dizin), timeout=300, **_METIN)
    else:
        gpp = shutil.which("g++") or shutil.which("clang++")
        assert gpp, "aparat: C++ derleyicisi (g++/clang++) yok"
        r = subprocess.run(
            [gpp, "-std=c++17", "-O0", "-w", f"-I{TAKIM}", f"-I{dizin}", *kaynaklar, "-o", exe.name],
            cwd=str(dizin),
            timeout=300,
            **_METIN,
        )
    # ⚠️ derleyici çıktısı yalnız hata hâlinde ve yalnız SON kısmı (kaynaklar sırsız: SensorManager / JsonSayi).
    assert r.returncode == 0 and exe.is_file(), f"derleme başarısız ({tur}):\n{(r.stdout or '')[-2500:]}"
    return exe


def derle(dizin: Path) -> Path:
    """GERÇEK SensorManager + koşum takımı → sensor_kosum."""
    return _derle(
        dizin,
        ("SensorManager.cpp", "SensorManager.h", "SharedDefs.h"),
        ["SensorManager.cpp", (TAKIM / "sensor_kosum.cpp").as_posix()],
        "sensor_kosum",
    )


def json_sayi(dizin: Path) -> dict:
    """GERÇEK `JsonSayi.h` → {(girdi, basamak): çıktı}."""
    exe = _derle(dizin, ("JsonSayi.h",), [(TAKIM / "json_sayi_kosum.cpp").as_posix()], "json_sayi_kosum")
    r = subprocess.run([str(exe)], timeout=60, **_METIN)
    assert r.returncode == 0, f"json_sayi_kosum rc={r.returncode}"
    sonuc = {}
    for s in r.stdout.splitlines():
        girdi, basamak, cikti = s.split()
        sonuc[(girdi, int(basamak))] = cikti
    return sonuc


def _sayi(s: str) -> float:
    return math.nan if s == "nan" else float(s)


def kos(exe: Path, senaryo: str, dizin: Path, ad: str = "senaryo") -> dict:
    """→ {"okumalar": [dict], "olaylar": [tür]}"""
    yol = dizin / f"{ad}.txt"
    yol.write_text(senaryo, encoding="ascii")
    r = subprocess.run([str(exe), str(yol)], timeout=120, **_METIN)
    assert r.returncode == 0, f"koşum takımı rc={r.returncode}: {r.stderr[-800:]}"
    okumalar, olaylar, son = [], [], None
    for s in r.stdout.splitlines():
        p = s.split()
        if not p:
            continue
        if p[0] == "D":
            okumalar.append(
                {
                    "t_ms": int(p[1]),
                    "temp_ok": p[2] == "1",
                    "nesne": _sayi(p[3]),
                    "ortam": _sayi(p[4]),
                    "mag_ok": p[5] == "1",
                    "mag": _sayi(p[6]),
                    "eksen": (_sayi(p[7]), _sayi(p[8]), _sayi(p[9])),
                    "cur_ok": p[10] == "1",
                    "akim": _sayi(p[11]),
                    "sensors_ok": p[12] == "1",
                }
            )
        elif p[0] == "E":
            olaylar.append(p[1])
        elif p[0] == "SON":
            son = s
    assert son, f"aparat: SON satırı yok (çöktü?): {r.stdout[-500:]}"
    return {"okumalar": okumalar, "olaylar": olaylar}
