# -*- coding: utf-8 -*-
"""D4.22 (B-10.202) — `build_tools/build_mac.sh` imza DOĞRULAMASI düşerse betik sıfır dışı kodla çıkar.

ARIZA: imza bloğu `codesign --verify --deep --strict … && echo "[OK] imza doğrulandı"` diyordu. `set -euo pipefail` altında `&&`
listesindeki (son olmayan) komutun başarısızlığı errexit'ten MUAFTIR ve o yüzden sıfır dışı dönen `if` bileşiği de betiği
durdurmaz → doğrulanamayan imzayla paketleme (zip + sha) sürüyor, `mac-backend.yml` yeşil bitip artefaktı yüklüyordu.

Ölçüm: satır metni DEĞİL kabuk semantiği — imza bloğu (`if [[ -n "${PEMF_CODESIGN_ID:-}" ]] … fi`) ve betiğin KENDİ `die()`'ı
betikten çıkarılır, `bash -euo pipefail` altında `codesign` gölge işleviyle koşar (gerçek codesign / Mac YOK).
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

pytestmark = pytest.mark.skipif(BASH is None, reason="bash yok")


def _blok_ve_die() -> tuple[str, str]:
    satirlar = BETIK.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    die = [s for s in satirlar if re.match(r"^die\(\)\s*\{", s)]
    assert len(die) == 1, f"çıpa: betikte tek satırlık die() bekleniyor: {die}"
    bas = [i for i, s in enumerate(satirlar) if s.startswith('if [[ -n "${PEMF_CODESIGN_ID:-}" ]]; then')]
    assert len(bas) == 1, "çıpa: imza bloğu (PEMF_CODESIGN_ID) bulunamadı"
    son = next(i for i in range(bas[0] + 1, len(satirlar)) if satirlar[i] == "fi")
    return "\n".join(satirlar[bas[0] : son + 1]), die[0]


def _kos(tmp_path: Path, dogrulama_kodu: int) -> subprocess.CompletedProcess:
    blok, die = _blok_ve_die()
    surucu = tmp_path / "imza_blogu.sh"
    surucu.write_bytes(
        (
            "set -euo pipefail\n"
            f"{die}\n"
            'DIST_DIR="dist-mac"\n'
            'PEMF_CODESIGN_ID="Developer ID Application: Sahte Test (TEAM0000)"\n'
            "codesign() {\n"
            '  if [ "$1" = "--verify" ]; then echo "sahte codesign --verify -> ' + str(dogrulama_kodu) + '" >&2; '
            f"return {dogrulama_kodu}; fi\n"
            '  echo "sahte codesign imza"; return 0\n'
            "}\n"
            f"{blok}\n"
            "echo SURUCU-SONU\n"
        ).encode("utf-8")
    )
    return subprocess.run(
        [BASH, surucu.as_posix()], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60
    )


def test_KRITIK_imza_dogrulamasi_DUSERSE_betik_DURUR_B10_202(tmp_path):
    r = _kos(tmp_path, 1)
    assert "sahte codesign imza" in r.stdout, f"blok imza dalını koşmadı (vakum):\n{r.stdout}\n{r.stderr}"
    assert r.returncode != 0, (
        f"codesign --verify 1 döndü ama betik ÇIKIŞ 0 ile devam etti (doğrulanmamış imzayla paketlenir):\n{r.stdout}\n{r.stderr}"
    )
    assert "SURUCU-SONU" not in r.stdout and "[OK] imza doğrulandı" not in r.stdout


def test_KARSIT_dogrulama_GECERSE_blok_devam_eder(tmp_path):
    r = _kos(tmp_path, 0)
    assert r.returncode == 0 and "[OK] imza doğrulandı" in r.stdout and "SURUCU-SONU" in r.stdout, (
        f"{r.stdout}\n{r.stderr}"
    )
