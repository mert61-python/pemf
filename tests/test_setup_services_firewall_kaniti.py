# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""setup_services.ps1 — Mosquitto firewall kuralı + runhidden log kanıtı (denetim 2026-09-06).

ARIZA: Inno `setup_services.ps1`'i `runhidden` ile çalıştırır. Eski `Log` yalnız `Write-Host`
yazıyordu → konsol yok → HER mesaj kayboluyordu. Aynı script'te Mosquitto firewall kuralı
(`PEMF Mosquitto MQTT`, TCP 1883 <- 192.168.137.0/24) try/catch'siz, `-ErrorAction Stop`suz ve
SON-KONTROLSÜZ oluşturuluyordu. MpsSvc durmuşsa / GPO firewall'u kilitlediyse cmdlet hata akışına
düşer, 1883 loopback probe'u yine geçer, "Mosquitto hazır" loglanır, `.install_verified` yazılır.
Sonuç: ESP bobini (hotspot subnet) broker'a ULAŞAMAZ ama yerel her gösterge YEŞİL — sıfır kanıt.
(D6.54: betiğin ESP bobin etiketi topolojiden — `live_state.ESP_COIL_IDS` — türetilip ölçülür; bugün "ESP bobin 8".)

Bu dosya ÜÇ şeyi ÖLÇER (metin aramaz):
  (a) `Ensure-PemfMosquittoFirewallRule` fonksiyonu, PowerShell'in KENDİ parser'ıyla script'ten
      çekilip pwsh altında MOCK'larla ÇALIŞTIRILIR: kural yaratılamıyor + sorgu boş → False döner ve
      Log'a eylem söyleyen UYARI düşer; kural varsa → True, UYARI yok, New-NetFirewallRule çağrılmaz.
  (b) `Log` fonksiyonu çalıştırılır: dosya-sink'e ISO damgalı satır yazar; yazılamayan dizinde bile
      ASLA fırlatmaz (kurulumu düşürmez).
  (c) AST yapısal kapı: script'teki HER `New-NetFirewallRule` çağrısı bir TryStatementAst içinde ve
      `-ErrorAction Stop` taşıyor; `Log` gövdesinde `Add-Content` var; `.install_verified` içeriğinde
      `mosqFirewall=` kanıtı var.

Mutasyonla KIRMIZI kanıtlandı (bkz. rapor): `-ErrorAction Stop` silinince (a)+(c) düşer, try
kaldırılınca (c) düşer, Log'dan Add-Content silinince (b)+(c) düşer.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import capraz
import pytest

REPO = Path(__file__).resolve().parent.parent
PS1 = REPO / "scripts" / "setup_services.ps1"
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(
    (PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) yok — PS fonksiyonu koşturulamaz"
)


# ─────────────────────────── yardımcılar ───────────────────────────
def _pwsh_file(tmp_path: Path, name: str, body: str) -> subprocess.CompletedProcess:
    """Geçici .ps1'i UTF-8-BOM ile yaz (Türkçe metin bozulmasın) ve pwsh -File ile koştur."""
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


def _esp_bobin_numarasi() -> str:
    """D6.54: betikteki ESP bobin etiketi TEK KAYNAKTAN — `live_state.ESP_COIL_IDS` (yönlendirme kümesi). Tek bobin "8",
    ardışık küme "6-8", dağınık küme "6, 8". Elle yazılmış "6-8" topoloji 2026-09-10'da (bobin 6-7 STM'e) değişince bayatladı."""
    from servers import live_state

    ids = sorted(int(i) for i in live_state.ESP_COIL_IDS)
    assert ids, "live_state.ESP_COIL_IDS BOŞ — ESP bobin etiketi türetilemez"
    if len(ids) == 1:
        return str(ids[0])
    if ids == list(range(ids[0], ids[-1] + 1)):
        return f"{ids[0]}-{ids[-1]}"
    return ", ".join(str(i) for i in ids)


# "ESP bobin 8", "ESP bobini (8)", "ESP bobinleri 6-8", "ESP 6-8" … — betikteki HER ESP bobin numarası (yorum dahil: aynı iddia).
# Tur 2 kolu (D67 çürütme, mutantlar a1 / a2): "ESP (bobin 6-8)", "ESP bobinleri: 6-8" ve uzun tire ("6–8") biçimleri de yakalanır.
_ESP_NUMARA_RE = re.compile(r"ESP(?:[ \t]*\(?[ \t]*bobin\w*)?[ \t]*[:(]?[ \t]*(\d+(?:[ \t]*[-–][ \t]*\d+)?)(?![\d.])")


def _ps_lit(s: str | Path) -> str:
    """Tek-tırnaklı PowerShell string literal'i (ters-bölüler ham kalır)."""
    return "'" + str(s).replace("'", "''") + "'"


# SON-A1.55 (22 · A1b): çekilen işlev aparatlarda (DEV-C4 / bu dosya / D3_07 / D3_08 / D3_32 / D3_42 / D3I / D5H1 / D5G2) gölgeyle
# KOŞTURULUR — eskiden izin listesi YOKTU: işlev gövdesine giren gölgelenmemiş cmdlet (Set-Content / Stop-Service / Remove-Item), .NET
# yöntemi (`[IO.File]::…`), dosyaya yönlendirme ve sürücü nitelikli değişken (`${C:\…}`) GERÇEKTEN koşuyordu (ölçüldü: işaret dosyaları
# yazıldı). Artık işlev ÇEKİLİRKEN bu deftere karşı denetlenir (D5 H-1 `_IzinDisi` sınıfı); defterde olmayan işlev çekilmez (fail-closed).
# (komutlar, yöntem adları, betik bloğu değişkeniyle çağrı `& $ad` izinli değişken adları)
_ISLEV_IZNI: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "Ensure-PemfMosquittoFirewallRule": (
        (
            "Get-NetFirewallAddressFilter",
            "Get-NetFirewallPortFilter",
            "Get-NetFirewallRule",
            "Get-Service",
            "Log",
            "New-NetFirewallRule",
            "Out-Null",
            "Remove-NetFirewallRule",
            "Set-NetFirewallRule",
            "Where-Object",
        ),
        (),
        ("IcerikUygun",),
    ),  # fmt: skip
    "Test-PemfAtRestDurumu": (("Invoke-RestMethod", "Start-Sleep"), (), ()),
    "Format-PemfEnvGunluk": (("ForEach-Object",), (), ()),
    "Test-PemfEspEtkin": ((), ("Trim", "Contains"), ()),
    "Test-PemfApiPortDegeri": ((), ("GetNumericValue", "Match", "ToCharArray"), ()),
    # Yalnız `test_Log_…` koşturur ($LogDir tmp_path'e yönlendirilmiş); varsayılan ProgramData dalı orada çağrılmaz.
    "Log": (("Add-Content", "Get-Date", "Join-Path", "New-Item", "Out-Null", "Write-Host"), (), ()),
}


def _ps_dizi(ogeler) -> str:
    return "@(" + ", ".join(_ps_lit(o) for o in ogeler) + ")"


def _extract_function(tmp_path: Path, func_name: str) -> str:
    """Fonksiyon metnini PowerShell'in kendi parser'ıyla (FunctionDefinitionAst.Extent.Text) çek.

    Regex DEĞİL: iç içe süslü parantez / here-string / yorumlar parser'a bırakılır.
    SON-A1.55: çekmeden ÖNCE işlev `_ISLEV_IZNI` defterine karşı denetlenir (izin dışı → çıkış 5, metin dönmez).
    """
    assert func_name in _ISLEV_IZNI, (
        f"'{func_name}' işlev izin defterinde (_ISLEV_IZNI) yok — aparat onu gölgeyle KOŞTURUR; komut / yöntem listesini deftere yazın"
    )
    komut, uye, degisken = _ISLEV_IZNI[func_name]
    out = tmp_path / f"{func_name}.txt"
    body = f"""
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile({_ps_lit(PS1)}, [ref]$tokens, [ref]$errors)
if ($errors.Count) {{ Write-Output ("PARSE-ERROR: " + ($errors | ForEach-Object {{ $_.Message }}) -join ' | '); exit 3 }}
$f = $ast.Find({{ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq {_ps_lit(func_name)} }}, $true)
if (-not $f) {{ Write-Output "NOT-FOUND"; exit 4 }}
$Komut = {_ps_dizi(komut)}; $Uye = {_ps_dizi(uye)}; $Degisken = {_ps_dizi(degisken)}
foreach ($c in @($f.FindAll({{ param($n) $n -is [System.Management.Automation.Language.CommandAst] }}, $true))) {{
    $ad = $c.GetCommandName()
    if ($ad) {{ if ($Komut -notcontains $ad) {{ Write-Output ("IZIN-DISI komut: " + $c.Extent.Text); exit 5 }}; continue }}
    $ilk = $c.CommandElements[0]
    if (-not ($ilk -is [System.Management.Automation.Language.VariableExpressionAst] -and $Degisken -contains $ilk.VariablePath.UserPath)) {{
        Write-Output ("IZIN-DISI degiskenle cagri: " + $c.Extent.Text); exit 5 }}
}}
foreach ($y in @($f.FindAll({{ param($n) $n -is [System.Management.Automation.Language.InvokeMemberExpressionAst] }}, $true))) {{
    if ($Uye -notcontains "$($y.Member.Extent.Text)") {{ Write-Output ("IZIN-DISI yontem: " + $y.Extent.Text); exit 5 }}
}}
foreach ($r in @($f.FindAll({{ param($n) $n -is [System.Management.Automation.Language.FileRedirectionAst] }}, $true))) {{
    if (-not ($r.Location -is [System.Management.Automation.Language.VariableExpressionAst] -and $r.Location.VariablePath.UserPath -eq 'null')) {{
        Write-Output ("IZIN-DISI yonlendirme: " + $r.Extent.Text); exit 5 }}
}}
foreach ($v in @($f.FindAll({{ param($n) $n -is [System.Management.Automation.Language.VariableExpressionAst] -and $n.VariablePath.IsDriveQualified -and
        $n.VariablePath.DriveName -ne 'env' }}, $true))) {{ Write-Output ("IZIN-DISI surucu nitelikli degisken: " + $v.Extent.Text); exit 5 }}
[System.IO.File]::WriteAllText({_ps_lit(out)}, $f.Extent.Text, [System.Text.UTF8Encoding]::new($false))
Write-Output "OK"
"""
    r = _pwsh_file(tmp_path, f"extract_{func_name}.ps1", body)
    izin_disi = [s for s in r.stdout.splitlines() if s.startswith("IZIN-DISI")]
    assert not izin_disi, (
        f"setup_services.ps1 '{func_name}' izin defteri DIŞINDA {izin_disi[0][len('IZIN-DISI ') :]} — aparat onu GERÇEKTEN koşardı; "
        f"KOŞTURULMADI. Ürün değişikliğini gözden geçirin ya da gölgeleyip _ISLEV_IZNI'ye ekleyin."
    )
    assert r.returncode == 0 and "OK" in r.stdout, (
        f"setup_services.ps1 icinde '{func_name}' fonksiyonu PARSER ile bulunamadi (rc={r.returncode}).\n"
        f"stdout={r.stdout}\nstderr={r.stderr}\n"
        f"-> Fonksiyon silinmis/yeniden adlandirilmis olabilir; script'i inline'a GERI DONDURME, "
        f"fonksiyonu geri getir (testler installer'i calistirmadan dot-source eder)."
    )
    return out.read_text(encoding="utf-8")


def _run_firewall_func(tmp_path: Path, *, rule_exists: bool, new_rule_fails: bool) -> tuple[str, str]:
    """Fonksiyonu mock'larla koştur → (RESULT satırı, Log dosyası içeriği)."""
    func = _extract_function(tmp_path, "Ensure-PemfMosquittoFirewallRule")
    log = tmp_path / "log.txt"
    log.write_text("", encoding="utf-8")
    get_body = (
        "[pscustomobject]@{ DisplayName = 'PEMF Mosquitto MQTT'; Enabled = 'True'; Action = 'Allow'; Direction = 'Inbound'; Profile = 'Any' }"
        if rule_exists
        else "$null"
    )
    new_body = 'Write-Error "RPC server unavailable"' if new_rule_fails else "$null"
    body = f"""
Import-Module Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility
$PSModuleAutoLoadingPreference = 'None'
$ErrorActionPreference = 'Continue'   # setup_services.ps1 ile AYNI (installer akisi kesilmesin)
# ── MOCK'lar: gerçek NetSecurity cmdlet'leri YOK; -ErrorAction gibi ortak parametreler CmdletBinding ile alınır ──
function Get-NetFirewallRule {{ [CmdletBinding()] param([Parameter(ValueFromRemainingArguments=$true)]$Rest) if ($Rest -contains 'Mosquitto MQTT') {{ return }}; {get_body} }}
# D3.42: fonksiyon kuralın İÇERİĞİNİ (uzak adres), eski 'Mosquitto MQTT' kuralını ve native servisi de sorar → bunlar da SAHTE; modül
# OTOMATİK YÜKLEME KAPALI: gölgelenmemiş bir NetSecurity cmdlet'i gerçek güvenlik duvarına ULAŞAMAZ ("komut yok" ile düşer).
function Get-NetFirewallAddressFilter {{ [CmdletBinding()] param([Parameter(ValueFromPipeline=$true)]$InputObject) process {{ [pscustomobject]@{{ RemoteAddress = '192.168.137.0/24' }} }} }}
# DEV-C4: fonksiyon kuralın port / protokol / durum içeriğini de okur → gerçek kural nesnesi gibi TAM içerik + port süzgeci gölgesi.
function Get-NetFirewallPortFilter {{ [CmdletBinding()] param([Parameter(ValueFromPipeline=$true)]$InputObject) process {{ [pscustomobject]@{{ Protocol = 'TCP'; LocalPort = '1883' }} }} }}
function Set-NetFirewallRule {{ [CmdletBinding()] param([Parameter(ValueFromPipeline=$true)]$InputObject, $RemoteAddress) process {{ throw 'D3.42 aparat: Set beklenmiyor' }} }}
function Remove-NetFirewallRule {{ [CmdletBinding()] param([Parameter(ValueFromPipeline=$true)]$InputObject) process {{ throw 'D3.42 aparat: Remove beklenmiyor' }} }}
function Get-Service {{ [CmdletBinding()] param($Name) }}
function New-NetFirewallRule {{
    [CmdletBinding()] param([Parameter(ValueFromRemainingArguments=$true)]$Rest)
    Add-Content -LiteralPath {_ps_lit(log)} -Value "MOCK-NEW-CALLED" -Encoding UTF8
    {new_body}
}}
function Log($m, $c = 'White') {{ Add-Content -LiteralPath {_ps_lit(log)} -Value $m -Encoding UTF8 }}
# ── script'ten PARSER ile çekilen GERÇEK fonksiyon ──
{func}
$r = Ensure-PemfMosquittoFirewallRule
Write-Output ("RESULT=" + $r + " TYPE=" + $r.GetType().Name)
"""
    r = _pwsh_file(tmp_path, "run_fw.ps1", body)
    assert r.returncode == 0, f"fonksiyon kostururken pwsh dustu (rc={r.returncode}):\n{r.stdout}\n{r.stderr}"
    m = re.search(r"RESULT=(\S+) TYPE=(\S+)", r.stdout)
    assert m, f"RESULT satiri yok:\n{r.stdout}\n{r.stderr}"
    assert m.group(2) == "Boolean", (
        f"Ensure-PemfMosquittoFirewallRule [bool] DEGIL ({m.group(2)}) donuyor — "
        f"ozet/.install_verified 'mosqFirewall=' degeri anlamsizlasir; 'return [bool]...' yap."
    )
    return m.group(1), log.read_text(encoding="utf-8-sig")


# ─────────────────────────── (a) firewall fonksiyonu DAVRANIŞI ───────────────────────────
def test_firewall_kural_yaratilamaz_ve_yok_ise_False_ve_eylemli_UYARI(tmp_path):
    """MpsSvc durmuş senaryosu: New-NetFirewallRule hata verir, sorgu boş → False + UYARI (eylemli)."""
    result, log = _run_firewall_func(tmp_path, rule_exists=False, new_rule_fails=True)
    assert result == "False", (
        f"Kural YOK ve yaratilamadi ama fonksiyon {result} dondu — sessiz-basari GERI GELDI. "
        f"Her yolda Get-NetFirewallRule ile YENIDEN SORGULA ve [bool] dondur.\nLog:\n{log}"
    )
    assert "UYARI" in log and "PEMF Mosquitto MQTT" in log, (
        f"Kural yok ama Log'a 'UYARI' + 'PEMF Mosquitto MQTT' dusmedi — runhidden'da sifir kanit.\nLog:\n{log}"
    )
    # Eylem söylesin (house rule): neyi kontrol edeceği + elle komut
    assert "MpsSvc" in log and "New-NetFirewallRule" in log, (
        f"UYARI eylem SOYLEMIYOR: 'MpsSvc' kontrolu ve elle 'New-NetFirewallRule' komutu olmali.\nLog:\n{log}"
    )
    etiket = f"ESP bobin {_esp_bobin_numarasi()}"
    assert etiket in log, f"UYARI sonucu ({etiket} ulasamaz — live_state.ESP_COIL_IDS) soylemiyor.\nLog:\n{log}"
    # catch dalı GERÇEKTEN çalıştı mı? (-ErrorAction Stop yoksa Write-Error yutulur, bu satır düşmez)
    assert "Firewall kuralı oluşturulamadı" in log and "RPC server unavailable" in log, (
        f"New-NetFirewallRule hatasi catch'e DUSMEDI — '-ErrorAction Stop' eksik/try yok; hata akisa "
        f"gidip kayboluyor (eski ariza). Cagriya '-ErrorAction Stop' ekle, try/catch icine al.\nLog:\n{log}"
    )


def test_firewall_kural_zaten_varsa_True_UYARI_yok_ve_yeniden_yaratilmaz(tmp_path):
    """Karşı-kanıt: kural varsa True döner, UYARI düşmez, New-NetFirewallRule HİÇ çağrılmaz (idempotent)."""
    result, log = _run_firewall_func(tmp_path, rule_exists=True, new_rule_fails=True)
    assert result == "True", f"Kural VAR ama fonksiyon {result} dondu — sahte kirmizi.\nLog:\n{log}"
    assert "UYARI" not in log, f"Kural varken UYARI dusmemeli (sahte alarm).\nLog:\n{log}"
    assert "MOCK-NEW-CALLED" not in log, (
        f"Kural VARKEN New-NetFirewallRule yine cagrildi — idempotentlik bozuldu (cift kural).\nLog:\n{log}"
    )


def test_firewall_yaratma_basarili_ama_sorgu_bos_ise_yine_False(tmp_path):
    """Cmdlet sessiz geçse bile kural GERÇEKTEN yoksa (GPO) → False. Son-kontrol cmdlet'e güvenmez."""
    result, log = _run_firewall_func(tmp_path, rule_exists=False, new_rule_fails=False)
    assert result == "False", (
        f"New-NetFirewallRule 'basarili' gorundu ama Get-NetFirewallRule bos; fonksiyon {result} dondu — "
        f"son-kontrol cmdlet donusune GUVENIYOR. Donusu Get-NetFirewallRule sorgusundan al.\nLog:\n{log}"
    )
    assert "MOCK-NEW-CALLED" in log, "kural yokken New-NetFirewallRule cagrilmali (yaratma denenmedi)"
    assert "UYARI" in log and "kuralı YOK" in log, f"kural yok ama UYARI dusmedi.\nLog:\n{log}"


# ─────────────────────────── (b) Log fonksiyonu DAVRANIŞI ───────────────────────────
def test_Log_dosya_sinkine_ISO_damgali_yazar_ve_yazamasa_bile_firlatmaz(tmp_path):
    func = _extract_function(tmp_path, "Log")
    good_dir = tmp_path / "logs_ok"  # henüz YOK → Log kendi yaratmalı (satir 134'ten ÖNCE çağrılıyor)
    bad_parent = tmp_path / "bir_dosya.txt"  # dosya → altına dizin açılamaz → Add-Content patlar
    bad_parent.write_text("x", encoding="utf-8")
    bad_dir = bad_parent / "logs"
    body = f"""
$ErrorActionPreference = 'Continue'
{func}
$LogDir = {_ps_lit(good_dir)}
Log "merhaba-dunya-ölçüm" "Green"
$LogDir = {_ps_lit(bad_dir)}
Log "bu-yazilamaz" "Yellow"
Write-Output "AFTER-BAD-OK"
$LogDir = $null
# fallback yolunu GERÇEKTEN yazmak istemiyoruz (C:\\ProgramData); yalnizca firlatmadigini olc:
Write-Output ("FALLBACK-LOGDIR-EMPTY=" + [string]::IsNullOrEmpty($LogDir))
"""
    r = _pwsh_file(tmp_path, "run_log.ps1", body)
    assert r.returncode == 0, f"Log kosumu dustu (rc={r.returncode}):\n{r.stdout}\n{r.stderr}"
    logf = good_dir / "setup_services.log"
    assert logf.exists(), (
        f"Log DOSYA sink'ine yazmadi ({logf}) — runhidden'da her mesaj KAYBOLUR. "
        f"Log() icine Add-Content (Join-Path $LogDir 'setup_services.log') ekle; dizini kendi yaratsin."
    )
    txt = logf.read_text(encoding="utf-8-sig")
    assert "merhaba-dunya-ölçüm" in txt, f"mesaj dosyada yok (encoding UTF8 mi?):\n{txt}"
    assert re.search(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", txt, re.M), f"ISO zaman damgasi yok:\n{txt}"
    assert "AFTER-BAD-OK" in r.stdout, (
        f"Yazilamayan LogDir'de Log FIRLATTI ve script'i DURDURDU — kurulumu loglama dusuremez; "
        f"Add-Content'i try/catch {{ }} icine al.\nstdout={r.stdout}\nstderr={r.stderr}"
    )


# ─────────────────────────── (c) AST YAPISAL kapı ───────────────────────────
@pytest.fixture(scope="module")
def ast_rapor(tmp_path_factory) -> dict:
    """pwsh Parser ile: her New-NetFirewallRule çağrısının try-atası + -ErrorAction Stop durumu; Log'da Add-Content."""
    tmp = tmp_path_factory.mktemp("ast")
    out = tmp / "ast.json"
    body = f"""
using namespace System.Management.Automation.Language
$tokens = $null; $errors = $null
$ast = [Parser]::ParseFile({_ps_lit(PS1)}, [ref]$tokens, [ref]$errors)
$calls = $ast.FindAll({{ param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'New-NetFirewallRule' }}, $true)
$rows = foreach ($c in $calls) {{
    $inTry = $false; $p = $c.Parent
    while ($p) {{ if ($p -is [TryStatementAst]) {{ $inTry = $true; break }}; $p = $p.Parent }}
    $eaStop = $false
    for ($i = 0; $i -lt $c.CommandElements.Count; $i++) {{
        $e = $c.CommandElements[$i]
        if ($e -is [CommandParameterAst] -and $e.ParameterName -eq 'ErrorAction') {{
            $arg = if ($e.Argument) {{ $e.Argument }} elseif ($i + 1 -lt $c.CommandElements.Count) {{ $c.CommandElements[$i + 1] }} else {{ $null }}
            if ($arg -and $arg.Extent.Text.Trim("'`"") -eq 'Stop') {{ $eaStop = $true }}
        }}
    }}
    # Kapsayan fonksiyon adı (rapor için)
    $fn = $null; $p = $c.Parent
    while ($p) {{ if ($p -is [FunctionDefinitionAst]) {{ $fn = $p.Name; break }}; $p = $p.Parent }}
    [pscustomobject]@{{ line = $c.Extent.StartLineNumber; inTry = $inTry; eaStop = $eaStop; func = $fn }}
}}
$logFn = $ast.Find({{ param($n) $n -is [FunctionDefinitionAst] -and $n.Name -eq 'Log' }}, $true)
$logAddContent = $null -ne $logFn.Body.Find({{ param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'Add-Content' }}, $true)
$logAddInTry = $false
if ($logAddContent) {{
    $ac = $logFn.Body.Find({{ param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'Add-Content' }}, $true)
    $p = $ac.Parent; while ($p) {{ if ($p -is [TryStatementAst]) {{ $logAddInTry = $true; break }}; $p = $p.Parent }}
}}
$fwFn = $ast.Find({{ param($n) $n -is [FunctionDefinitionAst] -and $n.Name -eq 'Ensure-PemfMosquittoFirewallRule' }}, $true)
# .install_verified yazan Set-Content çağrısı 'mosqFirewall=' kanıtını taşıyor mu?
$sc = $ast.FindAll({{ param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'Set-Content' -and $n.Extent.Text -like '*.install_verified*' }}, $true)
$verifiedHasFw = ($sc | Where-Object {{ $_.Extent.Text -like '*mosqFirewall=*' }} | Measure-Object).Count -gt 0
$rep = [ordered]@{{
    parseErrors     = $errors.Count
    newRuleCalls    = @($rows)
    logHasAddContent = $logAddContent
    logAddInTry     = $logAddInTry
    fwFunctionExists = ($null -ne $fwFn)
    installVerifiedCalls = ($sc | Measure-Object).Count
    installVerifiedHasFw = $verifiedHasFw
}}
[System.IO.File]::WriteAllText({_ps_lit(out)}, ($rep | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
Write-Output "OK"
"""
    r = _pwsh_file(tmp, "ast_check.ps1", body)
    assert r.returncode == 0 and "OK" in r.stdout, f"AST analizi dustu:\n{r.stdout}\n{r.stderr}"
    return json.loads(out.read_text(encoding="utf-8"))


def test_ast_script_parse_edilir(ast_rapor):
    assert ast_rapor["parseErrors"] == 0, "setup_services.ps1 PARSE HATASI — installer kurulumda patlar"


def test_ast_her_New_NetFirewallRule_try_icinde_ve_ErrorAction_Stop(ast_rapor):
    calls = ast_rapor["newRuleCalls"]
    if isinstance(calls, dict):  # ConvertTo-Json tek elemanı nesneye düşürür
        calls = [calls]
    assert len(calls) >= 2, (
        f"setup_services.ps1'de en az 2 New-NetFirewallRule bekleniyor (Mosquitto + Backend/UDP); "
        f"{len(calls)} bulundu — cagri silinmis/yeniden adlandirilmis olabilir."
    )
    kotu = [c for c in calls if not (c["inTry"] and c["eaStop"])]
    assert not kotu, (
        "New-NetFirewallRule cagrilari try/catch DISINDA veya '-ErrorAction Stop'SUZ: "
        + "; ".join(f"satir {c['line']} (fn={c['func']}, inTry={c['inTry']}, eaStop={c['eaStop']})" for c in kotu)
        + " -> cmdlet hatasi hata-akisina duser ve kaybolur (MpsSvc kapaliyken sessiz basari). "
        "Her cagriyi try { ... -ErrorAction Stop | Out-Null } catch { Log 'UYARI: ...' } icine al."
    )
    mosq = [c for c in calls if c["func"] == "Ensure-PemfMosquittoFirewallRule"]
    assert len(mosq) == 1, (
        f"Mosquitto kuralini yaratan New-NetFirewallRule 'Ensure-PemfMosquittoFirewallRule' icinde olmali "
        f"(bulunan: {[c['func'] for c in calls]}) — testler fonksiyonu dot-source ederek olcer, inline'a donme."
    )


def test_ast_Log_govdesinde_try_icinde_Add_Content_var(ast_rapor):
    assert ast_rapor["logHasAddContent"], (
        "Log() gövdesinde Add-Content YOK → runhidden altinda tum kurulum mesajlari kaybolur. "
        "Add-Content (Join-Path $LogDir 'setup_services.log') -Encoding UTF8 ekle (try/catch icinde)."
    )
    assert ast_rapor["logAddInTry"], (
        "Log() icindeki Add-Content try/catch DISINDA — kilitli/yazilamaz log dizini KURULUMU dusurur. "
        "try { ... } catch { } icine al."
    )


def test_ast_install_verified_mosqFirewall_kanitini_tasir(ast_rapor):
    assert ast_rapor["installVerifiedCalls"] >= 1, ".install_verified yazan Set-Content bulunamadi"
    assert ast_rapor["installVerifiedHasFw"], (
        ".install_verified icerigine 'mosqFirewall=$MosqFirewallOk' eklenmemis — sahada firewall kaniti "
        "dosyadan okunamaz. Inno yalniz FileExists kontrol eder (icerik ayristirilmaz); 2. satir olarak ekle."
    )


def test_MosqFirewallOk_her_yolda_tanimli_ve_ozette_gorunur():
    """Server/staging modunda fonksiyon çağrılmaz → değişken yine de $false ile tanımlı olmalı; özet satırı var."""
    src = PS1.read_text(encoding="utf-8-sig")
    fn_pos = src.find("function Ensure-PemfMosquittoFirewallRule")
    call_pos = src.find("$MosqFirewallOk = Ensure-PemfMosquittoFirewallRule")
    init = re.search(r"^\$MosqFirewallOk\s*=\s*\$false", src, re.M)
    assert fn_pos > 0 and call_pos > fn_pos, "fonksiyon tanimi cagridan ONCE olmali (PowerShell sirali okur)"
    assert init and fn_pos < init.start() < call_pos, (
        "$MosqFirewallOk script kapsaminda $false ile ON-TANIMLI degil → server/staging modunda "
        "'mosqFirewall=' bos yazilir. Fonksiyon tanimindan sonra, cagridan once '$MosqFirewallOk = $false' koy."
    )
    assert "mosqFirewall=$MosqFirewallOk" in src, "ozet/bayrak 'mosqFirewall=$MosqFirewallOk' kanitini tasimiyor"


def test_ESP_bobin_etiketi_HER_yerde_topolojiden_D6_54():
    """D6.54 (B-10.195): operatör uyarıları, NSSM açıklaması ve yorumlar ESP bobin numarasını `live_state.ESP_COIL_IDS` ile AYNI söyler.

    Bobin 6-7 2026-09-10'da STM'e taşındı (ESP_COIL_IDS = {8}); betik 'ESP bobin 6-8' diyordu → operatör olmayan iki bobini arardı.
    Tek uyarı satırına bakan (a) kolu ikiz yerleri (NSSM açıklaması, özet uyarıları, hotspot hatırlatması) görmez → dosyanın TAMAMI taranır."""
    beklenen = _esp_bobin_numarasi()
    src = PS1.read_text(encoding="utf-8-sig")
    bulunan = [
        (src.count("\n", 0, m.start()) + 1, re.sub(r"[ \t]+", "", m.group(1))) for m in _ESP_NUMARA_RE.finditer(src)
    ]
    assert bulunan, (
        "setup_services.ps1'de 'ESP bobin <numara>' etiketi HİÇ bulunamadı — desen ya da betik değişti; operatör uyarısı "
        "hangi bobinin broker'a ulaşamadığını SÖYLEMELİ."
    )
    yanlis = [(satir, numara) for satir, numara in bulunan if numara != beklenen]
    assert not yanlis, (
        f"setup_services.ps1 ESP bobin numarası topolojiyle ÇELİŞİYOR (live_state.ESP_COIL_IDS → '{beklenen}'): "
        + "; ".join(f"satır {s}: '{n}'" for s, n in yanlis)
        + f" — 'ESP bobin {beklenen}' yaz."
    )
    # NSSM servis açıklaması (services.msc'de operatörün gördüğü) da aynı etiketi taşır.
    aciklama = re.search(r'\$ServiceMosq\s+Description\s+"([^"]*)"', src)
    assert aciklama and f"ESP bobin {beklenen}" in aciklama.group(1), (
        f"Mosquitto NSSM açıklaması 'ESP bobin {beklenen}' demiyor: {aciklama.group(1) if aciklama else 'BULUNAMADI'}"
    )
