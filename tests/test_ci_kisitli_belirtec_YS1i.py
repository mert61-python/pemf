# -*- coding: utf-8 -*-
"""YS1i (GitHub windows-latest 3bec8be9): koşucu `runneradmin` YÜKSELTİLMİŞ → ürünün sır / veri kökü kilidi Administrators'a tam yetki
verdiği için ACL / ikinci-hesap benzetimleri ölçülemedi (24 kırmızı + 3 hata, kapsam %99,98). Süit, ürünün ve geliştiricinin koştuğu gibi
UAC-SÜZGEÇLİ belirteçle koşar: `scripts/ci_kisitli_belirtec.py` (Administrators yalnız-ret, en az ayrıcalık, bütünlük ORTA).

KAPI: (1) kısıtlı yol (`--zorla`) çocukta yönetici YOK, Administrators ETKİN DEĞİL; (2) çocuğun çıkış kodu AYNEN döner (kırmızı yutulmaz);
(3) yükseltilmemiş süreçte komut doğrudan koşar; (4) komutsuz kullanım → 2; (5) CI pytest adımı sarmalayıcıyla ve `shell: bash` (pwsh 7'nin
PSModulePath sızıntısı yok) koşar.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "ci_kisitli_belirtec.py"

_SONDA = r"""
import ctypes, sys
from ctypes import wintypes as wt
adm = bool(ctypes.windll.shell32.IsUserAnAdmin())
adv = ctypes.WinDLL("advapi32", use_last_error=True)
sid = ctypes.create_string_buffer(68); n = wt.DWORD(68); adv.CreateWellKnownSid(26, None, sid, ctypes.byref(n))
uye = wt.BOOL(); adv.CheckTokenMembership(None, sid, ctypes.byref(uye))
print(f"SONDA admin={adm} etkin={bool(uye.value)}", flush=True)
sys.exit(int(sys.argv[1]))
"""

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows belirteç API'si")


def _modul():
    spec = importlib.util.spec_from_file_location("ci_kisitli_belirtec_ys1i", BETIK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _kos(*arg: str, cikis: int = 0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BETIK), *arg, sys.executable, "-c", _SONDA, str(cikis)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        timeout=120,
    )


def test_KRITIK_kisitli_yolda_cocuk_YONETICI_DEGIL_ve_cikis_kodu_AYNEN_doner():
    c = _kos("--zorla", cikis=7)
    assert c.returncode == 7, (c.returncode, c.stdout, c.stderr)
    assert "UAC-süzgeçli belirteç" in c.stdout
    assert "SONDA admin=False etkin=False" in c.stdout, c.stdout


def test_KRITIK_yukseltilmemis_surecte_DOGRUDAN_kosar_cikis_kodu_aynen():
    if _modul().yukseltilmis_mi():
        pytest.skip("bu süreç yükseltilmiş — doğrudan kol yalnız yükseltilmemişte ölçülür (kısıtlı kol üstteki testte)")
    c = _kos(cikis=3)
    assert c.returncode == 3 and "UAC-süzgeçli" not in c.stdout and "SONDA admin=False" in c.stdout, (
        c.stdout,
        c.stderr,
    )


def test_komutsuz_kullanim_2():
    c = subprocess.run(
        [sys.executable, str(BETIK)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    assert c.returncode == 2 and "kullanım" in c.stderr


def test_main_dogrudan_kol_ve_zorla_ayristirma(monkeypatch):
    m = _modul()
    cagri = []
    monkeypatch.setattr(m, "yukseltilmis_mi", lambda: False)
    monkeypatch.setattr(m.subprocess, "call", lambda argv: cagri.append(("dogrudan", argv)) or 5)
    monkeypatch.setattr(m, "kisitli_kos", lambda argv: cagri.append(("kisitli", argv)) or 6)
    assert m.main(["a", "b"]) == 5
    assert m.main(["--zorla", "a"]) == 6
    monkeypatch.setattr(m, "yukseltilmis_mi", lambda: True)
    assert m.main(["a"]) == 6
    assert cagri == [("dogrudan", ["a", "b"]), ("kisitli", ["a"]), ("kisitli", ["a"])]


def test_KRITIK_CI_pytest_adimi_KISITLI_belirtecle_ve_bash_altinda_kosar():
    is_ = yaml.safe_load((KOK / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))["jobs"]["backend"]
    adim = [a for a in is_["steps"] if "pytest tests" in str(a.get("run", ""))]
    assert len(adim) == 1, adim
    assert str(adim[0]["run"]).startswith("python scripts/ci_kisitli_belirtec.py pytest tests "), adim[0]["run"]
    assert adim[0].get("shell") == "bash", (
        "pytest adımı pwsh altında — PSModulePath alt powershell.exe 5.1'e sızar (Get-Acl)"
    )
