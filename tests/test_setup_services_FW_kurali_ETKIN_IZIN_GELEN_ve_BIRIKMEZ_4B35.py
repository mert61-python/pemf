# -*- coding: utf-8 -*-
"""4B-3.5 (A3 inceleme, İG-9.5 `d85f3060` + C25 `0ef16a1e`) — `setup_services.ps1` güvenlik duvarı "içerik" denetimi LAN erişimini
belirleyen alanları GÖRMÜYOR; silme düşünce aynı adlı kural BİRİKİYOR.

İG-9.5 kuralı "ADIYLA değil İÇERİĞİYLE" doğrular — ama içerik = yalnız protokol + port + program. Ölçüldü (HEAD, gölge koşum,
`kayit/k2_ig95_sonda.txt`): aynı adlı kural doğru port/protokol/programla ama `Action Block` / `Enabled False` / `Direction Outbound` /
`Profile Domain` ise "uygun" sayılır, DOKUNULMAZ → backend dinler, LAN'dan (mobil / web istemci) erişim ENGELLİ kalır ve betik bunu
söylemez (`/api/health` yalnız localhost'ta ölçülür). `Remove-NetFirewallRule` düşünce (ör. GPO deposundaki aynı adlı kural) betik aynı adla
YENİ kural ekler; sonraki her koşuda eski kural yine "uymaz", silme yine düşer → her koşuda +1 kural.

⛔ Gerçek güvenlik duvarına DOKUNULMAZ: GERÇEK `$FwKurallar` + `foreach` deyimleri AST'den alınır; bütün NetFirewall cmdlet'leri sürücüde
durum tutan sahte tabloya gölgelenir (İG-9.5 kapısının deseni, tablo genişletilmiş).
D5 M-1 TUR 3 (çürütücü 2 A1 — aparat sızıntısı): sürücü PAYLAŞILAN `Ensure-PemfBackendFirewallKurali` gövdesini de koşar → modül otomatik
yükleme KAPALI (NetSecurity YÜKLENEMEZ), gölgeler Get-Command ile İŞLEV kanıtlı (değilse çıkış 99), çekilen her parça koşmadan ÖNCE izin
listesine karşı denetlenir (D5 H-1 `_IzinDisi`; dışında komut / yöntem → çıkış 5, KOŞMAZ).
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
PWSH = shutil.which("pwsh")
EXE = r"C:\PEMF\runtime\PEMF_Backend\PEMF_Backend.exe"
AD = "PEMF Backend API"
UDP = {"n": "PEMF UDP Discovery", "p": "UDP", "port": 5051, "prog": EXE}

# D5 M-1 TUR 3: ham `skipif` yerine ZORUNLU'ya bağlı atlama (yayın makinesinde Windows + pwsh yoksa DÜŞER).
if sys.platform != "win32":
    capraz.atla("pwsh aparatı Windows betik anlamını ölçer")
if PWSH is None:
    capraz.atla("pwsh (PowerShell 7) bulunamadı")

from test_install_backend_service_FW_kurali_ICERIKLE_D5H1 import aparat_sonucu_denetle, aparat_surucusu  # noqa: E402

_GOLGELER = (
    "Log",
    "Out-Null",
    "Get-NetFirewallRule",
    "Get-NetFirewallPortFilter",
    "Get-NetFirewallApplicationFilter",
    "New-NetFirewallRule",
    "Remove-NetFirewallRule",
    "Set-NetFirewallRule",
)
_IZINLI = (*_GOLGELER, "Where-Object", "Select-Object", "ForEach-Object", "Ensure-PemfBackendFirewallKurali")

_SURUCU = r"""
param([string]$Setup, [string]$Durum, [string]$Cikti)
Import-Module Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility
$PSModuleAutoLoadingPreference = 'None'
$ErrorActionPreference = 'Stop'
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Setup, [ref]$tokens, [ref]$errs)
if ($errs) { throw "ayristirilamadi" }
$ust = @($ast.EndBlock.Statements)
# D5 M-1: `$FwKurallar = …` → `foreach ($r in $FwKurallar)` bitişik dilimi + döngünün kullandığı kural işlevi (betikten, parser ile).
$bas = -1; $bit = -1
for ($i = 0; $i -lt $ust.Count; $i++) {
    if ($bas -lt 0 -and $ust[$i].Extent.Text -match '^\$FwKurallar\s*=') { $bas = $i }
    if ($ust[$i].Extent.Text -match '^foreach \(\$r in \$FwKurallar\)') { $bit = $i }
}
if ($bas -lt 0 -or $bit -lt $bas) { [IO.File]::WriteAllText($Cikti, (@{ cipa = "FwKurallar blogu bulunamadi: $bas..$bit" } | ConvertTo-Json)); exit 0 }
$sec = @($ust | Where-Object { $_ -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $_.Name -eq 'Ensure-PemfBackendFirewallKurali' }) +
    @($ust[$bas..$bit])
$d = Get-Content -LiteralPath $Durum -Raw | ConvertFrom-Json
$script:Tablo = [System.Collections.Generic.List[object]]::new()
function _ekle($k) {
    $script:Tablo.Add([pscustomobject]@{ DisplayName = $k.n; Protocol = $k.p; LocalPort = "$($k.port)"; Program = $k.prog
        Enabled = $(if ($k.enabled) { $k.enabled } else { 'True' }); Action = $(if ($k.action) { $k.action } else { 'Allow' })
        Direction = $(if ($k.dir) { $k.dir } else { 'Inbound' }); Profile = $(if ($k.profile) { $k.profile } else { 'Any' })
        Kilitli = [bool]$k.kilitli })
}
foreach ($k in @($d.kurallar)) { _ekle $k }
$script:Cagri = [System.Collections.Generic.List[string]]::new()
function Log { param($m, $c) $script:Cagri.Add("LOG " + $m) }
function Out-Null { param([Parameter(ValueFromPipeline = $true)]$x) process { } }
function Get-NetFirewallRule { param($DisplayName, $ErrorAction) @($script:Tablo | Where-Object { $_.DisplayName -eq $DisplayName }) }
function Get-NetFirewallPortFilter { param([Parameter(ValueFromPipeline = $true)]$InputObject, $AssociatedNetFirewallRule)
    process { $k = if ($InputObject) { $InputObject } else { $AssociatedNetFirewallRule }; [pscustomobject]@{ Protocol = $k.Protocol; LocalPort = $k.LocalPort } } }
function Get-NetFirewallApplicationFilter { param([Parameter(ValueFromPipeline = $true)]$InputObject, $AssociatedNetFirewallRule)
    process { $k = if ($InputObject) { $InputObject } else { $AssociatedNetFirewallRule }; [pscustomobject]@{ Program = $k.Program } } }
function New-NetFirewallRule { param($DisplayName, $Direction, $Program, $Action, $Protocol, $LocalPort, $Profile, $ErrorAction)
    $script:Cagri.Add("FW-YENI $DisplayName $Protocol $LocalPort")
    _ekle ([pscustomobject]@{ n = $DisplayName; p = $Protocol; port = $LocalPort; prog = $Program; action = $Action; dir = $Direction; profile = $Profile }) }
# D5 M-1: kural TEK TEK (boru hattıyla) silinir — gölge hem nesneyi hem adı kabul eder (gelişmiş işlev: -ErrorAction ortak parametre).
function Remove-NetFirewallRule { param([Parameter(ValueFromPipeline = $true)]$InputObject, $DisplayName)
    process {
        $ad = $(if ($InputObject) { $InputObject.DisplayName } else { $DisplayName })
        $script:Cagri.Add("FW-SIL $ad")
        $hedef = $(if ($InputObject) { @($InputObject) } else { @($script:Tablo | Where-Object { $_.DisplayName -eq $DisplayName }) })
        foreach ($k in @($hedef | Where-Object { -not $_.Kilitli })) { [void]$script:Tablo.Remove($k) }
        if (@($hedef | Where-Object { $_.Kilitli }).Count) { throw "Erisim engellendi (sahte: GPO deposundaki kural)" } } }
function Set-NetFirewallRule { param([Parameter(ValueFromPipeline = $true)]$InputObject, $DisplayName, $Protocol, $LocalPort, $Program, $Enabled, $Action, $Direction, $Profile)
    process { $script:Cagri.Add("FW-DEGISTIR $DisplayName") } }
# D5 M-1 TUR 3 (A1): gölge kanıtı + izin listesi — ikisi de çekilen kod KOŞMADAN önce.
foreach ($g in @@GOLGELER@@) {
    if ((Get-Command $g -ErrorAction SilentlyContinue).CommandType -ne 'Function') { [IO.File]::WriteAllText($Cikti, (@{ golge_yok = $g } | ConvertTo-Json)); exit 99 }
}
@@IZIN_PS@@
foreach ($s in $sec) {
    $ihlal = _IzinDisi $s @@IZINLI@@ @()
    if ($ihlal) { [IO.File]::WriteAllText($Cikti, (@{ izin_disi = $ihlal } | ConvertTo-Json)); exit 5 }
}
$StagingMi = [bool]$d.staging
$probePort = [int]$d.port
$BackendExe = $d.exe
foreach ($s in $sec) { . ([scriptblock]::Create($s.Extent.Text)) }
$son = @($script:Tablo | ForEach-Object { [ordered]@{ n = $_.DisplayName; p = $_.Protocol; port = "$($_.LocalPort)"; prog = $_.Program
    enabled = $_.Enabled; action = $_.Action; dir = $_.Direction; profile = $_.Profile; kilitli = $_.Kilitli } })
$api = Get-Variable -Name ApiFirewallOk -Scope Script -ErrorAction SilentlyContinue
[IO.File]::WriteAllText($Cikti, ([ordered]@{ tablo = $son; cagri = @($script:Cagri)
    api = $(if ($api) { "$($api.Value)" } else { 'TANIMSIZ' }) } | ConvertTo-Json -Depth 5))
"""


def _kos(tmp_path: Path, kurallar: list[dict], ad: str = "k") -> dict:
    surucu, durum, cikti = tmp_path / "surucu.ps1", tmp_path / f"durum_{ad}.json", tmp_path / f"cikti_{ad}.json"
    surucu.write_text(aparat_surucusu(_SURUCU, _GOLGELER, _IZINLI), encoding="utf-8-sig")
    durum.write_text(json.dumps({"staging": False, "port": 8000, "exe": EXE, "kurallar": kurallar}), encoding="utf-8")
    r = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(surucu), "-Setup", str(SETUP),
         "-Durum", str(durum), "-Cikti", str(cikti)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )  # fmt: skip
    assert cikti.exists(), f"sürücü sonuç yazmadı (rc={r.returncode}):\n{r.stdout[-800:]}\n{r.stderr[-800:]}"
    v = json.loads(cikti.read_text(encoding="utf-8-sig"))
    aparat_sonucu_denetle(v, r.returncode)
    assert "cipa" not in v, v
    t = v.get("tablo") or []
    v["tablo"] = [t] if isinstance(t, dict) else t
    v["cagri"] = v.get("cagri") or []
    return v


def _k(**e) -> dict:
    return {"n": AD, "p": "TCP", "port": 8000, "prog": EXE, **e}


def _api(v: dict) -> list[dict]:
    return [x for x in v["tablo"] if x["n"] == AD]


@pytest.mark.parametrize(
    "alan",
    [{"action": "Block"}, {"enabled": "False"}, {"dir": "Outbound"}, {"profile": "Domain"}],
    ids=lambda a: next(iter(a.items()))[1],
)
def test_KRITIK_ayni_adli_LAN_ERISIMI_VERMEYEN_kural_duzeltilir(tmp_path, alan):
    v = _kos(tmp_path, [_k(**alan), UDP])
    son = [(x["enabled"], x["action"], x["dir"], x["profile"]) for x in _api(v)]
    assert son == [("True", "Allow", "Inbound", "Any")], (
        f"'{AD}' kuralı doğru port/program ama {alan} ile 'uygun' sayıldı, DOKUNULMADI → LAN erişimi engelli kalır: {son}"
    )


def test_KARSIT_silinemeyen_GPO_kurali_varken_kural_BIRIKMEZ(tmp_path):
    """4B-3.5 sözleşmesi (D5 M-1 TUR 2 ürün kararıyla GERİ — install_backend_service H-1 ve launcher I-1 ile aynı): silinemeyen uymayan
    aynı adlı kural varken İLK koşuda doğru portlu kural yanına kurulur (LAN çalışsın), sonraki koşularda o doğru kural UYAR → ne silinir
    ne yeniden kurulur (birikme / sil-kur döngüsü yok; eskiden `-DisplayName` toplu silme her koşuda uyan kuralı da siliyordu). Silinemeyen
    kurala dokunulmaz; her koşuda eylemli UYARI + sonuç (ApiFirewallOk) False → özet / `.install_verified` apiFirewall=False."""
    durum = [_k(port=8099, kilitli=True), UDP]
    sayilar = []
    for i in range(3):
        v = _kos(tmp_path, durum, ad=str(i))
        sayilar.append(len(_api(v)))
        yeni = [c for c in v["cagri"] if c.startswith("FW-YENI")]
        assert yeni == ([f"FW-YENI {AD} TCP 8000"] if i == 0 else []), (
            f"{i}. koşu: doğru kural ilk koşuda TAM bir kez kurulmalı, sonra kurulmamalı (birikme): {v['cagri']}"
        )
        assert [(x["port"], x["kilitli"]) for x in _api(v)].count(("8000", False)) == 1, (
            f"{i}. koşu: doğru portlu (8000) kural yok ya da silindi — LAN erişimi kapalı: {_api(v)}"
        )
        assert [c for c in v["cagri"] if c.startswith("LOG UYARI") and "silinemedi" in c and "Elle:" in c], (
            f"{i}. koşu: silinemeyen kural için eylem söyleyen UYARI yok: {v['cagri']}"
        )
        assert v["api"] == "False", f"{i}. koşu: silinemeyen uymayan kural kaldı ama ApiFirewallOk = {v['api']}"
        durum = [
            {"n": x["n"], "p": x["p"], "port": x["port"], "prog": x["prog"], "kilitli": x["kilitli"]}
            for x in v["tablo"]
        ]
    assert sayilar[1] == sayilar[2] == sayilar[0], f"silme düşünce aynı adlı kural her koşuda birikiyor: {sayilar}"
    assert sayilar[0] == 2 and any(x["port"] == "8000" for x in _api(v)), (
        "ilk koşuda doğru portlu kural kurulmalı (LAN çalışsın)"
    )
    assert ("8099", True) in [(x["port"], x["kilitli"]) for x in _api(v)], f"silinemeyen kurala dokunuldu: {_api(v)}"


def test_KARSIT_dogru_kural_ve_karsilastirma_bicimleri_DOKUNULMAZ(tmp_path):
    for i, kur in enumerate([[_k(), UDP], [_k(prog=EXE.upper()), {**UDP, "prog": EXE.upper()}]]):
        v = _kos(tmp_path, kur, ad=f"karsit{i}")
        yazan = [c for c in v["cagri"] if c.startswith(("FW-YENI", "FW-SIL", "FW-DEGISTIR"))]
        assert not yazan, f"doğru kural varken güvenlik duvarı DEĞİŞTİRİLDİ: {yazan}"
