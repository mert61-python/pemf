# -*- coding: utf-8 -*-
"""`scripts/build_backend_exe.ps1`'in AI HAZIRLIK KAPISI bloğunu EXE BAŞLATMADAN koşturan sürücü (D0Ö.03/06).

Blok, PowerShell AYRIŞTIRICISIYLA betikten alınır ve GERÇEK metniyle çalıştırılır (kopya yok). `Start-Process`
bir işlevle gölgelenir: EXE başlatılmaz, o anda sürece GEÇECEK ortam (Process env) JSON'a yazılır.
Sağlık döngüsü `Start-Sleep`/`Invoke-RestMethod` sahteleriyle anında biter ("EXE açılmadı → kapı ATLANDI"
dalı). Gerçek EXE, ağ, port YOK. Betiğin kendi işlevleri (ör. kapı ortam yardımcıları) önce tanımlanır,
`Info/Warn/Die` ve süreç/ağ cmdlet'leri sonra sahtelerle ezilir.

Test modülü DEĞİL (adı `test_` ile başlamaz); `tests/` yolda olduğu için `import exe_kapisi_surucusu`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "build_backend_exe.ps1"
PWSH = shutil.which("pwsh")

#: Dış koşucunun/CI'nın ortama koyduğu yalıtım değişkenleri. Blok bunları KENDİSİ vermeli; miras alınırsa
#: kapı dış ortam yüzünden sahte-yeşil olurdu (koşucu PEMF_FW_AUTO_UPDATE=0 veriyor olabilir).
YALITIM_DEGISKENLERI = (
    "PEMF_FW_AUTO_UPDATE",
    "PEMF_STM_PORT",
    "PEMF_HOTSPOT",
    "PEMF_DATA_DIR",
    "PEMF_DEVICE_IDENTITY_DIR",
    "PEMF_SIMULATE",
    "PEMF_ESP_ENABLED",
    "SUPABASE_URL",
)

_SURUCU = r"""
param([string]$Betik, [string]$Kok, [string]$Cikti)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Betik, [ref]$tokens, [ref]$errs)
if ($errs) { throw "build betiği ayrıştırılamadı: $($errs | Out-String)" }
$blok = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.IfStatementAst] -and
    $n.Clauses[0].Item1.Extent.Text -match 'SkipAiGate' }, $true) | Select-Object -First 1
if (-not $blok) { throw "AI hazırlık kapısı bloğu bulunamadı (çıpa: '-not `$SkipAiGate')" }
foreach ($fn in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    Invoke-Expression $fn.Extent.Text
}
function Info { }
function Warn { }
function Die($m) { throw "DIE: $m" }
function Start-Sleep { }
function Invoke-RestMethod { throw "sahte: saglik yok" }
function Stop-Process { }
function Get-Process { @() }
$script:yakalanan = $null
function Start-Process {
    param($FilePath, $ArgumentList, $RedirectStandardOutput, $RedirectStandardError, [switch]$PassThru, $WindowStyle)
    $ortam = @{}
    foreach ($e in [Environment]::GetEnvironmentVariables('Process').GetEnumerator()) { $ortam[[string]$e.Key] = [string]$e.Value }
    $script:yakalanan = [ordered]@{ FilePath = [string]$FilePath; ArgumentList = @($ArgumentList | ForEach-Object { [string]$_ }); Env = $ortam }
    [pscustomobject]@{ Id = 0 }
}
$BuildRoot = $Kok
$dist = Join-Path $Kok 'dist'
$exe = Join-Path $dist 'PEMF_Backend\PEMF_Backend.exe'
New-Item -ItemType File -Force -Path $exe | Out-Null
$SkipAiGate = $false
$SkipProtect = $true
$once = @{}
foreach ($e in [Environment]::GetEnvironmentVariables('Process').GetEnumerator()) { $once[[string]$e.Key] = [string]$e.Value }
$hata = $null
try { & ([scriptblock]::Create($blok.Extent.Text)) } catch { $hata = "$_" }
$sonra = @{}
foreach ($e in [Environment]::GetEnvironmentVariables('Process').GetEnumerator()) { $sonra[[string]$e.Key] = [string]$e.Value }
[ordered]@{ yakalanan = $script:yakalanan; once = $once; sonra = $sonra; hata = $hata } |
    ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Cikti -Encoding UTF8
"""


class AltSurecVekili:
    """Senaryo modülündeki `subprocess` ADININ yerine konur — KÜRESEL `subprocess` modülüne DOKUNMAZ
    (aynı testte pwsh sürücüsü gerçek `subprocess.run`'ı kullanabilsin). Yalnız verilen sahteler
    (ör. `Popen`, `run`) çağrılabilir; sahtelenmemiş bir süreç işlevi çağrılırsa test KIRMIZI olur —
    gerçek süreç (EXE, powershell, cmdkey) BAŞLATILMAZ."""

    STDOUT, PIPE, DEVNULL = subprocess.STDOUT, subprocess.PIPE, subprocess.DEVNULL
    TimeoutExpired, CalledProcessError = subprocess.TimeoutExpired, subprocess.CalledProcessError

    def __init__(self, **sahteler):
        self.__dict__.update(sahteler)

    def __getattr__(self, ad):
        raise AssertionError(f"senaryo modülü sahtelenmemiş subprocess.{ad} çağırdı — gerçek süreç başlatılmaz")


def urun_senaryolari_modulu():
    """`scripts/urun_senaryolari.py` (paket değil) — modül düzeyinde yalnız sabitler kurar, EXE başlatmaz."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("urun_senaryolari_kapi", KOK / "scripts" / "urun_senaryolari.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def kostur_ortami(tmp_path: Path, monkeypatch) -> dict:
    """`urun_senaryolari.kostur`un EXE'ye vereceği ortam — Popen SAHTE, EXE BAŞLATILMAZ.
    Dış yalıtım değişkenleri ÖNCE silinir (koşucu/CI kendisi verebilir → sahte-yeşil olmasın).
    Ortam adları BÜYÜK harfe çevrilir."""
    for ad in YALITIM_DEGISKENLERI:
        monkeypatch.delenv(ad, raising=False)
    us = urun_senaryolari_modulu()
    yakalanan = {}

    class _SahteSurec:
        def __init__(self, argv, env=None, **kw):
            yakalanan["argv"] = list(argv)
            yakalanan["env"] = {k.upper(): v for k, v in (env or {}).items()}

        def poll(self):
            return 0

    monkeypatch.setattr(us, "subprocess", AltSurecVekili(Popen=_SahteSurec))
    calisma = tmp_path / "calisma"
    calisma.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(us, "CALISMA", calisma)
    us.kostur(tmp_path / "veri", sifreli=False, sure=1, saglik_bekle=False)
    assert "env" in yakalanan, "kostur EXE'yi Popen ile başlatmadı (çıpa kaymış)"
    return yakalanan["env"]


def build_makinesi_ortami(tmp_path: Path) -> dict:
    """Bir build makinesinin ortamı: yalıtım değişkenleri YOK, APPDATA/PROGRAMDATA "gerçek" gibi (tmp nöbetçi)."""
    ortam = {k: v for k, v in os.environ.items() if k.upper() not in YALITIM_DEGISKENLERI}
    for ad in ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA"):
        ortam[ad] = str(tmp_path / f"GERCEK_{ad}")
    ortam.pop("PYTEST_ADDOPTS", None)
    return ortam


def kapi_blogunu_kostur(tmp_path: Path, ortam: dict) -> dict:
    """Bloğu koştur; {'yakalanan': {FilePath, ArgumentList, Env}, 'once', 'sonra', 'hata'} döndür.
    Ortam adları BÜYÜK harfe çevrilir (Windows'ta env adları büyük/küçük harf duyarsız)."""
    assert PWSH, "pwsh (PowerShell 7) yok"
    surucu = tmp_path / "kapi_surucusu.ps1"
    surucu.write_text(_SURUCU, encoding="utf-8-sig")
    kok = tmp_path / "build_kok"
    kok.mkdir(exist_ok=True)
    cikti = tmp_path / "kapi_ortami.json"
    # pwsh açılışta Microsoft'a telemetri gönderir ve güncelleme denetler (ağ) — bekçi alt sürece geçmez.
    ortam = {**ortam, "POWERSHELL_TELEMETRY_OPTOUT": "1", "POWERSHELL_UPDATECHECK": "Off"}
    r = subprocess.run(
        [
            PWSH,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(surucu),
            str(BETIK),
            str(kok),
            str(cikti),
        ],
        env=ortam,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert r.returncode == 0 and cikti.is_file(), (
        f"kapı sürücüsü düştü (rc={r.returncode}):\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}"
    )
    veri = json.loads(cikti.read_text(encoding="utf-8-sig"))
    for anahtar in ("once", "sonra"):
        veri[anahtar] = {k.upper(): v for k, v in (veri.get(anahtar) or {}).items()}
    if veri.get("yakalanan"):
        veri["yakalanan"]["Env"] = {k.upper(): v for k, v in (veri["yakalanan"].get("Env") or {}).items()}
    veri["kok"] = str(kok)
    return veri
