# -*- coding: utf-8 -*-
"""Y312 (sahip 20-11: "tam testlerde süreler kısalsın" · "xdist kur") — Y30 tam süiti pytest-xdist KURULUYSA PARALEL koşar.

ÖLÇÜLEN (PX, istem 60): Y30 (`yayin_oncesi_suit.ps1`) süiti TEK süreçte koşuyordu — 12 736 test ~1 sa 47 dk (B7, 20-11 06:10); makinede
8 fiziksel çekirdek boştaydı. DÜZELTME: kancasız (TAM) kipte xdist varsa `-n <min(8, fiziksel çekirdek, ⌊RAM GB / 5⌋)> --dist loadgroup`
(dosya grupları: tests/xdist_grup.py; RAM tavanı: guii'de 8 işçi gerçek ağırlıklarla RAM'i %99,5'e çıkardı — istem kuralı "RAM %80'i
aşarsa 6 işçi"); xdist YOKSA SERİ + UYARI (yayın DURMAZ); `-Isci 0` elle SERİ; kancalı (denetim) kip SERİ (bekçi işçiye geçmez). İşçi
sayısı süiti DARALTMAZ: TAM kip, Y176 damgası AYNEN.

KAPI (gerçek pwsh + gerçek betik, geçici git deposunda — test_Y176_yesil_suit_damgasi düzeneği):
  · xdist kurulu → paralel satırı, işçi = min(8, fiziksel çekirdek, ⌊RAM GB / 5⌋), komutta `-n <işçi> --dist loadgroup`, aynı test
    sayısı, TAM damga;
  · xdist YOK (yoklamayı boş döndüren sarmal yorumlayıcı) → UYARI + SERİ, süit yine koşar ve damga yazılır (yayın DURMAZ);
  · `-Isci 0` → SERİ, TAM kip (damga yazılır) · kancalı kip → SERİ, damgaya dokunmaz;
  · paralel KIRMIZI → çıkış kodu taşınır, eski damga silinir, kırmızı kısa özette ADIYLA.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import capraz
import pytest
from test_Y176_yesil_suit_damgasi import PWSH, _damga_yaz, _damga_yolu, _head, _testler, depo  # noqa: F401 (fikstür)

_GOVDE = "import os\n\n\ndef _isci():\n    return os.environ.get('PYTEST_XDIST_WORKER', '')\n" + "".join(
    f"\n\ndef test_{i}():\n    assert {{kosul}}, 'Y312-KIP ' + repr(_isci())\n" for i in (1, 2, 3)
)
# Testin KENDİSİ hangi kipte koştuğunu kanıtlar (`-q` kipi işçi satırı basmaz): paralelde xdist işçisi, seride değil.
_ISCIDE = _GOVDE.format(kosul="_isci().startswith('gw')")
_SERIDE = _GOVDE.format(kosul="not _isci()")
_KIRMIZI = _ISCIDE + "\n\ndef test_duser():\n    assert False, 'Y312-KIRMIZI'\n"
_SARMAL = '@echo off\r\nif "%~1"=="-c" exit /b 0\r\n"{py}" %*\r\n'


def _kos(d: Path, *ek: str, python: str | None = None) -> tuple[int, str]:
    if PWSH is None or os.name != "nt":
        capraz.atla("pwsh 7 + Windows gerekir (Y30 yayın makinesi)")
    komut = [
        PWSH,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(d / "scripts" / "yayin_oncesi_suit.ps1"),
    ]
    if "-PytestOnek" not in ek:
        komut += ["-Python", python or sys.executable]
    komut += list(ek)
    # PYTEST_*: bu kapı paralel süitte bir xdist işçisinde koşarken içteki süit dış işçinin kimliğini miras almasın.
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "PYTEST_"))}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    r = subprocess.run(
        komut, cwd=d, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=300
    )
    return r.returncode, r.stdout + r.stderr


def _cim(sorgu: str) -> int:
    r = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command", sorgu], capture_output=True, text=True, timeout=120
    )
    return int(r.stdout.strip())


def _fiziksel_cekirdek() -> int:
    return _cim("(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum")


def _ram_gb() -> int:
    return _cim("[int][Math]::Floor((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)")


def _komut_satiri(cikti: str) -> str:
    m = re.search(r"^\[YAYIN-ONCESI\] tam suit \(ZORUNLU=1, GOLDEN_REQUIRED=1\): (.*)$", cikti, re.M)
    assert m, f"komut satırı yok:\n{cikti[-1500:]}"
    return m.group(1)


def _damga(d: Path) -> dict:
    y = _damga_yolu(d)
    assert y.exists(), "TAM kip yeşilken damga YAZILMADI"
    return json.loads(y.read_text(encoding="utf-8-sig"))


def test_KRITIK_xdist_KURULU_TAM_kip_PARALEL_isci_min8_fiziksel_RAM5GB_ayni_test_sayisi_damga_AYNEN(depo):
    capraz.paket_yoksa_atla("xdist", sebep="pytest-xdist (requirements-test.txt) — paralel Y30")
    _testler(depo, _ISCIDE)
    rc, cikti = _kos(depo)
    assert rc == 0, cikti[-1500:]
    m = re.search(
        r"^\[YAYIN-ONCESI\] paralel: pytest-xdist (\S+) - (\d+) isci \(fiziksel cekirdek (\d+), RAM (\d+) GB\), --dist loadgroup",
        cikti,
        re.M,
    )
    assert m, f"xdist kuruluyken paralel kip seçilmedi:\n{cikti[-1500:]}"
    import xdist

    isci, cekirdek, ram = int(m.group(2)), int(m.group(3)), int(m.group(4))
    assert m.group(1) == xdist.__version__
    assert cekirdek == _fiziksel_cekirdek() and ram == _ram_gb(), (cekirdek, ram)
    # Y312 (PX, guii ölçümü): 8 işçi RAM'i %99,5'e çıkardı → işçi başına ~5 GB bütçe (bu makinede 31 GB → 6 işçi).
    assert isci == max(1, min(8, cekirdek, ram // 5)), (isci, cekirdek, ram)
    assert f" -n {isci} --dist loadgroup" in _komut_satiri(cikti)
    assert "3 passed" in cikti, f"testler xdist işçisinde koşmadı ya da işçi sayısı süiti DARALTTI:\n{cikti[-1500:]}"
    d = _damga(depo)
    assert d["head"] == _head(depo) and d["kip"] == "TAM", d


def test_KRITIK_xdist_YOKKEN_SERI_ve_UYARI_yayin_DURMAZ_damga_yazilir(depo, tmp_path):
    _testler(depo, _SERIDE)
    sarmal = tmp_path / "xdistsiz_python.cmd"
    sarmal.write_text(_SARMAL.format(py=sys.executable), encoding="ascii")
    rc, cikti = _kos(depo, python=str(sarmal))
    assert rc == 0, cikti[-1500:]
    assert "UYARI: pytest-xdist kurulu degil - suit SERI kosuyor" in cikti, cikti[-1500:]
    assert " -n " not in _komut_satiri(cikti) and "paralel:" not in cikti
    assert "3 passed" in cikti
    assert _damga(depo)["kip"] == "TAM"


def test_KRITIK_Isci_0_elle_SERI_TAM_kip_damga_yazilir(depo):
    _testler(depo, _SERIDE)
    rc, cikti = _kos(depo, "-Isci", "0")
    assert rc == 0, cikti[-1500:]
    assert "-Isci 0: suit SERI" in cikti and " -n " not in _komut_satiri(cikti), cikti[-1500:]
    assert "3 passed" in cikti
    assert _damga(depo)["kip"] == "TAM"


def test_KRITIK_kancali_kip_SERI_bekci_isciye_gecmez_damgaya_DOKUNMAZ(depo):
    _testler(depo, _SERIDE)
    y = _damga_yaz(depo, zaman=12345)
    once = y.read_bytes()
    rc, cikti = _kos(depo, "-PytestOnek", f"{sys.executable},-m,pytest")
    assert rc == 0, cikti[-1500:]
    assert "denetim kancasi: suit SERI" in cikti and " -n " not in _komut_satiri(cikti), cikti[-1500:]
    assert y.read_bytes() == once


def test_KRITIK_paralel_KIRMIZI_cikis_kodu_TASINIR_eski_damga_SILINIR_kirmizi_ADIYLA(depo):
    capraz.paket_yoksa_atla("xdist", sebep="pytest-xdist (requirements-test.txt) — paralel Y30")
    _testler(depo, _KIRMIZI)
    y = _damga_yaz(depo)
    rc, cikti = _kos(depo)
    assert rc == 1 and "YAYIN DURDU" in cikti, f"rc={rc}\n{cikti[-1500:]}"
    assert " --dist loadgroup" in _komut_satiri(cikti)
    assert not y.exists(), "paralel kırmızı süitten sonra eski damga DURUYOR"
    assert re.search(r"^FAILED \S*test_y176_ornek\.py::test_duser\b", cikti, re.M), cikti[-1500:]
    assert "1 failed, 3 passed" in cikti
