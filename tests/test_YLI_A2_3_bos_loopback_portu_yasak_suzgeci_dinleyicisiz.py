# -*- coding: utf-8 -*-
"""YLI-A2.3 — `Get-BosLoopbackPortu`'nun YASAK port süzgeci (8000 / 8100 / 1883 / 5173 / 8177 / 8200) DİNLEYİCİSİZ ve İŞLETİM SİSTEMİNDEN
bağımsız sınanır.

ÖLÇÜLEN (A2, kaynak okuması): YH D5 kapısı (`test_KRITIK_bos_loopback_portu_YASAK_port_vermez_ve_baglanabilir`) süzgeci GERÇEK
`TcpListener(127.0.0.1, 0)` ile sınıyor. Windows'un varsayılan dinamik port aralığı 49152–65535 → işletim sistemi yasak portların HİÇBİRİNİ
vermez; süzgeç (`if ($yasak -notcontains $port)`) silinse ya da liste boşaltılsa kapı YEŞİL kalır (kendi mutantında kırmızı olamaz). Ayrıca kapı
gerçek dinleyici açtığı için dinleyici yasaklı oturumlarda (YLI A2) hiç koşturulamıyor.

Bu kapı: fonksiyon AST'den çıkarılır, YALNIZ `[System.Net.Sockets.TcpListener]::new(...)` çağrısı sahte bir nesneyle (sıradaki port listeden)
değiştirilir — ağ YOK. Yasak portlar atlanır, ilk serbest port döner; hepsi yasaksa `Die` ile durur; liste ürünle aynı (kapı sabiti AYRI).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import capraz
import pytest

KOK = next(p for p in Path(__file__).resolve().parents if (p / "versions.json").exists())
BETIK = KOK / "scripts" / "build_backend_exe.ps1"
YASAK = [8000, 8100, 1883, 5173, 8177, 8200]  # kapı sabiti — betikten OKUNMAZ
_PWSH = shutil.which("pwsh")
_YAPICI = "[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)"

_CAGIR = r"""param([string]$Betik, [string]$Portlar, [string]$Yapici)
$ErrorActionPreference = 'Stop'
$t = $null; $e = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Betik, [ref]$t, [ref]$e)
if ($e.Count) { throw "ayristirma hatasi: $($e.Count)" }
$f = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Get-BosLoopbackPortu' }, $true)
if (-not $f) { throw 'Get-BosLoopbackPortu yok' }
$metin = $f.Extent.Text
if (-not $metin.Contains($Yapici)) { throw 'dinleyici yapicisi bulunamadi (fonksiyon degisti - kapiyi guncelle)' }
$script:sira = [System.Collections.Generic.Queue[int]]::new([int[]]($Portlar | ConvertFrom-Json))
$script:acilan = 0
function global:Yeni-SahteDinleyici {
  $p = $script:sira.Dequeue()
  $script:acilan++
  $o = [pscustomobject]@{ LocalEndpoint = [pscustomobject]@{ Port = $p } }
  $o | Add-Member -MemberType ScriptMethod -Name Start -Value { }
  $o | Add-Member -MemberType ScriptMethod -Name Stop -Value { }
  return $o
}
function Die($m) { throw "DIE: $m" }
Invoke-Expression ($metin.Replace($Yapici, '(Yeni-SahteDinleyici)'))
try { $sonuc = @{ port = (Get-BosLoopbackPortu); die = $null } } catch { $sonuc = @{ port = $null; die = "$($_.Exception.Message)" } }
$sonuc['acilan'] = $script:acilan
[IO.File]::WriteAllText($env:YLI_A23_CIKTI, (ConvertTo-Json -InputObject $sonuc -Compress), (New-Object Text.UTF8Encoding $false))
"""


def _cagir(tmp_path: Path, portlar: list[int]) -> dict:
    if not _PWSH:
        capraz.atla("pwsh (PowerShell 7) yok")
    (tmp_path / "cagir.ps1").write_bytes(b"\xef\xbb\xbf" + _CAGIR.encode("utf-8"))
    cikti = tmp_path / "sonuc.json"
    r = subprocess.run(
        [
            _PWSH,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tmp_path / "cagir.ps1"),
            "-Betik",
            str(BETIK),
            "-Portlar",
            json.dumps(portlar),
            "-Yapici",
            _YAPICI,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env={**os.environ, "YLI_A23_CIKTI": str(cikti)},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(cikti.read_text(encoding="utf-8"))


def test_KRITIK_her_yasak_port_ATLANIR_ilk_serbest_port_doner(tmp_path):
    s = _cagir(tmp_path, YASAK + [50123, 50124])
    assert s["port"] == 50123 and s["acilan"] == len(YASAK) + 1, f"yasak port atlanmadı / yanlış port: {s}"


@pytest.mark.parametrize("yasak", YASAK)
def test_KRITIK_tek_yasak_port_bile_SECILMEZ(tmp_path, yasak):
    s = _cagir(tmp_path, [yasak, 49999])
    assert s["port"] == 49999, f"{yasak} seçildi: {s}"


def test_KRITIK_hep_yasak_port_gelirse_DURUR(tmp_path):
    s = _cagir(tmp_path, [8177] * 25)
    assert s["port"] is None and s["die"] and "DIE:" in s["die"] and s["acilan"] == 20, (
        f"sonsuz döngü ya da yasak port: {s}"
    )


def test_KARSIT_serbest_port_ilk_denemede_doner(tmp_path):
    assert _cagir(tmp_path, [50001])["port"] == 50001
