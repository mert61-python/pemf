# -*- coding: utf-8 -*-
"""4B-1.1 — build AI hazırlık kapısı (D4.28) build makinesinde HTTP(S)_PROXY tanımlıyken KENDİ sağlam EXE'sini
"açılmadı / yabancı" sayıp derlemeyi YANLIŞ durdurur.

ÖLÇÜLDÜ (sonda `_inceleme/sonda/k1_vekil.ps1`): pwsh 7 `Invoke-RestMethod "http://127.0.0.1:<port>/…"` ortamdaki
HTTP_PROXY'yi loopback için de kullanır (`HttpClient.DefaultProxy.IsBypassed(127.0.0.1)` = False; bağlantı sahte vekile
ulaştı). Vekil isteği kendi EXE'mize iletmez (uzak vekil) ya da `X-Forwarded-For` ekler → backend `launcherNonce`'u
YALNIZ proxysiz loopback'e verir (gerçek `/api/health` aşağıda ölçülür) → kapı "PEMF_HEALTH_NONCE yansımadı" der.

Kapı (gerçek EXE / sabit port / ağ YOK):
  * AI bloğu ve son blok build betiğinden AST ile GERÇEK metinleriyle; betiğin GERÇEK Info/Warn/Die'ı (Die = exit 1).
  * `Invoke-RestMethod` GERÇEK cmdlet'tir; kapının portu (YH D5 · S-YH.9: `Get-BosLoopbackPortu`) gölgede testin loopback
    sahte EXE portunu döndürür; bütün parametreler (ör. -NoProxy) AYNEN gerçek cmdlet'e geçer.
  * Sahte EXE (127.0.0.1:rastgele) nonce'u yalnız `X-Forwarded-For` / `Via` YOKKEN yansıtır (gerçek backend'in kuralı);
    sahte vekil (127.0.0.1:rastgele) her isteğe hemen 502 döner ve isabetleri sayar.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "build_backend_exe.ps1"
PWSH = shutil.which("pwsh")

_SURUCU = r"""
param([string]$Betik, [string]$Kok, [string]$Iz, [int]$SahtePort)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Betik, [ref]$tokens, [ref]$errs)
if ($errs) { throw "build betiği ayrıştırılamadı: $($errs | Out-String)" }
$ust = $ast.EndBlock.Statements
$ai = $ust | Where-Object { $_ -is [System.Management.Automation.Language.IfStatementAst] -and $_.Clauses[0].Item1.Extent.Text -match 'SkipAiGate' } | Select-Object -First 1
$son = $ust[$ust.Count - 1]
if (-not $ai -or -not ($son.Extent.Text -match 'EXE hazır')) { throw "çıpa: AI kapısı ya da son blok bulunamadı" }
foreach ($fn in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    Invoke-Expression $fn.Extent.Text
}
$global:IZ = $Iz
$global:SAHTE_PORT = $SahtePort
# YH D5 · S-YH.9: kapı portu boş loopback portundan gelir — gölge sahte EXE'nin portunu verir.
function Get-BosLoopbackPortu { $global:SAHTE_PORT }
New-Item -ItemType Directory -Force -Path $Iz | Out-Null
function Start-Sleep { }
function Stop-Process { }
function Wait-Process { }
function Get-Process { @() }
function Start-Process {
    param($FilePath, $ArgumentList, $RedirectStandardOutput, $RedirectStandardError, [switch]$PassThru, $WindowStyle)
    $n = [Environment]::GetEnvironmentVariable('PEMF_HEALTH_NONCE', 'Process')
    [IO.File]::WriteAllText((Join-Path $global:IZ 'nonce.txt'), [string]$n)
    [pscustomobject]@{ Id = 0; HasExited = $false; ExitCode = $null }
}
# GERÇEK cmdlet; istenen port sahte EXE'ninki değilse (ör. eski sabit 8177) iz bırakır ve DÜŞER.
function Invoke-RestMethod {
    [CmdletBinding()]
    param([Parameter(Position = 0)][uri]$Uri, [int]$TimeoutSec, [switch]$NoProxy)
    if ($Uri.Port -ne $global:SAHTE_PORT) { [IO.File]::WriteAllText((Join-Path $global:IZ 'yanlis_port.txt'), [string]$Uri.Port); throw "yanlis port $($Uri.Port)" }
    Microsoft.PowerShell.Utility\Invoke-RestMethod @PSBoundParameters
}
$BuildRoot = $Kok
$dist = Join-Path $Kok 'dist'
$exe = Join-Path $dist 'PEMF_Backend\PEMF_Backend.exe'
New-Item -ItemType File -Force -Path $exe | Out-Null
$SkipAiGate = $false
$SkipProtect = $true
$dt = [timespan]::Zero
& ([scriptblock]::Create($ai.Extent.Text))
& ([scriptblock]::Create($son.Extent.Text))
Write-Host 'SURUCU-SONU'
exit 0
"""

_RAPOR = {
    "hazir": 1, "toplam": 1, "eksik": [],
    "moduller": [{"modul": "yara_kapanma", "hazir": True, "yukleme": "pyd"}],
    "xai": {"hazir": True, "grad_cam": True, "shap": True, "captum": True, "ttach": True, "em_ref_stats_eksik": []},
    "pip_yasagi": {"etkin": True},
}  # fmt: skip


class _Sunucu:
    """Loopback rastgele portta küçük HTTP sunucusu (yalnız 127.0.0.1)."""

    def __init__(self, isleyici):
        self.isabet = 0
        dis = self

        class _H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                dis.isabet += 1
                kod, govde = isleyici(self)
                veri = json.dumps(govde).encode("utf-8")
                self.send_response(kod)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(veri)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(veri)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), _H)
        self.port = self.srv.server_address[1]
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()

    def kapat(self):
        self.srv.shutdown()
        self.srv.server_close()


def _kos(tmp_path: Path, vekil_var: bool) -> tuple[subprocess.CompletedProcess, int, int]:
    iz = tmp_path / "iz"
    iz.mkdir(parents=True, exist_ok=True)

    def exe_isleyici(h):
        if h.path.startswith("/api/health"):
            nonce_yolu = iz / "nonce.txt"
            nonce = nonce_yolu.read_text(encoding="utf-8") if nonce_yolu.exists() else ""
            # gerçek backend kuralı: vekil başlığı varsa nonce VERİLMEZ (system_router `_via_proxy`)
            vekilden = bool(h.headers.get("X-Forwarded-For") or h.headers.get("Via"))
            return 200, {"status": "online", "launcherNonce": (None if vekilden else nonce)}
        if h.path.startswith("/api/ai/hazirlik"):
            return 200, _RAPOR
        return 404, {}

    exe = _Sunucu(exe_isleyici)
    vekil = _Sunucu(lambda h: (502, {"vekil": "hedefe ulasilamadi"}))
    try:
        surucu = tmp_path / "surucu.ps1"
        surucu.write_text(_SURUCU, encoding="utf-8-sig")
        kok = tmp_path / "build_kok"
        kok.mkdir(exist_ok=True)
        ortam = {
            k: v
            for k, v in os.environ.items()
            if k.upper() not in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
        }
        ortam.update({"POWERSHELL_TELEMETRY_OPTOUT": "1", "POWERSHELL_UPDATECHECK": "Off"})
        if vekil_var:
            ortam["HTTP_PROXY"] = ortam["HTTPS_PROXY"] = f"http://127.0.0.1:{vekil.port}"
        r = subprocess.run(
            [PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(surucu),
             str(BETIK), str(kok), str(iz), str(exe.port)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=ortam, timeout=300,
        )  # fmt: skip
        assert "çıpa" not in (r.stdout + r.stderr), r.stderr[-800:]
        assert "AI hazırlık kapısı" in r.stdout, (
            f"kodlama bozuk ya da AI bloğu koşmadı:\n{r.stdout[-800:]}\n{r.stderr[-800:]}"
        )
        return r, exe.isabet, vekil.isabet
    finally:
        exe.kapat()
        vekil.kapat()


pytestmark = pytest.mark.skipif((PWSH is None) and not capraz.ZORUNLU, reason="pwsh yok — build betiği pwsh ile koşar")


def test_KARSIT_vekilsiz_makinede_saglam_EXE_kapidan_GECER(tmp_path):
    """Aparat kanıtı: vekil YOKKEN aynı sahte EXE nonce'u yansıtır ve build 0 ile biter."""
    r, exe_isabet, vekil_isabet = _kos(tmp_path, vekil_var=False)
    assert r.returncode == 0 and "Headless backend EXE hazır" in r.stdout, f"{r.stdout[-1500:]}\n{r.stderr[-800:]}"
    assert exe_isabet >= 2 and vekil_isabet == 0


def test_KRITIK_HTTP_PROXY_tanimli_build_makinesinde_saglam_EXE_YANLIS_DURDURULMAZ(tmp_path):
    """Build makinesinde HTTP_PROXY/HTTPS_PROXY var: kapının loopback istekleri vekile GİTMEMELİ."""
    r, exe_isabet, vekil_isabet = _kos(tmp_path, vekil_var=True)
    assert vekil_isabet == 0, (
        f"kapının 127.0.0.1 sağlık/hazırlık istekleri VEKİLE gitti ({vekil_isabet} isabet; kendi EXE'ye {exe_isabet}) — "
        "vekil X-Forwarded-For ekler ya da hedefe ulaşamaz → nonce yansımaz"
    )
    assert r.returncode == 0 and "Headless backend EXE hazır" in r.stdout, (
        f"sağlam EXE vekil yüzünden 'AÇILMADI/yabancı' sayılıp build YANLIŞ durdu:\n{r.stdout[-1500:]}"
    )


def test_ONCUL_gercek_saglik_ucu_X_Forwarded_For_ile_nonce_VERMEZ(monkeypatch):
    """Öncül (bugün yeşil): GERÇEK `/api/health` loopback'te nonce'u verir, aynı istek `X-Forwarded-For` taşırsa VERMEZ —
    yerel bir vekil (XFF ekleyen) üzerinden giden kapı isteği kendi EXE'mize ulaşsa bile nonce'u kaybeder."""
    from fastapi.testclient import TestClient
    from servers import api_server

    monkeypatch.setenv("PEMF_HEALTH_NONCE", "NONCE-4B11")
    with TestClient(api_server.app, client=("127.0.0.1", 51234)) as c:
        dogrudan = c.get("/api/health").json()
        vekilden = c.get("/api/health", headers={"X-Forwarded-For": "127.0.0.1"}).json()
    with TestClient(api_server.app, client=("::1", 51234)) as c:
        ipv6 = c.get("/api/health").json()
    assert dogrudan.get("launcherNonce") == "NONCE-4B11"
    assert ipv6.get("launcherNonce") == "NONCE-4B11"
    assert vekilden.get("launcherNonce") is None
