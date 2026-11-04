# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.16 (B-10.75) — `scripts/install_hotspot_task.ps1`'in ürettiği VBS başlatıcı Windows PowerShell 5.1'i (System32 tam yolu) çağırır.

NEDEN: Mobile Hotspot WinRT API'si PowerShell 7'de YOK ("Operation is not supported on this platform (0x80131539)"); `pwsh`
ile koşan görev netsh yedeğine düşer, o da yönetici ister ve SESSİZCE başarısız olur → ESP bobinleri (6-8) bağlanamaz
(2026-09-10 sahada ölçüldü). Betik bunu `$Ps51 = <SystemRoot>\\System32\\WindowsPowerShell\\v1.0\\powershell.exe` ile çözüyor,
ama hiçbir test ÜRETİLEN VBS'e bakmıyordu: `$Ps51` → pwsh mutantı bugün YEŞİL (plan B-10.75).

ÖLÇÜM: betik GERÇEKTEN pwsh'ta koşar; zamanlanmış görev cmdlet'leri (`Register-ScheduledTask`, `Unregister-ScheduledTask`,
`New-ScheduledTask*`) GÖLGE işlevlerdir — gerçek Görev Zamanlayıcı'ya ASLA gidilmez: gölgelerin çözüldüğü (`Get-Command` →
Function) betikten ÖNCE denetlenir, değilse sarmalayıcı 99 ile çıkar. `LOCALAPPDATA` geçici dizine yönlenir (VBS ve günlük
oraya yazılır). Üretilen VBS okunur: yorumlayıcı = System32 altındaki WindowsPowerShell v1.0 `powershell.exe`, `pwsh` YOK;
görev `wscript.exe` + bu VBS ile kaydedilir.
MUTASYON: `$Ps51` → `pwsh` → KIRMIZI.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "install_hotspot_task.ps1"
PWSH = shutil.which("pwsh")

# D5-L (L-1): platform (Windows) atlaması eser yokluğu DEĞİL — ayrı kalır; pwsh ARAÇ yokluğu ZORUNLU kipte DÜŞER
pytestmark = [
    pytest.mark.skipif(os.name != "nt", reason="Windows yok"),
    pytest.mark.skipif(PWSH is None and not capraz.ZORUNLU, reason="pwsh yok"),
]

_SARMAL = r"""
param([string]$Betik, [string]$Ps1, [string]$Kayit)
$ErrorActionPreference = 'Stop'
function global:Register-ScheduledTask {
  param($TaskName, $Action, $Trigger, $Settings, [switch]$Force)
  Add-Content -LiteralPath $Kayit -Value (ConvertTo-Json -Compress @{ cagri = 'Register'; ad = $TaskName; exe = $Action.Execute; arg = $Action.Argument; gizli = $Settings.Hidden })
  [pscustomobject]@{ TaskName = $TaskName }
}
function global:Unregister-ScheduledTask { param($TaskName, [switch]$Confirm) Add-Content -LiteralPath $Kayit -Value '{"cagri":"Unregister"}' }
function global:New-ScheduledTaskAction { param($Execute, $Argument) [pscustomobject]@{ Execute = $Execute; Argument = $Argument } }
function global:New-ScheduledTaskTrigger { param([switch]$AtLogOn, [switch]$Once, $At, $RepetitionInterval, $User) [pscustomobject]@{ Repetition = $RepetitionInterval } }
function global:New-ScheduledTaskSettingsSet { param([switch]$AllowStartIfOnBatteries, [switch]$DontStopIfGoingOnBatteries, $ExecutionTimeLimit) [pscustomobject]@{ Hidden = $false } }
foreach ($ad in 'Register-ScheduledTask', 'Unregister-ScheduledTask', 'New-ScheduledTaskAction', 'New-ScheduledTaskTrigger', 'New-ScheduledTaskSettingsSet') {
  if ((Get-Command $ad).CommandType -ne 'Function') { Write-Output "GOLGE DEVREDE DEGIL: $ad"; exit 99 }
}
& $Betik -Ps1Yolu $Ps1
exit $LASTEXITCODE
"""


def _kos(tmp_path: Path):
    yerel = tmp_path / "LocalAppData"
    yerel.mkdir()
    ps1 = tmp_path / "runtime" / "start_hotspot.ps1"
    ps1.parent.mkdir()
    ps1.write_text("# sahte start_hotspot (koşturulmaz)\n", encoding="utf-8")
    sarmal = tmp_path / "sarmal.ps1"
    sarmal.write_text(_SARMAL, encoding="utf-8-sig")
    kayit = tmp_path / "gorev_kaydi.jsonl"
    kayit.write_text("", encoding="utf-8")
    env = {**os.environ, "LOCALAPPDATA": str(yerel)}
    r = subprocess.run(
        [
            PWSH,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(sarmal),
            str(BETIK),
            str(ps1),
            str(kayit),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )
    assert "GOLGE DEVREDE DEGIL" not in r.stdout, f"görev cmdlet gölgesi devrede değil — betik KOŞTURULMADI: {r.stdout}"
    cagrilar = [json.loads(s) for s in kayit.read_text(encoding="utf-8").splitlines() if s.strip()]
    return r, yerel / "PEMF_System" / "start_hotspot_hidden.vbs", ps1, cagrilar


def test_KRITIK_VBS_Windows_PowerShell_51_TAM_YOLUNU_cagirir_pwsh_DEGIL(tmp_path):
    r, vbs, ps1, _ = _kos(tmp_path)
    assert r.returncode == 0, f"betik başarısız ({r.returncode}): {r.stdout}\n{r.stderr}"
    assert vbs.is_file(), "VBS başlatıcı üretilmedi"
    metin = vbs.read_text(encoding="ascii")
    m = re.search(r'^ps51 = "([^"]+)"\s*$', metin, re.M)
    assert m, f"VBS'te yorumlayıcı ataması (ps51 = \"…\") yok:\n{metin}"
    beklenen = (
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    )
    assert os.path.normcase(m.group(1)) == os.path.normcase(str(beklenen)), (
        f"VBS görevi {m.group(1)!r} ile koşturuyor — Mobile Hotspot WinRT API'si yalnız Windows PowerShell 5.1'de var; "
        f"pwsh ile görev SESSİZCE düşer (D5.16 / B-10.75). Beklenen: {beklenen}"
    )
    assert "pwsh" not in metin.lower(), f"VBS pwsh'a başvuruyor:\n{metin}"
    assert re.search(r'^ps1 = "' + re.escape(str(ps1)) + r'"\s*$', metin, re.M), (
        f"VBS verilen start_hotspot.ps1'e işaret etmiyor:\n{metin}"
    )


def test_KRITIK_gorev_wscript_ile_VBS_i_GIZLI_kaydeder(tmp_path):
    r, vbs, _ps1, cagrilar = _kos(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    kayitlar = [c for c in cagrilar if c.get("cagri") == "Register"]
    assert len(kayitlar) == 1, f"görev tam bir kez kaydedilmeli: {cagrilar}"
    k = kayitlar[0]
    assert k["ad"] == "PEMF-Hotspot" and str(k["exe"]).lower() == "wscript.exe", k
    assert str(vbs) in str(k["arg"]), f"görev üretilen VBS'i çalıştırmıyor: {k}"
    assert k["gizli"] is True, f"görev gizli değil (her 3 dk pencere): {k}"


def test_KRITIK_gorev_betigi_BEKCI_kipinde_cagirir_PEMF_kapaliyken_ACMAZ(tmp_path):
    """Sahip 2026-11-04: görev (logon + her 3 dk) hotspot'u PEMF'e BAKMADAN açıyordu → PEMF kapatılınca da geri geliyordu.
    VBS'in çalıştırdığı komut satırı start_hotspot.ps1'i `-BekciKipi` ile çağırmalı (backend yoksa betik dokunmadan çıkar)."""
    r, vbs, _ps1, _ = _kos(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    satir = [s for s in vbs.read_text(encoding="ascii").splitlines() if s.startswith("sh.Run ")]
    assert len(satir) == 1, f"VBS'te tek bir sh.Run satırı olmalı:\n{vbs.read_text(encoding='ascii')}"
    assert re.search(r'-File " & q & ps1 & q & " -BekciKipi", 0, False\s*$', satir[0]), (
        f"görev betiği bekçi kipinde çağırmıyor (PEMF kapalıyken hotspot'u yeniden açar): {satir[0]}"
    )
