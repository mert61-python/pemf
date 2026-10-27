# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5 H-1 (DEV-C4 / G-2 sınıfı) — `install_backend_service.ps1` (A-11'in ikinci kurulum yolu) 'PEMF Backend API' ve 'PEMF UDP Discovery'
kurallarını ADIYLA değil İÇERİĞİYLE doğrular; API kuralının portu servisin GERÇEKTEN dinleyeceği porttur (servis ortamı `PEMF_API_PORT`).

ÖLÇÜLEN (HEAD c1aaba61, `:279-293`): `if (-not (Get-NetFirewallRule -DisplayName "PEMF Backend API" …)) { New-NetFirewallRule … -LocalPort 8000 }`
— aynı adlı kural devre dışı, Block, giden, yanlış protokol, başka port (eski `PEMF_API_PORT`), dar profilli ya da başka programın (taşınmış
kurulum) olsa da "var" sayılıyor, hiçbir düzeltme / uyarı yok; servis LAN'dan (mobil / web istemci — ACİL DURDUR dahil) erişilemezken betik
"Backend servisi kuruldu" ile bitiyordu. Port SABİT 8000: profil (`deploy\\<Mode>.env`, servise `AppEnvironmentExtra` ile giden) başka port
verirse backend o portta dinler, kural 8000'i açar. Betiğin güvenlik duvarı adımına hiçbir kapı dokunmuyordu (D2.73 aparatı onu ATLAR).
SÖZLEŞME (setup_services.ps1 API döngüsünün İG-9.5 + 4B-3.5 ölçütü + DEV-C4'ün kural kural işleyişi): içerik = protokol · port · program ·
etkin · Allow · Inbound · tüm profiller. Uymayan aynı adlı kural silinir; uyan kural yoksa doğrusu kurulur (çift kural yok); silinemez /
kurulamaz → `False` + eylemli UYARI; son doğrulama adla değil içerikle; sonuç kurulum özetine girer. Uzak adres KAPSAMINA dokunulmaz (A-01:
LAN güvenilir; yeni kural uzak adres vermeden kurulur, mevcut kuralın uzak adresi değiştirilmez). API portu `PEMF_API_PORT` backend'in
`ortam_portu` kuralıyla (`Test-PemfApiPortDegeri` — setup_services.ps1 ile BİREBİR; eşlik Python `int()` anlamına karşı ölçülür); yoksa /
bozuksa backend gibi 8000 (bozuksa eylemli UYARI).
⛔ Gerçek güvenlik duvarı YOK: fonksiyonlar ve güvenlik duvarı adımı PowerShell parser'ıyla çekilir; NetSecurity cmdlet'leri durum tutan
sahtelerle gölgelenir, gölgelerin İŞLEV olduğu Get-Command ile KANITLANIR (değilse çıkış 99) ve modül OTOMATİK YÜKLEME KAPALI. Betiğin kendisi
(yönetici denetimi, NSSM, servis adımları) ÇALIŞTIRILMAZ.
"""

from __future__ import annotations

import json
from pathlib import Path

import capraz
import pytest
from test_setup_services_firewall_kaniti import PWSH, _extract_function, _ps_lit, _pwsh_file

pytestmark = pytest.mark.skipif(
    (PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) yok — PS fonksiyonu koşturulamaz"
)

BETIK = Path(__file__).resolve().parents[1] / "scripts" / "install_backend_service.ps1"
FONK = "Ensure-PemfBackendFirewallKurali"
PORT_FONK = "Get-PemfServisApiPortu"
API = "PEMF Backend API"
KESIF = "PEMF UDP Discovery"
PROG = r"C:\PEMF\dist\PEMF_Backend\PEMF_Backend.exe"
# Profil portu bilerek 8000 DEĞİL: sabit 8000 kodu bu kapıda görünür.
PORT = 8010
DOGRU_API = {
    "n": API,
    "p": "TCP",
    "port": str(PORT),
    "prog": PROG,
    "en": "True",
    "act": "Allow",
    "dir": "Inbound",
    "prof": "Any",
    "ra": ["Any"],
}
DOGRU_KESIF = dict(DOGRU_API, n=KESIF, p="UDP", port="5051")
GOLGELER = (
    "Get-NetFirewallRule",
    "Get-NetFirewallPortFilter",
    "Get-NetFirewallApplicationFilter",
    "Get-NetFirewallAddressFilter",
    "Set-NetFirewallRule",
    "Remove-NetFirewallRule",
    "New-NetFirewallRule",
    "Write-Status",
    "Write-Host",
)

_SURUCU = r"""
Import-Module Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility
$PSModuleAutoLoadingPreference = 'None'
$Durum = @@DURUM@@; $Olay = @@OLAY@@; $SilDuser = @@SILDUSER@@; $YeniDuser = @@YENIDUSER@@; $YeniBozuk = @@YENIBOZUK@@
$SorguDuser = @@SORGUDUSER@@
function _Oku { $j = Get-Content -LiteralPath $Durum -Raw | ConvertFrom-Json; foreach ($k in @($j)) { if ($k) { $k } } }  # PS 5.1 + 7
function _Yaz($t) { Set-Content -LiteralPath $Durum -Value (ConvertTo-Json -InputObject @($t) -Depth 5) -Encoding UTF8 }
function _Olay($m) { Add-Content -LiteralPath $Olay -Value $m -Encoding UTF8 }
function _Bul($o) { @(_Oku) | Where-Object { $_.id -eq $o.Kimlik } | Select-Object -First 1 }
function _Nesne($k) { [pscustomobject]@{ DisplayName = $k.n; Enabled = $k.en; Action = $k.act; Direction = $k.dir; Profile = $k.prof; Kimlik = $k.id } }
# D5 M-1 TUR 2: `sorguduser` — NetSecurity sorgusu FIRLATIR (modül yok / MpsSvc durmuş / beklenmeyen istisna) → çağıranın dış `catch`i ölçülür.
function Get-NetFirewallRule { [CmdletBinding()] param($DisplayName)
    if ($SorguDuser) { throw 'NetSecurity sorgusu düştü (sahte: MpsSvc durmuş)' }
    foreach ($k in @(_Oku)) { if ($k.n -eq $DisplayName) { _Nesne $k } } }
function Get-NetFirewallPortFilter { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject)
    process { $k = _Bul $InputObject; if ($k) { [pscustomobject]@{ Protocol = $k.p; LocalPort = $k.port } } } }
function Get-NetFirewallApplicationFilter { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject)
    process { $k = _Bul $InputObject; if ($k) { [pscustomobject]@{ Program = $k.prog } } } }
function Get-NetFirewallAddressFilter { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject)
    process { $k = _Bul $InputObject; if ($k) { [pscustomobject]@{ RemoteAddress = @($k.ra) } } } }
function Set-NetFirewallRule { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject, $DisplayName, $RemoteAddress,
        $LocalPort, $Program, $Enabled, $Action, $Profile, $Direction, $Protocol)
    process { _Olay ("SET " + $(if ($InputObject) { $InputObject.DisplayName } else { $DisplayName })) } }
function Remove-NetFirewallRule { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject, $DisplayName)
    process { if ($SilDuser) { throw 'Erişim reddedildi' }
        $ad = if ($InputObject) { $InputObject.DisplayName } else { $DisplayName }; _Olay ("REMOVE " + $ad)
        _Yaz @(@(_Oku) | Where-Object { if ($InputObject) { $_.id -ne $InputObject.Kimlik } else { $_.n -ne $DisplayName } }) } }
function New-NetFirewallRule { [CmdletBinding()] param($DisplayName, $Direction, $Program, $Action, $Protocol, $LocalPort, $Profile,
        $RemoteAddress, $Description)
    if ($YeniDuser) { throw 'RPC server unavailable' }
    _Olay ("NEW " + (@($DisplayName, $Direction, $Program, $Action, $Protocol, $LocalPort, (@($Profile) -join ','), (@($RemoteAddress) -join ',')) -join '|'))
    $t = @(_Oku); $t += [pscustomobject]@{ id = "yeni" + $t.Count; n = $DisplayName; p = "$Protocol"; port = "$LocalPort"; prog = "$Program"
        en = $(if ($YeniBozuk) { 'False' } else { 'True' }); act = "$Action"; dir = "$Direction"; prof = (@($Profile) -join ',')
        ra = @($(if ($RemoteAddress) { $RemoteAddress } else { 'Any' })) }; _Yaz $t }
function Write-Status($m, $c = 'White') { _Olay ("LOG " + $m) }
function Write-Host { param([Parameter(Position = 0)]$Object, $ForegroundColor, [switch]$NoNewline) _Olay ("HOST " + $Object) }
foreach ($g in @@GOLGELER@@) {
    if ((Get-Command $g -ErrorAction SilentlyContinue).CommandType -ne 'Function') { _Olay "GOLGE-YOK $g"; exit 99 }
}
$ErrorActionPreference = 'Stop'   # betiğin kendi tercihi (install_backend_service.ps1 başı)
@@KOD@@
"""


def surucu_kos(tmp_path: Path, kod: str, kurallar: list[dict], **bayrak) -> tuple[list[str], list[dict]]:
    """`kod`u gölgeli sürücüde koştur → (olay satırları, son kural tablosu). Sonda da kullanır (HEAD bloğu)."""
    durum, olay = tmp_path / "durum.json", tmp_path / "olay.txt"
    durum.write_text(json.dumps([dict(k, id=f"k{i}") for i, k in enumerate(kurallar)]), encoding="utf-8")
    olay.write_text("", encoding="utf-8")
    govde = _SURUCU.replace("@@DURUM@@", _ps_lit(durum)).replace("@@OLAY@@", _ps_lit(olay))
    for ad in ("SILDUSER", "YENIDUSER", "YENIBOZUK", "SORGUDUSER"):
        govde = govde.replace(f"@@{ad}@@", "$true" if bayrak.get(ad.lower()) else "$false")
    govde = govde.replace("@@GOLGELER@@", ", ".join(_ps_lit(g) for g in GOLGELER)).replace("@@KOD@@", kod)
    r = _pwsh_file(tmp_path, "d5h1.ps1", govde)
    satir = [s for s in olay.read_text(encoding="utf-8-sig").splitlines() if s.strip()]
    assert r.returncode == 0, (
        f"sürücü düştü (rc={r.returncode}; 99 = gölge kanıtlanamadı):\n{satir}\n{r.stdout}\n{r.stderr}"
    )
    son = json.loads(durum.read_text(encoding="utf-8-sig") or "[]")
    return satir, ([son] if isinstance(son, dict) else son)


# D5 M-1 TUR 2 (çürütücü 4. bulgu): betikten çekilen kod aparatta GERÇEKTEN koşar — ürün gerilemesi işleve / dilime gölgesiz bir dış komut
# (`netsh advfirewall …`, `Start-Process`, `Stop-Process`, `sc.exe`, `& $degisken`, `[Diagnostics.Process]::…`) eklerse test onu yönetici
# kabuğunda GERÇEKTEN çalıştırırdı. Çekilen her parça İZİN LİSTESİNE karşı denetlenir: listede olmayan komut (modül nitelikli ad ve
# değişkenle çağrı dahil) ya da yöntem çağrısı → IZIN-DISI (çıkış 5), kod KOŞTURULMAZ. Listedeki her komut sürücüde gölgelidir ya da saftır.
IZINLI_KOMUT = (
    *GOLGELER,
    "Log",
    "Where-Object",
    "Select-Object",
    "ForEach-Object",
    "Out-Null",
    "Test-PemfApiPortDegeri",
    "Get-PemfServisApiPortu",
    "Ensure-PemfBackendFirewallKurali",
)
IZINLI_UYE = ("Match", "ToCharArray", "GetNumericValue", "Split")
IZIN_PS = r"""
function _IzinDisi($Dugum, [string[]]$Komut, [string[]]$Uye) {
    foreach ($c in @($Dugum.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true))) {
        if ($Komut -notcontains "$($c.GetCommandName())") { return ("komut: " + $c.Extent.Text) }
    }
    foreach ($y in @($Dugum.FindAll({ param($n) $n -is [System.Management.Automation.Language.InvokeMemberExpressionAst] }, $true))) {
        if ($Uye -notcontains "$($y.Member.Extent.Text)") { return ("yontem: " + $y.Extent.Text) }
    }
    $null
}
"""


def ps_dizi(ogeler) -> str:
    return "@(" + ", ".join(_ps_lit(o) for o in ogeler) + ")"


def izin_disi_iletisi(betik: Path, ne: str, cikti: str) -> str:
    satir = [s for s in cikti.splitlines() if s.startswith("IZIN-DISI")]
    return (
        f"{betik.name} {ne}: izin listesi DIŞINDA {satir[0][len('IZIN-DISI ') :]} — aparat onu GERÇEKTEN koşardı "
        "(gerçek güvenlik duvarı / süreç / servis); kod KOŞTURULMADI. Ürün değişikliğini gözden geçirin ya da komutu gölgeleyip listeye ekleyin."
        if satir
        else ""
    )


def betik_fonksiyonu(
    tmp_path: Path, ad: str, betik: Path = BETIK, izinli: tuple = IZINLI_KOMUT, uye: tuple = IZINLI_UYE
) -> str:
    """Fonksiyon metnini PowerShell'in KENDİ parser'ıyla (FunctionDefinitionAst.Extent.Text) çek — regex değil. Gövde izin listesine
    karşı denetlenir (IZIN-DISI → çıkış 5, metin döndürülmez)."""
    cikti = tmp_path / f"{ad}.txt"
    govde = (
        IZIN_PS
        + f"""
$t = $null; $h = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile({_ps_lit(betik)}, [ref]$t, [ref]$h)
if ($h.Count) {{ Write-Output ("PARSE-ERROR: " + (($h | ForEach-Object {{ $_.Message }}) -join ' | ')); exit 3 }}
$f = $ast.Find({{ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq {_ps_lit(ad)} }}, $true)
if (-not $f) {{ Write-Output "NOT-FOUND"; exit 4 }}
$ihlal = _IzinDisi $f {ps_dizi(izinli)} {ps_dizi(uye)}
if ($ihlal) {{ Write-Output ("IZIN-DISI " + $ihlal); exit 5 }}
[System.IO.File]::WriteAllText({_ps_lit(cikti)}, $f.Extent.Text, [System.Text.UTF8Encoding]::new($false))
Write-Output "OK"
"""
    )
    r = _pwsh_file(tmp_path, f"cek_{ad}.ps1", govde)
    assert r.returncode != 5, izin_disi_iletisi(betik, f"'{ad}' işlevi", r.stdout)
    assert r.returncode == 0 and "OK" in r.stdout, (
        f"{betik.name} içinde '{ad}' fonksiyonu parser ile bulunamadı (rc={r.returncode}):\n{r.stdout}\n{r.stderr}"
    )
    return cikti.read_text(encoding="utf-8")


# Betiğin GERÇEK güvenlik duvarı adımı: üst düzeydeki NetFirewall / port / kural fonksiyonu çağrısı içeren ifadeler + sonuç değişkenlerinin
# (`$ApiFirewallOk` / `$KesifFirewallOk`) üst düzey atamaları (sırasıyla) + o fonksiyonların tanımları. HEAD'de bu, adla arayan
# `try { if (-not (Get-NetFirewallRule …)) … }` bloğudur (sonda aynı çekiciyi kullanır). D5 M-1 TUR 2: çekilen her parça İZİN LİSTESİNE karşı
# denetlenir (IZIN-DISI → çıkış 5); sonuç değişkenlerinin başlangıç ataması da adıma girer (dış `catch` yolunda sonuç ölçülür).
_ADIM = r"""
using namespace System.Management.Automation.Language
@@IZIN_PS@@
$t = $null; $h = $null
$ast = [Parser]::ParseFile(@@BETIK@@, [ref]$t, [ref]$h)
if ($h.Count) { Write-Output "PARSE-ERROR"; exit 3 }
$adlar = @('Test-PemfApiPortDegeri', 'Get-PemfServisApiPortu', 'Ensure-PemfBackendFirewallKurali')
$parca = [System.Collections.Generic.List[string]]::new()
$fonklar = @($ast.EndBlock.Statements | Where-Object { $_ -is [FunctionDefinitionAst] -and $adlar -contains $_.Name })
foreach ($f in $fonklar) { $parca.Add($f.Extent.Text) }
$adim = @($ast.EndBlock.Statements | Where-Object { $_ -isnot [FunctionDefinitionAst] -and ($_.Find({ param($n)
    $n -is [CommandAst] -and ("$($n.GetCommandName())" -like '*-NetFirewall*' -or $adlar -contains "$($n.GetCommandName())") }, $true) -or
    ($_ -is [AssignmentStatementAst] -and @('$ApiFirewallOk', '$KesifFirewallOk') -contains $_.Left.Extent.Text)) })
if (-not $adim.Count) { Write-Output "ADIM-YOK"; exit 4 }
foreach ($s in @($fonklar) + @($adim)) { $ihlal = _IzinDisi $s @@IZINLI@@ @@UYE@@; if ($ihlal) { Write-Output ("IZIN-DISI " + $ihlal); exit 5 } }
foreach ($s in $adim) { $parca.Add($s.Extent.Text) }
[System.IO.File]::WriteAllText(@@CIKTI@@, ($parca -join "`n"), [System.Text.UTF8Encoding]::new($false))
Write-Output ("OK " + $adim.Count)
"""


def betik_adimi(tmp_path: Path, betik: Path = BETIK) -> str:
    cikti = tmp_path / "adim.txt"
    govde = (
        _ADIM.replace("@@IZIN_PS@@", IZIN_PS)
        .replace("@@BETIK@@", _ps_lit(betik))
        .replace("@@CIKTI@@", _ps_lit(cikti))
        .replace("@@IZINLI@@", ps_dizi(IZINLI_KOMUT))
        .replace("@@UYE@@", ps_dizi(IZINLI_UYE))
    )
    r = _pwsh_file(tmp_path, "adim.ps1", govde)
    assert r.returncode != 5, izin_disi_iletisi(betik, "güvenlik duvarı adımı", r.stdout)
    assert r.returncode == 0 and r.stdout.startswith("OK"), f"güvenlik duvarı adımı çekilemedi:\n{r.stdout}\n{r.stderr}"
    return cikti.read_text(encoding="utf-8")


def adim_kos(tmp_path: Path, ortam: list[str], kurallar: list[dict], **bayrak) -> tuple[list[str], list[dict]]:
    """Betiğin güvenlik duvarı ADIMINI (servis ortamı `ortam`, program PROG) gölgeli sürücüde koştur. Son olaylar: `SONUC <Api> <Kesif>`."""
    on = f"$AppEnv = @({', '.join(_ps_lit(s) for s in ortam)})\n$FirewallProgram = {_ps_lit(PROG)}\n"
    son_ek = '\n_Olay ("SONUC " + "$ApiFirewallOk" + " " + "$KesifFirewallOk")\n_Olay \'ADIM-BITTI\'\n'
    satir, son = surucu_kos(tmp_path, on + betik_adimi(tmp_path) + son_ek, kurallar, **bayrak)
    assert "ADIM-BITTI" in satir, f"adım sonuna ulaşılmadı:\n{satir}"
    return satir, son


def _kos(
    tmp_path, kurallar: list[dict], *, ad: str = API, p: str = "TCP", port: int = PORT, **bayrak
) -> tuple[str, list[str], list[dict]]:
    kod = betik_fonksiyonu(tmp_path, FONK) + (
        f"\n$r = {FONK} -Ad {_ps_lit(ad)} -Protokol {_ps_lit(p)} -Port {port} -Program {_ps_lit(PROG)}\n"
        '_Olay ("SONUC " + $r + " " + $r.GetType().Name)\n'
    )
    satir, son = surucu_kos(tmp_path, kod, kurallar, **bayrak)
    sonuc = [s for s in satir if s.startswith("SONUC ")]
    assert sonuc and sonuc[-1].endswith(" Boolean"), f"fonksiyon [bool] döndürmedi:\n{satir}"
    return sonuc[-1].split()[1], satir, son


def _icerik(k: dict) -> tuple:
    ra = k["ra"] if isinstance(k["ra"], list) else [k["ra"]]
    return (k["n"], k["p"], str(k["port"]), k["prog"].lower(), k["en"], k["act"], k["dir"], k["prof"], tuple(ra))


def _degisiklik(satir: list[str]) -> list[str]:
    return [s for s in satir if s.startswith(("SET ", "REMOVE ", "NEW "))]


def _uyari(satir: list[str]) -> list[str]:
    return [s for s in satir if s.startswith("LOG UYARI")]


def _yeni(k: dict) -> str:
    """Doğru kuralın New-NetFirewallRule argümanları (ad|yön|program|eylem|protokol|port|profil|uzak adres) — uzak adres VERİLMEZ (A-01)."""
    return f"NEW {k['n']}|Inbound|{PROG}|Allow|{k['p']}|{k['port']}|Any|"


BOZUK = {
    "devre_disi": {"en": "False"},
    "engelle": {"act": "Block"},
    "giden": {"dir": "Outbound"},
    "yanlis_protokol": {"p": "UDP"},
    "baska_port": {"port": "8000"},
    "dar_profil": {"prof": "Private"},
    "baska_program": {"prog": r"D:\ESKI\PEMF_Backend\PEMF_Backend.exe"},
}


@pytest.mark.parametrize("bozukluk", list(BOZUK))
def test_KRITIK_API_ayni_adli_ICERIGI_UYMAYAN_kural_silinir_DOGRUSU_kurulur(tmp_path, bozukluk):
    sonuc, satir, son = _kos(tmp_path, [dict(DOGRU_API, **BOZUK[bozukluk])])
    assert [_icerik(k) for k in son] == [_icerik(DOGRU_API)], (
        f"aynı adlı ama içeriği uymayan ({bozukluk}) API kuralı yerinde kaldı — yalnız ADA bakılıyor; servis LAN'dan erişilemez:\n"
        f"{son}\n{satir}"
    )
    assert f"REMOVE {API}" in satir and _yeni(DOGRU_API) in satir, (
        f"uymayan kural silinip yerine DOĞRU (TCP {PORT}, program, Inbound Allow Any) kural kurulmadı:\n{satir}"
    )
    assert sonuc == "True" and not _uyari(satir), f"doğrusu kuruldu ama sonuç {sonuc} / uyarı var:\n{satir}"


@pytest.mark.parametrize("bozukluk", [{"p": "TCP"}, {"port": "5052"}, {"en": "False"}])
def test_KRITIK_KESIF_ayni_adli_ICERIGI_UYMAYAN_kural_silinir_DOGRUSU_kurulur(tmp_path, bozukluk):
    sonuc, satir, son = _kos(tmp_path, [dict(DOGRU_KESIF, **bozukluk)], ad=KESIF, p="UDP", port=5051)
    assert [_icerik(k) for k in son] == [_icerik(DOGRU_KESIF)], (
        f"aynı adlı ama içeriği uymayan ({bozukluk}) keşif kuralı yerinde kaldı — mobil uygulama cihazı bulamaz:\n{son}\n{satir}"
    )
    assert _yeni(DOGRU_KESIF) in satir and sonuc == "True", (
        f"keşif kuralı DOĞRU argümanlarla (UDP 5051, program, Inbound Allow Any) kurulmadı ya da sonuç {sonuc}:\n{satir}"
    )


def _yeniden(son: list[dict]) -> list[dict]:
    """Bir koşunun son tablosu → sonraki koşunun girdisi (kimlikler sürücüde yeniden verilir)."""
    return [{x: k[x] for x in k if x != "id"} for k in son]


@pytest.mark.parametrize(
    "kural", [dict(DOGRU_API, en="False"), dict(DOGRU_API, port="8099")], ids=["devre_disi", "baska_port_Allow"]
)
def test_KRITIK_uymayan_kural_SILINEMEZSE_ona_DOKUNULMAZ_DOGRUSU_yine_kurulur_FALSE_ve_eylemli_UYARI(tmp_path, kural):
    """D5 M-1 TUR 2 ürün kararı (4B-3.5 'ilk koşuda doğru portlu kural kurulsun — LAN çalışsın', launcher I-1 ile aynı): silinemeyen
    (ilke deposu) uymayan aynı adlı kural yerinde kalır, yanına DOĞRU kural kurulur; sonuç yine False + eylemli UYARI (silinemeyen kural
    Block ise Allow'u ezer — özet görünür kılar). Eskiden (H-1) doğru kural HİÇ kurulmuyor, LAN (mobil ACİL DURDUR dahil) kapalı kalıyordu."""
    sonuc, satir, son = _kos(tmp_path, [kural], silduser=True)
    assert sonuc == "False", f"uymayan kural silinemedi ama sonuç True:\n{satir}"
    assert _icerik(kural) in [_icerik(k) for k in son], (
        f"silinemeyen kurala dokunuldu / tablodan düştü:\n{son}\n{satir}"
    )
    assert _yeni(DOGRU_API) in satir and sorted(_icerik(k) for k in son) == sorted(
        [_icerik(kural), _icerik(DOGRU_API)]
    ), (
        f"silinemeyen uymayan kural varken DOĞRU kural (TCP {PORT}, program, Inbound Allow Any) kurulmadı — LAN erişimi kapalı kalır:\n"
        f"{son}\n{satir}"
    )
    assert [
        s for s in _uyari(satir) if "silinemedi" in s and "Remove-NetFirewallRule" in s and "New-NetFirewallRule" in s
    ], f"silinemeyen kural için eylem söyleyen UYARI yok:\n{satir}"


def test_KRITIK_silinemeyen_kural_varken_IKINCI_kosuda_BIRIKMEZ_ve_SIL_KUR_dongusu_yok(tmp_path):
    """İdempotens: ilk koşu doğruyu yanına kurar; ikinci koşuda doğru kural UYAR → yenisi kurulmaz, uyan silinmez, tablo AYNI kalır."""
    kural = dict(DOGRU_API, port="8099")
    (tmp_path / "1").mkdir()
    (tmp_path / "2").mkdir()
    birinci, satir1, son1 = _kos(tmp_path / "1", [kural], silduser=True)
    ikinci, satir2, son2 = _kos(tmp_path / "2", _yeniden(son1), silduser=True)
    assert len([s for s in satir1 if s.startswith("NEW ")]) == 1, f"ilk koşu doğru kuralı kurmadı:\n{satir1}"
    assert not [s for s in satir2 if s.startswith(("NEW ", "REMOVE "))], (
        f"ikinci koşuda kural yeniden kuruldu / silindi:\n{satir2}"
    )
    assert sorted(_icerik(k) for k in son2) == sorted(_icerik(k) for k in son1) and len(son2) == 2, (
        f"silme düşünce aynı adlı kural BİRİKİYOR / değişiyor:\n{son1}\n{son2}"
    )
    assert birinci == ikinci == "False", f"silinemeyen uymayan kural duruyor ama sonuç {birinci}/{ikinci}"


def test_KARSIT_ayni_adli_IKI_DOGRU_kural_dokunulmaz_TRUE(tmp_path):
    """Çürütücü x1 (eşik +1: `Count -gt 0` → `-eq 1`): aynı adlı iki doğru kural (ör. elle eklenmiş kopya) LAN'ı açar — dokunulmaz, True."""
    sonuc, satir, son = _kos(tmp_path, [DOGRU_API, dict(DOGRU_API)])
    assert not _degisiklik(satir) and not _uyari(satir), f"iki doğru kural varken değişiklik / sahte UYARI:\n{satir}"
    assert len(son) == 2 and sonuc == "True", (
        f"aynı adlı iki DOĞRU kural varken sonuç {sonuc} (beklenen True):\n{satir}"
    )


def test_KRITIK_uyan_kuralin_YANINDA_silinemeyen_uymayan_kural_varsa_FALSE(tmp_path):
    """Windows güvenlik duvarında Block, Allow'u ezer: uyan kural dursa da silinemeyen aynı adlı Block kuralı LAN erişimini keser."""
    sonuc, satir, son = _kos(tmp_path, [DOGRU_API, dict(DOGRU_API, act="Block")], silduser=True)
    assert sonuc == "False", (
        f"uyan kuralın yanında silinemeyen Block kuralı kaldı (erişim kesik) ama sonuç 'doğrulandı' (True):\n{satir}"
    )
    assert len(son) == 2 and not [s for s in satir if s.startswith("NEW ")], (
        f"silinemeyen ikizde tablo değişti:\n{son}\n{satir}"
    )
    assert [s for s in _uyari(satir) if "silinemedi" in s and "Remove-NetFirewallRule" in s], (
        f"silinemeyen kural için eylem söyleyen UYARI yok:\n{satir}"
    )


def test_KRITIK_uymayan_silindi_ama_YENISI_kurulamadi_FALSE_ve_YOK_uyarisi(tmp_path):
    sonuc, satir, son = _kos(tmp_path, [dict(DOGRU_API, act="Block")], yeniduser=True)
    assert not [k for k in son if k["n"] == API], f"aparat: yeni kural kurulamadığı hâlde tabloda kural var:\n{son}"
    assert sonuc == "False", f"kural silindi, yenisi kurulamadı (kural YOK) ama sonuç {sonuc}:\n{satir}"
    assert [s for s in _uyari(satir) if "kuralı YOK" in s and "New-NetFirewallRule" in s and str(PORT) in s], (
        f"kural kurulamadı ama 'kuralı YOK' + elle kurma komutu söyleyen UYARI yok:\n{satir}"
    )


def test_KRITIK_SON_DOGRULAMA_adla_degil_ICERIKLE_kurulan_kural_uymuyorsa_FALSE(tmp_path):
    """Cmdlet 'başarılı' ama ortaya çıkan kural devre dışı (ör. ilke) → son sorgu adla değil içerikle: False + UYARI."""
    sonuc, satir, _son = _kos(tmp_path, [], yenibozuk=True)
    assert _yeni(DOGRU_API) in satir, f"kural doğru argümanlarla kurulmadı (beklenen {_yeni(DOGRU_API)!r}):\n{satir}"
    assert sonuc == "False", f"kurulan kural devre dışı ama son doğrulama yalnız ADA baktı (True):\n{satir}"
    assert [s for s in _uyari(satir) if API in s], f"içerikle doğrulanamayan kural için UYARI yok:\n{satir}"


def test_KARSIT_uyan_kural_VARKEN_dokunulmaz_uyari_yok(tmp_path):
    sonuc, satir, son = _kos(tmp_path, [DOGRU_API])
    assert not _degisiklik(satir) and not _uyari(satir), satir
    assert [_icerik(k) for k in son] == [_icerik(DOGRU_API)] and sonuc == "True"


def test_KARSIT_program_yolu_BUYUK_KUCUK_harf_farki_UYAN_sayilir(tmp_path):
    """Windows yolları harf duyarsız (setup_services `-ne` ile aynı) — yalnız harf farkı yüzünden kural silinip yeniden kurulmaz."""
    kural = dict(DOGRU_API, prog=PROG.upper())
    sonuc, satir, _son = _kos(tmp_path, [kural])
    assert not _degisiklik(satir) and sonuc == "True", satir


def test_KARSIT_uyan_ve_uymayan_IKIZ_yalniz_uymayan_silinir_CIFT_kural_kurulmaz(tmp_path):
    sonuc, satir, son = _kos(tmp_path, [DOGRU_API, dict(DOGRU_API, act="Block")])
    assert [_icerik(k) for k in son] == [_icerik(DOGRU_API)], (
        f"ikizden yanlış olan kaldı ya da çift kural kuruldu:\n{son}\n{satir}"
    )
    assert not [s for s in satir if s.startswith("NEW ")] and sonuc == "True", satir


def test_KARSIT_kural_yoksa_DOGRU_icerikle_ve_uzak_adres_VERILMEDEN_kurulur(tmp_path):
    sonuc, satir, son = _kos(tmp_path, [])
    assert _yeni(DOGRU_API) in satir, (
        f"kural TCP {PORT} · program · Inbound Allow Any (uzak adres verilmeden) kurulmadı:\n{satir}"
    )
    assert [_icerik(k) for k in son] == [_icerik(DOGRU_API)] and sonuc == "True" and not _uyari(satir), satir


@pytest.mark.parametrize("ra", [["LocalSubnet"], ["192.168.1.0/24", "192.168.137.0/24"]])
def test_KARSIT_uzak_adres_KAPSAMI_DEGISTIRILMEZ_A01(tmp_path, ra):
    """A-01 (LAN güvenilir): kapsam kararı bu düzeltmenin işi değil — içeriği uyan kuralın uzak adresi ne genişletilir ne daraltılır."""
    kural = dict(DOGRU_API, ra=ra)
    sonuc, satir, son = _kos(tmp_path, [kural])
    assert not _degisiklik(satir) and [_icerik(k) for k in son] == [_icerik(kural)], (
        f"uzak adres kapsamı değiştirildi (A-01 kararı olmadan):\n{satir}"
    )
    assert sonuc == "True", satir


# ── Betik ADIMI (gerçek üst düzey ifadeler): port servis ortamından, iki kural, içerikle ──
def test_KRITIK_ADIM_API_kurali_PROFIL_portunu_acar_SABIT_8000_degil(tmp_path):
    satir, son = adim_kos(tmp_path, ["PEMF_HEADLESS=1", f"PEMF_API_PORT={PORT}", "PEMF_LOG_DIR=C:\\x"], [])
    assert sorted(_icerik(k) for k in son) == sorted([_icerik(DOGRU_API), _icerik(DOGRU_KESIF)]), (
        f"servis {PORT}'da dinler (profil PEMF_API_PORT) ama güvenlik duvarı başka port açtı — LAN erişimi engelli:\n{son}\n{satir}"
    )


def test_KRITIK_ADIM_ayni_adli_bozuk_IKI_kural_da_duzeltilir(tmp_path):
    kurallar = [dict(DOGRU_API, en="False"), dict(DOGRU_KESIF, act="Block")]
    satir, son = adim_kos(tmp_path, [f"PEMF_API_PORT={PORT}"], kurallar)
    assert sorted(_icerik(k) for k in son) == sorted([_icerik(DOGRU_API), _icerik(DOGRU_KESIF)]), (
        f"betik adımı aynı adlı bozuk kuralları 'var' sayıp bıraktı:\n{son}\n{satir}"
    )


def test_KRITIK_ADIM_eski_PORTLU_kural_yeni_profil_portuna_TASINIR(tmp_path):
    """İG-9.5'in 'eski PEMF_API_PORT' kolu: kural 8000'de, profil 8010 → 8000 kuralı silinir, 8010 açılır."""
    satir, son = adim_kos(tmp_path, [f"PEMF_API_PORT={PORT}"], [dict(DOGRU_API, port="8000"), DOGRU_KESIF])
    assert sorted(_icerik(k) for k in son) == sorted([_icerik(DOGRU_API), _icerik(DOGRU_KESIF)]), (
        f"eski porttaki (8000) aynı adlı kural profil portuna ({PORT}) taşınmadı:\n{son}\n{satir}"
    )


def test_KRITIK_ADIM_NetSecurity_sorgusu_FIRLATIRSA_denetlenemedi_UYARISI_ve_sonuc_FALSE(tmp_path):
    """Çürütücü x2 sınıfı (dış catch yolu): kural işlevi FIRLATIRSA (NetSecurity modülü yok / MpsSvc durmuş) sonuç başlangıç değerinde
    kalır — o değer False olmalı ve günlük 'denetlenemedi' demeli; özet 'kural DOĞRULANAMADI' der."""
    satir, _son = adim_kos(tmp_path, [f"PEMF_API_PORT={PORT}"], [], sorguduser=True)
    assert [s for s in _uyari(satir) if "denetlenemedi" in s], (
        f"kural denetimi fırladı ama 'denetlenemedi' UYARIsı yok:\n{satir}"
    )
    assert "SONUC False False" in satir, f"kural denetimi fırladı ama sonuç (Api / Keşif) 'doğrulandı' kaldı:\n{satir}"


def test_KARSIT_ADIM_kural_YOKSA_ikisi_kurulur_sonuc_TRUE(tmp_path):
    satir, _son = adim_kos(tmp_path, [f"PEMF_API_PORT={PORT}"], [])
    assert "SONUC True True" in satir and not _uyari(satir), f"iki kural kuruldu ama sonuç / UYARI:\n{satir}"


# ── Sıra (AST): betik YUKARIDAN AŞAĞIYA koşar — üst düzeyde çağrılan her betik işlevi ilk çağrısından ÖNCE tanımlı olmalı ──
_SIRA = r"""
using namespace System.Management.Automation.Language
$t = $null; $h = $null
$ast = [Parser]::ParseFile(@@BETIK@@, [ref]$t, [ref]$h)
if ($h.Count) { Write-Output "PARSE-ERROR"; exit 3 }
$ust = @($ast.EndBlock.Statements)
$tanim = @{}
for ($i = 0; $i -lt $ust.Count; $i++) { if ($ust[$i] -is [FunctionDefinitionAst] -and -not $tanim.ContainsKey($ust[$i].Name)) { $tanim[$ust[$i].Name] = $i } }
$ihlal = [System.Collections.Generic.List[string]]::new()
$denetlenen = [System.Collections.Generic.List[string]]::new()
for ($i = 0; $i -lt $ust.Count; $i++) {
    if ($ust[$i] -is [FunctionDefinitionAst]) { continue }
    foreach ($c in @($ust[$i].FindAll({ param($n) $n -is [CommandAst] }, $true))) {
        $p = $c.Parent; $ic = $false
        while ($p -and -not [object]::ReferenceEquals($p, $ust[$i])) { if ($p -is [FunctionDefinitionAst]) { $ic = $true; break }; $p = $p.Parent }
        $ad = "$($c.GetCommandName())"
        if ($ic -or -not $tanim.ContainsKey($ad)) { continue }
        $denetlenen.Add($ad)
        if ($tanim[$ad] -gt $i) { $ihlal.Add("$ad (tanim ifadesi #$($tanim[$ad]) > cagri ifadesi #$i, satir $($c.Extent.StartLineNumber))") }
    }
}
[pscustomobject]@{ ihlal = @($ihlal); denetlenen = @($denetlenen | Sort-Object -Unique) } | ConvertTo-Json -Compress
"""


def tanim_cagri_sirasi(tmp_path: Path, betik: Path) -> dict:
    r = _pwsh_file(tmp_path, f"sira_{betik.stem}.ps1", _SIRA.replace("@@BETIK@@", _ps_lit(betik)))
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    a = json.loads(r.stdout.strip().splitlines()[-1])
    return {k: (v if isinstance(v, list) else [v]) for k, v in a.items()}


def test_KRITIK_islev_TANIMI_ilk_UST_DUZEY_cagrisindan_ONCE(tmp_path):
    """Çürütücü x3 (tanım YERİ): işlev tanımı çağıran ifadenin ARKASINA taşınırsa metin birebir kalır, parser ile çeken aparat işlevi
    dilimin önüne koyduğu için yeşil kalır — ama gerçek betikte çağrı anında işlev YOKTUR (CommandNotFound → dış catch → kural HİÇ
    kurulmaz, her kurulumda 'kural DOĞRULANAMADI')."""
    a = tanim_cagri_sirasi(tmp_path, BETIK)
    assert {FONK, PORT_FONK} <= set(a["denetlenen"]), (
        f"aparat: kural / port işlevi çağrısı üst düzeyde bulunamadı (kör denetim): {a}"
    )
    assert not a["ihlal"], (
        f"{BETIK.name}: işlev ilk üst düzey çağrısından SONRA tanımlanmış — çağrı anında işlev YOK: {a['ihlal']}"
    )


def test_KARSIT_ADIM_profilde_port_YOKSA_8000(tmp_path):
    satir, son = adim_kos(tmp_path, ["PEMF_HEADLESS=1"], [])
    beklenen = dict(DOGRU_API, port="8000")
    assert sorted(_icerik(k) for k in son) == sorted([_icerik(beklenen), _icerik(DOGRU_KESIF)]), (
        f"profilde PEMF_API_PORT yokken (backend 8000) güvenlik duvarı 8000 + 5051 açmadı:\n{son}\n{satir}"
    )
    assert not _uyari(satir), f"geçerli kurulumda UYARI basıldı:\n{satir}"


def test_KRITIK_ADIM_profilde_port_BOZUKSA_backend_gibi_8000_ve_eylemli_UYARI(tmp_path):
    """Backend `ortam_portu` bozuk değerde uyarıyla 8000'e düşer — kural da 8000'i açar ve kurulum günlüğü bunu SÖYLER."""
    satir, son = adim_kos(tmp_path, ["PEMF_API_PORT=80O0"], [])
    beklenen = dict(DOGRU_API, port="8000")
    assert sorted(_icerik(k) for k in son) == sorted([_icerik(beklenen), _icerik(DOGRU_KESIF)]), (
        f"bozuk PEMF_API_PORT'ta backend 8000'de dinler ama güvenlik duvarı 8000 + 5051 açmadı:\n{son}\n{satir}"
    )
    assert [s for s in _uyari(satir) if "PEMF_API_PORT" in s and "80O0" in s and "8000" in s], (
        f"bozuk PEMF_API_PORT sessiz geçti (eylemli UYARI yok):\n{satir}"
    )


# ── Port: backend `ortam_portu` (Python int() + 1..65535) anlamı; setup_services.ps1 ile EŞLİK ──
_PORT_GIRDILERI = [
    "8000",
    "8010",
    " 8010 ",
    "+8010",
    "08000",
    "8_010",
    "\u0668\u0660\u0661\u0660",
    "1",
    "65535",
    "0",
    "65536",
    "-1",
    "80O0",
    "",
    "sekizbin",
    "1_",
    "_1",
    "8__0",
    "1e3",
    "8010.0",
]


def _backend_portu(ham: str) -> int:
    """`backend_service.ortam_portu`nun anlamı (Python int(); 1..65535; aksi 8000) — ürün kodu İÇE AKTARILMADAN."""
    try:
        p = int(ham)
    except ValueError:
        return 8000
    return p if 1 <= p <= 65535 else 8000


def test_KRITIK_API_portu_backend_anlaminda_ve_setup_services_ile_ESLIK(tmp_path):
    kendi = betik_fonksiyonu(tmp_path, "Test-PemfApiPortDegeri") + "\n" + betik_fonksiyonu(tmp_path, PORT_FONK)
    kurulum = _extract_function(tmp_path, "Test-PemfApiPortDegeri").replace(
        "Test-PemfApiPortDegeri", "Test-PemfApiPortDegeri_SetupServices", 1
    )
    satirlar = []
    for i, ham in enumerate(_PORT_GIRDILERI):
        s = _ps_lit(ham)
        satirlar.append(
            f'Write-Output ("{i} " + ({PORT_FONK} @({_ps_lit("PEMF_API_PORT=" + ham)})) + " " + '
            f"$(if ((Test-PemfApiPortDegeri_SetupServices {s}).Port) {{ (Test-PemfApiPortDegeri_SetupServices {s}).Port }} else {{ 8000 }}))"
        )
    govde = "function Write-Status($m, $c) { }\n" + "\n".join([kendi, kurulum, *satirlar]) + "\n"
    r = _pwsh_file(tmp_path, "port.ps1", govde)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    sonuc = {int(s.split()[0]): s.split()[1:] for s in r.stdout.splitlines() if s.strip()}
    for i, ham in enumerate(_PORT_GIRDILERI):
        beklenen = str(_backend_portu(ham))
        assert sonuc.get(i, [None])[0] == beklenen, (
            f"PEMF_API_PORT={ham!r} → güvenlik duvarı portu {sonuc.get(i)} — backend {beklenen}'de dinler (ortam_portu)"
        )
        assert sonuc[i][0] == sonuc[i][1], f"setup_services.ps1 ile API portu AYRIŞTI ({ham!r}): {sonuc[i]}"


@pytest.mark.parametrize(
    ("ortam", "beklenen"),
    [
        ([], "8000"),
        (["PEMF_HEADLESS=1"], "8000"),
        (["PEMF_API_PORTU=9000"], "8000"),
        (["X_PEMF_API_PORT=9000"], "8000"),
        (["PEMF_API_HOST=0.0.0.0", "PEMF_API_PORT=8123"], "8123"),
    ],
)
def test_KRITIK_API_portu_YALNIZ_PEMF_API_PORT_anahtarindan(tmp_path, ortam, beklenen):
    kod = betik_fonksiyonu(tmp_path, "Test-PemfApiPortDegeri") + "\n" + betik_fonksiyonu(tmp_path, PORT_FONK)
    dizi = ", ".join(_ps_lit(s) for s in ortam)
    kod += f"\n_Olay (\"PORT \" + ({PORT_FONK} @({dizi})))\n"
    satir, _son = surucu_kos(tmp_path, kod, [])
    assert f"PORT {beklenen}" in satir, f"servis ortamı {ortam} → port {satir} (beklenen {beklenen})"


# ── Betik bağlantısı (AST): eski ad-araması geri gelemez, iki çağrı, port servis ortamından, sonuç özete girer ──
_AST = r"""
using namespace System.Management.Automation.Language
$t = $null; $h = $null
$ast = [Parser]::ParseFile(@@BETIK@@, [ref]$t, [ref]$h)
function _FonkIci($n) { $p = $n.Parent; while ($p) { if ($p -is [FunctionDefinitionAst]) { return $true }; $p = $p.Parent }; $false }
function _TryIci($n) { $p = $n.Parent; while ($p) { if ($p -is [TryStatementAst]) { return $true }; $p = $p.Parent }; $false }
function _Arg($c, [string]$ad) {
    for ($i = 0; $i -lt $c.CommandElements.Count; $i++) {
        $e = $c.CommandElements[$i]
        if ($e -is [CommandParameterAst] -and $e.ParameterName -eq $ad) {
            if ($e.Argument) { return $e.Argument } elseif ($i + 1 -lt $c.CommandElements.Count) { return $c.CommandElements[$i + 1] }
        }
    }
    $null
}
function _Deger($e) { if ($e -is [StringConstantExpressionAst]) { $e.Value } elseif ($e) { $e.Extent.Text } else { '' } }
function _Atanan($c) { $p = $c.Parent; while ($p -and -not ($p -is [AssignmentStatementAst])) { $p = $p.Parent }; if ($p) { $p.Left.VariablePath.UserPath } else { '' } }
function _SonraIfte($ad, $sonra) {
    [bool]@($ast.FindAll({ param($n) $n -is [IfStatementAst] -and -not (_FonkIci $n) -and $n.Extent.StartOffset -gt $sonra }, $true) |
        Where-Object { $_.Clauses | Where-Object { $_.Item1.FindAll({ param($v) $v -is [VariableExpressionAst] -and $v.VariablePath.UserPath -eq $ad }, $true) } }).Count
}
$komut = @($ast.FindAll({ param($n) $n -is [CommandAst] }, $true))
$fw = @($komut | Where-Object { "$($_.GetCommandName())" -like '*-NetFirewall*' })
$cagri = @($komut | Where-Object { $_.GetCommandName() -eq @@FONK@@ -and -not (_FonkIci $_) })
$portCagri = @($komut | Where-Object { $_.GetCommandName() -eq @@PORTFONK@@ -and -not (_FonkIci $_) })
$ortamCagri = $komut | Where-Object { $_.Extent.Text -match 'AppEnvironmentExtra' } | Select-Object -First 1
$ortamDeg = ''
if ($ortamCagri) { $y = $ortamCagri.CommandElements | Where-Object { $_ -is [VariableExpressionAst] -and $_.Splatted } | Select-Object -First 1; if ($y) { $ortamDeg = $y.VariablePath.UserPath } }
$portDeg = ''; $portArg = ''
if ($portCagri.Count -eq 1) {
    $portDeg = _Atanan $portCagri[0]
    $a = $portCagri[0].CommandElements | Select-Object -Skip 1 | Select-Object -First 1
    if ($a -is [VariableExpressionAst]) { $portArg = $a.VariablePath.UserPath }
}
$kurallar = @($cagri | ForEach-Object {
    $pe = _Arg $_ 'Port'; $pr = _Arg $_ 'Program'
    [pscustomobject]@{
        ad = _Deger (_Arg $_ 'Ad'); protokol = _Deger (_Arg $_ 'Protokol'); port = _Deger $pe
        port_degisken = $(if ($pe -is [VariableExpressionAst]) { $pe.VariablePath.UserPath } else { '' })
        program = $(if ($pr -is [VariableExpressionAst]) { $pr.VariablePath.UserPath } else { '' })
        hedef = _Atanan $_; sonra = (_SonraIfte (_Atanan $_) $_.Extent.EndOffset)
    } })
$url = @($ast.FindAll({ param($n) $n -is [ExpandableStringExpressionAst] -and $n.Value -match 'localhost:' -and -not (_FonkIci $n) }, $true) |
    ForEach-Object { @($_.NestedExpressions | Where-Object { $_ -is [VariableExpressionAst] } | ForEach-Object { $_.VariablePath.UserPath }) -join ',' })
$sabitUrl = @($ast.FindAll({ param($n) $n -is [StringConstantExpressionAst] -and $n.Value -match 'localhost:\d' }, $true) | ForEach-Object { $_.Value })
[pscustomobject]@{
    hata = @($h | ForEach-Object { $_.Message })
    fonk_disi_fw = @($fw | Where-Object { -not (_FonkIci $_) } | ForEach-Object { $_.Extent.Text })
    new_kosulsuz = @($fw | Where-Object { $_.GetCommandName() -eq 'New-NetFirewallRule' -and -not ((_TryIci $_) -and $_.Extent.Text -match '-ErrorAction\s+Stop') } | ForEach-Object { $_.Extent.Text })
    kurallar = $kurallar; port_cagri = $portCagri.Count; port_deg = $portDeg; port_arg = $portArg; ortam_deg = $ortamDeg
    url = $url; sabit_url = $sabitUrl
} | ConvertTo-Json -Depth 5 -Compress
"""


def test_KRITIK_betik_FW_adimi_icerik_fonksiyonuna_BAGLI_port_TEK_kaynaktan_ve_ozete_girer(tmp_path):
    govde = (
        _AST.replace("@@BETIK@@", _ps_lit(BETIK))
        .replace("@@FONK@@", _ps_lit(FONK))
        .replace("@@PORTFONK@@", _ps_lit(PORT_FONK))
    )
    r = _pwsh_file(tmp_path, "ast.ps1", govde)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    a = json.loads(r.stdout.strip().splitlines()[-1])
    assert not a["hata"], f"betik ayrıştırılamadı: {a['hata']}"
    assert not a["fonk_disi_fw"], (
        f"fonksiyon DIŞINDA NetFirewall çağrısı var — adla arayan eski adım geri mi geldi? {a['fonk_disi_fw']}"
    )
    assert not a["new_kosulsuz"], f"New-NetFirewallRule try dışında / -ErrorAction Stop'suz: {a['new_kosulsuz']}"
    kurallar = a["kurallar"] if isinstance(a["kurallar"], list) else [a["kurallar"]]
    gorulen = sorted((k["ad"], k["protokol"].upper()) for k in kurallar)
    assert gorulen == [(API, "TCP"), (KESIF, "UDP")], (
        f"{FONK} betikte API (TCP) + keşif (UDP) için birer kez çağrılmalı (görülen {gorulen}) — güvenlik duvarı adımı bağlı değil"
    )
    assert a["ortam_deg"] and a["port_cagri"] == 1 and a["port_arg"] == a["ortam_deg"], (
        f"API portu servise giden ortamdan (${a['ortam_deg'] or '?'}, AppEnvironmentExtra) hesaplanmıyor: {PORT_FONK} "
        f"{a['port_cagri']} kez, argüman ${a['port_arg'] or '?'}"
    )
    for k in kurallar:
        assert k["program"] == "FirewallProgram", (
            f"{k['ad']} kuralı servis ikilisine ($FirewallProgram) bağlı değil: {k}"
        )
        assert k["hedef"] and k["sonra"], (
            f"{k['ad']} sonucu (${k['hedef'] or '?'}) sonraki bir koşulda kullanılmıyor — kurulum özeti doğrulanamayan kuralı söylemez"
        )
    api = next(k for k in kurallar if k["ad"] == API)
    kesif = next(k for k in kurallar if k["ad"] == KESIF)
    assert api["port_degisken"] and api["port_degisken"] == a["port_deg"], (
        f"API kuralının portu ({api['port']}) servis ortamından hesaplanan değişken (${a['port_deg']}) değil — sabit port mu?"
    )
    assert kesif["port"] == "5051", f"keşif kuralı backend'in keşif portunu (UDP 5051, headless_core) açmıyor: {kesif}"
    url = a["url"] if isinstance(a["url"], list) else [a["url"]]
    assert url and all(a["port_deg"] in u.split(",") for u in url) and not a["sabit_url"], (
        f"kurulum özetindeki URL servis portunu (${a['port_deg']}) göstermiyor: {url} / sabit {a['sabit_url']}"
    )
