# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5 G-2 (DEV-C4 sınıfı) — `install_mosquitto_service.ps1` (A-11'in ikinci kurulum yolu) 'PEMF Mosquitto MQTT' kuralını ADIYLA değil
İÇERİĞİYLE doğrular: TCP · 1883 · Inbound · Allow · etkin · tüm profiller · uzak adres YALNIZ hotspot alt ağı (192.168.137.0/24).

ÖLÇÜLEN (HEAD 8d9169cf, `:130`): `if (-not (Get-NetFirewallRule -DisplayName "PEMF Mosquitto MQTT" …))` — aynı adlı kural devre dışı,
Block, giden, UDP, başka port, dar profilli ya da uzak adresi Any (P0-3: anonim broker klinik LAN'ına açık) olsa da "var" sayılıyor,
hiçbir düzeltme / uyarı yapılmıyor, betik "✓ Mosquitto servisi çalışıyor" ile bitiyordu. Betiğin güvenlik duvarı adımına hiçbir kapı
dokunmuyordu (tek kapı `test_A11_…_G33` yalnız `$conf` bloğunu okur).
SÖZLEŞME (setup_services.ps1 `Ensure-PemfMosquittoFirewallRule` — D3.42 + DEV-C4 — ile AYNI): ESP KAPALI (varsayılan): içeriği uymayan
aynı adlı kural silinir, doğrusu kurulur (uyan kural varsa yenisi kurulmaz); geniş uzak adres hotspot'a daraltılır; uzak adres
OKUNAMAZSA değiştirilmez. ESP ETKİN: dokunulmaz (Y3 / A-04), eylemli UYARI. Silinemez / kurulamaz → `False` + eylemli UYARI. Son
doğrulama adla değil içerikle. ESP kipi backend'in anlamıyla (`Test-PemfEspEtkin`, setup_services ile eşlik ÖLÇÜLÜR) makine
ortamından okunur; sonuç kurulum özetine girer.
⛔ Gerçek güvenlik duvarı YOK: fonksiyon PowerShell parser'ıyla çekilir; NetSecurity cmdlet'leri durum tutan sahtelerle gölgelenir,
gölgelerin İŞLEV olduğu Get-Command ile KANITLANIR (değilse çıkış 99) ve modül OTOMATİK YÜKLEME KAPALI. Betiğin kendisi (yönetici
denetimi, Program Files / servis adımları) ÇALIŞTIRILMAZ.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_setup_services_firewall_kaniti import PWSH, _extract_function, _ps_lit, _pwsh_file

pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh (PowerShell 7) yok — PS fonksiyonu koşturulamaz")

BETIK = Path(__file__).resolve().parents[1] / "scripts" / "install_mosquitto_service.ps1"
FONK = "Ensure-PemfMosquittoServisFirewallRule"
AD = "PEMF Mosquitto MQTT"
HOTSPOT = "192.168.137.0/24"
DOGRU = {
    "n": AD,
    "ra": [HOTSPOT],
    "p": "TCP",
    "port": "1883",
    "en": "True",
    "act": "Allow",
    "dir": "Inbound",
    "prof": "Any",
}
GOLGELER = (
    "Get-NetFirewallRule",
    "Get-NetFirewallAddressFilter",
    "Get-NetFirewallPortFilter",
    "Set-NetFirewallRule",
    "Remove-NetFirewallRule",
    "New-NetFirewallRule",
    "Write-Status",
)

_SURUCU = r"""
Import-Module Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility
$PSModuleAutoLoadingPreference = 'None'
$Durum = @@DURUM@@; $Olay = @@OLAY@@; $SilDuser = @@SILDUSER@@; $YeniDuser = @@YENIDUSER@@; $YeniBozuk = @@YENIBOZUK@@
$AdresOkunmaz = @@ADRESOKUNMAZ@@
function _Oku { $j = Get-Content -LiteralPath $Durum -Raw | ConvertFrom-Json; foreach ($k in @($j)) { if ($k) { $k } } }  # PS 5.1 + 7
function _Yaz($t) { Set-Content -LiteralPath $Durum -Value (ConvertTo-Json -InputObject @($t) -Depth 5) -Encoding UTF8 }
function _Olay($m) { Add-Content -LiteralPath $Olay -Value $m -Encoding UTF8 }
function _Nesne($k) { [pscustomobject]@{ DisplayName = $k.n; Enabled = $k.en; Action = $k.act; Direction = $k.dir; Profile = $k.prof; Kimlik = $k.id } }
function Get-NetFirewallRule { [CmdletBinding()] param($DisplayName)
    foreach ($k in @(_Oku)) { if ($k.n -eq $DisplayName) { _Nesne $k } } }
function Get-NetFirewallAddressFilter { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject)
    process { if ($AdresOkunmaz) { return }; $k = @(_Oku) | Where-Object { $_.id -eq $InputObject.Kimlik }; [pscustomobject]@{ RemoteAddress = @($k.ra) } } }
function Get-NetFirewallPortFilter { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject)
    process { $k = @(_Oku) | Where-Object { $_.id -eq $InputObject.Kimlik }; [pscustomobject]@{ Protocol = $k.p; LocalPort = $k.port } } }
function Set-NetFirewallRule { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject, $RemoteAddress)
    process { _Olay ("SET " + $InputObject.DisplayName + " " + $RemoteAddress)
        $t = @(_Oku); foreach ($k in $t) { if ($k.id -eq $InputObject.Kimlik) { $k.ra = @($RemoteAddress) } }; _Yaz $t } }
function Remove-NetFirewallRule { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject, $DisplayName)
    process { if ($SilDuser) { throw 'Erişim reddedildi' }
        $ad = if ($InputObject) { $InputObject.DisplayName } else { $DisplayName }; _Olay ("REMOVE " + $ad)
        _Yaz @(@(_Oku) | Where-Object { if ($InputObject) { $_.id -ne $InputObject.Kimlik } else { $_.n -ne $DisplayName } }) } }
function New-NetFirewallRule { [CmdletBinding()] param($DisplayName, $Direction, $Protocol, $LocalPort, $RemoteAddress, $Action, $Profile)
    if ($YeniDuser) { throw 'RPC server unavailable' }
    _Olay ("NEW " + (@($DisplayName, $Direction, $Protocol, $LocalPort, $RemoteAddress, $Action, $Profile) -join '|'))
    $t = @(_Oku); $t += [pscustomobject]@{ id = "yeni" + $t.Count; n = $DisplayName; ra = @($RemoteAddress); p = "$Protocol"; port = "$LocalPort"
        en = $(if ($YeniBozuk) { 'False' } else { 'True' }); act = "$Action"; dir = "$Direction"; prof = "$Profile" }; _Yaz $t }
function Write-Status($m, $c = 'White') { _Olay ("LOG " + $m) }
foreach ($g in @@GOLGELER@@) {
    if ((Get-Command $g -ErrorAction SilentlyContinue).CommandType -ne 'Function') { _Olay "GOLGE-YOK $g"; exit 99 }
}
$ErrorActionPreference = 'Stop'   # betiğin kendi tercihi (install_mosquitto_service.ps1 başı)
@@KOD@@
"""

# Doğru kuralın New-NetFirewallRule argümanları (ad|yön|protokol|port|uzak adres|eylem|profil) — D3.32 sınıfı bu betikte de pinli.
YENI_DOGRU = f"NEW {AD}|Inbound|TCP|1883|{HOTSPOT}|Allow|Any"


def surucu_kos(tmp_path: Path, kod: str, kurallar: list[dict], **bayrak) -> tuple[list[str], list[dict]]:
    """`kod`u gölgeli sürücüde koştur → (olay satırları, son kural tablosu). Sonda da kullanır (HEAD bloğu)."""
    durum, olay = tmp_path / "durum.json", tmp_path / "olay.txt"
    durum.write_text(json.dumps([dict(k, id=f"k{i}") for i, k in enumerate(kurallar)]), encoding="utf-8")
    olay.write_text("", encoding="utf-8")
    govde = _SURUCU.replace("@@DURUM@@", _ps_lit(durum)).replace("@@OLAY@@", _ps_lit(olay))
    for ad in ("SILDUSER", "YENIDUSER", "YENIBOZUK", "ADRESOKUNMAZ"):
        govde = govde.replace(f"@@{ad}@@", "$true" if bayrak.get(ad.lower()) else "$false")
    govde = govde.replace("@@GOLGELER@@", ", ".join(_ps_lit(g) for g in GOLGELER)).replace("@@KOD@@", kod)
    r = _pwsh_file(tmp_path, "d5g2.ps1", govde)
    satir = [s for s in olay.read_text(encoding="utf-8-sig").splitlines() if s.strip()]
    assert r.returncode == 0, (
        f"sürücü düştü (rc={r.returncode}; 99 = gölge kanıtlanamadı):\n{satir}\n{r.stdout}\n{r.stderr}"
    )
    son = json.loads(durum.read_text(encoding="utf-8-sig") or "[]")
    return satir, ([son] if isinstance(son, dict) else son)


def betik_fonksiyonu(tmp_path: Path, ad: str, betik: Path = BETIK) -> str:
    """Fonksiyon metnini PowerShell'in KENDİ parser'ıyla (FunctionDefinitionAst.Extent.Text) çek — regex değil."""
    cikti = tmp_path / f"{ad}.txt"
    govde = f"""
$t = $null; $h = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile({_ps_lit(betik)}, [ref]$t, [ref]$h)
if ($h.Count) {{ Write-Output ("PARSE-ERROR: " + (($h | ForEach-Object {{ $_.Message }}) -join ' | ')); exit 3 }}
$f = $ast.Find({{ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq {_ps_lit(ad)} }}, $true)
if (-not $f) {{ Write-Output "NOT-FOUND"; exit 4 }}
[System.IO.File]::WriteAllText({_ps_lit(cikti)}, $f.Extent.Text, [System.Text.UTF8Encoding]::new($false))
Write-Output "OK"
"""
    r = _pwsh_file(tmp_path, f"cek_{ad}.ps1", govde)
    assert r.returncode == 0 and "OK" in r.stdout, (
        f"{betik.name} içinde '{ad}' fonksiyonu parser ile bulunamadı (rc={r.returncode}):\n{r.stdout}\n{r.stderr}"
    )
    return cikti.read_text(encoding="utf-8")


def _kos(tmp_path, kurallar: list[dict], *, esp: bool = False, **bayrak) -> tuple[str, list[str], list[dict]]:
    kod = betik_fonksiyonu(tmp_path, FONK) + (
        f"\n$r = {FONK} -EspEtkin {'$true' if esp else '$false'}\n_Olay (\"SONUC \" + $r + \" \" + $r.GetType().Name)\n"
    )
    satir, son = surucu_kos(tmp_path, kod, kurallar, **bayrak)
    sonuc = [s for s in satir if s.startswith("SONUC ")]
    assert sonuc and sonuc[-1].endswith(" Boolean"), f"fonksiyon [bool] döndürmedi:\n{satir}"
    return sonuc[-1].split()[1], satir, son


def _icerik(k: dict) -> tuple:
    ra = k["ra"] if isinstance(k["ra"], list) else [k["ra"]]
    return (k["n"], tuple(ra), k["p"], str(k["port"]), k["en"], k["act"], k["dir"], k["prof"])


def _degisiklik(satir: list[str]) -> list[str]:
    return [s for s in satir if s.startswith(("SET ", "REMOVE ", "NEW "))]


def _uyari(satir: list[str]) -> list[str]:
    return [s for s in satir if s.startswith("LOG UYARI")]


BOZUK = {
    "devre_disi": {"en": "False"},
    "engelle": {"act": "Block"},
    "giden": {"dir": "Outbound"},
    "udp": {"p": "UDP"},
    "baska_port": {"port": "1884"},
    "dar_profil": {"prof": "Private"},
}


@pytest.mark.parametrize("bozukluk", list(BOZUK))
def test_KRITIK_ESP_kapali_ayni_adli_ICERIGI_UYMAYAN_kural_silinir_DOGRUSU_kurulur(tmp_path, bozukluk):
    sonuc, satir, son = _kos(tmp_path, [dict(DOGRU, **BOZUK[bozukluk])])
    assert [_icerik(k) for k in son] == [_icerik(DOGRU)], (
        f"aynı adlı ama içeriği uymayan ({bozukluk}) kural yerinde kaldı — yalnız ADA bakılıyor; ESP bobinleri 1883'e ulaşamaz:\n"
        f"{son}\n{satir}"
    )
    assert f"REMOVE {AD}" in satir and YENI_DOGRU in satir, (
        f"uymayan kural silinip yerine DOĞRU (TCP 1883 <- {HOTSPOT}, Inbound Allow Any) kural kurulmadı:\n{satir}"
    )
    assert sonuc == "True" and not _uyari(satir), f"doğrusu kuruldu ama sonuç {sonuc} / uyarı var:\n{satir}"


def test_KRITIK_ESP_kapali_GENIS_uzak_adres_hotspota_DARALTILIR(tmp_path):
    """P0-3: eski (06-27 öncesi) `-RemoteAddress Any` kuralı anonim broker'ı klinik LAN'ına açar — adla "var" sayılmaz."""
    sonuc, satir, son = _kos(tmp_path, [dict(DOGRU, ra=["Any"])])
    assert [_icerik(k) for k in son] == [_icerik(DOGRU)], (
        f"geniş (Any) kural daraltılmadı — 1883 klinik LAN'ına açık:\n{son}\n{satir}"
    )
    assert f"SET {AD} {HOTSPOT}" in satir and not [s for s in satir if s.startswith("NEW ")], satir
    assert sonuc == "True", satir


def test_KRITIK_uzak_adres_OKUNAMAZSA_degistirilmez_FALSE_ve_UYARI(tmp_path):
    """D3.42 ile aynı: bilinmeyen kurala yazılmaz — ama 'doğrulandı' da denmez."""
    sonuc, satir, son = _kos(tmp_path, [DOGRU], adresokunmaz=True)
    assert not _degisiklik(satir) and [_icerik(k) for k in son] == [_icerik(DOGRU)], (
        f"uzak adresi OKUNAMAYAN kurala yazıldı (D3.42: bilinmeyen kurala yazılmaz):\n{satir}"
    )
    assert sonuc == "False" and [s for s in _uyari(satir) if "OKUNAMADI" in s], (
        f"okunamayan adres doğrulandı sayıldı:\n{satir}"
    )


@pytest.mark.parametrize("bozukluk", ["devre_disi", "dar_profil"])
def test_KRITIK_ESP_ETKIN_icerigi_uymayan_kurala_DOKUNULMAZ_FALSE_ve_eylemli_UYARI(tmp_path, bozukluk):
    kural = dict(DOGRU, **BOZUK[bozukluk])
    sonuc, satir, son = _kos(tmp_path, [kural], esp=True)
    assert not _degisiklik(satir), f"ESP ETKİN iken kural değişti (Y3):\n{satir}"
    assert [_icerik(k) for k in son] == [_icerik(kural)]
    assert sonuc == "False", f"içeriği uymayan kural 'doğrulandı' (True) sayıldı:\n{satir}"
    uyari = [s for s in _uyari(satir) if AD in s and "ESP ETKİN" in s]
    assert uyari and "Remove-NetFirewallRule" in uyari[0] and "New-NetFirewallRule" in uyari[0], (
        f"ESP ETKİN uyarısı eylem söylemiyor:\n{satir}"
    )


def test_KRITIK_ESP_ETKIN_GENIS_kural_DARALTILMAZ_ve_UYARIR(tmp_path):
    """Y3: hotspot dışındaki ESP'nin (bobin 8) STOP yolu kesilmesin — daraltma yok, eylemli uyarı var (D3.42 ile aynı)."""
    kural = dict(DOGRU, ra=["Any"])
    sonuc, satir, son = _kos(tmp_path, [kural], esp=True)
    assert not _degisiklik(satir) and [_icerik(k) for k in son] == [_icerik(kural)], (
        f"ESP ETKİN iken daraltıldı:\n{satir}"
    )
    assert [s for s in _uyari(satir) if "GENİŞ" in s and "Set-NetFirewallRule" in s], (
        f"geniş kural uyarısı yok:\n{satir}"
    )


def test_KRITIK_uymayan_kural_SILINEMEZSE_FALSE_ve_eylemli_UYARI(tmp_path):
    kural = dict(DOGRU, en="False")
    sonuc, satir, son = _kos(tmp_path, [kural], silduser=True)
    assert sonuc == "False", f"uymayan kural silinemedi ama sonuç True:\n{satir}"
    assert [_icerik(k) for k in son] == [_icerik(kural)] and not [s for s in satir if s.startswith("NEW ")], satir
    assert [s for s in _uyari(satir) if "silinemedi" in s and "Remove-NetFirewallRule" in s], satir


def test_KRITIK_uymayan_silindi_ama_YENISI_kurulamadi_FALSE_ve_YOK_uyarisi(tmp_path):
    sonuc, satir, son = _kos(tmp_path, [dict(DOGRU, act="Block")], yeniduser=True)
    assert not [k for k in son if k["n"] == AD], f"aparat: yeni kural kurulamadığı hâlde tabloda kural var:\n{son}"
    assert sonuc == "False", f"kural silindi, yenisi kurulamadı (kural YOK) ama sonuç {sonuc}:\n{satir}"
    assert [s for s in _uyari(satir) if "kuralı YOK" in s and "New-NetFirewallRule" in s], satir


def test_KRITIK_SON_DOGRULAMA_adla_degil_ICERIKLE_kurulan_kural_uymuyorsa_FALSE(tmp_path):
    """Cmdlet 'başarılı' ama ortaya çıkan kural devre dışı (ör. ilke) → son sorgu adla değil içerikle: False + UYARI."""
    sonuc, satir, _son = _kos(tmp_path, [], yenibozuk=True)
    assert YENI_DOGRU in satir, f"kural DAR / doğru argümanlarla kurulmadı (beklenen {YENI_DOGRU!r}):\n{satir}"
    assert sonuc == "False", f"kurulan kural devre dışı ama son doğrulama yalnız ADA baktı (True):\n{satir}"
    assert [s for s in _uyari(satir) if AD in s], satir


def test_KARSIT_uyan_kural_VARKEN_dokunulmaz_uyari_yok(tmp_path):
    sonuc, satir, son = _kos(tmp_path, [DOGRU])
    assert not _degisiklik(satir) and not _uyari(satir), satir
    assert [_icerik(k) for k in son] == [_icerik(DOGRU)] and sonuc == "True"


def test_KARSIT_uyan_ve_uymayan_IKIZ_yalniz_uymayan_silinir_CIFT_kural_kurulmaz(tmp_path):
    sonuc, satir, son = _kos(tmp_path, [DOGRU, dict(DOGRU, en="False")])
    assert [_icerik(k) for k in son] == [_icerik(DOGRU)], (
        f"ikizden yanlış olan kaldı ya da çift kural kuruldu:\n{son}\n{satir}"
    )
    assert not [s for s in satir if s.startswith("NEW ")] and sonuc == "True", satir


def test_KARSIT_kural_yoksa_DOGRU_icerikle_ve_DAR_argumanlarla_kurulur(tmp_path):
    sonuc, satir, son = _kos(tmp_path, [])
    assert YENI_DOGRU in satir, f"kural hotspot alt ağına DAR / TCP 1883 Inbound Allow Any kurulmadı:\n{satir}"
    assert [_icerik(k) for k in son] == [_icerik(DOGRU)] and sonuc == "True" and not _uyari(satir), satir


# ── ESP kipi: backend'in anlamı ("1" = açık, varsayılan KAPALI) — setup_services.ps1 ile EŞLİK ölçülür ──
_ESP_MATRISI = [
    # (profil PEMF_ESP_ENABLED | None, makine değeri | None, beklenen)
    (None, None, False),
    (None, "", False),
    (None, "0", False),
    (None, "1", True),
    (None, " 1 ", True),
    (None, "true", False),
    (None, "01", False),
    ("0", "1", False),
    ("1", None, True),
]


def _ps_deger(v) -> str:
    return "$null" if v is None else _ps_lit(v)


def test_KRITIK_ESP_kipi_backend_anlaminda_ve_setup_services_ile_ESLIK(tmp_path):
    kendi = betik_fonksiyonu(tmp_path, "Test-PemfEspEtkin")
    kurulum = _extract_function(tmp_path, "Test-PemfEspEtkin").replace(
        "Test-PemfEspEtkin", "Test-PemfEspEtkin_SetupServices", 1
    )
    satirlar = []
    for i, (profil, makine, _b) in enumerate(_ESP_MATRISI):
        p = "$null" if profil is None else f"@{{ PEMF_ESP_ENABLED = {_ps_lit(profil)} }}"
        satirlar.append(
            f'Write-Output ("{i} " + (Test-PemfEspEtkin {p} {_ps_deger(makine)}) + " " + '
            f"(Test-PemfEspEtkin_SetupServices {p} {_ps_deger(makine)}))"
        )
    r = _pwsh_file(tmp_path, "esp.ps1", "\n".join([kendi, kurulum, *satirlar]) + "\n")
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    sonuc = {int(s.split()[0]): s.split()[1:] for s in r.stdout.splitlines() if s.strip()}
    for i, (profil, makine, beklenen) in enumerate(_ESP_MATRISI):
        assert sonuc.get(i, [None])[0] == str(beklenen), (
            f"ESP kipi (profil={profil!r}, makine={makine!r}) {sonuc.get(i)} — beklenen {beklenen} (backend: yalnız '1' açık)"
        )
        assert sonuc[i][0] == sonuc[i][1], (
            f"setup_services.ps1 ile ESP kipi AYRIŞTI (profil={profil!r}, makine={makine!r}): {sonuc[i]}"
        )


# ── Betik bağlantısı (AST): eski ad-araması geri gelemez, çağrı ESP kipini makine ortamından alır, sonuç özete girer ──
_AST = r"""
using namespace System.Management.Automation.Language
$t = $null; $h = $null
$ast = [Parser]::ParseFile(@@BETIK@@, [ref]$t, [ref]$h)
function _FonkIci($n) { $p = $n.Parent; while ($p) { if ($p -is [FunctionDefinitionAst]) { return $true }; $p = $p.Parent }; $false }
function _TryIci($n) { $p = $n.Parent; while ($p) { if ($p -is [TryStatementAst]) { return $true }; $p = $p.Parent }; $false }
$komut = @($ast.FindAll({ param($n) $n -is [CommandAst] }, $true))
$fw = @($komut | Where-Object { "$($_.GetCommandName())" -like '*-NetFirewall*' })
$cagri = @($komut | Where-Object { $_.GetCommandName() -eq @@FONK@@ -and -not (_FonkIci $_) })
$esp = ''; $hedef = ''; $sonraKullanim = $false
if ($cagri.Count -eq 1) {
    $c = $cagri[0]
    for ($i = 0; $i -lt $c.CommandElements.Count; $i++) {
        $e = $c.CommandElements[$i]
        if ($e -is [CommandParameterAst] -and $e.ParameterName -eq 'EspEtkin') {
            $esp = if ($e.Argument) { $e.Argument.Extent.Text } elseif ($i + 1 -lt $c.CommandElements.Count) { $c.CommandElements[$i + 1].Extent.Text } else { '' }
        }
    }
    $p = $c.Parent; while ($p -and -not ($p -is [AssignmentStatementAst])) { $p = $p.Parent }
    if ($p) {
        $hedef = $p.Left.VariablePath.UserPath
        $sonraKullanim = [bool]@($ast.FindAll({ param($n) $n -is [IfStatementAst] -and -not (_FonkIci $n) -and $n.Extent.StartOffset -gt $c.Extent.EndOffset }, $true) |
            Where-Object { $_.Clauses | Where-Object { $_.Item1.FindAll({ param($v) $v -is [VariableExpressionAst] -and $v.VariablePath.UserPath -eq $hedef }, $true) } }).Count
    }
}
[pscustomobject]@{
    hata = @($h | ForEach-Object { $_.Message })
    fonk_disi_fw = @($fw | Where-Object { -not (_FonkIci $_) } | ForEach-Object { $_.Extent.Text })
    new_kosulsuz = @($fw | Where-Object { $_.GetCommandName() -eq 'New-NetFirewallRule' -and -not ((_TryIci $_) -and $_.Extent.Text -match '-ErrorAction\s+Stop') } | ForEach-Object { $_.Extent.Text })
    cagri = $cagri.Count; esp = $esp; hedef = $hedef; sonra_kullanim = $sonraKullanim
} | ConvertTo-Json -Depth 4 -Compress
"""


def test_KRITIK_betik_FW_adimi_icerik_fonksiyonuna_BAGLI_ve_ozete_girer(tmp_path):
    govde = _AST.replace("@@BETIK@@", _ps_lit(BETIK)).replace("@@FONK@@", _ps_lit(FONK))
    r = _pwsh_file(tmp_path, "ast.ps1", govde)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    a = json.loads(r.stdout.strip().splitlines()[-1])
    assert not a["hata"], f"betik ayrıştırılamadı: {a['hata']}"
    assert not a["fonk_disi_fw"], (
        f"fonksiyon DIŞINDA NetFirewall çağrısı var — adla arayan eski adım geri mi geldi? {a['fonk_disi_fw']}"
    )
    assert not a["new_kosulsuz"], f"New-NetFirewallRule try dışında / -ErrorAction Stop'suz: {a['new_kosulsuz']}"
    assert a["cagri"] == 1, (
        f"{FONK} betikte {a['cagri']} kez çağrılıyor (1 beklenir) — güvenlik duvarı adımı bağlı değil"
    )
    esp = a["esp"]
    assert "Test-PemfEspEtkin" in esp and "'PEMF_ESP_ENABLED'" in esp and "'Machine'" in esp, (
        f"-EspEtkin backend'in ESP kipinden (makine ortamı PEMF_ESP_ENABLED) gelmiyor: {esp!r}"
    )
    assert a["hedef"] and a["sonra_kullanim"], (
        f"FW sonucu (${a['hedef'] or '?'}) sonraki bir koşulda kullanılmıyor — kurulum özeti doğrulanamayan kuralı söylemez"
    )
