# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y44 (sahip — 1-B açık madde 5, i1-B3) — kurulum `PEMF_API_PORT`'u backend'le AYNI kuralla doğrular; bozuksa
servis adımlarına BAŞLAMADAN açık hatayla durur; sağlık sondası DOĞRULANMIŞ portu kullanır.

ÖLÇÜLEN KUSUR (89cc4b2): `setup_services.ps1` profildeki değeri hiç doğrulamıyordu — servis bozuk değerle kuruluyor
(backend uyarıyla 8000'e düşer), sağlık sondası HAM değeri URL'ye koyuyordu (`http://localhost:80O0/api/health`) →
8 deneme sonra "CİHAZ ÇALIŞMIYOR" yanlış teşhisi. Backend'in kabul ettiği yazımlar (`+8000`, `08000`, `8_000`) da
sondayı bozuyordu.

KURAL EŞLİĞİ ÖLÇÜLÜR (metin değil): PowerShell işlevi AST'den çekilip bir değer tablosunda koşar, sonuç GERÇEK
`backend_service.ortam_portu()` ile karşılaştırılır.

⛔ Betik GERÇEKTEN koşmaz (görev kuralı): yalnız ilgili işlevler ve üst-düzey ifadeler AST'den çekilir; çalıştırmadan
ÖNCE her komut bir izin listesine karşı denetlenir (ihlalde çıkış 3). Sahte kök geçici dizindedir; `Log` kayıtçıdır.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
SETUP = KOK / "scripts" / "setup_services.ps1"
_PWSH = shutil.which("pwsh")

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="pwsh aparatı Windows betik anlamını ölçer"),
    pytest.mark.skipif((_PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) bulunamadı"),
]

#: Backend'in (`int()`) kabul ettiği/etmediği yazımlar — sınırlar, işaret, alt çizgi, Unicode rakam, ondalık/onaltılık.
TABLO = [
    "8000",
    " 8000 ",
    "\t8001",
    "+8000",
    "08000",
    "0008000",
    "8_000",
    "1",
    "65535",
    "65536",
    "0",
    "-1",
    "-8000",
    "+0",
    "80O0",
    "sekizbin",
    "",
    " ",
    "8000.0",
    "0x1F40",
    "1e3",
    "8 000",
    "8__000",
    "_8000",
    "8000_",
    "++8000",
    "٨٠٠٠",  # Arapça-Hint rakamları 8000
    "８０００",  # tam genişlik 8000
    "99999999999999999999999",
    "000000000000000000065535",
]

_APARAT = r"""
param([string]$Setup, [string]$Kok, [string]$Senaryo, [string]$Girdi, [string]$Cikti)
$ErrorActionPreference = 'Stop'
$script:Kayit = [System.Collections.Generic.List[string]]::new()
function Log { param($m, $c) $script:Kayit.Add([string]$m) }
$t = $null; $e = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Setup, [ref]$t, [ref]$e)
if ($e) { [Console]::Out.WriteLine("APARAT_HATASI parse"); exit 3 }
$izinli = 'Log','Join-Path','Split-Path','Test-Path','Where-Object','Select-Object','Get-Content',
          'Test-PemfApiPortDegeri','Get-PemfProfilEnvDosyasi','Read-PemfProfilEnv'
$izinliUye = 'Match','ToCharArray','GetNumericValue','Trim','StartsWith','Contains','Split'
function Denetle($agac) {
    foreach ($c in $agac.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true)) {
        $ad = $c.GetCommandName()
        if (-not $ad -or $izinli -notcontains $ad) { [Console]::Out.WriteLine("APARAT_HATASI izin disi komut: " + $c.Extent.Text); exit 3 }
    }
    # SON-A1.55 (22 · A1b; D5 §5 AÇIK — D5 H-1 `_IzinDisi` sınıfı): komutsuz yazım da izin dışı — .NET yöntemi (yalnız ayrıştırma
    # yöntemleri), dosyaya yönlendirme ($null dışı) ve sürücü nitelikli değişken (env: dışı). Eskiden üçü de GERÇEKTEN koşuyordu (ölçüldü).
    foreach ($y in $agac.FindAll({ param($n) $n -is [System.Management.Automation.Language.InvokeMemberExpressionAst] }, $true)) {
        if ($izinliUye -notcontains "$($y.Member.Extent.Text)") { [Console]::Out.WriteLine("APARAT_HATASI izin disi yontem: " + $y.Extent.Text); exit 3 }
    }
    foreach ($r in $agac.FindAll({ param($n) $n -is [System.Management.Automation.Language.FileRedirectionAst] }, $true)) {
        if (-not ($r.Location -is [System.Management.Automation.Language.VariableExpressionAst] -and $r.Location.VariablePath.UserPath -eq 'null')) {
            [Console]::Out.WriteLine("APARAT_HATASI izin disi yonlendirme: " + $r.Extent.Text); exit 3 }
    }
    foreach ($v in $agac.FindAll({ param($n) $n -is [System.Management.Automation.Language.VariableExpressionAst] -and $n.VariablePath.IsDriveQualified -and
            $n.VariablePath.DriveName -ne 'env' }, $true)) { [Console]::Out.WriteLine("APARAT_HATASI izin disi surucu degiskeni: " + $v.Extent.Text); exit 3 }
}
function Yukle([string[]]$Adlar, [switch]$Varsa) {
    foreach ($ad in $Adlar) {
        $f = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $ad }, $true) | Select-Object -First 1
        if (-not $f -and $Varsa) { continue }
        if (-not $f) { [Console]::Out.WriteLine("YOK_ISLEV " + $ad); exit 4 }
        Denetle $f
        . ([ScriptBlock]::Create($f.Extent.Text))
    }
}
$ifadeler = @($ast.EndBlock.Statements)
switch ($Senaryo) {
    'kural' {
        . Yukle @('Test-PemfApiPortDegeri')
        $tablo = Get-Content -LiteralPath $Girdi -Raw -Encoding UTF8 | ConvertFrom-Json
        $sonuc = @(foreach ($h in $tablo) { $r = Test-PemfApiPortDegeri ([string]$h); [pscustomobject]@{ ham = [string]$h; port = $r.Port; hata = $r.Hata } })
        ConvertTo-Json -InputObject $sonuc -Depth 3 | Set-Content -LiteralPath $Cikti -Encoding UTF8
    }
    'sonda' {
        . Yukle @('Test-PemfApiPortDegeri') -Varsa  # sondanın kendisi ölçülür (işlevi kullanmasa da koşar)
        $s = @($ifadeler | Where-Object { $_.Extent.Text -match '^\$probePort\s*=' })
        if ($s.Count -ne 1) { [Console]::Out.WriteLine("YOK_SONDA " + $s.Count); exit 4 }
        Denetle $s[0]
        $tablo = Get-Content -LiteralPath $Girdi -Raw -Encoding UTF8 | ConvertFrom-Json
        $sonuc = @(foreach ($h in $tablo) {
            $EnvMap = [ordered]@{ "PYTHONUNBUFFERED" = "1" }
            if ($null -ne $h) { $EnvMap["PEMF_API_PORT"] = [string]$h }
            . ([ScriptBlock]::Create($s[0].Extent.Text))
            [pscustomobject]@{ ham = $h; sonda = [string]$probePort }
        })
        ConvertTo-Json -InputObject $sonuc -Depth 3 | Set-Content -LiteralPath $Cikti -Encoding UTF8
    }
    'kurulum' {
        # Kaldırma dalından SONRAKİ ilk üst-düzey ifadeler: Y44 ön doğrulaması (port denetimine dek). Gerçek kurulum
        # adımı (New-Item, nssm, servis, güvenlik duvarı) bu dilime GİREMEZ — izin listesi engeller.
        $u = -1
        for ($i = 0; $i -lt $ifadeler.Count; $i++) {
            if ($ifadeler[$i] -is [System.Management.Automation.Language.IfStatementAst] -and $ifadeler[$i].Clauses[0].Item1.Extent.Text -eq '$Uninstall') { $u = $i }
        }
        $son = -1
        for ($i = $u + 1; $i -lt $ifadeler.Count; $i++) {
            if ($ifadeler[$i].Extent.Text -match 'Test-PemfApiPortDegeri') { $son = $i; break }
        }
        if ($u -lt 0 -or $son -lt 0) { [Console]::Out.WriteLine("YOK_ON_DOGRULAMA u=$u son=$son"); exit 4 }
        $dilim = $ifadeler[($u + 1)..$son]
        foreach ($x in $dilim) { Denetle $x }
        . Yukle @('Test-PemfApiPortDegeri', 'Get-PemfProfilEnvDosyasi', 'Read-PemfProfilEnv')
        $AppDir = Join-Path $Kok 'app'; $Mode = 'device'
        $blok = Join-Path $Kok 'scripts\on_dogrulama.ps1'
        Set-Content -LiteralPath $blok -Value (($dilim | ForEach-Object { $_.Extent.Text }) -join "`n") -Encoding UTF8
        # Dot-source edilen dosyadaki `exit N` yalnız o dosyayı bitirir ve $LASTEXITCODE'u N yapar (gerçek betikte
        # `-File` ile koşulduğunda kurulumun TAMAMI N ile biter) — ölçüldü 2026-10-03.
        $global:LASTEXITCODE = 0
        . $blok
        if ($LASTEXITCODE -ne 0) { $script:Kayit.Add("CIKIS $LASTEXITCODE") } else { $script:Kayit.Add("DEVAM") }
        @{ kayit = @($script:Kayit); dilim = $dilim.Count } | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $Cikti -Encoding UTF8
    }
}
exit 0
"""


def _kos(tmp_path: Path, senaryo: str, girdi=None) -> tuple[subprocess.CompletedProcess, object]:
    aparat = tmp_path / "aparat.ps1"
    aparat.write_text(_APARAT, encoding="utf-8-sig")
    (tmp_path / "kok" / "scripts").mkdir(parents=True, exist_ok=True)
    gp = tmp_path / "girdi.json"
    gp.write_text(json.dumps(girdi if girdi is not None else [], ensure_ascii=False), encoding="utf-8")
    cikti = tmp_path / "cikti.json"
    p = subprocess.run(
        [
            _PWSH,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(aparat),
            "-Setup",
            str(SETUP),
            "-Kok",
            str(tmp_path / "kok"),
            "-Senaryo",
            senaryo,
            "-Girdi",
            str(gp),
            "-Cikti",
            str(cikti),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert "APARAT_HATASI" not in p.stdout, p.stdout + p.stderr
    veri = json.loads(cikti.read_text(encoding="utf-8-sig")) if cikti.exists() else None
    return p, veri


def test_KRITIK_kural_ESLIGI_kurulum_dogrulamasi_backend_ortam_portu_ile_AYNI(tmp_path, monkeypatch):
    import backend_service as bs

    p, veri = _kos(tmp_path, "kural", TABLO)
    assert p.returncode == 0 and veri is not None, f"rc={p.returncode} {p.stdout[-800:]} {p.stderr[-800:]}"
    assert [v["ham"] for v in veri] == TABLO, "aparat: tablo eksik/bozuk aktarıldı"
    farklar = []
    for v in veri:
        monkeypatch.setenv("PEMF_API_PORT", v["ham"])
        port, uyari = bs.ortam_portu()
        backend_gecerli = uyari is None
        kurulum_gecerli = not v["hata"]
        if backend_gecerli != kurulum_gecerli or (backend_gecerli and v["port"] != port):
            farklar.append(
                (
                    v["ham"],
                    f"backend={port if backend_gecerli else 'GECERSIZ'}",
                    f"kurulum={v['port'] if kurulum_gecerli else 'GECERSIZ'}",
                )
            )
    assert not farklar, f"kurulum doğrulaması backend kuralından AYRIŞIYOR: {farklar}"
    hatali = next(v for v in veri if v["ham"] == "80O0")
    assert "PEMF_API_PORT geçersiz: '80O0'" in hatali["hata"] and "düzeltin" in hatali["hata"], hatali["hata"]


def _profil(tmp_path: Path, satir: str | None) -> None:
    d = tmp_path / "kok" / "app" / "deploy"
    d.mkdir(parents=True, exist_ok=True)
    govde = "# profil\nPEMF_API_HOST=0.0.0.0\n" + (f"{satir}\n" if satir is not None else "") + "PEMF_HEADLESS=1\n"
    (d / "device.env").write_text(govde, encoding="utf-8")


@pytest.mark.parametrize(
    "satir", ["PEMF_API_PORT=80O0", "PEMF_API_PORT=70000", "PEMF_API_PORT=", "PEMF_API_PORT = sekiz bin"]
)
def test_KRITIK_bozuk_portta_kurulum_SERVIS_ADIMLARINA_BASLAMADAN_acik_hatayla_DURUR(tmp_path, satir):
    _profil(tmp_path, satir)
    p, veri = _kos(tmp_path, "kurulum")
    assert "YOK_ON_DOGRULAMA" not in p.stdout, (
        "kaldırma dalından sonra PEMF_API_PORT ön doğrulaması YOK — kurulum bozuk portla servisi kurar "
        f"(backend 8000'e düşer, sonda ham değere bakar): {p.stdout[-300:]}"
    )
    assert veri is not None, f"rc={p.returncode} {p.stdout[-800:]} {p.stderr[-800:]}"
    assert "CIKIS 1" in veri["kayit"] and "DEVAM" not in veri["kayit"], f"bozuk portta kurulum DURMADI: {veri}"
    hata = [k for k in veri["kayit"] if "PEMF_API_PORT geçersiz" in k]
    assert hata and "düzeltin" in hata[0] and "device.env" in hata[0], (
        f"hata metni nedeni/eylemi/dosyayı söylemiyor: {veri}"
    )


@pytest.mark.parametrize("satir", ["PEMF_API_PORT=8000", "PEMF_API_PORT=+8001", None])
def test_KARSIT_gecerli_ya_da_YOK_portta_kurulum_SURER(tmp_path, satir):
    _profil(tmp_path, satir)
    p, veri = _kos(tmp_path, "kurulum")
    assert p.returncode == 0 and veri is not None and veri["kayit"][-1] == "DEVAM", (
        f"{p.returncode} {veri} {p.stdout[-400:]}"
    )
    assert not any("geçersiz" in k for k in veri["kayit"]), veri


def test_KRITIK_saglik_sondasi_DOGRULANMIS_portu_kullanir(tmp_path):
    """i1-B3: sonda `$EnvMap['PEMF_API_PORT']`ı HAM kullanıyordu → backend'in kabul ettiği `+8000`/`08001`/`8_002`
    yazımlarında URL bozuk (`localhost:+8000`), sağlıklı kurulum "CİHAZ ÇALIŞMIYOR" ile düşüyordu."""
    girdi = ["+8000", "08001", "8_002", " 8003", None]
    p, veri = _kos(tmp_path, "sonda", girdi)
    assert p.returncode == 0 and veri is not None, f"rc={p.returncode} {p.stdout[-800:]} {p.stderr[-800:]}"
    bulunan = {(v["ham"] if v["ham"] is not None else "YOK"): v["sonda"] for v in veri}
    assert bulunan == {"+8000": "8000", "08001": "8001", "8_002": "8002", " 8003": "8003", "YOK": "8000"}, bulunan
