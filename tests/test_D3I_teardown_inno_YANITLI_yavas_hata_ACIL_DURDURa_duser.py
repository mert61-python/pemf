# Author: mertaygn, cglrgrkn
"""D3I-A1.4 — kapanış ucu (`/api/hardware/kapanis_durdur`) YANITLI HTTP hatasını (eski backend 405, 5xx) 2 sn'den GEÇ dönerse
`scripts/pemf_teardown.ps1::Invoke-PemfAcilDurdurIstegi` ve Inno `PemfEstopPortaGonder` (`build_tools/PEMF_Backend_Setup.iss`) onu
zaman aşımı sayıp `throw` ediyor → operatörün ACİL DURDUR ucu (`/api/hardware/emergency_stop`) HİÇ denenmeden kill. Launcher
(`durdur_iste`: `ureq::Error::Status` → `UcYok` → ACİL DURDUR) ve NSIS (18K K2 `5b9144ad`: `-not $_.Exception.Response -and … ≥ 2 sn`)
yanıtlı hatayı süreden bağımsız "uç yok" sayar; 2 sn eşiği yalnız YANITSIZ hataya (asılı backend: ikinci 10 sn'lik istek kaldırmayı
uzatır, kazandırmaz). Ö.4-Y8: gönderim yalnız ARTAR — dört ikiz aynı kuralı taşımalı.

İKİ yorumlayıcıda, sürüme ÖZGÜ GERÇEKÇİ istisna tipleriyle (ağ YOK, dinleyici YOK):
* Windows PowerShell 5.1 (`powershell.exe` — Inno `[Code]` ve `setup_services.ps1 -Uninstall` bunu çağırır): HTTP hatası =
  `WebException(ProtocolError, Response = HttpWebResponse)`; zaman aşımı = `WebException(Timeout)`; red = `WebException(ConnectFailure)`
  (ikisinde `Response` BOŞ);
* PowerShell 7 (`pemf_uninstall_all.ps1` elle): HTTP hatası = `HttpResponseException(Response = HttpResponseMessage)`; zaman aşımı =
  `TaskCanceledException`; red = `HttpRequestException` (`Response` özelliği YOK → `$null`, StrictMode kullanılmıyor).
Teardown: MEVCUT güvenli aparat (`test_teardown_ve_nssm_DAVRANIS_pwsh._APARAT` — gerçek betik DOT-SOURCE EDİLMEZ, izinli işlevler
AST'den denetlenerek, yıkıcı komutlar gölge + kanarya, `Invoke-RestMethod` gölge). Inno: `[Code]`'daki `Komut` dizesi Pascal
birleştirmesinden ÇÖZÜLÜR, `-Command` gövdesi AST'den denetlenir (yalnız `Invoke-RestMethod` / `Get-Date` / `ConvertTo-Json` /
`Write-Host`), `Invoke-RestMethod` gölgelenir, gölgenin FONKSİYON olarak çözüldüğü doğrulanmadan hiçbir şey koşmaz.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import capraz
import pytest
import test_teardown_ve_nssm_DAVRANIS_pwsh as h

KOK = Path(__file__).resolve().parents[1]
ISS = KOK / "build_tools" / "PEMF_Backend_Setup.iss"
_PS51 = shutil.which("powershell.exe") or shutil.which("powershell")
_PS7 = shutil.which("pwsh")
YORUMLAYICILAR = [
    pytest.param(
        _PS51,
        id="PS5.1",
        marks=pytest.mark.skipif((_PS51 is None) and not capraz.ZORUNLU, reason="Windows PowerShell 5.1 yok"),
    ),
    pytest.param(_PS7, id="pwsh7", marks=pytest.mark.skipif((_PS7 is None) and not capraz.ZORUNLU, reason="pwsh yok")),
]
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows betik anlamı")

# Sürüme özgü sahte istisna (kapanış ucunda); `$tur`: yavas_* = 2,3 sn sonra; *_405 yanıtlı; *_zaman / *_red yanıtsız.
_ISTISNA = r"""
    $ps7 = $PSVersionTable.PSVersion.Major -ge 6
    if ($tur -like 'yavas_*') { [System.Threading.Thread]::Sleep(2300) }
    if ($tur -like '*_405') {
        if ($ps7) { throw [Microsoft.PowerShell.Commands.HttpResponseException]::new('sahte: (405) Method Not Allowed', [System.Net.Http.HttpResponseMessage]::new([System.Net.HttpStatusCode]::MethodNotAllowed)) }
        throw [System.Net.WebException]::new('sahte: (405) Method Not Allowed', $null, [System.Net.WebExceptionStatus]::ProtocolError, [System.Runtime.Serialization.FormatterServices]::GetUninitializedObject([System.Net.HttpWebResponse]))
    }
    if ($tur -like '*_zaman') {
        if ($ps7) { throw [System.Threading.Tasks.TaskCanceledException]::new('sahte: HttpClient.Timeout') }
        throw [System.Net.WebException]::new('sahte: The operation has timed out', [System.Net.WebExceptionStatus]::Timeout)
    }
    if ($tur -like '*_red') {
        if ($ps7) { throw [System.Net.Http.HttpRequestException]::new('sahte: No connection could be made') }
        throw [System.Net.WebException]::new('sahte: Unable to connect to the remote server', [System.Net.WebExceptionStatus]::ConnectFailure)
    }
"""
DURUMLAR = ["yavas_405", "hizli_405", "yavas_zaman", "hizli_red"]
# Beklenen (dört ikizin ORTAK kuralı — launcher `durdur_iste` / NSIS 18K K2): yanıtlı → ACİL DURDUR; yanıtsız → yalnız < 2 sn ise.
BEKLENEN_ESTOP = {"yavas_405": True, "hizli_405": True, "yavas_zaman": False, "hizli_red": True}

# ── Teardown (mevcut güvenli aparat + sürüme özgü istisna) ─────────────────────────────────────────────────────────────────────
_CAPA_DAVRANIS = "    if ($script:HttpDavranis -eq 'kapanis_yavas' -and $Uri -like '*kapanis_durdur') {"
_CAPA_SENARYO = "            'estop_kapanis_yavas' { Set-Content"


@pytest.fixture
def aparat(monkeypatch):
    a = h._APARAT
    assert a.count(_CAPA_DAVRANIS) == 1 and a.count(_CAPA_SENARYO) == 1, "aparat değişti — çapa yok"
    ek_davranis = (
        "    if ($script:HttpDavranis -like 'd3i_*' -and $Uri -like '*kapanis_durdur') { $tur = $script:HttpDavranis.Substring(4)\n"
        + _ISTISNA
        + "    }\n"
    )
    ek_senaryo = "".join(
        f"            'estop_d3i_{d}' {{ Set-Content -LiteralPath $portDosyasi -Value '48123'; $script:AcikPortlar = @(48123); "
        f"$script:HttpDavranis = 'd3i_{d}' }}\n"
        for d in DURUMLAR
    )
    a = a.replace(_CAPA_DAVRANIS, ek_davranis + _CAPA_DAVRANIS).replace(_CAPA_SENARYO, ek_senaryo + _CAPA_SENARYO)
    # PS 5.1'de `sc` = Set-Content TAKMA ADI (takma ad işlevden ÖNCE çözülür) → aparatın kanaryası "gölgelenemedi" deyip HİÇBİR şey
    # koşmadan çıkar (güvenli ret, ölçüldü). Yalnız bu alt süreçte takma ad kaldırılır; kanarya yine HER gölgenin işlev olduğunu doğrular.
    ilk_satir = a.index("\n", a.index("param(")) + 1
    a = (
        a[:ilk_satir]
        + "if (Test-Path alias:sc) { Microsoft.PowerShell.Management\\Remove-Item -LiteralPath alias:sc -Force }\n"
        + a[ilk_satir:]
    )
    monkeypatch.setattr(h, "_APARAT", a)
    return monkeypatch


@pytest.mark.parametrize("durum", DURUMLAR)
@pytest.mark.parametrize("exe", YORUMLAYICILAR)
def test_KRITIK_teardown_YANITLI_hata_sureden_bagimsiz_ACIL_DURDUR_yanitsiz_yavas_TEK_istek(
    aparat, tmp_path, exe, durum
):
    aparat.setattr(h, "_PWSH", exe)
    s = h._kos(tmp_path, f"estop_d3i_{durum}")
    k = s["kayit"]
    http = [x for x in k if x.startswith("HTTP ")]
    beklenen = ["HTTP Post http://127.0.0.1:48123/api/hardware/kapanis_durdur"]
    if BEKLENEN_ESTOP[durum]:
        beklenen.append("HTTP Post http://127.0.0.1:48123/api/hardware/emergency_stop")
    assert http == beklenen, f"{durum}: {http}"
    assert "Stop-Process" in k, "kapanış ucunun hatası kaldırmayı durdurdu (kill kapı DEĞİL)"
    if BEKLENEN_ESTOP[durum]:
        assert k.index("Stop-Process") > h._ilk(k, "HTTP Post http://127.0.0.1:48123/api/hardware/emergency_stop")


# ── Inno `[Code]` ikizi (`PemfEstopPortaGonder`) — Pascal `Komut` dizesi çözülür, gölgeli Invoke-RestMethod ile koşar ──────────────
def _inno_komut_govdesi(port: int) -> str:
    g = ISS.read_bytes().decode("utf-8", "replace")
    m = re.search(
        r"procedure PemfEstopPortaGonder\(Port: Integer\);.*?\n  Komut := (.*?);\r?\n  if Exec\('powershell\.exe', Komut",
        g,
        re.S,
    )
    assert m, "Inno PemfEstopPortaGonder Komut ataması bulunamadı (yapı değişti)"
    parca, i, ifade = [], 0, m.group(1)
    jeton = re.compile(r"\s+|\+|'((?:[^']|'')*)'|IntToStr\(Port\)")
    while i < len(ifade):
        j = jeton.match(ifade, i)
        assert j, f"Pascal ifadesi çözülemedi: {ifade[i : i + 60]!r}"
        if j.group(0).startswith("'"):
            parca.append(j.group(1).replace("''", "'"))
        elif j.group(0) == "IntToStr(Port)":
            parca.append(str(port))
        i = j.end()
    komut = "".join(parca)
    c = re.fullmatch(r'-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "(.*)"', komut, re.S)
    assert c and '"' not in c.group(1), f"Inno komut biçimi değişti: {komut[:120]!r}"
    return c.group(1)


_INNO_APARAT = r"""
$ErrorActionPreference = 'Continue'
$tur = '__TUR__'
function Invoke-RestMethod {
    [CmdletBinding()] param([string]$Uri, [string]$Method, $TimeoutSec, [string]$ContentType, $Body)
    [Console]::Out.WriteLine('HTTP ' + $Method + ' ' + $Uri)
    if ($Uri -like '*kapanis_durdur') {
__ISTISNA__
    }
    [pscustomobject]@{ status = 'success'; confirmed = $true; stmStopped = $true; mqttResults = @() }
}
$ic = @'
__GOVDE__
'@
$hata = $null; $jeton = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($ic, [ref]$jeton, [ref]$hata)
if ($hata) { [Console]::Out.WriteLine('APARAT_HATASI parse'); exit 3 }
foreach ($c in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true)) {
    if (@('Invoke-RestMethod', 'Get-Date', 'ConvertTo-Json', 'Write-Host') -notcontains $c.GetCommandName()) {
        [Console]::Out.WriteLine('APARAT_HATASI izinsiz komut: ' + $c.GetCommandName()); exit 3
    }
}
if ((Get-Command Invoke-RestMethod | Select-Object -First 1).CommandType -ne 'Function') { [Console]::Out.WriteLine('APARAT_HATASI golge'); exit 3 }
[Console]::Out.WriteLine('SURUM ' + $PSVersionTable.PSVersion.Major)
. ([ScriptBlock]::Create($ic))
"""


def _inno_kos(tmp_path: Path, exe: str, tur: str) -> tuple[int, list[str], str]:
    betik = (
        _INNO_APARAT.replace("__TUR__", tur)
        .replace("__ISTISNA__", _ISTISNA)
        .replace("__GOVDE__", _inno_komut_govdesi(48123))
    )
    yol = tmp_path / "inno_aparat.ps1"
    yol.write_text(betik, encoding="utf-8-sig")
    r = subprocess.run(
        [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(yol)],
        capture_output=True,
        timeout=120,
        cwd=str(tmp_path),
    )
    out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    assert "APARAT_HATASI" not in out, f"Inno aparatı güvenli değil — koşmadı: {out[-600:]}"
    return r.returncode, [s for s in out.splitlines() if s.startswith("HTTP ")], out


@pytest.mark.parametrize("durum", DURUMLAR)
@pytest.mark.parametrize("exe", YORUMLAYICILAR)
def test_KRITIK_inno_YANITLI_hata_sureden_bagimsiz_ACIL_DURDUR_yanitsiz_yavas_TEK_istek(tmp_path, exe, durum):
    rc, http, out = _inno_kos(tmp_path, exe, durum)
    assert ("SURUM 5" in out) == (exe == _PS51), out[-300:]
    beklenen = ["HTTP POST http://127.0.0.1:48123/api/hardware/kapanis_durdur"]
    if BEKLENEN_ESTOP[durum]:
        beklenen.append("HTTP POST http://127.0.0.1:48123/api/hardware/emergency_stop")
    assert http == beklenen, f"{durum}: {http} · {out[-300:]}"
    if BEKLENEN_ESTOP[durum]:
        assert rc == 0 and "OK uc=2" in out, f"ACİL DURDUR yanıtı raporlanmadı (rc={rc}): {out[-300:]}"
    else:
        assert rc == 1 and "FAIL=" in out, f"yanıtsız yavaş hata raporlanmadı (rc={rc}): {out[-300:]}"


def test_IKIZ_kurali_teardown_inno_nsis_AYNI_ifade():
    """Üç PowerShell ikizi aynı koşulu taşır (launcher Rust ikizi `durdur_iste` / `safe_stop_coils` — kendi testleri)."""
    kural = r"-not \$_\.Exception\.Response -and \(\(Get-Date\) - \$t0\)\.TotalSeconds -ge 2\) \{ throw \}"
    teardown = (KOK / "scripts" / "pemf_teardown.ps1").read_text(encoding="utf-8-sig")
    nsis = (KOK / "launcher" / "app" / "windows" / "hooks.nsi").read_bytes().decode("utf-8", "replace")
    inno = _inno_komut_govdesi(1)
    assert re.search(kural, teardown), "teardown"
    assert re.search(kural.replace(r"\$", r"\$\$"), nsis), "NSIS (18K K2) — kural değişti mi?"
    assert re.search(kural, inno), "Inno"
