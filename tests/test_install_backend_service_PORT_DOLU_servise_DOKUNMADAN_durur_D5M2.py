# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5 M-2 (H-1 kapsam dışı gözlemi · E2-2.4 / S-E.4 sınıfı) — `install_backend_service.ps1` (A-11'in ikinci kurulum yolu) servisin
dinleyeceği port BAŞKA bir süreç (launcher'ın backend çocuğu / başka kurulum) tarafından tutulurken kurulumu servise DOKUNMADAN durdurur.

ÖLÇÜLEN (HEAD d38b0db5): `setup_services.ps1` E2-2.4 ön denetimi (`Get-NetTCPConnection … -State Listen` sahibi bu kurulumun dışındaysa
"port dolu" + exit 1, hiçbir servis değiştirilmeden) bu betikte YOKTU: betik eski `PemfBackend` servisini `nssm stop/remove` ile kaldırıp
yenisini kuruyor, launcher backend'i portu tutarken yeni servis bind edemeyip NSSM döngüsünde çöküyor, betik yine "Backend servisi
kuruldu" diyordu (sağlık sondası da yok). Mobil / web istemci (ACİL DURDUR dahil) eski launcher backend'ine bağlı kalırken klinik servisi
çalışmıyor.
SÖZLEŞME: port = servise giden profil portu (`Get-PemfServisApiPortu $AppEnv`, D5 H-1 ile TEK kaynak); dinleyen süreçlerden HERHANGİ biri
değiştirilecek servisin süreç ağacı (nssm + çocukları, python ara başlatıcısı için 4 kuşağa dek) DEĞİLSE eylemli HATA (port · PID · yol ·
ne yapılacak) + `exit 1` — servis kaldırma / kurma / NSSM indirme / günlük dizini adımlarından ÖNCE. O süreç ÖLDÜRÜLMEZ, servis
DURDURULMAZ (ACİL DURDUR bu betiğin işi değil). setup_services.ps1 E2-2.4 ile EŞLİK ortak senaryolarda ölçülür; tek bilinçli fark (pinli):
kurulum dizininde elle başlatılmış (servis ağacı dışı) EXE — setup_services onu kendisi öldürür (Stop-PemfKurulumBackendi) ve sürer, bu
betik öldürmez → DURUR.
TUR 2 (çürütücü): iki dinleyen (kendi servisi 0.0.0.0 + launcher çocuğu 127.0.0.1, iki sırada) · 4 kuşak SÜRER / 5 kuşak DURUR (pencere) ·
install önekinde betikte TANIMLI `$AppDir` (dizin ölçütü gerilemesi görünür) · süreç / servis öldürme KAYITÇI gölgeleri + "öldürülmez /
durdurulmaz" iddiası HER koşuda · çekilen kod İZİN LİSTESİNE karşı denetlenir · "durdu ama çıkış kodu 0" davranış iletisi.
⛔ Gerçek ağ / süreç / servis sorgusu ya da işlemi YOK: `Get-NetTCPConnection` / `Get-CimInstance` (Win32_Process, Win32_Service) senaryo
tablosundan yanıt veren gölgelerdir; `Stop-Process` / `Stop-Service` / `taskkill` / `Stop-PemfKurulumBackendi` / `& $NssmExe` yalnız KAYIT
tutan gölgelerdir (Get-Command ile İŞLEV kanıtlı, modül otomatik yükleme KAPALI). Betikten yalnız denetim işlevi ve onu kullanan üst düzey
ifadeler (parser ile) koşar ve önce İZİN LİSTESİNE karşı denetlenir (listede olmayan komut / yöntem / değişkenle çağrı → koşmaz, KIRMIZI).
Fikstür PID'leri GERÇEK OLAMAZ: tek sayı (Windows PID'leri 4'ün katıdır) ve 2·10⁹ üstü; servis adı `…_SAHTE` — aparat düşse bile gerçek
bir sürece / servise denk gelmez.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import capraz
import pytest
from test_setup_services_firewall_kaniti import _ps_lit, _pwsh_file

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "install_backend_service.ps1"
SETUP = KOK / "scripts" / "setup_services.ps1"
FONK = "Get-PemfPortDisSahibi"
_PWSH = shutil.which("pwsh")

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="pwsh aparatı Windows betik anlamını ölçer"),
    pytest.mark.skipif((_PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) bulunamadı"),
]

PORT = 8010  # profil portu bilerek 8000 DEĞİL: sabit 8000 sorgusu bu kapıda görünür
APP = r"C:\PEMF\dist\PEMF_Backend"
EXE = APP + r"\PEMF_Backend.exe"
NSSM = r"C:\Program Files\PEMF\nssm\nssm.exe"
LAUNCHER = r"C:\Users\klinik\AppData\Local\PEMF Vet Client\PEMF Vet Client.exe"
LAUNCHER_COCUGU = r"C:\Users\klinik\AppData\Local\PEMF Vet Client\runtime\PEMF_Backend\PEMF_Backend.exe"
PYTHON_VENV = r"C:\PEMF\guii\.venv\Scripts\python.exe"
PYTHON_TABAN = r"C:\Python310\python.exe"
CMD = r"C:\Windows\System32\cmd.exe"

# Fikstür PID'leri: TEK sayı + 2·10⁹ üstü (Int32 içinde — betik `[int]` ile çevirir) → gerçek bir Windows süreci OLAMAZ.
P_KOK = 2_000_000_001  # launcher'ın ebeveyni
P_SCM = 2_000_000_641  # nssm'in ebeveyni (services.exe yerine)
P_EXPLORER = 2_000_000_077
P_LAUNCHER = 2_000_000_901
P_COCUK = 2_000_000_303  # launcher'ın backend çocuğu
P_NSSM = 2_000_000_501  # PemfBackend servisi = nssm
P_SERVIS = 2_000_000_503  # nssm → backend EXE
P_VENV = 2_000_000_511
P_TABAN = 2_000_000_513
P_BILINMEYEN = 2_000_004_243
P_ELLE = 2_000_000_777
P_KUSAK = (2_000_000_521, 2_000_000_523, 2_000_000_525, 2_000_000_527, 2_000_000_529)


def _senaryo(dinleyen=(), surec=(), servis=()) -> dict:
    return {
        "dinleyen": [{"port": p, "pid": i} for p, i in dinleyen],
        "surec": [{"pid": i, "ppid": pp, "yol": y} for i, pp, y in surec],
        "servis": [{"ad": a, "pid": i} for a, i in servis],
    }


def _kusak_zinciri(n: int) -> list[tuple]:
    """nssm → cmd → venv python → taban python … : dinleyen, nssm'in n. kuşak torunu (n ara süreç)."""
    yollar = [CMD, PYTHON_VENV, PYTHON_TABAN, PYTHON_TABAN, PYTHON_TABAN]
    zincir, ebeveyn = [], P_NSSM
    for i in range(n):
        zincir.append((P_KUSAK[i], ebeveyn, yollar[i]))
        ebeveyn = P_KUSAK[i]
    return zincir


# Ortak süreç tablosu: launcher → backend çocuğu; PemfBackend servisi = nssm → backend.
_SUREC = [
    (P_LAUNCHER, P_KOK, LAUNCHER),
    (P_COCUK, P_LAUNCHER, LAUNCHER_COCUGU),
    (P_NSSM, P_SCM, NSSM),
    (P_SERVIS, P_NSSM, EXE),
]
# Servis adı da GERÇEK OLAMAZ (betikte `PemfBackend`): gölge düşse bile bu makinedeki gerçek servise ulaşılmaz.
SERVIS_ADI = "PemfBackend_D5M2_SAHTE"
_SERVIS = [(SERVIS_ADI, P_NSSM)]
SENARYOLAR = {
    "launcher_cocugu": _senaryo([(PORT, P_COCUK)], _SUREC, _SERVIS),
    "bos": _senaryo([], _SUREC, _SERVIS),
    "kendi_servisi": _senaryo([(PORT, P_SERVIS)], _SUREC, _SERVIS),
    "bilinmeyen_sahip": _senaryo([(PORT, P_BILINMEYEN)], _SUREC, _SERVIS),
    "baska_portta_launcher": _senaryo([(8000, P_COCUK)], _SUREC, _SERVIS),
    # python geliştirme kurulumu: nssm → venv başlatıcısı → taban python dinler
    "kendi_servisi_python_iki_kusak": _senaryo(
        [(PORT, P_TABAN)], [*_SUREC[:3], (P_VENV, P_NSSM, PYTHON_VENV), (P_TABAN, P_VENV, PYTHON_TABAN)], _SERVIS
    ),
    # kuşak penceresi (4 kuşağa dek): dinleyen nssm'in 4. kuşak torunu → kendi; 5. kuşak → pencere dışı → dış sayılır
    "kendi_servisi_dort_kusak": _senaryo([(PORT, P_KUSAK[3])], [*_SUREC, *_kusak_zinciri(4)], _SERVIS),
    "bes_kusak_pencere_disi": _senaryo([(PORT, P_KUSAK[4])], [*_SUREC, *_kusak_zinciri(5)], _SERVIS),
    # kurulum dizininde ELLE başlatılmış EXE (servis ağacı dışı; ebeveyni explorer)
    "elle_baslatilmis_ayni_dizin": _senaryo([(PORT, P_ELLE)], [*_SUREC, (P_ELLE, P_EXPLORER, EXE)], _SERVIS),
    # servis kayıtlı ama durmuş (ProcessId 0) — portu launcher tutuyor
    "servis_durmus_launcher": _senaryo([(PORT, P_COCUK)], _SUREC, [(SERVIS_ADI, 0)]),
    # İKİ dinleyen (Windows daha özgül bağlamaya izin verir): kendi servisi 0.0.0.0, launcher çocuğu 127.0.0.1 — localhost istemciler
    # launcher'a gider (E2-2.4'ün asıl tehlikesi); sıra bağımsız DURUR
    "iki_dinleyen_kendi_once": _senaryo([(PORT, P_SERVIS), (PORT, P_COCUK)], _SUREC, _SERVIS),
    "iki_dinleyen_launcher_once": _senaryo([(PORT, P_COCUK), (PORT, P_SERVIS)], _SUREC, _SERVIS),
}


def _tum_pidler() -> set[int]:
    pidler = set()
    for s in SENARYOLAR.values():
        pidler |= {d["pid"] for d in s["dinleyen"]} | {p["pid"] for p in s["surec"]} | {p["ppid"] for p in s["surec"]}
        pidler |= {v["pid"] for v in s["servis"]}
    return pidler - {0}


def test_KARSIT_aparat_fikstur_PIDleri_GERCEK_olamaz():
    """Aparat düşse (gölge yüklenmese) bile öldürme / durdurma çağrısı gerçek bir sürece denk gelmesin."""
    gercekci = sorted(p for p in _tum_pidler() if p % 4 == 0 or p < 2_000_000_000 or p > 2**31 - 1)
    assert not gercekci, (
        f"fikstür PID'i gerçek bir Windows süreci olabilir (4'ün katı / 2·10⁹ altı / Int32 dışı): {gercekci}"
    )
    assert "SAHTE" in SERVIS_ADI, f"fikstür servis adı gerçek bir servise denk gelebilir: {SERVIS_ADI}"


# Süreç / servis öldürme ve NSSM çağrısı KAYITÇI gölgelerdir (`$NssmExe` gölge işlevin adı). Bu kapı hiçbir senaryoda bu olayları beklemez.
_SURUCU = r"""
Import-Module Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility
$PSModuleAutoLoadingPreference = 'None'
$Olay = @@OLAY@@
function _Olay($m) { Add-Content -LiteralPath $Olay -Value $m -Encoding UTF8 }
$Senaryo = Get-Content -LiteralPath @@SENARYO@@ -Raw | ConvertFrom-Json
function Get-NetTCPConnection { [CmdletBinding()] param($LocalPort, $State)
    _Olay ("PORT-SORGU " + $LocalPort + " " + $State)
    foreach ($b in @($Senaryo.dinleyen)) {
        if ($b -and [int]$b.port -eq [int]$LocalPort -and "$State" -eq 'Listen') { [pscustomobject]@{ LocalPort = [int]$b.port; State = 'Listen'; OwningProcess = [int]$b.pid } } } }
function Get-CimInstance { [CmdletBinding()] param([Parameter(Position = 0)]$ClassName, $Filter)
    if ($ClassName -eq 'Win32_Process') {
        foreach ($p in @($Senaryo.surec)) { if ($p) { [pscustomobject]@{ ProcessId = [int]$p.pid; ParentProcessId = [int]$p.ppid; ExecutablePath = $p.yol } } }
    } elseif ($ClassName -eq 'Win32_Service') {
        foreach ($s in @($Senaryo.servis)) { if ($s -and "$Filter" -match "Name\s*=\s*'([^']+)'" -and $Matches[1] -eq $s.ad) { [pscustomobject]@{ Name = $s.ad; ProcessId = [int]$s.pid } } }
    } else { _Olay "BEKLENMEYEN-SINIF $ClassName"; exit 98 } }
function Stop-Process { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject, [Parameter(Position = 0)]$Id, $Name, [switch]$Force, [switch]$PassThru)
    process { _Olay ("OLDUR Stop-Process " + "$Id$Name" + $(if ($InputObject) { " " + $InputObject.Id })) } }
function Stop-Service { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject, [Parameter(Position = 0)]$Name, [switch]$Force, [switch]$NoWait)
    process { _Olay ("DURDUR Stop-Service " + "$Name" + $(if ($InputObject) { " " + $InputObject.Name })) } }
function taskkill { _Olay ("OLDUR taskkill " + ($args -join ' ')) }
function Stop-PemfKurulumBackendi { _Olay ("OLDUR Stop-PemfKurulumBackendi " + ($args -join ' ')) }
function nssm-golge { _Olay ("NSSM " + ($args -join ' ')) }
$NssmExe = 'nssm-golge'
function Write-Status($m, $c = 'White') { _Olay ("LOG " + $m) }
function Log($m, $c = 'White') { _Olay ("LOG " + $m) }
function Write-Host { param([Parameter(Position = 0)]$Object, $ForegroundColor, [switch]$NoNewline) _Olay ("HOST " + $Object) }
function pause { _Olay 'PAUSE' }
foreach ($g in 'Get-NetTCPConnection', 'Get-CimInstance', 'Stop-Process', 'Stop-Service', 'taskkill', 'Stop-PemfKurulumBackendi', 'nssm-golge',
        'Write-Status', 'Log', 'Write-Host', 'pause') {
    if ((Get-Command $g).CommandType -ne 'Function') { _Olay "GOLGE-YOK $g"; exit 99 } }
$ErrorActionPreference = @@EAP@@
@@KOD@@
_Olay 'DEVAM'
exit 0
"""

# Çekilen koda izin verilen komutlar: sorgu gölgeleri, günlükçüler, saf boru komutları, denetim işlevi ve KAYITÇI öldürme gölgeleri
# (izin verilir ki öldürme girişimi davranış iddiasında "öldürüldü" diye görünsün). Değişkenle çağrı yalnız `& $NssmExe` (gölge adı).
IZINLI_KOMUT = (
    "Get-NetTCPConnection",
    "Get-CimInstance",
    "Select-Object",
    "Where-Object",
    "Write-Status",
    "Log",
    "Write-Host",
    "pause",
    FONK,
    "Stop-Process",
    "Stop-Service",
    "taskkill",
    "Stop-PemfKurulumBackendi",
)

# Betikten: denetim işlevi (varsa) + onu çağıran / sonucunu kullanan üst düzey ifadeler (install) ya da E2-2.4 dilimi (setup_services).
_CEK = r"""
using namespace System.Management.Automation.Language
$t = $null; $h = $null
$ast = [Parser]::ParseFile(@@BETIK@@, [ref]$t, [ref]$h)
if ($h.Count) { Write-Output "PARSE-ERROR"; exit 3 }
$ust = @($ast.EndBlock.Statements)
$parca = [System.Collections.Generic.List[string]]::new()
$sec = @()
if (@@KIP@@ -eq 'install') {
    $sec += @($ust | Where-Object { $_ -is [FunctionDefinitionAst] -and $_.Name -eq @@FONK@@ })
    $sec += @($ust | Where-Object { $_ -isnot [FunctionDefinitionAst] -and $_.Find({ param($n)
        ($n -is [CommandAst] -and $n.GetCommandName() -eq @@FONK@@) -or ($n -is [VariableExpressionAst] -and $n.VariablePath.UserPath -eq 'PortunDisSahibi') }, $true) })
} else {
    $sec += @($ust | Where-Object { $_.Extent.Text -match '^\$OnSondaPort\s*=' -or ($_ -is [ForEachStatementAst] -and $_.Variable.VariablePath.UserPath -eq 'PortSahibi') })
}
if (-not $sec.Count) { Write-Output "IFADE-YOK"; exit 4 }
$izinli = @@IZINLI@@
foreach ($s in $sec) {
    foreach ($c in @($s.FindAll({ param($n) $n -is [CommandAst] }, $true))) {
        $ad = "$($c.GetCommandName())"
        $nssm = (-not $ad) -and $c.InvocationOperator -eq 'Ampersand' -and $c.CommandElements[0] -is [VariableExpressionAst] -and
            $c.CommandElements[0].VariablePath.UserPath -eq 'NssmExe'
        if (-not $nssm -and $izinli -notcontains $ad) { Write-Output ("IZIN-DISI komut: " + $c.Extent.Text); exit 5 }
    }
    foreach ($y in @($s.FindAll({ param($n) $n -is [InvokeMemberExpressionAst] }, $true))) { Write-Output ("IZIN-DISI yontem: " + $y.Extent.Text); exit 5 }
    foreach ($a in @($s.FindAll({ param($n) $n -is [AssignmentStatementAst] -and $n.Left.Extent.Text -match '^\$NssmExe$' }, $true))) {
        Write-Output ("IZIN-DISI atama: " + $a.Extent.Text); exit 5 }
    $parca.Add($s.Extent.Text)
}
[System.IO.File]::WriteAllText(@@CIKTI@@, ($parca -join "`n"), [System.Text.UTF8Encoding]::new($false))
Write-Output ("OK " + $sec.Count)
"""


def _cek(tmp_path: Path, kip: str) -> str:
    cikti = tmp_path / f"cek_{kip}.txt"
    betik = BETIK if kip == "install" else SETUP
    govde = (
        _CEK.replace("@@BETIK@@", _ps_lit(betik))
        .replace("@@KIP@@", _ps_lit(kip))
        .replace("@@FONK@@", _ps_lit(FONK))
        .replace("@@IZINLI@@", "@(" + ", ".join(_ps_lit(k) for k in IZINLI_KOMUT) + ")")
        .replace("@@CIKTI@@", _ps_lit(cikti))
    )
    r = _pwsh_file(tmp_path, f"cek_{kip}.ps1", govde)
    izin_disi = [s for s in r.stdout.splitlines() if s.startswith("IZIN-DISI")]
    assert not izin_disi, (
        f"{betik.name}: port-dolu denetimi izin listesi DIŞINDA {izin_disi[0][len('IZIN-DISI ') :]} çağırıyor — denetim yalnız SORGU + "
        "HATA + exit yapmalı (süreç / servis / NSSM işlemi yok); aparat onu GERÇEKTEN koşardı, kod KOŞTURULMADI."
    )
    assert r.returncode == 0 and r.stdout.startswith("OK"), (
        f"{betik.name}: port-dolu denetimi parser ile bulunamadı ({kip}; rc={r.returncode}):\n{r.stdout}\n{r.stderr}"
    )
    return cikti.read_text(encoding="utf-8")


def kos(tmp_path: Path, kip: str, senaryo: str, port: int = PORT) -> tuple[int, list[str]]:
    """`kip` = install (install_backend_service.ps1) | setup (setup_services.ps1 E2-2.4) → (çıkış kodu, olaylar).
    HER koşuda: süreç / servis öldürülmez · durdurulmaz · NSSM çağrılmaz; durursa çıkış kodu 0 OLMAZ."""
    d = tmp_path / f"{kip}_{senaryo}"
    d.mkdir()
    olay, sen = d / "olay.txt", d / "senaryo.json"
    olay.write_text("", encoding="utf-8")
    sen.write_text(json.dumps(SENARYOLAR[senaryo]), encoding="utf-8")
    if kip == "install":
        # betiğin kendi tercihi (EAP Stop) + betikte TANIMLI değişkenler: $ApiPort (M-2 ataması), $ServiceName, $AppDir (frozen EXE dizini)
        on, eap = f"$ApiPort = {port}\n$ServiceName = {_ps_lit(SERVIS_ADI)}\n$AppDir = {_ps_lit(APP)}\n", "'Stop'"
    else:
        on, eap = f"$AppDir = {_ps_lit(APP)}\n$OnPort = [pscustomobject]@{{ Port = {port} }}\n", "'Continue'"
    govde = (
        _SURUCU.replace("@@OLAY@@", _ps_lit(olay))
        .replace("@@SENARYO@@", _ps_lit(sen))
        .replace("@@EAP@@", eap)
        .replace("@@KOD@@", on + _cek(d, kip))
    )
    r = _pwsh_file(d, "surucu.ps1", govde)
    satir = [s for s in olay.read_text(encoding="utf-8-sig").splitlines() if s.strip()]
    assert r.returncode in (0, 1), (
        f"sürücü düştü (rc={r.returncode}; 99 gölge yok, 98 beklenmeyen sınıf):\n{satir}\n{r.stdout}\n{r.stderr}"
    )
    islem = [s for s in satir if s.startswith(("OLDUR ", "DURDUR ", "NSSM "))]
    assert not islem, (
        f"[{kip}/{senaryo}] port-dolu denetimi süreç / servis ÖLDÜRDÜ / DURDURDU ya da NSSM çağırdı — portu tutan süreç ÖLDÜRÜLMEZ "
        f"(ACİL DURDUR bu betiğin işi değil), servis durmadan önce DEĞİŞTİRİLMEZ: {islem}\n{satir}"
    )
    durdu = "DEVAM" not in satir
    assert not (durdu and r.returncode == 0), (
        f"[{kip}/{senaryo}] kurulum DURDU (sonraki adımlara geçmedi) ama çıkış kodu 0 — çağıran (Inno / operatör) kurulumu BAŞARILI sanar:\n{satir}"
    )
    assert durdu or r.returncode == 0, f"aparat: DEVAM'a ulaşıldı ama çıkış kodu {r.returncode}:\n{satir}"
    return r.returncode, satir


def _hata(satir: list[str]) -> list[str]:
    return [s for s in satir if s.startswith("LOG HATA")]


# ── install_backend_service.ps1 davranışı ────────────────────────────────────────────────────────────────────────────
def test_KRITIK_launcher_cocugu_portu_tutarken_kurulum_DURUR_eylemli_HATA(tmp_path):
    rc, satir = kos(tmp_path, "install", "launcher_cocugu")
    assert rc == 1, (
        f"launcher'ın backend çocuğu {PORT}'u tutarken kurulum DURMADI (servis bind edemeyip döngüde çöker):\n{satir}"
    )
    hata = _hata(satir)
    assert [
        s
        for s in hata
        if "dolu" in s and str(PORT) in s and str(P_COCUK) in s and LAUNCHER_COCUGU in s and "PEMF_API_PORT" in s
    ], f"HATA eylem söylemiyor (port · PID · yol · ne yapılacak):\n{satir}"
    assert f"PORT-SORGU {PORT} Listen" in satir, f"profil portu ({PORT}) sorgulanmadı:\n{satir}"
    assert "PAUSE" in satir, f"operatör HATA'yı göremeden pencere kapanır (pause yok):\n{satir}"


def test_KRITIK_kurulum_dizininde_ELLE_baslatilmis_EXE_de_DURDURUR_bilincli_fark(tmp_path):
    """Bu betik eski servisi `nssm stop/remove` ile durdurur, kurulum dizinindeki süreçleri ÖLDÜRMEZ → servis ağacı dışındaki EXE portu
    tutmaya devam eder; dizin ölçütü (setup_services) burada sessiz çöküşü geri getirirdi. Önekte `$AppDir` betikteki gibi TANIMLI —
    dizin ölçütü geri gelirse (`$SahipYolu -like "$AppDir\\*"`) bu kol KIRMIZI olur."""
    rc, satir = kos(tmp_path, "install", "elle_baslatilmis_ayni_dizin")
    assert rc == 1 and [s for s in _hata(satir) if str(P_ELLE) in s and EXE in s], (
        f"kurulum dizinindeki servis ağacı DIŞI süreç 'kendi' sayıldı (dizin ölçütü?) — servis bind edemeyip döngüde çöker:\n{satir}"
    )


def test_KRITIK_bilinmeyen_sahip_ve_DURMUS_servis_kendi_SAYILMAZ(tmp_path):
    for senaryo in ("bilinmeyen_sahip", "servis_durmus_launcher"):
        rc, satir = kos(tmp_path, "install", senaryo)
        assert rc == 1 and _hata(satir), f"[{senaryo}] portu dışarıdan tutan süreç varken kurulum sürdü:\n{satir}"


@pytest.mark.parametrize("senaryo", ["iki_dinleyen_kendi_once", "iki_dinleyen_launcher_once"])
def test_KRITIK_IKI_dinleyenden_biri_DIS_ise_sira_bagimsiz_DURUR(tmp_path, senaryo):
    """Çürütücü y1 (some ↔ every): kendi servisi 0.0.0.0'da, launcher çocuğu 127.0.0.1'de aynı portu dinleyebilir — localhost istemciler
    launcher'a gider. Bir dinleyenin 'kendi' olması ötekini AKLAMAZ."""
    rc, satir = kos(tmp_path, "install", senaryo)
    assert rc == 1, (
        f"[{senaryo}] kendi servisinin yanında launcher çocuğu da dinlerken kurulum sürdü (dış dinleyen aklandı):\n{satir}"
    )
    assert [s for s in _hata(satir) if str(P_COCUK) in s and LAUNCHER_COCUGU in s], (
        f"[{senaryo}] kurulum durdu ama HATA dış dinleyeni (launcher çocuğu PID {P_COCUK} / yol) söylemiyor — kendi servisini 'dış' mı saydı?\n"
        f"{satir}"
    )


def test_KARSIT_port_BOS_ise_kurulum_surer(tmp_path):
    rc, satir = kos(tmp_path, "install", "bos")
    assert rc == 0 and not _hata(satir) and "PAUSE" not in satir, satir


@pytest.mark.parametrize("senaryo", ["kendi_servisi", "kendi_servisi_python_iki_kusak", "kendi_servisi_dort_kusak"])
def test_KARSIT_portu_DEGISTIRILECEK_servisin_kendisi_tutuyorsa_surer(tmp_path, senaryo):
    """Kuşak penceresi 4: nssm → cmd → venv → taban python → dinleyen (çürütücü y2: pencere 2'ye inerse python kipi engellenir)."""
    rc, satir = kos(tmp_path, "install", senaryo)
    assert rc == 0 and not _hata(satir), (
        f"[{senaryo}] portu bu betiğin durdurup yeniden kuracağı PemfBackend servisi tutuyor — yeniden kurulum ENGELLENDİ:\n{satir}"
    )


def test_KRITIK_kusak_penceresi_SINIRLI_5_kusak_DIS_sayilir(tmp_path):
    """Pencere üst sınırı (sınırsız ata yürüyüşü PID yeniden kullanımı döngüsünde bitmez / ilgisiz süreci 'kendi' sayar)."""
    rc, satir = kos(tmp_path, "install", "bes_kusak_pencere_disi")
    assert rc == 1 and [s for s in _hata(satir) if str(P_KUSAK[4]) in s], (
        f"nssm'in 5. kuşak torunu 'kendi' sayıldı — kuşak penceresi 4'ten geniş:\n{satir}"
    )


def test_KARSIT_launcher_BASKA_portta_ise_surer(tmp_path):
    rc, satir = kos(tmp_path, "install", "baska_portta_launcher")
    assert rc == 0 and not _hata(satir), (
        f"launcher 8000'de, servis {PORT}'da dinleyecek — çakışma yok ama kurulum durdu:\n{satir}"
    )


# ── Eşlik: setup_services.ps1 E2-2.4 ile ortak senaryolarda AYNI karar ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("senaryo", "durur"),
    [
        ("launcher_cocugu", True),
        ("bos", False),
        ("kendi_servisi", False),
        ("bilinmeyen_sahip", True),
        ("baska_portta_launcher", False),
        ("iki_dinleyen_kendi_once", True),
        ("iki_dinleyen_launcher_once", True),
    ],
)
def test_KRITIK_ESLIK_setup_services_E2_2_4_ile_AYNI_karar(tmp_path, senaryo, durur):
    sonuc = {kip: kos(tmp_path, kip, senaryo)[0] for kip in ("install", "setup")}
    assert sonuc == {"install": int(durur), "setup": int(durur)}, (
        f"[{senaryo}] iki kurulum yolu port-dolu kararında AYRIŞTI (beklenen {'DUR' if durur else 'SÜR'}): {sonuc}"
    )


def test_KARSIT_ESLIK_bilincli_fark_ELLE_baslatilmis_EXE_setup_services_surer(tmp_path):
    """Fark pinli: setup_services kurulum dizinindeki süreçleri kendisi öldürür (Stop-PemfKurulumBackendi) → sürer; install DURUR."""
    assert kos(tmp_path, "setup", "elle_baslatilmis_ayni_dizin")[0] == 0
    assert kos(tmp_path, "install", "elle_baslatilmis_ayni_dizin")[0] == 1


# ── Betik bağlantısı (AST): port tek kaynaktan, denetim servise dokunan HER adımdan ÖNCE ─────────────────────────────────
_AST = r"""
using namespace System.Management.Automation.Language
$t = $null; $h = $null
$ast = [Parser]::ParseFile(@@BETIK@@, [ref]$t, [ref]$h)
$ust = @($ast.EndBlock.Statements)
function _Ilk([scriptblock]$k) { for ($i = 0; $i -lt $ust.Count; $i++) { if ($ust[$i] -isnot [FunctionDefinitionAst] -and $ust[$i].Find($k, $true)) { return $i } }; -1 }
$dur = -1
for ($i = 0; $i -lt $ust.Count; $i++) {
    $x = $ust[$i]
    if ($dur -lt 0 -and $x -is [IfStatementAst] -and $x.Clauses[0].Item1.Find({ param($n) $n -is [VariableExpressionAst] -and $n.VariablePath.UserPath -eq 'PortunDisSahibi' }, $true) -and
        $x.Find({ param($n) $n -is [ExitStatementAst] }, $true)) { $dur = $i }
}
$cagri = @($ast.FindAll({ param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq @@FONK@@ }, $true) | Where-Object {
    $p = $_.Parent; $ic = $false; while ($p) { if ($p -is [FunctionDefinitionAst]) { $ic = $true; break }; $p = $p.Parent }; -not $ic })
$portArg = ''
if ($cagri.Count -eq 1) {
    $e = $cagri[0].CommandElements
    for ($j = 0; $j -lt $e.Count; $j++) { if ($e[$j] -is [CommandParameterAst] -and $e[$j].ParameterName -eq 'Port' -and $j + 1 -lt $e.Count -and $e[$j + 1] -is [VariableExpressionAst]) { $portArg = $e[$j + 1].VariablePath.UserPath } }
}
$tanim = -1
for ($i = 0; $i -lt $ust.Count; $i++) { if ($tanim -lt 0 -and $ust[$i] -is [FunctionDefinitionAst] -and $ust[$i].Name -eq @@FONK@@) { $tanim = $i } }
$portAtama = _Ilk { param($n) $n -is [AssignmentStatementAst] -and $n.Left.Extent.Text -eq '$ApiPort' -and $n.Right.Extent.Text -match '^Get-PemfServisApiPortu\s+\$AppEnv$' }
[pscustomobject]@{
    hata = @($h | ForEach-Object { $_.Message }); dur = $dur; cagri = $cagri.Count; port_arg = $portArg; port_atama = $portAtama; tanim = $tanim
    cagri_ifadesi = (_Ilk { param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq @@FONK@@ })
    profil = (_Ilk { param($n) $n -is [IfStatementAst] -and $n.Clauses[0].Item1.Extent.Text -match '^-not \$AppEnv$' })
    nssm = (_Ilk { param($n) $n -is [CommandAst] -and $n.Extent.Text -match '^&\s*\$NssmExe\s+(stop|remove|install)' })
    indirme = (_Ilk { param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'Invoke-WebRequest' })
    gunluk = (_Ilk { param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'New-Item' -and $n.Extent.Text -match '\$LogDir' })
} | ConvertTo-Json -Compress
"""


def test_KRITIK_denetim_profil_PORTUYLA_ve_servise_DOKUNAN_her_adimdan_ONCE(tmp_path):
    r = _pwsh_file(tmp_path, "ast.ps1", _AST.replace("@@BETIK@@", _ps_lit(BETIK)).replace("@@FONK@@", _ps_lit(FONK)))
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    a = json.loads(r.stdout.strip().splitlines()[-1])
    assert not a["hata"], a
    assert a["dur"] >= 0 and a["cagri"] == 1, f"port-dolu denetimi ({FONK} + exit'li if) betikte yok / birden çok: {a}"
    assert a["port_arg"] == "ApiPort" and 0 <= a["port_atama"] < a["dur"], (
        f"denetim servisin profil portunu (Get-PemfServisApiPortu $AppEnv → $ApiPort) sorgulamıyor: {a}"
    )
    assert 0 <= a["tanim"] < a["cagri_ifadesi"], (
        f"{FONK} tanımı ilk çağrısından SONRA — betik sırayla koşar, çağrı anında işlev YOK: {a}"
    )
    assert 0 <= a["profil"] < a["dur"], f"denetim profil (D2.73) korumasından ÖNCE — port profilden okunamaz: {a}"
    for adim in ("nssm", "indirme", "gunluk"):
        assert 0 <= a["dur"] < a[adim], (
            f"port-dolu denetimi '{adim}' adımından SONRA (ya da adım bulunamadı) — servis değiştirildikten sonra durmak yarım kurulum bırakır: {a}"
        )
