# -*- coding: utf-8 -*-
"""KI G3 (22 A3a G3 · Ö.4-Y8 "gönderim yalnız artar") — kapanış ucu (`/api/hardware/kapanis_durdur`) 2xx döner ama yanıt PEMF İMZASI
taşımazsa (HTML, yabancı JSON, `status` taklidi) AYNI porta operatörün ACİL DURDUR ucu (`/api/hardware/emergency_stop`) da denenir.

Launcher (`backend.rs::durdur_yanitini_yorumla` → `UcYok` → `estop_ucuyla_durdur`) ve NSIS PREUNINSTALL (YLI-A3.3) bunu yapıyordu; Inno
`PemfEstopPortaGonder` (`build_tools/PEMF_Backend_Setup.iss`) yanıtın imzasına HİÇ bakmıyordu (imzasız 2xx'i "uç var" sayıp ACİL DURDUR'u
atlıyordu) ve `scripts/pemf_teardown.ps1::Invoke-PemfAcilDurdurIstegi` imzasız yanıtı çağırana döndürüyordu → `Send-PemfAcilDurdur`
"PEMF değil" deyip SONRAKİ porta geçiyordu (bu porttaki backend ACİL DURDUR almıyordu). Üç ikiz AYNI senaryo tablosuyla koşar.

İmza (dört ikizde aynı): `status` ∈ {success, partial, error} + `stmStopped` + `mqttResults` (`_emergency_stop_all` her yanıtta basar).
DOĞRULANDI (çıkış 0) Inno / NSIS'te yalnız imza + `confirmed:true` + `status:success`.

GÜVENLİ APARAT (hafıza "pwsh aparatı gerçek NetSecurity'ye ulaşır"): otomatik modül yükleme KAPALI (`$PSModuleAutoLoadingPreference =
'None'`, yalnız Management + Utility açıkça yüklenir); `Invoke-RestMethod` GÖLGE işlev (ağ YOK, dinleyici YOK, gerçek port YOK); gölgenin
işlev olarak çözüldüğü doğrulanmadan hiçbir şey koşmaz. Inno / NSIS gövdesi AST'den izin listesiyle denetlenir; teardown mevcut aparatla
(`test_teardown_ve_nssm_DAVRANIS_pwsh._APARAT`: gerçek betik dot-source EDİLMEZ, işlevler AST'den, yıkıcı komutlar gölge + kanarya).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import test_D3I_teardown_inno_YANITLI_yavas_hata_ACIL_DURDURa_duser as d3i
import test_nsis_estop_IMZASI_YLI_A3_3 as nsis
import test_teardown_ve_nssm_DAVRANIS_pwsh as h

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows betik anlamı")

PORT = 48123
_OTOMATIK_YUKLEME_KAPALI = "Import-Module Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility\n$PSModuleAutoLoadingPreference = 'None'\n"

# Kapanış ucunun yanıtı (`$tur`); ACİL DURDUR ucu gerçek imzalı teyit döner — `yabanci_iki_uc` dışında.
_YANIT = r"""
function G3Yanit([string]$tur, [string]$Uri) {
    $pemf = [pscustomobject]@{ status = 'success'; confirmed = $true; stmStopped = $true; mqttResults = @() }
    $yabanci = [pscustomobject]@{ confirmed = $true }
    if ($Uri -like '*kapanis_durdur') {
        switch ($tur) {
            'html' { return '<!doctype html><html><body>baska servis</body></html>' }
            'yabanci_confirmed' { return $yabanci }
            'status_taklit' { return [pscustomobject]@{ status = 'success'; confirmed = $true } }
            'status_stm_taklit' { return [pscustomobject]@{ status = 'success'; confirmed = $true; stmStopped = $true } }
            'yabanci_iki_uc' { return $yabanci }
            'pemf' { return $pemf }
        }
        throw "aparat: bilinmeyen tur $tur"
    }
    if ($tur -eq 'yabanci_iki_uc') { return $yabanci }
    return $pemf
}
"""
IMZASIZ = ["html", "yabanci_confirmed", "status_taklit", "status_stm_taklit"]
TURLER = IMZASIZ + ["yabanci_iki_uc", "pemf"]
# Beklenen uç dizisi (AYNI port) — imzasız 2xx'te ACİL DURDUR da denenir; imzalı yanıtta ikinci istek YOK.
BEKLENEN_UCLAR = {t: ["kapanis_durdur", "emergency_stop"] for t in IMZASIZ + ["yabanci_iki_uc"]}
BEKLENEN_UCLAR["pemf"] = ["kapanis_durdur"]

_PS51 = d3i._PS51
_PS7 = d3i._PS7


def _uclar(satirlar: list[str]) -> list[str]:
    """`HTTP <yöntem> http://127.0.0.1:<port>/api/hardware/<uç>` → uç adları; port hep AYNI olmalı."""
    uclar = []
    for s in satirlar:
        url = s.split()[-1]
        assert f"127.0.0.1:{PORT}/" in url, f"başka porta istek: {s}"
        uclar.append(url.rsplit("/", 1)[-1])
    return uclar


# ── Inno `[Code]` · `PemfEstopPortaGonder` (Pascal `Komut` dizesi çözülür; gövde AST izin listesi) ─────────────────────────────────
_INNO_APARAT = (
    _OTOMATIK_YUKLEME_KAPALI
    + r"""
$ErrorActionPreference = 'Continue'
$tur = '__TUR__'
"""
    + _YANIT
    + r"""
function Invoke-RestMethod {
    [CmdletBinding()] param([string]$Uri, [string]$Method, $TimeoutSec, [string]$ContentType, $Body)
    [Console]::Out.WriteLine('HTTP ' + $Method + ' ' + $Uri)
    G3Yanit $tur $Uri
}
$ic = @'
__GOVDE__
'@
$hata = $null; $jeton = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($ic, [ref]$jeton, [ref]$hata)
if ($hata) { [Console]::Out.WriteLine('APARAT_HATASI parse'); exit 3 }
foreach ($c in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true)) {
    if (@(__IZINLI__) -notcontains $c.GetCommandName()) {
        [Console]::Out.WriteLine('APARAT_HATASI izinsiz komut: ' + $c.GetCommandName()); exit 3
    }
}
if ((Get-Command Invoke-RestMethod | Select-Object -First 1).CommandType -ne 'Function') { [Console]::Out.WriteLine('APARAT_HATASI golge'); exit 3 }
if ($PSModuleAutoLoadingPreference -ne 'None') { [Console]::Out.WriteLine('APARAT_HATASI otomatik yukleme acik'); exit 3 }
[Console]::Out.WriteLine('SURUM ' + $PSVersionTable.PSVersion.Major)
. ([ScriptBlock]::Create($ic))
"""
)


def _govde_kos(tmp_path: Path, exe: str, tur: str, govde: str, izinli: list[str]) -> tuple[int, list[str], str]:
    betik = (
        _INNO_APARAT.replace("__TUR__", tur)
        .replace("__IZINLI__", ", ".join(f"'{a}'" for a in izinli))
        .replace("__GOVDE__", govde)
    )
    yol = tmp_path / f"g3_{tur}.ps1"
    yol.write_text(betik, encoding="utf-8-sig")
    r = subprocess.run(
        [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(yol)],
        capture_output=True,
        timeout=120,
        cwd=str(tmp_path),
    )
    out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    assert "APARAT_HATASI" not in out, f"aparat güvenli değil — koşmadı: {out[-600:]}"
    assert "SURUM " in out, f"aparat gövdeye ulaşmadı: {out[-600:]}"
    return r.returncode, [s for s in out.splitlines() if s.startswith("HTTP ")], out


def _dogrulama_beklentisi(tur: str, rc: int, out: str, uclar: list[str]) -> None:
    if tur == "yabanci_iki_uc":
        assert rc == 2, f"iki ucu da yabancı ({{confirmed:true}}) yanıt DOĞRULANDI sayıldı (rc={rc}): {out[-300:]}"
    elif tur == "pemf":
        assert rc == 0 and "OK uc=1" in out, f"imzalı teyit DOĞRULANDI değil (rc={rc}): {out[-300:]}"
    else:
        assert rc == 0 and "OK uc=2" in out, f"ACİL DURDUR ucunun imzalı teyidi raporlanmadı (rc={rc}): {out[-300:]}"


@pytest.mark.parametrize("tur", TURLER)
@pytest.mark.parametrize("exe", d3i.YORUMLAYICILAR)
def test_KRITIK_KI_G3_inno_imzasiz_2xx_AYNI_porta_ACIL_DURDUR(tmp_path, exe, tur):
    rc, http, out = _govde_kos(
        tmp_path,
        exe,
        tur,
        d3i._inno_komut_govdesi(PORT),
        ["Invoke-RestMethod", "Get-Date", "ConvertTo-Json", "Write-Host"],
    )
    assert ("SURUM 5" in out) == (exe == _PS51), out[-300:]
    uclar = _uclar(http)
    print(f"G3OLC|inno|{tur}|rc={rc}|{uclar}")
    assert uclar == BEKLENEN_UCLAR[tur], f"Inno {tur}: {uclar} · {out[-300:]}"
    _dogrulama_beklentisi(tur, rc, out, uclar)


@pytest.mark.parametrize("tur", TURLER)
def test_KRITIK_KI_G3_nsis_ikizi_AYNI_kural(tmp_path, tur):
    """NSIS PREUNINSTALL (YLI-A3.3) — kural zaten buydu; üç ikiz aynı tabloyla ölçülür (32-bit PowerShell varsa o)."""
    rc, http, out = _govde_kos(
        tmp_path,
        nsis._ps(),
        tur,
        nsis._estop_komutu(PORT),
        ["Invoke-RestMethod", "Get-Date", "ConvertTo-Json", "Write-Host", "Write-Output"],
    )
    uclar = _uclar(http)
    print(f"G3OLC|nsis|{tur}|rc={rc}|{uclar}")
    assert uclar == BEKLENEN_UCLAR[tur], f"NSIS {tur}: {uclar} · {out[-300:]}"
    _dogrulama_beklentisi(tur, rc, out, uclar)


# ── Teardown (`pemf_teardown.ps1`) — mevcut güvenli aparat + otomatik yükleme kapalı + G3 yanıt davranışı ───────────────────────────
_CAPA_PARAM = (
    "param([string]$Teardown, [string]$Setup, [string]$Kok, [string]$Senaryo, [string]$Cikti, [int]$Bekleme = 0)\n"
)
_CAPA_DAVRANIS = "    $port = ([uri]$Uri).Port\n"
_CAPA_SENARYO = "            'estop_kapanis_yavas' { Set-Content"


@pytest.fixture
def aparat(monkeypatch):
    a = h._APARAT
    assert a.count(_CAPA_PARAM) == 1 and a.count(_CAPA_DAVRANIS) == 1 and a.count(_CAPA_SENARYO) == 1, (
        "aparat değişti — çapa yok"
    )
    ek_param = (
        _OTOMATIK_YUKLEME_KAPALI
        # PS 5.1'de `sc` = Set-Content TAKMA ADI (işlevden önce çözülür) → kanarya "gölgelenemedi" der (D3I aparatıyla aynı önlem).
        + "if (Test-Path alias:sc) { Microsoft.PowerShell.Management\\Remove-Item -LiteralPath alias:sc -Force }\n"
        + _YANIT
    )
    ek_davranis = (
        "    if ($script:HttpDavranis -like 'g3_*') { return (G3Yanit $script:HttpDavranis.Substring(3) $Uri) }\n"
    )
    ek_senaryo = "".join(
        f"            'estop_g3_{t}' {{ Set-Content -LiteralPath $portDosyasi -Value '{PORT}'; $script:AcikPortlar = @({PORT}); "
        f"$script:HttpDavranis = 'g3_{t}' }}\n"
        for t in TURLER
    )
    a = (
        a.replace(_CAPA_PARAM, _CAPA_PARAM + ek_param)
        .replace(_CAPA_DAVRANIS, ek_davranis + _CAPA_DAVRANIS)
        .replace(_CAPA_SENARYO, ek_senaryo + _CAPA_SENARYO)
    )
    monkeypatch.setattr(h, "_APARAT", a)
    return monkeypatch


@pytest.mark.parametrize("tur", TURLER)
@pytest.mark.parametrize("exe", d3i.YORUMLAYICILAR)
def test_KRITIK_KI_G3_teardown_imzasiz_2xx_AYNI_porta_ACIL_DURDUR_sonra_kill(aparat, tmp_path, exe, tur):
    aparat.setattr(h, "_PWSH", exe)
    s = h._kos(tmp_path, f"estop_g3_{tur}")
    k = s["kayit"]
    uclar = _uclar([x for x in k if x.startswith("HTTP ")])
    print(f"G3OLC|teardown|{tur}|{uclar}")
    assert uclar == BEKLENEN_UCLAR[tur], f"teardown {tur}: {uclar}"
    assert "Stop-Process" in k, "ACİL DURDUR yolu kaldırmayı durdurdu (kill kapı DEĞİL)"
    son_http = max(i for i, x in enumerate(k) if x.startswith("HTTP "))
    assert k.index("Stop-Process") > son_http, "kill ACİL DURDUR denemesinden ÖNCE"
    gonderildi = any(x.startswith(f"LOG ACİL DURDUR gönderildi: 127.0.0.1:{PORT}") for x in k)
    if tur == "yabanci_iki_uc":
        assert not gonderildi, "iki ucu da yabancı yanıt 'gönderildi' sayıldı"
        assert any(x.startswith("LOG ACİL DURDUR TEYİT EDİLEMEDİ") for x in k), f"teyitsizlik özeti yok: {k}"
    else:
        assert gonderildi, (
            f"{tur}: imzalı ACİL DURDUR yanıtı 'gönderildi' sayılmadı: {[x for x in k if x.startswith('LOG')]}"
        )


def test_KI_G3_aparat_otomatik_yukleme_KAPALI_ve_golge_kanitli(aparat, tmp_path):
    """Aparatın kendisi: otomatik modül yükleme kapalıyken gölgelenmemiş bir NetSecurity cmdlet'i ÇÖZÜLEMEZ (gerçek güvenlik duvarına
    ulaşılamaz) ve yama üç çapada da uygulandı."""
    a = h._APARAT
    assert (
        "$PSModuleAutoLoadingPreference = 'None'" in a and "estop_g3_html" in a and "G3Yanit $script:HttpDavranis" in a
    )
    yol = tmp_path / "kanit.ps1"
    yol.write_text(
        _OTOMATIK_YUKLEME_KAPALI
        + "if (Get-Command Get-NetFirewallRule -ErrorAction SilentlyContinue) { 'COZULDU' } else { 'COZULEMEDI' }\n",
        encoding="utf-8-sig",
    )
    for exe in [e for e in (_PS51, _PS7) if e]:
        r = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(yol)],
            capture_output=True,
            timeout=60,
        )
        assert r.stdout.decode("utf-8", "replace").strip() == "COZULEMEDI", (exe, r.stdout, r.stderr)
