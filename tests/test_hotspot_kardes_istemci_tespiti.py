# Author: mertaygn, cglrgrkn
"""start_hotspot.ps1 — "kardeş makinenin hotspot'una istemci" tespiti kapısı (saha 2026-09-08).

ARIZA: iki klinik makinesi aynı SSID'yi (PEMF-Gateway, sahip kararı) yayınlar. İkinci makine
Windows'un kayıtlı istemci profiliyle BİRİNCİNİN hotspot'una katılınca 192.168.137.106 gibi bir
adresi DHCP'den alıyordu; eski kontrol (`192.168.137.*` var mı) bunu kendi hotspot'u sanıp
"zaten aktif — atlandı" diyordu (hotspot.log 2026-09-08 13:22:58). Sonuç: o makinenin bobinleri
öteki makineye bağlanır, mDNS adı çakışır, kullanıcı "iki makinede aynı hesap → biri çevrimdışı"
diye görür.

Bu dosya `Test-PemfHotspotDurumu` fonksiyonunu PowerShell'in KENDİ parser'ıyla script'ten çekip
pwsh altında `Get-NetIPAddress` MOCK'uyla ÇALIŞTIRIR (metin aramaz). Mutasyonla KIRMIZI kanıtlandı:
sahip koşulu eski `-like '192.168.137.*'` mantığına döndürülünce istemci testi düşer.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PS1 = REPO / "scripts" / "start_hotspot.ps1"
PWSH = shutil.which("pwsh")
pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh (PowerShell 7) yok — PS fonksiyonu koşturulamaz")


def _pwsh_file(tmp_path: Path, name: str, body: str) -> subprocess.CompletedProcess:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8-sig", newline="\n")
    return subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(p)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def _ps_lit(s: str | Path) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _fonksiyon_metni(tmp_path: Path, ad: str) -> str:
    out = tmp_path / f"{ad}.txt"
    body = f"""
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile({_ps_lit(PS1)}, [ref]$tokens, [ref]$errors)
if ($errors.Count) {{ Write-Output ("PARSE-ERROR: " + (($errors | ForEach-Object {{ $_.Message }}) -join ' | ')); exit 3 }}
$f = $ast.Find({{ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq {_ps_lit(ad)} }}, $true)
if (-not $f) {{ Write-Output "NOT-FOUND"; exit 4 }}
[System.IO.File]::WriteAllText({_ps_lit(out)}, $f.Extent.Text, [System.Text.UTF8Encoding]::new($false))
$p = $ast.ParamBlock
Write-Output ("PARAMS=" + (($p.Parameters | ForEach-Object {{ $_.Name.VariablePath.UserPath }}) -join ','))
Write-Output "OK"
"""
    r = _pwsh_file(tmp_path, f"extract_{ad}.ps1", body)
    assert r.returncode == 0 and "OK" in r.stdout, (
        f"'{ad}' parser ile bulunamadı (rc={r.returncode})\n{r.stdout}\n{r.stderr}"
    )
    m = re.search(r"PARAMS=(.*)", r.stdout)
    assert m and "Kontrol" in m.group(1).split(","), f"-Kontrol anahtarı param bloğunda yok: {r.stdout}"
    return out.read_text(encoding="utf-8")


def _durum(tmp_path: Path, adresler: list[tuple[str, str, str]]) -> str:
    """adresler: (ip, PrefixOrigin, InterfaceAlias) — mock Get-NetIPAddress bunları döndürür."""
    func = _fonksiyon_metni(tmp_path, "Test-PemfHotspotDurumu")
    nesneler = (
        ", ".join(
            f"[pscustomobject]@{{ IPAddress = '{ip}'; PrefixOrigin = '{po}'; InterfaceAlias = '{al}'; AddressFamily = 'IPv4' }}"
            for ip, po, al in adresler
        )
        or "$null"
    )
    body = f"""
$ErrorActionPreference = 'Continue'
function Get-NetIPAddress {{ [CmdletBinding()] param([Parameter(ValueFromRemainingArguments=$true)]$Rest) @({nesneler}) }}
{func}
$d = Test-PemfHotspotDurumu
Write-Output ("DURUM=" + $d.Durum + " IP=" + $d.Ip + " ARAYUZ=" + $d.Arayuz)
"""
    r = _pwsh_file(tmp_path, "run_hotspot_durum.ps1", body)
    assert r.returncode == 0, f"pwsh düştü (rc={r.returncode})\n{r.stdout}\n{r.stderr}"
    m = re.search(r"DURUM=(\S+) IP=(\S*) ARAYUZ=(.*)", r.stdout)
    assert m, f"DURUM satırı yok:\n{r.stdout}\n{r.stderr}"
    return m.group(0)


def test_KRITIK_DHCP_ile_alinan_137_adresi_ISTEMCIdir_sahip_degil(tmp_path):
    """Saha kaydı: Wi-Fi 192.168.137.106 (Dhcp) → 'istemci' (eski kod bunu 'zaten aktif' sayıyordu)."""
    s = _durum(tmp_path, [("192.168.137.106", "Dhcp", "Wi-Fi"), ("10.0.0.5", "Dhcp", "Ethernet")])
    assert s.startswith("DURUM=istemci IP=192.168.137.106"), s
    assert "ARAYUZ=Wi-Fi" in s, s


def test_ICS_ana_bilgisayar_adresi_SAHIP(tmp_path):
    s = _durum(tmp_path, [("192.168.137.1", "Manual", "Local Area Connection* 12")])
    assert s.startswith("DURUM=sahip IP=192.168.137.1"), s


def test_hem_sahip_hem_istemci_varsa_SAHIP_kazanir(tmp_path):
    s = _durum(
        tmp_path, [("192.168.137.106", "Dhcp", "Wi-Fi"), ("192.168.137.1", "WellKnown", "Local Area Connection* 3")]
    )
    assert s.startswith("DURUM=sahip IP=192.168.137.1"), s


def test_137_adresi_yoksa_YOK(tmp_path):
    s = _durum(tmp_path, [("192.168.1.20", "Dhcp", "Wi-Fi")])
    assert s.startswith("DURUM=yok"), s
    assert _durum(tmp_path, []).startswith("DURUM=yok")


def test_yapisal_erken_cikis_YALNIZ_sahip_dalinda():
    """'atlandı' + exit 0 yalnız Durum -eq 'sahip' altında; eski `if ($active)` deseni GERİ GELMEMELİ."""
    src = PS1.read_text(encoding="utf-8-sig")
    assert "if ($active)" not in src, "eski 192.168.137.* tabanlı 'zaten aktif' kontrolü geri gelmiş"
    m = re.search(r"if \(\$durum\.Durum -eq 'sahip'\) \{(.*?)\n\}", src, re.DOTALL)
    assert m and "atlandı" in m.group(1) and "exit 0" in m.group(1), "sahip dalı 'atlandı' + exit 0 taşımıyor"
    ist = re.search(r"if \(\$durum\.Durum -eq 'istemci'\) \{(.*?)\n\}", src, re.DOTALL)
    assert ist and "UYARI" in ist.group(1) and "netsh wlan disconnect" in ist.group(1), (
        "istemci dalı eylemli UYARI vermiyor"
    )
    assert "exit 0" not in ist.group(1), "istemci dalı hotspot'u başlatmadan çıkıyor (eski arıza)"
    assert "connectionmode=manual" in ist.group(1), "kardeş SSID'ye otomatik yeniden katılım kapatılmıyor"
