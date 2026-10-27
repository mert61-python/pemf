# -*- coding: utf-8 -*-
"""YLI-A3.3 (L4 · O-13.1 NSIS ikizi) — PREUNINSTALL ACİL DURDUR tek satırı yanıtı PEMF İMZASIYLA yorumlamalı.

Launcher (`backend.rs::durdur_yanitini_yorumla`, LN L4) ve `scripts/pemf_teardown.ps1` imzasız 2xx'i "uç yok" sayıp operatörün ACİL
DURDUR ucuna düşer; "doğrulandı" yalnız `confirmed:true` + `status:success` + imza. NSIS satırı hâlâ yalnız `confirmed`'a bakıyor ve
ACİL DURDUR'a yalnız İSTİSNADA düşüyor (LN "SONRAKİ").

SAHTE SUNUCUSUZ: hooks.nsi'deki GERÇEK `-Command` metni (NSIS `$$` → `$`, `$2` → port) koşturulur; önüne `Invoke-RestMethod`'u
GÖLGELEYEN bir PowerShell işlevi eklenir (işlev > cmdlet önceliği) → ağ yok, dinleyici yok. Çağrılan uçlar bir dosyaya yazılır.
32-bit PowerShell (kaldırıcı x86) varsa o kullanılır.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[2]
if not (KOK / "launcher").is_dir():  # kalıcı kapı olarak tests/ altına taşınırsa
    KOK = Path(__file__).resolve().parents[1]
HOOKS = KOK / "launcher" / "app" / "windows" / "hooks.nsi"

_SAHTE = r"""
function Invoke-RestMethod { param($Uri, $Method, $ContentType, $Body, $TimeoutSec)
  Add-Content -LiteralPath $env:A3_CAGRI -Value $Uri
  $kip = $env:A3_KIP
  if ($Uri -like '*kapanis_durdur') {
    switch ($kip) {
      'yabanci' { return [pscustomobject]@{ confirmed = $true } }
      'html'    { return '<!doctype html><html><body>baska servis</body></html>' }
      'pemf'    { return [pscustomobject]@{ status = 'success'; confirmed = $true; stmStopped = $true; mqttResults = @() } }
      'pemf_teyitsiz' { return [pscustomobject]@{ status = 'partial'; confirmed = $false; stmStopped = $true; mqttResults = @() } }
      'eski'    { throw 'The remote server returned an error: (405) Method Not Allowed.' }
    }
  } else {
    switch ($kip) {
      'eski'    { return [pscustomobject]@{ status = 'success'; stmStopped = $true; mqttResults = @(); reason = 'manual' } }
      'yabanci' { return [pscustomobject]@{ confirmed = $true } }
      default   { return [pscustomobject]@{ status = 'success'; confirmed = $true; stmStopped = $true; mqttResults = @() } }
    }
  }
}
"""


def _estop_komutu(port: int) -> str:
    m = re.search(r"!macro\s+NSIS_HOOK_PREUNINSTALL\b(.*?)!macroend", HOOKS.read_text(encoding="utf-8"), re.DOTALL)
    assert m, "PREUNINSTALL yok"
    satir = next(
        s.strip()
        for s in m.group(1).splitlines()
        if s.strip().startswith("nsExec::ExecToStack") and "kapanis_durdur" in s
    )
    k = re.search(r'-Command "(.*)"\'\s*$', satir)
    assert k, satir[:120]
    return k.group(1).replace("$$", "$").replace("$2", str(port))


def _ps() -> str:
    s = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    for p in (
        s / "SysWOW64" / "WindowsPowerShell" / "v1.0" / "powershell.exe",
        s / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe",
    ):
        if p.is_file():
            return str(p)
    # D5-L TUR 2: erken dönüş + koşulsuz skip ZORUNLU kipte de atlıyordu — araç yokluğu ZORUNLU kipte DÜŞER
    capraz.atla("powershell yok")


def _kos(kip: str, tmp_path: Path) -> tuple[int, str, list[str]]:
    cagri = tmp_path / f"cagri_{kip}.txt"
    r = subprocess.run(
        [
            _ps(),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            _SAHTE + "\n" + _estop_komutu(48123),
        ],
        env={**os.environ, "A3_CAGRI": str(cagri), "A3_KIP": kip},
        capture_output=True,
        timeout=90,
    )
    uclar = [u.rsplit("/", 1)[-1] for u in cagri.read_text(encoding="utf-8-sig").split()] if cagri.exists() else []
    return r.returncode, (r.stdout + r.stderr).decode("cp857", errors="replace").strip(), uclar


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell")


def test_KRITIK_A3_3_yabanci_confirmed_true_DOGRULANDI_sayilmaz_ACIL_DURDURa_duser(tmp_path):
    """Aynı portta yabancı servis `{"confirmed":true}` → DOĞRULANDI (çıkış 0) DEĞİL; launcher ikizi gibi ACİL DURDUR ucu da denenir."""
    rc, cikti, uclar = _kos("yabanci", tmp_path)
    print(f"A3OLC|nsis|yabanci|rc={rc}|{cikti}|{uclar}")
    assert rc != 0, (
        f"imzasız yabancı yanıt DOĞRULANDI sayıldı (MessageBox 'bobinleri ELLE kontrol edin' çıkmaz): {cikti!r}"
    )
    assert uclar == ["kapanis_durdur", "emergency_stop"], f"imzasız yanıtta ACİL DURDUR ucuna düşülmedi: {uclar}"


def test_KRITIK_A3_3_imzasiz_2xx_html_ACIL_DURDUR_ucuna_duser(tmp_path):
    """Kapanış ucu 200 + HTML (sözleşme dışı) → launcher `UcYok` → ACİL DURDUR; NSIS de düşmeli."""
    rc, cikti, uclar = _kos("html", tmp_path)
    print(f"A3OLC|nsis|html|rc={rc}|{cikti}|{uclar}")
    assert uclar == ["kapanis_durdur", "emergency_stop"], f"sözleşme dışı 2xx'te ACİL DURDUR ucuna düşülmedi: {uclar}"


def test_A3_3_KARSIT_gercek_imzali_teyit_DOGRULANDI_tek_istek(tmp_path):
    rc, cikti, uclar = _kos("pemf", tmp_path)
    print(f"A3OLC|nsis|pemf|rc={rc}|{cikti}|{uclar}")
    assert rc == 0 and cikti.startswith("OK uc=1") and uclar == ["kapanis_durdur"], (rc, cikti, uclar)


def test_A3_3_KARSIT_imzali_teyitsiz_cikis_2_ikinci_uc_YOK(tmp_path):
    rc, cikti, uclar = _kos("pemf_teyitsiz", tmp_path)
    print(f"A3OLC|nsis|pemf_teyitsiz|rc={rc}|{cikti}|{uclar}")
    assert rc == 2 and uclar == ["kapanis_durdur"], (rc, cikti, uclar)


def test_A3_3_KARSIT_eski_backend_405_ACIL_DURDUR_eski_imza_teyitsiz(tmp_path):
    rc, cikti, uclar = _kos("eski", tmp_path)
    print(f"A3OLC|nsis|eski|rc={rc}|{cikti}|{uclar}")
    assert rc == 2 and cikti.startswith("OK uc=2") and uclar == ["kapanis_durdur", "emergency_stop"], (rc, cikti, uclar)


def test_A3_3_satir_NSIS_azami_dizge_uzunlugunu_asmaz():
    """NSIS_MAX_STRLEN (standart derleme 1024): `nsExec` argümanı (çözülmüş `$2` = 5 hane dahil) sınırı aşarsa makensis keser."""
    m = re.search(r"!macro\s+NSIS_HOOK_PREUNINSTALL\b(.*?)!macroend", HOOKS.read_text(encoding="utf-8"), re.DOTALL)
    satir = next(
        s.strip()
        for s in m.group(1).splitlines()
        if s.strip().startswith("nsExec::ExecToStack") and "kapanis_durdur" in s
    )
    arguman = re.search(r"'(.*)'\s*$", satir).group(1).replace("$$", "$").replace("$2", "65535")
    print(f"A3OLC|nsis|uzunluk|{len(arguman)}")
    assert len(arguman) < 1000, len(arguman)
