# Author: mertaygn, cglrgrkn
"""D3.42 (B-9.22) — `setup_services.ps1` mevcut 'PEMF Mosquitto MQTT' kuralını ADIYLA değil İÇERİĞİYLE (uzak adres) doğrular; install_mosquitto.ps1'in
RFC1918 'Mosquitto MQTT' kuralını ve native 'mosquitto' servisini tanır.

ÖLÇÜLEN (HEAD): aynı adlı ESKİ kural `-RemoteAddress Any` iken fonksiyon `True` döner, hiçbir düzeltme çağrısı yapmaz (1883 her kaynağa açık,
"doğrulandı"); 'Mosquitto MQTT' (1883 ← LocalSubnet + RFC1918) kuralı ve native servis hiç sorgulanmaz.
SÖZLEŞME — ESP KAPALI (HEAD varsayılanı): geniş kural 192.168.137.0/24'e daraltılır, RFC1918 kuralı kaldırılır. ESP ETKİN: DOKUNULMAZ + uyarı (Y3 —
"1883'ü LAN'a kapatmak bobin 8'in STOP yolunu keser"; A-04 ESP dönüşüyle). Uzak adres okunamazsa / düzeltme düşerse değiştirilmez, `False` + uyarı.
⛔ Gerçek güvenlik duvarı YOK: fonksiyon PowerShell parser'ıyla çekilir; NetSecurity cmdlet'leri durum tutan sahtelerle gölgelenir ve modül
OTOMATİK YÜKLEME KAPALI — gölgelenmemiş bir NetSecurity çağrısı gerçek cmdlet'e ulaşamaz, "komut yok" ile düşer.
"""

from __future__ import annotations

import json

import capraz
import pytest
from test_setup_services_firewall_kaniti import PS1, PWSH, _extract_function, _ps_lit, _pwsh_file  # noqa: F401 — aparat

pytestmark = pytest.mark.skipif(
    (PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) yok — PS fonksiyonu koşturulamaz"
)

HOTSPOT = "192.168.137.0/24"


def _kos(
    tmp_path, kurallar: dict, *, esp: bool, servis: bool = False, adres_okunmaz: bool = False, set_duser: bool = False
):
    func = _extract_function(tmp_path, "Ensure-PemfMosquittoFirewallRule")
    durum = tmp_path / "durum.json"
    durum.write_text(json.dumps(kurallar), encoding="utf-8")
    olay = tmp_path / "olay.txt"
    olay.write_text("", encoding="utf-8")
    body = f"""
Import-Module Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility
$PSModuleAutoLoadingPreference = 'None'
$ErrorActionPreference = 'Continue'
$Durum = {_ps_lit(durum)}; $Olay = {_ps_lit(olay)}
function _Oku {{ Get-Content -LiteralPath $Durum -Raw | ConvertFrom-Json -AsHashtable }}
function _Yaz($d) {{ Set-Content -LiteralPath $Durum -Value ($d | ConvertTo-Json -Depth 5) -Encoding UTF8 }}
function _Olay($m) {{ Add-Content -LiteralPath $Olay -Value $m -Encoding UTF8 }}
function Get-NetFirewallRule {{ [CmdletBinding()] param($DisplayName)
    $d = _Oku; if ($d.ContainsKey($DisplayName)) {{ [pscustomobject]@{{ DisplayName = $DisplayName; Enabled = 'True'; Action = 'Allow'; Direction = 'Inbound'; Profile = 'Any' }} }} }}
# DEV-C4: fonksiyon kuralın port / protokol / durum içeriğini de okur → gerçek kural nesnesi gibi TAM içerik + port süzgeci gölgesi.
function Get-NetFirewallPortFilter {{ [CmdletBinding()] param([Parameter(ValueFromPipeline=$true)]$InputObject) process {{ [pscustomobject]@{{ Protocol = 'TCP'; LocalPort = '1883' }} }} }}
function Get-NetFirewallAddressFilter {{ [CmdletBinding()] param([Parameter(ValueFromPipeline=$true)]$InputObject)
    process {{ if ({'$true' if adres_okunmaz else '$false'}) {{ return }}; $d = _Oku; [pscustomobject]@{{ RemoteAddress = @($d[$InputObject.DisplayName]) }} }} }}
function Set-NetFirewallRule {{ [CmdletBinding()] param([Parameter(ValueFromPipeline=$true)]$InputObject, $RemoteAddress)
    process {{ if ({'$true' if set_duser else '$false'}) {{ throw 'Erişim reddedildi' }}
        _Olay ("SET " + $InputObject.DisplayName + " " + $RemoteAddress); $d = _Oku; $d[$InputObject.DisplayName] = @($RemoteAddress); _Yaz $d }} }}
function Remove-NetFirewallRule {{ [CmdletBinding()] param([Parameter(ValueFromPipeline=$true)]$InputObject)
    process {{ _Olay ("REMOVE " + $InputObject.DisplayName); $d = _Oku; $d.Remove($InputObject.DisplayName); _Yaz $d }} }}
function New-NetFirewallRule {{ [CmdletBinding()] param($DisplayName, $Direction, $Protocol, $LocalPort, $RemoteAddress, $Action, $Profile)
    _Olay ("NEW " + $DisplayName + " " + $RemoteAddress); $d = _Oku; $d[$DisplayName] = @($RemoteAddress); _Yaz $d }}
function Get-Service {{ [CmdletBinding()] param($Name)
    if ({'$true' if servis else '$false'} -and $Name -eq 'mosquitto') {{ [pscustomobject]@{{ Name = 'mosquitto'; Status = 'Running' }} }} }}
function Log($m, $c = 'White') {{ _Olay ("LOG " + $m) }}
$ServiceMosq = 'PemfMosquitto'
{func}
$r = Ensure-PemfMosquittoFirewallRule -EspEtkin ${'true' if esp else 'false'}
_Olay ("SONUC " + $r + " " + $r.GetType().Name)
"""
    r = _pwsh_file(tmp_path, "d342.ps1", body)
    assert r.returncode == 0, r.stdout + r.stderr
    satir = [s for s in olay.read_text(encoding="utf-8-sig").splitlines() if s.strip()]
    return satir, json.loads(durum.read_text(encoding="utf-8-sig"))


def _sonuc(satir):
    s = [x for x in satir if x.startswith("SONUC ")]
    assert s and s[-1].endswith("Boolean"), satir
    return s[-1].split()[1]


def test_KRITIK_D3_42_ESP_kapali_GENIS_kural_hotspota_DARALTILIR(tmp_path):
    satir, son = _kos(tmp_path, {"PEMF Mosquitto MQTT": ["Any"]}, esp=False)
    assert f"SET PEMF Mosquitto MQTT {HOTSPOT}" in satir, f"geniş kural düzeltilmedi (yalnız ada bakılıyor):\n{satir}"
    assert son["PEMF Mosquitto MQTT"] == [HOTSPOT]
    assert _sonuc(satir) == "True"


def test_KRITIK_D3_42_ESP_kapali_RFC1918_Mosquitto_MQTT_kurali_KALDIRILIR(tmp_path):
    satir, son = _kos(
        tmp_path,
        {
            "PEMF Mosquitto MQTT": [HOTSPOT],
            "Mosquitto MQTT": ["LocalSubnet", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
        },
        esp=False,
    )
    assert "REMOVE Mosquitto MQTT" in satir, f"install_mosquitto'nun RFC1918 kuralı görülmedi:\n{satir}"
    assert "Mosquitto MQTT" not in son
    assert _sonuc(satir) == "True"


def test_KRITIK_D3_42_ESP_ETKIN_kurallara_DOKUNULMAZ_ve_UYARILIR_Y3(tmp_path):
    satir, son = _kos(tmp_path, {"PEMF Mosquitto MQTT": ["Any"], "Mosquitto MQTT": ["192.168.0.0/16"]}, esp=True)
    assert not [x for x in satir if x.startswith(("SET ", "REMOVE "))], (
        f"ESP ETKİN iken kural değişti (bobin 8 STOP yolu):\n{satir}"
    )
    assert son == {"PEMF Mosquitto MQTT": ["Any"], "Mosquitto MQTT": ["192.168.0.0/16"]}
    uyari = [x for x in satir if x.startswith("LOG UYARI") and "ESP ETKİN" in x]
    assert len(uyari) == 2, f"ESP ETKİN kolu iki kuralı da uyarmalı:\n{satir}"


@pytest.mark.parametrize("kip", ["adres_okunmaz", "set_duser"])
def test_KRITIK_D3_42_dogrulanamayan_kural_FALSE_ve_uyari(tmp_path, kip):
    satir, son = _kos(tmp_path, {"PEMF Mosquitto MQTT": ["Any"]}, esp=False, **{kip: True})
    assert _sonuc(satir) == "False", f"kural doğrulanamadı/daraltılamadı ama 'doğrulandı' (True):\n{satir}"
    assert [x for x in satir if x.startswith("LOG UYARI") and "PEMF Mosquitto MQTT" in x], satir
    assert son == {"PEMF Mosquitto MQTT": ["Any"]}


def test_KRITIK_D3_42_native_mosquitto_servisi_UYARILIR(tmp_path):
    satir, _ = _kos(tmp_path, {"PEMF Mosquitto MQTT": [HOTSPOT]}, esp=False, servis=True)
    assert [x for x in satir if x.startswith("LOG UYARI") and "native 'mosquitto'" in x], satir


def test_KARSIT_D3_42_dar_kural_tek_basina_DOKUNULMAZ_uyari_yok(tmp_path):
    satir, son = _kos(tmp_path, {"PEMF Mosquitto MQTT": [HOTSPOT]}, esp=False)
    assert not [x for x in satir if x.startswith(("SET ", "REMOVE ", "NEW ", "LOG UYARI"))], satir
    assert son == {"PEMF Mosquitto MQTT": [HOTSPOT]} and _sonuc(satir) == "True"


def test_KARSIT_D3_42_kural_yoksa_DAR_kural_kurulur(tmp_path):
    satir, son = _kos(tmp_path, {}, esp=False)
    assert f"NEW PEMF Mosquitto MQTT {HOTSPOT}" in satir and son == {"PEMF Mosquitto MQTT": [HOTSPOT]}


@pytest.mark.parametrize(
    ("profil", "makine", "beklenen"),
    [
        ({"PEMF_ESP_ENABLED": "1"}, "", "True"),
        ({"PEMF_ESP_ENABLED": "0"}, "1", "False"),
        ({}, "1", "True"),
        ({}, "", "False"),
        (None, None, "False"),
    ],
)
def test_D3_42_ESP_ETKIN_karari_profil_ONCE_makine_sonra(tmp_path, profil, makine, beklenen):
    func = _extract_function(tmp_path, "Test-PemfEspEtkin")
    p = (
        "$null"
        if profil is None
        else "[ordered]@{" + "; ".join(f"{_ps_lit(k)} = {_ps_lit(v)}" for k, v in profil.items()) + "}"
    )
    m = "$null" if makine is None else _ps_lit(makine)
    r = _pwsh_file(tmp_path, "esp.ps1", f"{func}\nWrite-Output (Test-PemfEspEtkin ({p}) ({m}))")
    assert r.returncode == 0 and r.stdout.strip().splitlines()[-1] == beklenen, r.stdout + r.stderr


def test_D3_42_cagri_yeri_ESP_kararini_GECIRIR():
    src = PS1.read_text(encoding="utf-8")
    assert "Ensure-PemfMosquittoFirewallRule -EspEtkin $EspEtkin" in src
    assert "$EspEtkin = Test-PemfEspEtkin $OnProfil" in src
