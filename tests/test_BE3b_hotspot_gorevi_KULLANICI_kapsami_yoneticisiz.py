# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""BE 3b · Y231 — `scripts/install_hotspot_task.ps1` `PEMF-Hotspot` görevini YÖNETİCİSİZ kurulabilecek biçimde (bu kullanıcının oturum
açılışına bağlı tetikleyici) kaydeder.

ÖLÇÜLEN KÖK (31.10, sahip makinesi): görev `New-ScheduledTaskTrigger -AtLogOn` KULLANICISIZ ("herhangi bir kullanıcı") kuruluyordu →
Görev Zamanlayıcı yönetici ister → her açılışta `hotspot.log`: "gorev kurulamadi: Erişim engellendi". Görev hiç olmadığı için Windows
PEMF-Gateway'i bağlı cihaz yokken ~4 dk'da kapatınca geri açan YOKTU ("Kablosuz Bağlantı: Kapalı" doğruydu). `-User <USERDOMAIN\\USERNAME>`
ile aynı kayıt yöneticisiz geçiyor (koordinatör ölçtü, deneme görevi silindi).
⚠️ BE 3b-2 (31.10, GERÇEK kurulumda ölçüldü): yalnız oturum açılışı tetikleyicisi olan görevin `NextRunTime`'ı BOŞ — tekrarlar ancak bir
SONRAKİ oturum açılışında başlar; uyku / uyanma ile kullanılan makinede görev hiç koşmaz. Bu yüzden ikinci tetikleyici: kurulum anından
(başlatıcı görevi her uygulama açılışında yeniden kurar) başlayan, 3 dk'da bir tekrarlayan zaman tetikleyicisi (kullanıcı görevi — yönetici yok).

ÖLÇÜM: betik GERÇEKTEN pwsh'ta koşar; görev cmdlet'leri GÖLGE (gerçek Görev Zamanlayıcı'ya ASLA gidilmez — gölge çözümü betikten ÖNCE
denetlenir, değilse 99). Kaydedilen: oturum açılışı tetikleyicisinin `-User` değeri; `Register-ScheduledTask`'a yönetici ilkesi
(`-RunLevel Highest`, `-Principal`, `-User SYSTEM`) GEÇMEZ; tekrar aralığı (≤ 3 dk) ve profil kapısı (`-Kaldir`) aynen.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "install_hotspot_task.ps1"
PWSH = shutil.which("pwsh")

pytestmark = [
    pytest.mark.skipif(os.name != "nt", reason="Windows yok"),
    pytest.mark.skipif(PWSH is None and not capraz.ZORUNLU, reason="pwsh yok"),
]

_SARMAL = r"""
param([string]$Betik, [string]$Ps1, [string]$Kayit, [string]$Kip)
$ErrorActionPreference = 'Stop'
function global:Register-ScheduledTask {
  param($TaskName, $Action, $Trigger, $Settings, $Principal, $User, $Password, $RunLevel, [switch]$Force)
  Add-Content -LiteralPath $Kayit -Value (ConvertTo-Json -Compress @{
    cagri = 'Register'; ad = $TaskName; exe = $Action.Execute
    principal = [bool]$Principal; user = [string]$User; runlevel = [string]$RunLevel
    tetikler = @($Trigger | ForEach-Object { @{ logon = [bool]$_.AtLogOn; once = [bool]$_.Once; user = [string]$_.User; at_fark_sn = $_.AtFarkSn; tekrar_dk = $_.Repetition.Dk } })
  })
  [pscustomobject]@{ TaskName = $TaskName }
}
function global:Unregister-ScheduledTask { param($TaskName, [switch]$Confirm) Add-Content -LiteralPath $Kayit -Value '{"cagri":"Unregister"}' }
function global:New-ScheduledTaskAction { param($Execute, $Argument) [pscustomobject]@{ Execute = $Execute; Argument = $Argument } }
function global:New-ScheduledTaskTrigger {
  param([switch]$AtLogOn, [switch]$Once, $At, $RepetitionInterval, $User)
  $fark = if ($At) { [math]::Round((([datetime]$At) - (Get-Date)).TotalSeconds) } else { $null }
  $dk = if ($RepetitionInterval) { ([timespan]$RepetitionInterval).TotalMinutes } else { $null }
  [pscustomobject]@{ AtLogOn = [bool]$AtLogOn; Once = [bool]$Once; User = $User; AtFarkSn = $fark; Repetition = [pscustomobject]@{ Dk = $dk } }
}
function global:New-ScheduledTaskSettingsSet { param([switch]$AllowStartIfOnBatteries, [switch]$DontStopIfGoingOnBatteries, $ExecutionTimeLimit) [pscustomobject]@{ Hidden = $false } }
function global:New-ScheduledTaskPrincipal { param($UserId, $LogonType, $RunLevel) Add-Content -LiteralPath $Kayit -Value '{"cagri":"Principal"}'; [pscustomobject]@{ UserId = $UserId } }
foreach ($ad in 'Register-ScheduledTask', 'Unregister-ScheduledTask', 'New-ScheduledTaskAction', 'New-ScheduledTaskTrigger', 'New-ScheduledTaskSettingsSet', 'New-ScheduledTaskPrincipal') {
  if ((Get-Command $ad).CommandType -ne 'Function') { Write-Output "GOLGE DEVREDE DEGIL: $ad"; exit 99 }
}
if ($Kip -eq 'kaldir') { & $Betik -Kaldir } else { & $Betik -Ps1Yolu $Ps1 }
exit $LASTEXITCODE
"""


def _kos(tmp_path: Path, kip: str = "kur"):
    yerel = tmp_path / "LocalAppData"
    yerel.mkdir()
    ps1 = tmp_path / "runtime" / "start_hotspot.ps1"
    ps1.parent.mkdir()
    ps1.write_text("# sahte start_hotspot (koşturulmaz)\n", encoding="utf-8")
    sarmal = tmp_path / "sarmal.ps1"
    sarmal.write_text(_SARMAL, encoding="utf-8-sig")
    kayit = tmp_path / "gorev_kaydi.jsonl"
    kayit.write_text("", encoding="utf-8")
    env = {**os.environ, "LOCALAPPDATA": str(yerel), "USERDOMAIN": "KLINIK-PC", "USERNAME": "hekim"}
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
            kip,
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
    return r, cagrilar, yerel / "PEMF_System" / "hotspot.log"


def test_KRITIK_oturum_acilisi_tetikleyicisi_BU_KULLANICIYA_bagli_yoneticisiz_kurulur(tmp_path):
    r, cagrilar, gunluk = _kos(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    kayit = [c for c in cagrilar if c.get("cagri") == "Register"]
    assert len(kayit) == 1, cagrilar
    logon = [t for t in kayit[0]["tetikler"] if t["logon"]]
    assert len(logon) == 1, kayit[0]
    assert logon[0]["user"] == r"KLINIK-PC\hekim", (
        f"oturum açılışı tetikleyicisi kullanıcısız ({logon[0]['user']!r}) — 'herhangi bir kullanıcı' tetikleyicisi YÖNETİCİ ister, "
        "standart hesapta 'Erişim engellendi' ile görev HİÇ kurulmaz (Y231, hotspot.log)"
    )


def test_KRITIK_BE3b2_oturum_ACIKKEN_de_kurulumdan_itibaren_3_dk_da_bir_kosar(tmp_path):
    """Yalnız oturum açılışı tetikleyicisi → `NextRunTime` boş (gerçek kurulumda ölçüldü): uyku / uyanmayla kullanılan makinede görev HİÇ koşmaz."""
    _r, cagrilar, _g = _kos(tmp_path)
    k = [c for c in cagrilar if c.get("cagri") == "Register"][0]
    zaman = [t for t in k["tetikler"] if t["once"]]
    assert len(zaman) == 1, (
        f"kurulum anından başlayan zaman tetikleyicisi YOK — görev ancak bir sonraki oturum açılışında koşar: {k}"
    )
    assert zaman[0]["at_fark_sn"] is not None and -60 <= zaman[0]["at_fark_sn"] <= 120, zaman[0]
    assert zaman[0]["tekrar_dk"] == 3, zaman[0]
    assert [t["tekrar_dk"] for t in k["tetikler"] if t["logon"]] == [3], k


def test_KRITIK_yonetici_ilkesi_YOK_tekrar_araligi_ve_gizlilik_AYNEN(tmp_path):
    _r, cagrilar, _g = _kos(tmp_path)
    k = [c for c in cagrilar if c.get("cagri") == "Register"][0]
    assert not k["principal"] and not k["user"] and not k["runlevel"], f"yönetici gerektiren ilke geçildi: {k}"
    assert not any(c.get("cagri") == "Principal" for c in cagrilar), cagrilar
    assert str(k["exe"]).lower() == "wscript.exe" and k["ad"] == "PEMF-Hotspot", k


def test_profil_kapisi_Kaldir_AYNEN(tmp_path):
    r, cagrilar, _g = _kos(tmp_path, "kaldir")
    assert r.returncode == 0, r.stdout + r.stderr
    assert [c["cagri"] for c in cagrilar] == ["Unregister"], cagrilar
