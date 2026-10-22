# -*- coding: utf-8 -*-
"""YH D5 · S-YH.9 [ÖNERİLEN UYGULANDI] — build AI hazırlık kapısı üretilen EXE'yi BOŞ bir loopback portunda ve yalnız 127.0.0.1'de açar.

ÖLÇÜLEN (YH, 2026-10-22; `scripts/build_backend_exe.ps1` HEAD): kapı `$gatePort = 8177` (SABİT) ve `PEMF_API_HOST` vermeden EXE'yi açıyordu →
backend varsayılanı `0.0.0.0` (`backend_service.build_arg_parser`). Sonuç: (1) 8177 bu makinede sahibin portu (testlerin `SAHIP_PORTLARI`,
ORTAK §1 "dinleme de yasak"; D4B §8: "gerçek EXE ve 8177 bu oturumda yasaktı") — port doluysa kapı "yabancı süreç" diye YANLIŞ düşer ya da
isteği başka bir backend'e gönderirdi; (2) build makinesinde LAN'a açık dinleyici ve her yeni EXE yolu için Windows güvenlik duvarı uyarısı
(GÖRÜNÜR pencere). Gerçek derleme (D5) bu yüzden kapı düzeltilmeden koşulamazdı.

Kapı: `Get-BosLoopbackPortu` AST'den çıkarılıp GERÇEK çağrılır (yasak port vermez, bağlanabilir loopback portu); kapı bloğu portu ondan alır ve
`gateOrtam` `PEMF_API_HOST=127.0.0.1` taşır; backend o değişkeni GERÇEKTEN host olarak kullanır.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "build_backend_exe.ps1"
YASAK = {8000, 8100, 1883, 5173, 8177, 8200}
_PWSH = shutil.which("pwsh")

_CAGIR = r"""param([string]$Betik)
$ErrorActionPreference = 'Stop'
$t = $null; $e = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Betik, [ref]$t, [ref]$e)
if ($e.Count) { throw "ayristirma hatasi: $($e.Count)" }
foreach ($ad in 'Die', 'Get-BosLoopbackPortu') {
  $f = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $ad }, $true)
  if (-not $f) { throw "fonksiyon yok: $ad" }
  Invoke-Expression $f.Extent.Text
}
$portlar = foreach ($i in 1..8) { Get-BosLoopbackPortu }
[IO.File]::WriteAllText($env:YH_D5_CIKTI, (ConvertTo-Json -InputObject @($portlar) -Compress), (New-Object Text.UTF8Encoding $false))
"""


def test_KRITIK_bos_loopback_portu_YASAK_port_vermez_ve_baglanabilir(tmp_path):
    if not _PWSH:
        pytest.skip("pwsh (PowerShell 7) yok")
    (tmp_path / "cagir.ps1").write_bytes(b"\xef\xbb\xbf" + _CAGIR.encode("utf-8"))
    cikti = tmp_path / "portlar.json"
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
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env={**os.environ, "YH_D5_CIKTI": str(cikti)},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    portlar = json.loads(cikti.read_text(encoding="utf-8"))
    assert len(portlar) == 8 and all(isinstance(p, int) and 1024 < p < 65536 for p in portlar), portlar
    assert not (set(portlar) & YASAK), f"yasak / sahip portu seçildi: {portlar}"
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", portlar[-1]))  # boş olduğu ölçülür (loopback; dinlemeye geçilmez)
    finally:
        s.close()


def test_KRITIK_kapi_portu_BOS_PORTTAN_ve_EXE_YALNIZ_loopbackte():
    metin = BETIK.read_text(encoding="utf-8-sig")
    assert re.search(r"^\s*\$gatePort = Get-BosLoopbackPortu\s*$", metin, re.M), (
        "kapı portu boş loopback portundan alınmıyor"
    )
    assert not re.search(r"\$gatePort\s*=\s*\d+", metin), "kapı portu SABİT sayı"
    blok = re.search(r"\$gateOrtam = \[ordered\]@\{(.*?)\n    \}", metin, re.S)
    assert blok, "gateOrtam bloğu bulunamadı"
    assert re.search(r'^\s*PEMF_API_HOST\s*=\s*"127\.0\.0\.1"', blok.group(1), re.M), (
        "kapı EXE'si 0.0.0.0'a (LAN) bağlanır"
    )


def test_backend_PEMF_API_HOST_u_host_olarak_KULLANIR(monkeypatch):
    import backend_service as bs

    monkeypatch.setenv("PEMF_API_HOST", "127.0.0.1")
    assert bs.build_arg_parser().parse_args([]).host == "127.0.0.1"
    monkeypatch.delenv("PEMF_API_HOST")
    assert bs.build_arg_parser().parse_args([]).host == "0.0.0.0"  # varsayılan (servis kurulumu) DEĞİŞMEDİ
