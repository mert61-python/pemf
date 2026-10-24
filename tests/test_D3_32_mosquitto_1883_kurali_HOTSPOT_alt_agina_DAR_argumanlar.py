# Author: mertaygn, cglrgrkn
"""D3.32 (B-10.14) — `setup_services.ps1` 1883 güvenlik duvarı kuralı HOTSPOT alt ağına (192.168.137.0/24) DAR: ARGÜMANLARI kaydeden kapı.

ÖLÇÜLEN KÖR KAPI: `test_setup_services_firewall_kaniti` kuralın VAR olup olmadığını ve hata yolunu ölçüyor; sahte `New-NetFirewallRule`
argümanları YUTUYOR → `-RemoteAddress Any` mutantında 9 / 9 YEŞİL (plan). Anonim broker (A-04: ESP dönünce kimlikli olur) klinik LAN'ına
açılmamalı.
SÖZLEŞME (ESP KAPALI kurulum — HEAD varsayılanı `PEMF_ESP_ENABLED=0`): kural TCP 1883, Inbound, Allow, `-RemoteAddress 192.168.137.0/24`.
ESP ETKİN kolu (daraltma yalnız ESP'nin alt ağda olduğu kanıtlanınca; değilse uyarı + eski kural — orkestratör notu, Y3 "1883'ü LAN'a
kapatmak bobin 8'in STOP yolunu keser") A-04'e bağlı ve ESP dönüşüyle yapılır → TEZGÂH-2 / ESP dönüşü listesinde.
Gerçek NetSecurity cmdlet'i YOK: fonksiyon PowerShell parser'ıyla çekilir, cmdlet'ler sahte (argüman kaydı).
"""

from __future__ import annotations

import pytest
from test_setup_services_firewall_kaniti import PWSH, _extract_function, _ps_lit, _pwsh_file  # noqa: F401 — aparat

pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh (PowerShell 7) yok — PS fonksiyonu koşturulamaz")


def _kos(tmp_path, *, kural_var: bool):
    func = _extract_function(tmp_path, "Ensure-PemfMosquittoFirewallRule")
    kayit = tmp_path / "arg.txt"
    kayit.write_text("", encoding="utf-8")
    durum = tmp_path / "durum.txt"
    durum.write_text("var" if kural_var else "", encoding="utf-8")
    body = f"""
$ErrorActionPreference = 'Continue'
function Get-NetFirewallRule {{ [CmdletBinding()] param([Parameter(ValueFromRemainingArguments=$true)]$Rest)
    if ((Get-Content -LiteralPath {_ps_lit(durum)} -Raw) -match 'var') {{ [pscustomobject]@{{ DisplayName = 'PEMF Mosquitto MQTT' }} }} }}
function New-NetFirewallRule {{
    [CmdletBinding()] param($DisplayName, $Direction, $Protocol, $LocalPort, $RemoteAddress, $Action, $Profile, $Program)
    foreach ($k in 'DisplayName','Direction','Protocol','LocalPort','RemoteAddress','Action','Profile','Program') {{
        if ($PSBoundParameters.ContainsKey($k)) {{ Add-Content -LiteralPath {_ps_lit(kayit)} -Value ("$k=" + (Get-Variable $k -ValueOnly)) -Encoding UTF8 }}
    }}
    Set-Content -LiteralPath {_ps_lit(durum)} -Value 'var' -Encoding UTF8
}}
function Log($m, $c = 'White') {{ }}
{func}
$null = Ensure-PemfMosquittoFirewallRule
"""
    r = _pwsh_file(tmp_path, "d332.ps1", body)
    assert r.returncode == 0, r.stdout + r.stderr
    satirlar = [s.strip() for s in kayit.read_text(encoding="utf-8-sig").splitlines() if s.strip()]
    return dict(s.split("=", 1) for s in satirlar)


def test_KRITIK_D3_32_yeni_1883_kurali_YALNIZ_hotspot_alt_agindan(tmp_path):
    a = _kos(tmp_path, kural_var=False)
    assert a, "kural yokken New-NetFirewallRule çağrılmadı"
    assert a.get("RemoteAddress") == "192.168.137.0/24", (
        f"1883 hotspot alt ağına DAR değil (anonim broker LAN'a açılır): {a}"
    )
    assert a.get("LocalPort") == "1883" and a.get("Protocol") == "TCP", a
    assert a.get("Direction") == "Inbound" and a.get("Action") == "Allow", a
    assert "Program" not in a, "kural program kapsamlı — port kuralı olmalı"


def test_KARSIT_D3_32_kural_varken_yeniden_YARATILMAZ(tmp_path):
    assert _kos(tmp_path, kural_var=True) == {}
