# -*- coding: utf-8 -*-
"""4B-3.2 (A3 inceleme, D4.22 ailesi) — `build_tools/build_mac.sh` smoke adımı (`"$APP_BIN" --help`) DÜŞERSE betik DURUR.

ARIZA (HEAD `0ef16a1e`): 6/7 adımındaki smoke `set +e; "$APP_BIN" --help; rc=$?; set -e; [[ $rc -eq 0 ]] && echo OK || echo "(--help
desteklenmiyor olabilir …)"` — `&& … || echo` kalıbı sıfır dışı kodu YUTAR: import zinciri kırık / imzası geçersiz (Apple Silicon'da
SIGKILL → 137) bir Mach-O ile betik 7/7'de zip + sha üretir ve "✓ BİTTİ" der. Yutmanın gerekçesi ("--help desteklenmiyor olabilir")
ürün için YANLIŞ: `backend_service.main(["--help"])` argparse ile 0 döner (aşağıdaki KARŞIT-KANIT). Windows yolunda aynı sınıf
("EXE açılmazsa") D4.19 ile DURUYOR → mac yerel kanalı asimetrik.

Ölçüm (D4.22 kapısının deseni): smoke bölümü (`# Smoke:` satırından `# --- 7)` başlığına kadar) + betiğin KENDİ `die()`'ı betikten
çıkarılır, `bash -euo pipefail` altında `APP_BIN` = verilen kodla çıkan sahte ikili ile koşar (gerçek Mac / PyInstaller YOK).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "build_tools" / "build_mac.sh"
BASH = shutil.which("bash")


def _smoke_ve_die() -> tuple[str, str]:
    satirlar = BETIK.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    die = [s for s in satirlar if re.match(r"^die\(\)\s*\{", s)]
    assert len(die) == 1, f"çıpa: betikte tek satırlık die() bekleniyor: {die}"
    bas = [i for i, s in enumerate(satirlar) if s.startswith("# Smoke:")]
    son = [i for i, s in enumerate(satirlar) if s.startswith("# --- 7)")]
    assert len(bas) == 1 and len(son) == 1 and bas[0] < son[0], "çıpa: smoke bölümü / 7) başlığı bulunamadı"
    blok = "\n".join(satirlar[bas[0] : son[0]])
    assert '"$APP_BIN"' in blok, "çıpa: smoke bölümü APP_BIN'i çağırmıyor (vakum)"
    return blok, die[0]


def _kos(tmp_path: Path, kod: int) -> subprocess.CompletedProcess:
    blok, die = _smoke_ve_die()
    ikili = tmp_path / "PEMF_Backend"
    iz = tmp_path / "smoke_kostu.txt"  # smoke çıktıyı /dev/null'a atar → koştuğunun kanıtı dosyada
    ikili.write_bytes(f'#!/usr/bin/env bash\necho "$1 -> {kod}" > "{iz.as_posix()}"\nexit {kod}\n'.encode("utf-8"))
    ikili.chmod(0o755)
    surucu = tmp_path / "smoke_blogu.sh"
    surucu.write_bytes(
        (f"set -euo pipefail\n{die}\nAPP_BIN=\"{ikili.as_posix()}\"\n{blok}\necho SURUCU-SONU-PAKETLEME\n").encode(
            "utf-8"
        )
    )
    return subprocess.run(
        [BASH, surucu.as_posix()], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60
    )


@pytest.mark.skipif(BASH is None, reason="bash yok")
@pytest.mark.parametrize("kod", [1, 137])
def test_KRITIK_smoke_DUSERSE_paketleme_YAPILMAZ(tmp_path, kod):
    r = _kos(tmp_path, kod)
    iz = tmp_path / "smoke_kostu.txt"
    assert iz.exists() and iz.read_text(encoding="utf-8").strip() == f"--help -> {kod}", (
        f"smoke sahte ikiliyi koşmadı (vakum):\n{r.stdout}\n{r.stderr}"
    )
    assert r.returncode != 0 and "SURUCU-SONU-PAKETLEME" not in r.stdout, (
        f"'$APP_BIN --help' {kod} döndü ama betik 7/7 paketlemeye geçti (bozuk Mach-O zip + sha alır):\n{r.stdout}\n{r.stderr}"
    )


@pytest.mark.skipif(BASH is None, reason="bash yok")
def test_KARSIT_smoke_GECERSE_paketlemeye_gecer(tmp_path):
    r = _kos(tmp_path, 0)
    assert r.returncode == 0 and "SURUCU-SONU-PAKETLEME" in r.stdout, f"{r.stdout}\n{r.stderr}"


def test_KARSIT_KANIT_urun_help_DESTEKLER_cikis_0():
    """Yutmanın gerekçesi ("--help desteklenmiyor olabilir") ürün için yanlış: ana giriş --help'te 0 ile çıkar."""
    import backend_service as bs

    with pytest.raises(SystemExit) as e:
        bs.main(["--help"])
    assert e.value.code in (0, None), f"backend_service --help çıkış kodu {e.value.code!r}"
