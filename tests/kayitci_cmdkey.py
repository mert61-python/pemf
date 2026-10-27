# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Test aparatı: KAYITÇI `cmdkey` — testler GERÇEK Windows kimlik kasasına YAZMAZ, ondan OKUMAZ.

Kaynak: e035b25 (1-B §9 #10 hijyeni; `test_teardown_system_kasasi`) — 1-D'de (1-C §9 #16) ortak modüle alındı ve
`test_teardown_kimlik_dogrulama` da buna geçti (o dosya Python'dan yalın `cmdkey /add:PEMF_GATE_<uuid>` ile gerçek
kasaya yazıp `finally`'de siliyordu: her tam süitte 8 gerçek kasa çağrısı; süreç arada ölürse sahte kayıt kalırdı).

Sürücüler/betikler `cmdkey`i ADIYLA çağırır → PowerShell PATH sırasıyla çözer → PATH'in başındaki kayıtçı `cmdkey.cmd`
gerçek `System32\\cmdkey.exe`den ÖNCE bulunur. Kayıtçı sahte kasa dosyası üzerinde gerçek cmdkey'in tel sözleşmesini taklit
eder (ölçülen gerçek davranış, bkz. `scripts/pemf_teardown.ps1`):
  /generic:<ad> ve /add:<ad> → ekler (rc 0) · /delete:<ad> → varsa siler (rc 0), yoksa "CMDKEY: Element not found." (rc 1) ·
  /list:<ad> → varsa ad 2 KEZ (başlık + "Target:"), yoksa "* NONE *" (ad 1 kez) · /list → her kayıt için "Target: <ad>".
Her çağrı satır olarak kaydedilir (`cagrilar`): betiğin çağrılarının KAYITÇIYA geldiği iddia edilir (gelmeseydi gerçek
kasaya gitmiş olurdu). Python tarafı kayıtçıyı TAM YOLLA çağırır (`cmdkey`) — Windows CreateProcess System32'yi PATH'ten
ÖNCE arar, yalın "cmdkey" GERÇEK aracı bulurdu; Python'dan yalın `cmdkey` süreci başlatılırsa test KIRMIZI (bekçi).
DEV-C3 (D1B §8 #10 · D1C §7 #16): bekçi tüm süreç başlatma yollarında (Popen tabanı + os.system/spawnv/startfile), `kur`
PATH çözümünü kanıtlar; kapı `tests/test_kayitci_cmdkey_GERCEK_kasaya_gitmez_DEV_C3.py`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import types
from pathlib import Path

KAYITCI_CMD = (
    "@echo off\r\n"
    'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0kayitci_cmdkey.ps1" %*\r\n'
    "exit /b %ERRORLEVEL%\r\n"
)
KAYITCI_PS1 = r"""
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$a)
$kasa = $env:PEMF_SAHTE_KASA
$kayit = $env:PEMF_CMDKEY_KAYIT
if (-not $kasa -or -not $kayit) { 'kayitci: PEMF_SAHTE_KASA / PEMF_CMDKEY_KAYIT yok'; exit 99 }
if (-not $a) { $a = @() }
Add-Content -LiteralPath $kayit -Value ($a -join ' ') -Encoding UTF8
$var = @()
if (Test-Path -LiteralPath $kasa) { $var = @(Get-Content -LiteralPath $kasa -Encoding UTF8 | Where-Object { $_ -ne '' }) }
$ilk = if ($a.Count -gt 0) { $a[0] } else { '' }
if ($ilk -like '/generic:*' -or $ilk -like '/add:*') {
    $ad = $ilk.Substring($ilk.IndexOf(':') + 1)
    if ($var -notcontains $ad) { Add-Content -LiteralPath $kasa -Value $ad -Encoding UTF8 }
    'CMDKEY: Credential added successfully.'; exit 0
}
if ($ilk -like '/delete:*') {
    $ad = $ilk.Substring(8)
    if ($var -contains $ad) {
        Set-Content -LiteralPath $kasa -Value @($var | Where-Object { $_ -ne $ad }) -Encoding UTF8
        'CMDKEY: Credential deleted successfully.'; exit 0
    }
    'CMDKEY: Element not found.'; exit 1
}
if ($ilk -like '/list:*') {
    $ad = $ilk.Substring(6)
    "Currently stored credentials for ${ad}:"
    ''
    if ($var -contains $ad) { "    Target: $ad"; '    Type: Generic'; '    User: x' } else { '* NONE *' }
    exit 0
}
if ($ilk -eq '/list') {
    'Currently stored credentials:'
    ''
    if ($var.Count -eq 0) { '* NONE *' } else { foreach ($v in $var) { "    Target: $v"; '    Type: Generic'; '' } }
    exit 0
}
'kayitci: bilinmeyen cmdkey komutu'; exit 2
"""


def kur(tmp_path: Path, monkeypatch) -> types.SimpleNamespace:
    """PATH başında kayıtçı cmdkey + boş sahte kasa + çağrı kaydı; Python'dan yalın `cmdkey` YASAK (bekçi)."""
    kok = tmp_path / "kayitci_cmdkey"
    kok.mkdir()
    (kok / "cmdkey.cmd").write_text(KAYITCI_CMD, encoding="ascii", newline="")
    (kok / "kayitci_cmdkey.ps1").write_text(KAYITCI_PS1, encoding="utf-8-sig")
    kasa = tmp_path / "sahte_kasa.txt"
    kasa.write_text("", encoding="utf-8")
    cagri = tmp_path / "cmdkey_cagrilari.txt"
    monkeypatch.setenv("PATH", f"{kok}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("PEMF_SAHTE_KASA", str(kasa))
    monkeypatch.setenv("PEMF_CMDKEY_KAYIT", str(cagri))
    monkeypatch.setenv("PEMF_KAYITCI_CMDKEY", str(kok / "cmdkey.cmd"))
    # PowerShell yalın `cmdkey`i PATH SIRASIYLA çözer; kayıtçı başta değilse torun süreçler GERÇEK kasaya gider → KIRMIZI.
    cozulen = shutil.which("cmdkey")
    assert cozulen and os.path.normcase(cozulen) == os.path.normcase(str(kok / "cmdkey.cmd")), (
        f"PATH'te yalın `cmdkey` kayıtçıya değil {cozulen!r}'e çözülüyor — gerçek kasaya düşülür"
    )
    # DEV-C3: bekçi süreç başlatmanın ORTAK noktasında (Popen._execute_child: run/call/check_output/Popen/asyncio) ve
    # os.system / os.spawnv / os.startfile'da; süreç BAŞLATILMADAN kırmızı. Eski bekçi yalnız subprocess.run'ı sarıyordu.
    gercek_yurut = subprocess.Popen._execute_child

    def _bekci_yurut(self, args, executable, *a, **k):
        _bekle(executable, args)
        return gercek_yurut(self, args, executable, *a, **k)

    monkeypatch.setattr(subprocess.Popen, "_execute_child", _bekci_yurut)

    def _sar(gercek, program_ve_argv):
        def _sarili(*a, **k):
            _bekle(*program_ve_argv(*a, **k))
            return gercek(*a, **k)

        return _sarili

    monkeypatch.setattr(os, "system", _sar(os.system, lambda komut: (None, komut)))
    for ad in ("spawnv", "spawnve"):
        if hasattr(os, ad):
            monkeypatch.setattr(os, ad, _sar(getattr(os, ad), lambda kip, yol, argv, *a: (yol, argv)))
    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", _sar(os.startfile, lambda yol, *a, **k: (None, [yol])))
    return types.SimpleNamespace(kok=kok, kasa=kasa, cagri=cagri)


_CMD_BAYRAKLARI = ("/c", "/k", "/s", "/q", "/d", "/r")


def _parcala(komut) -> list[str]:
    if isinstance(komut, (list, tuple)):
        return [os.fsdecode(p) if isinstance(p, (bytes, os.PathLike)) else str(p) for p in komut]
    metin = os.fsdecode(komut) if isinstance(komut, (bytes, os.PathLike)) else str(komut)
    return [a or b for a, b in re.findall(r'"([^"]*)"|(\S+)', metin)]


def _govde(parca: str) -> str:
    ad = re.split(r"[\\/]", parca.strip().strip('"'))[-1].lower()
    return ad.rsplit(".", 1)[0] if "." in ad else ad


def kasa_araci_mi(executable, args) -> bool:
    """Başlatılacak program (ya da `cmd /c`nin iç programı) adı `cmdkey` olan bir şey mi (yol / uzantı / büyük-küçük farksız)."""
    parca = _parcala(args)
    if executable:
        parca = [os.fsdecode(executable)] + parca[1:]
    if not parca:
        return False
    prog = _govde(parca[0])
    if prog == "cmdkey":
        return True
    if prog == "cmd":
        kalan = [p for p in parca[1:] if p.lower() not in _CMD_BAYRAKLARI]
        if kalan:
            return kasa_araci_mi(None, " ".join(kalan).strip().strip('"'))
    return False


def _bekle(executable, args) -> None:
    if kasa_araci_mi(executable, args):
        raise AssertionError(
            f"bu test GERÇEK cmdkey'i (kimlik kasası) başlatmak üzereydi: {args!r} — süreç BAŞLATILMADI; Python'dan adı "
            "cmdkey olan HİÇBİR program başlatılmaz, kayıtçı `kayitci_cmdkey.cmdkey()` kullanılmalı"
        )


def cagrilar(kayitci) -> list[str]:
    return kayitci.cagri.read_text(encoding="utf-8-sig").splitlines() if kayitci.cagri.exists() else []


def cmdkey(*args: str) -> subprocess.CompletedProcess:
    """KAYITÇI cmdkey (TAM YOL) — gerçek kasaya ASLA gitmez; kayıtçı kurulmamışsa KIRMIZI (sessiz geri düşüş yok).

    DEV-C3: kayıtçının PowerShell gövdesi DOĞRUDAN koşulur (`cmd /c ...\\cmdkey.cmd` DEĞİL): Python'dan adı cmdkey olan
    hiçbir program başlatılmaz → bekçi ve test kafesi (adı cmdkey olan programı reddeder) kayıtçıyı gerçek araçla
    karıştırmaz; eskiden bu yüzden kafeste 5 test kırmızıydı."""
    kayitci = os.environ.get("PEMF_KAYITCI_CMDKEY", "")
    assert kayitci and Path(kayitci).exists(), "kayıtçı cmdkey kurulmamış — gerçek kasaya düşülmez"
    betik = Path(kayitci).with_name("kayitci_cmdkey.ps1")
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(betik), *args],
        capture_output=True,
        timeout=30,
    )
