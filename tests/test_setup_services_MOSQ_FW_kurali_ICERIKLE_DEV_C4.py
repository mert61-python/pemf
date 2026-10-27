# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DEV-C4 (D4B §8 #2) — `Ensure-PemfMosquittoFirewallRule` aynı adlı 'PEMF Mosquitto MQTT' kuralını yalnız UZAK ADRESİYLE değil TÜM İÇERİĞİYLE
(TCP · 1883 · Inbound · Allow · etkin · tüm profiller) doğrular — İG-9.5 / 4B-3.5'in API kuralına getirdiği sınıfın 1883 karşılığı.

ÖLÇÜLEN (HEAD 5bc99be1): fonksiyon kuralı ADIYLA bulur, içerikten yalnız `RemoteAddress`e bakar (D3.42). Aynı adlı kural devre dışı, Block, giden,
UDP, başka port ya da dar profilli olsa da `True` döner, hiçbir düzeltme / uyarı yapmaz → kurulum özeti ve `.install_verified` `mosqFirewall=True`
yazar; ESP bobinleri (6-8) broker'a ULAŞAMAZ (ESP etkin kurulumda) ama gösterge YEŞİL.
SÖZLEŞME — ESP KAPALI (varsayılan): içeriği uymayan aynı adlı kural silinir, doğrusu (TCP 1883 ← 192.168.137.0/24) kurulur; uyan kural varsa
yenisi kurulmaz (çift kural yok). Silinemezse değiştirilmez, `False` + eylemli UYARI. ESP ETKİN: D3.42 / Y3 gibi DOKUNULMAZ, eylemli UYARI,
`False` (kural uymuyor → doğrulanamadı). Son doğrulama da adla değil içerikle yapılır.
⛔ Gerçek güvenlik duvarı YOK: fonksiyon PowerShell parser'ıyla çekilir; NetSecurity cmdlet'leri durum tutan sahtelerle gölgelenir, gölgelerin
İŞLEV olduğu Get-Command ile KANITLANIR (değilse çıkış 99) ve modül OTOMATİK YÜKLEME KAPALI.
"""

from __future__ import annotations

import json

import capraz
import pytest
from test_setup_services_firewall_kaniti import PWSH, _extract_function, _ps_lit, _pwsh_file  # noqa: F401 — aparat

pytestmark = pytest.mark.skipif(
    (PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) yok — PS fonksiyonu koşturulamaz"
)

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

_SURUCU = r"""
Import-Module Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility
$PSModuleAutoLoadingPreference = 'None'
$ErrorActionPreference = 'Continue'
$Durum = @@DURUM@@; $Olay = @@OLAY@@; $SilDuser = @@SILDUSER@@; $YeniDuser = @@YENIDUSER@@; $YeniBozuk = @@YENIBOZUK@@
function _Oku { @(Get-Content -LiteralPath $Durum -Raw | ConvertFrom-Json) | Where-Object { $_ } }
function _Yaz($t) { Set-Content -LiteralPath $Durum -Value (ConvertTo-Json -InputObject @($t) -Depth 5) -Encoding UTF8 }
function _Olay($m) { Add-Content -LiteralPath $Olay -Value $m -Encoding UTF8 }
function _Nesne($k, $i) { [pscustomobject]@{ DisplayName = $k.n; Enabled = $k.en; Action = $k.act; Direction = $k.dir; Profile = $k.prof; Kimlik = $i } }
function Get-NetFirewallRule { [CmdletBinding()] param($DisplayName)
    $t = @(_Oku); for ($i = 0; $i -lt $t.Count; $i++) { if ($t[$i].n -eq $DisplayName) { _Nesne $t[$i] $t[$i].id } } }
function Get-NetFirewallAddressFilter { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject)
    process { $k = @(_Oku) | Where-Object { $_.id -eq $InputObject.Kimlik }; [pscustomobject]@{ RemoteAddress = @($k.ra) } } }
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
    _Olay ("NEW " + $DisplayName + " " + $Protocol + " " + $LocalPort + " " + $RemoteAddress)
    $t = @(_Oku); $t += [pscustomobject]@{ id = "yeni" + $t.Count; n = $DisplayName; ra = @($RemoteAddress); p = $Protocol; port = "$LocalPort"
        en = $(if ($YeniBozuk) { 'False' } else { 'True' }); act = $Action; dir = $Direction; prof = $Profile }; _Yaz $t }
function Get-Service { [CmdletBinding()] param($Name) }
function Log($m, $c = 'White') { _Olay ("LOG " + $m) }
foreach ($g in 'Get-NetFirewallRule', 'Get-NetFirewallAddressFilter', 'Get-NetFirewallPortFilter', 'Set-NetFirewallRule', 'Remove-NetFirewallRule',
               'New-NetFirewallRule', 'Get-Service') {
    if ((Get-Command $g).CommandType -ne 'Function') { _Olay "GOLGE-YOK $g"; exit 99 }
}
$ServiceMosq = 'PemfMosquitto'
@@FUNC@@
$r = Ensure-PemfMosquittoFirewallRule -EspEtkin @@ESP@@
_Olay ("SONUC " + $r + " " + $r.GetType().Name)
"""


def _kos(
    tmp_path,
    kurallar: list[dict],
    *,
    esp: bool = False,
    sil_duser: bool = False,
    yeni_duser: bool = False,
    yeni_bozuk: bool = False,
):
    func = _extract_function(tmp_path, "Ensure-PemfMosquittoFirewallRule")
    durum, olay = tmp_path / "durum.json", tmp_path / "olay.txt"
    durum.write_text(json.dumps([dict(k, id=f"k{i}") for i, k in enumerate(kurallar)]), encoding="utf-8")
    olay.write_text("", encoding="utf-8")
    govde = (
        _SURUCU.replace("@@DURUM@@", _ps_lit(durum))
        .replace("@@OLAY@@", _ps_lit(olay))
        .replace("@@SILDUSER@@", "$true" if sil_duser else "$false")
        .replace("@@YENIDUSER@@", "$true" if yeni_duser else "$false")
        .replace("@@YENIBOZUK@@", "$true" if yeni_bozuk else "$false")
        .replace("@@ESP@@", "$true" if esp else "$false")
        .replace("@@FUNC@@", func)
    )
    r = _pwsh_file(tmp_path, "devc4.ps1", govde)
    satir = [s for s in olay.read_text(encoding="utf-8-sig").splitlines() if s.strip()]
    assert r.returncode == 0, (
        f"sürücü düştü (rc={r.returncode}; 99 = gölge kanıtlanamadı):\n{satir}\n{r.stdout}\n{r.stderr}"
    )
    son = json.loads(durum.read_text(encoding="utf-8-sig") or "[]")
    son = [son] if isinstance(son, dict) else son
    sonuc = [s for s in satir if s.startswith("SONUC ")]
    assert sonuc and sonuc[-1].endswith("Boolean"), satir
    return sonuc[-1].split()[1], satir, son


def _icerik(k: dict) -> tuple:
    ra = k["ra"] if isinstance(k["ra"], list) else [k["ra"]]
    return (k["n"], tuple(ra), k["p"], str(k["port"]), k["en"], k["act"], k["dir"], k["prof"])


_BOZUK = {
    "devre_disi": {"en": "False"},
    "engelle": {"act": "Block"},
    "giden": {"dir": "Outbound"},
    "udp": {"p": "UDP"},
    "baska_port": {"port": "1884"},
    "dar_profil": {"prof": "Private"},
}


@pytest.mark.parametrize("bozukluk", list(_BOZUK))
def test_KRITIK_ESP_kapali_ayni_adli_ICERIGI_UYMAYAN_kural_silinir_DOGRUSU_kurulur(tmp_path, bozukluk):
    sonuc, satir, son = _kos(tmp_path, [dict(DOGRU, **_BOZUK[bozukluk])])
    assert [_icerik(k) for k in son if k["n"] == AD] == [_icerik(DOGRU)], (
        f"aynı adlı ama içeriği uymayan ({bozukluk}) kural yerinde kaldı — yalnız ADA bakılıyor; ESP bobinleri 1883'e ulaşamaz:\n{son}\n{satir}"
    )
    assert f"REMOVE {AD}" in satir and f"NEW {AD} TCP 1883 {HOTSPOT}" in satir, satir
    assert sonuc == "True", f"doğrusu kuruldu ama sonuç {sonuc}:\n{satir}"


@pytest.mark.parametrize("bozukluk", ["devre_disi", "dar_profil"])
def test_KRITIK_ESP_ETKIN_icerigi_uymayan_kurala_DOKUNULMAZ_FALSE_ve_eylemli_UYARI(tmp_path, bozukluk):
    kural = dict(DOGRU, **_BOZUK[bozukluk])
    sonuc, satir, son = _kos(tmp_path, [kural], esp=True)
    assert not [s for s in satir if s.startswith(("SET ", "REMOVE ", "NEW "))], (
        f"ESP ETKİN iken kural değişti (Y3):\n{satir}"
    )
    assert [_icerik(k) for k in son] == [_icerik(kural)]
    assert sonuc == "False", f"içeriği uymayan kural 'doğrulandı' (True) sayıldı → mosqFirewall=True yalanı:\n{satir}"
    uyari = [s for s in satir if s.startswith("LOG UYARI") and AD in s and "ESP ETKİN" in s]
    assert uyari and "Remove-NetFirewallRule" in uyari[0] and "New-NetFirewallRule" in uyari[0], (
        f"ESP ETKİN uyarısı eylem söylemiyor:\n{satir}"
    )


def test_KRITIK_uymayan_kural_SILINEMEZSE_FALSE_ve_eylemli_UYARI(tmp_path):
    kural = dict(DOGRU, en="False")
    sonuc, satir, son = _kos(tmp_path, [kural], sil_duser=True)
    assert sonuc == "False", f"uymayan kural silinemedi ama sonuç True:\n{satir}"
    assert [_icerik(k) for k in son] == [_icerik(kural)] and not [s for s in satir if s.startswith("NEW ")], satir
    assert [s for s in satir if s.startswith("LOG UYARI") and "silinemedi" in s and "Remove-NetFirewallRule" in s], (
        satir
    )


def test_KRITIK_uymayan_silindi_ama_YENISI_kurulamadi_FALSE_ve_YOK_uyarisi(tmp_path):
    sonuc, satir, son = _kos(tmp_path, [dict(DOGRU, act="Block")], yeni_duser=True)
    assert sonuc == "False" and not [k for k in son if k["n"] == AD], satir
    assert [s for s in satir if s.startswith("LOG UYARI") and "kuralı YOK" in s], satir


def test_KRITIK_SON_DOGRULAMA_adla_degil_ICERIKLE_kurulan_kural_uymuyorsa_FALSE(tmp_path):
    """Cmdlet 'başarılı' ama ortaya çıkan kural devre dışı (ör. ilke) → son sorgu adla değil içerikle: False + UYARI."""
    sonuc, satir, son = _kos(tmp_path, [], yeni_bozuk=True)
    assert f"NEW {AD} TCP 1883 {HOTSPOT}" in satir, satir
    assert sonuc == "False", f"kurulan kural devre dışı ama son doğrulama yalnız ADA baktı (True):\n{satir}"
    assert [s for s in satir if s.startswith("LOG UYARI") and AD in s], satir


def test_KARSIT_uyan_kural_VARKEN_dokunulmaz_uyari_yok(tmp_path):
    sonuc, satir, son = _kos(tmp_path, [DOGRU])
    assert not [s for s in satir if s.startswith(("SET ", "REMOVE ", "NEW ", "LOG UYARI"))], satir
    assert [_icerik(k) for k in son] == [_icerik(DOGRU)] and sonuc == "True"


def test_KARSIT_uyan_ve_uymayan_IKIZ_yalniz_uymayan_silinir_CIFT_kural_kurulmaz(tmp_path):
    sonuc, satir, son = _kos(tmp_path, [DOGRU, dict(DOGRU, en="False")])
    assert [_icerik(k) for k in son] == [_icerik(DOGRU)], (
        f"ikizden yanlış olan kaldı ya da çift kural kuruldu:\n{son}\n{satir}"
    )
    assert not [s for s in satir if s.startswith("NEW ")] and sonuc == "True", satir


def test_KARSIT_kural_yoksa_DOGRU_icerikle_kurulur(tmp_path):
    sonuc, satir, son = _kos(tmp_path, [])
    assert [_icerik(k) for k in son] == [_icerik(DOGRU)] and sonuc == "True", satir
