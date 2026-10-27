# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5 M-3 (Y44 — sahip kararı; H-1 [SAHİBE] (1), orkestratör: ÖNERİLEN UYGULANDI) — `install_backend_service.ps1` (A-11'in ikinci
kurulum yolu) profildeki bozuk `PEMF_API_PORT`'ta kurulumu servise / NSSM'e / günlük dizinine DOKUNMADAN, eylemli HATA ile durdurur.

ÖLÇÜLEN (HEAD d38b0db5, M-3 ölçümü + çürütücü iki yöntemle): betikte `PEMF_API_PORT`'a bağlı `exit`li üst düzey ifade YOKTU; bozuk değer
yalnız güvenlik duvarı adımında (servis kaldırılıp yeniden KURULDUKTAN sonra) `Get-PemfServisApiPortu` ile "8000 + UYARI"ya çevriliyordu →
servis bozuk değerle kuruluyor, backend çalışma anında uyarıyla 8000'e düşüyor, profil niyeti sessizce aşılıyordu (setup_services.ps1 Y44
aynı durumda servis adımlarına BAŞLAMADAN durur). M-2 port-dolu denetimi de bozuk değerde 8000'i sorup asıl nedeni söylemeden "8000 dolu"
diyebilirdi.
SÖZLEŞME: D2.73 profil korumasından hemen SONRA, M-2 port-dolu denetiminden, `$ApiPort` atamasından ve HER NSSM / indirme / günlük dizini
adımından ÖNCE; profil `PEMF_API_PORT` satırı `Test-PemfApiPortDegeri` (Python `int()` + 1..65535) ile denetlenir; bozuksa
`HATA: <neden + eylem> Dosya: <profil> — kurulum DURDU, hiçbir servis değiştirilmedi.` + `pause` + `exit 1` (setup_services.ps1 Y44 ile
AYNI karar ve AYNI metin — eşlik bu dosyada ölçülür). Satır yoksa / geçerliyse kurulum sürer. Çalışma anındaki uyarılı 8000'e düşüş
(ACİL DURDUR ucu) AYNEN kalır.
TUR 3 (çürütücü 2): sürücü betiğin `-Mode` parametresini TANIMLAR ve Y44 iki kipte (device / server) ölçülür — kip koşullu koruma (q2 / q2b)
görünür; değer listesinde çok `_`li geçerli yazım (`8_0_10` = 8010, Python `int()`) SÜRER, çift `_` (`8__010`) DURUR (q4).
TUR 3b (çürütücü 3): Y44 profil ARAMASIYLA (kip → `deploy\\<Mode>.env`) her kipte koşar — setup device / server / staging, install device /
server; yalnız o kipin profili bozukken DURUR ve HATA o dosyayı söyler, başka kipin bozuk profili DURDURMAZ (q2c / q2d) · install AST: Y44
`if` koşulu ve okuduğu dosya servis ortamının profil değişkeni · izin denetimi dosyaya yönlendirmeyi ve sürücü nitelikli değişkeni de reddeder.
⛔ Betik GERÇEKTEN koşmaz: yalnız `Test-PemfApiPortDegeri` + `Read-PemfProfilEnv` tanımları ve Y44 üst düzey ifadesi parser ile çekilir,
koşturulmadan ÖNCE izin listesine karşı denetlenir (dışında komut / yöntem → koşmaz, KIRMIZI); `Write-Status` / `Log` / `Write-Host` /
`pause` kayıtçı gölgedir (Get-Command ile İŞLEV kanıtlı, modül otomatik yükleme KAPALI). Profil dosyası test geçici dizinindedir.
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
_PWSH = shutil.which("pwsh")

# D5 M-3 TUR 3: ham `skipif` yerine ZORUNLU'ya bağlı atlama (yayın makinesinde Windows + pwsh yoksa DÜŞER).
if sys.platform != "win32":
    capraz.atla("pwsh aparatı Windows betik anlamını ölçer")
if _PWSH is None:
    capraz.atla("pwsh (PowerShell 7) bulunamadı")

# Backend `int()` anlamında geçerli / geçersiz yazımlar (değer profil satırına `PEMF_API_PORT=<değer>` olarak yazılır; satır kırpılır).
DEGERLER = [
    "8010",
    "+8010",
    "08000",
    "8_010",
    "8_0_10",
    "8__010",
    "٨٠١٠",
    "1",
    "65535",
    "0",
    "65536",
    "-1",
    "80O0",
    "",
    "sekizbin",
    "1_",
    "8010.0",
    "1e3",
]
IZINLI_KOMUT = (
    "Read-PemfProfilEnv",
    "Test-PemfApiPortDegeri",
    "Get-Content",
    "Write-Status",
    "Log",
    "Write-Host",
    "pause",
)
IZINLI_UYE = ("Contains", "Trim", "StartsWith", "Split", "Match", "ToCharArray", "GetNumericValue")

# İzin denetimi (D5 M-3 TUR 3b): komut · yöntem · dosyaya yönlendirme (yalnız `$null` hedefi serbest) · sürücü nitelikli değişken (yalnız
# `env:` serbest) — D5 H-1 `_IzinDisi` ile AYNI sınıf (çürütücü 3 n7r / n7v / a1r / a1v: yük komutsuz / yöntemsiz GERÇEK diske yazıyordu).
# Bu dosya başka test modülünü içe aktarmaz; denetim burada kendi kopyasıyla durur.
_IZIN_PS = r"""
function _IzinDisiY44($Dugum, [string[]]$Komut, [string[]]$Uye) {
    foreach ($c in @($Dugum.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true))) {
        if ($Komut -notcontains "$($c.GetCommandName())") { return ("komut: " + $c.Extent.Text) } }
    foreach ($y in @($Dugum.FindAll({ param($n) $n -is [System.Management.Automation.Language.InvokeMemberExpressionAst] }, $true))) {
        if ($Uye -notcontains "$($y.Member.Extent.Text)") { return ("yontem: " + $y.Extent.Text) } }
    foreach ($r in @($Dugum.FindAll({ param($n) $n -is [System.Management.Automation.Language.FileRedirectionAst] }, $true))) {
        if (-not ($r.Location -is [System.Management.Automation.Language.VariableExpressionAst] -and $r.Location.VariablePath.UserPath -eq 'null')) {
            return ("yonlendirme: " + $r.Extent.Text) } }
    foreach ($v in @($Dugum.FindAll({ param($n) $n -is [System.Management.Automation.Language.VariableExpressionAst] -and
            $n.VariablePath.IsDriveQualified -and $n.VariablePath.DriveName -ne 'env' }, $true))) {
        return ("surucu nitelikli degisken: " + $v.Extent.Text) }
    $null
}
"""

_SURUCU = r"""
Import-Module Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility
$PSModuleAutoLoadingPreference = 'None'
$Olay = @@OLAY@@
function _Olay($m) { Add-Content -LiteralPath $Olay -Value $m -Encoding UTF8 }
function Write-Status($m, $c = 'White') { _Olay ("LOG " + $m) }
function Log($m, $c = 'White') { _Olay ("LOG " + $m) }
function Write-Host { param([Parameter(Position = 0)]$Object, $ForegroundColor, [switch]$NoNewline) _Olay ("HOST " + $Object) }
function pause { _Olay 'PAUSE' }
foreach ($g in 'Write-Status', 'Log', 'Write-Host', 'pause') { if ((Get-Command $g).CommandType -ne 'Function') { _Olay "GOLGE-YOK $g"; exit 99 } }
$ErrorActionPreference = @@EAP@@
@@KOD@@
_Olay 'DEVAM'
exit 0
"""

# Betikten: iki tanım + `Test-PemfApiPortDegeri`yi çağıran İLK üst düzey ifade (Y44 ön doğrulaması — `exit` içerip içermediği AST kolunda
# ölçülür; burada şart koşulmaz ki `exit`siz gerileme davranış kolunda "DURMADI" diye görünsün). İzin listesi denetimi.
_CEK = r"""
using namespace System.Management.Automation.Language
@@IZIN_PS@@
$t = $null; $h = $null
$ast = [Parser]::ParseFile(@@BETIK@@, [ref]$t, [ref]$h)
if ($h.Count) { Write-Output "PARSE-ERROR"; exit 3 }
$ust = @($ast.EndBlock.Statements)
$tanim = @($ust | Where-Object { $_ -is [FunctionDefinitionAst] -and @('Test-PemfApiPortDegeri', 'Read-PemfProfilEnv') -contains $_.Name })
$y44 = @($ust | Where-Object { $_ -isnot [FunctionDefinitionAst] -and
    $_.Find({ param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'Test-PemfApiPortDegeri' }, $true) } | Select-Object -First 1)
if ($tanim.Count -ne 2 -or $y44.Count -ne 1) { Write-Output "Y44-YOK tanim=$($tanim.Count) ifade=$($y44.Count)"; exit 4 }
foreach ($s in @($tanim) + @($y44)) { $ihlal = _IzinDisiY44 $s @@IZINLI@@ @@UYE@@; if ($ihlal) { Write-Output ("IZIN-DISI " + $ihlal); exit 5 } }
[System.IO.File]::WriteAllText(@@CIKTI@@, ((@($tanim) + @($y44) | ForEach-Object { $_.Extent.Text }) -join "`n"), [System.Text.UTF8Encoding]::new($false))
Write-Output "OK"
"""


def _ps_dizi(ogeler) -> str:
    return "@(" + ", ".join(_ps_lit(k) for k in ogeler) + ")"


def _izin_disi_denetle(betik: Path, ne: str, stdout: str) -> None:
    izin_disi = [s for s in stdout.splitlines() if s.startswith("IZIN-DISI")]
    assert not izin_disi, (
        f"{betik.name}: {ne} izin listesi DIŞINDA {izin_disi[0][len('IZIN-DISI ') :]} çağırıyor / yazıyor — ön doğrulama yalnız profili "
        "ARAR + OKUR + HATA + exit yapar; aparat onu GERÇEKTEN koşardı (dosya sistemi / süreç), kod KOŞTURULMADI."
    )


def _cek(tmp_path: Path, betik: Path) -> str:
    cikti = tmp_path / f"cek_{betik.stem}.txt"
    govde = (
        _CEK.replace("@@IZIN_PS@@", _IZIN_PS)
        .replace("@@BETIK@@", _ps_lit(betik))
        .replace("@@IZINLI@@", _ps_dizi(IZINLI_KOMUT))
        .replace("@@UYE@@", _ps_dizi(IZINLI_UYE))
        .replace("@@CIKTI@@", _ps_lit(cikti))
    )
    r = _pwsh_file(tmp_path, f"cek_{betik.stem}.ps1", govde)
    _izin_disi_denetle(betik, "Y44 ön doğrulaması", r.stdout)
    assert r.returncode == 0 and r.stdout.startswith("OK"), (
        f"{betik.name}: Y44 ön doğrulaması (Test-PemfApiPortDegeri çağıran üst düzey ifade) parser ile bulunamadı "
        f"(rc={r.returncode}) — bozuk PEMF_API_PORT ile servis kurulur:\n{r.stdout}\n{r.stderr}"
    )
    return cikti.read_text(encoding="utf-8")


def kos(tmp_path: Path, kip: str, satir: str | None, mode: str = "device") -> tuple[int, list[str], Path]:
    """`kip` = install | setup; profil dosyasında `satir` (None = PEMF_API_PORT satırı YOK) → (çıkış kodu, olaylar, profil yolu).
    `mode` = betiğin `-Mode` parametresi (device | server) — sürücü onu betikteki gibi TANIMLAR (TUR 3, çürütücü 2 q2b)."""
    d = tmp_path / kip
    d.mkdir(parents=True)
    profil = d / "deploy" / "device.env"
    profil.parent.mkdir()
    profil.write_text(
        "# profil\nPEMF_API_HOST=0.0.0.0\n" + (f"{satir}\n" if satir is not None else "") + "PEMF_HEADLESS=1\n",
        encoding="utf-8",
    )
    olay = d / "olay.txt"
    olay.write_text("", encoding="utf-8")
    if kip == "install":
        betik, on, eap = BETIK, f"$ProfilDosyasi = {_ps_lit(profil)}\n", "'Stop'"  # betiğin kendi tercihi
    else:
        betik, on, eap = SETUP, f"$OnEnvFile = {_ps_lit(profil)}\n", "'Continue'"
    on = f"$Mode = {_ps_lit(mode)}\n" + on
    govde = _SURUCU.replace("@@OLAY@@", _ps_lit(olay)).replace("@@EAP@@", eap).replace("@@KOD@@", on + _cek(d, betik))
    r = _pwsh_file(d, "surucu.ps1", govde)
    olaylar = [s for s in olay.read_text(encoding="utf-8-sig").splitlines() if s.strip()]
    assert r.returncode in (0, 1), f"sürücü düştü (rc={r.returncode}; 99 gölge yok):\n{olaylar}\n{r.stdout}\n{r.stderr}"
    durdu = "DEVAM" not in olaylar
    assert not (durdu and r.returncode == 0), (
        f"[{kip}] kurulum DURDU ama çıkış kodu 0 — çağıran başarı sanar:\n{olaylar}"
    )
    assert durdu or r.returncode == 0, f"aparat: DEVAM'a ulaşıldı ama çıkış kodu {r.returncode}:\n{olaylar}"
    return r.returncode, olaylar, profil


def _hata(olaylar: list[str]) -> list[str]:
    return [s for s in olaylar if s.startswith("LOG HATA")]


def _gecerli(deger: str) -> bool:
    """Backend `ortam_portu` anlamı (D5 H-1 `_backend_portu` ile aynı): Python `int()` + 1..65535; profil satırı kırpılır."""
    try:
        return 1 <= int(deger.strip()) <= 65535
    except ValueError:
        return False


@pytest.mark.parametrize("deger", DEGERLER)
def test_KRITIK_bozuk_PEMF_API_PORT_kurulumu_DURDURUR_gecerli_SURER_backend_int_anlaminda(tmp_path, deger):
    rc, olaylar, profil = kos(tmp_path, "install", f"PEMF_API_PORT={deger}")
    if _gecerli(deger):
        assert rc == 0 and not _hata(olaylar) and "PAUSE" not in olaylar, (
            f"PEMF_API_PORT={deger!r} backend için GEÇERLİ ama kurulum durdu / HATA bastı:\n{olaylar}"
        )
        return
    assert rc == 1, (
        f"PEMF_API_PORT={deger!r} bozuk (backend uyarıyla 8000'e düşer) ama kurulum DURMADI — servis bozuk değerle kurulur:\n{olaylar}"
    )
    hata = _hata(olaylar)
    assert [
        s
        for s in hata
        if f"PEMF_API_PORT geçersiz: '{deger}'" in s and "düzeltin" in s and str(profil) in s and "kurulum DURDU" in s
    ], f"HATA nedeni (değer) · eylemi (düzeltin) · dosyayı · durduğunu söylemiyor:\n{olaylar}"
    assert "PAUSE" in olaylar, f"operatör HATA'yı göremeden pencere kapanır (pause yok):\n{olaylar}"


@pytest.mark.parametrize("mode", ["device", "server"])
def test_KRITIK_Y44_KIPTEN_BAGIMSIZ_bozuk_portta_iki_kipte_de_DURDURUR(tmp_path, mode):
    """Çürütücü 2 q2 / q2b (kip koşullu koruma): Y44 `$Mode` ile koşullanırsa (yalnız device ya da server dışı) server.env'deki bozuk port
    ile servis kurulur. Sürücü `-Mode`'u betikteki gibi tanımlar; iki kipte de bozuk değer DURDURUR, geçerli değer SÜRER (iki kurulum yolu)."""
    for kip in ("install", "setup"):
        rc, olaylar, _p = kos(tmp_path / f"{mode}_bozuk", kip, "PEMF_API_PORT=80O0", mode=mode)
        assert rc == 1 and _hata(olaylar), (
            f"[{kip} / -Mode {mode}] bozuk PEMF_API_PORT kurulumu DURDURMADI — Y44 kipe bağlı atlanıyor, servis bozuk değerle kurulur:\n"
            f"{olaylar}"
        )
        rc2, olaylar2, _p2 = kos(tmp_path / f"{mode}_gecerli", kip, "PEMF_API_PORT=8010", mode=mode)
        assert rc2 == 0 and not _hata(olaylar2), (
            f"[{kip} / -Mode {mode}] geçerli port (8010) ile kurulum durdu:\n{olaylar2}"
        )


# ── Y44 PROFİL ARAMASIYLA (D5 M-3 TUR 3b, çürütücü 3 q2c / q2d): yukarıdaki kollar profil yolunu önekte DOĞRUDAN verir — kip → dosya bağı
# (`Get-PemfProfilEnvDosyasi $AppDir $Mode …` + profil değişkeninin ataması) çekilmez; "Y44 hep device profilini doğrular" (q2d) ya da
# "staging kipinde Y44 atlanır" (q2c) gerilemesi görünmüyordu. Burada betikten: üç tanım (Test-PemfApiPortDegeri · Read-PemfProfilEnv ·
# Get-PemfProfilEnvDosyasi) + Y44'ten önceki EN YAKIN profil değişkeni ataması + Y44 ifadesi çekilir, izin listesine karşı denetlenir ve
# betiğin her kipinde (setup: device / server / staging — ValidateSet; install: device / server) yalnız O KİPİN profili bozukken koşar.
_KIPLER = {"setup": ("device", "server", "staging"), "install": ("device", "server")}
_PROFIL_DEGISKENI = {"setup": "$OnEnvFile", "install": "$ProfilDosyasi"}
_ARAMA_IZINLI = (
    *IZINLI_KOMUT,
    "Get-PemfProfilEnvDosyasi",
    "Join-Path",
    "Test-Path",
    "Where-Object",
    "Select-Object",
    "Split-Path",
)
_ARAMA_CEK = r"""
using namespace System.Management.Automation.Language
@@IZIN_PS@@
$t = $null; $h = $null
$ast = [Parser]::ParseFile(@@BETIK@@, [ref]$t, [ref]$h)
if ($h.Count) { Write-Output "PARSE-ERROR"; exit 3 }
$ust = @($ast.EndBlock.Statements)
$tanim = @($ust | Where-Object { $_ -is [FunctionDefinitionAst] -and @('Test-PemfApiPortDegeri', 'Read-PemfProfilEnv', 'Get-PemfProfilEnvDosyasi') -contains $_.Name })
$i44 = -1
for ($i = 0; $i -lt $ust.Count; $i++) {
    if ($ust[$i] -isnot [FunctionDefinitionAst] -and $ust[$i].Find({ param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'Test-PemfApiPortDegeri' }, $true)) { $i44 = $i; break } }
$j = $i44 - 1
while ($j -ge 0 -and -not ($ust[$j] -is [AssignmentStatementAst] -and $ust[$j].Left.Extent.Text -eq @@DEGISKEN@@)) { $j-- }
if ($tanim.Count -ne 3 -or $i44 -lt 0 -or $j -lt 0) { Write-Output "Y44-ARAMA-YOK tanim=$($tanim.Count) y44=$i44 atama=$j"; exit 4 }
$sec = @($tanim) + @($ust[$j]) + @($ust[$i44])
foreach ($s in $sec) { $ihlal = _IzinDisiY44 $s @@IZINLI@@ @@UYE@@; if ($ihlal) { Write-Output ("IZIN-DISI " + $ihlal); exit 5 } }
[System.IO.File]::WriteAllText(@@CIKTI@@, (($sec | ForEach-Object { $_.Extent.Text }) -join "`n"), [System.Text.UTF8Encoding]::new($false))
Write-Output "OK"
"""


def kos_arama(tmp_path: Path, kip: str, mode: str, bozuk_kip: str) -> tuple[int, list[str], Path]:
    """Betiğin `kip` kurulum yolu, `-Mode mode`; `deploy\\<m>.env` profillerinin hepsi var, yalnız `bozuk_kip`inki bozuk portlu.
    → (çıkış kodu, olaylar, `mode`un profil dosyası)."""
    d = tmp_path / f"{kip}_{mode}_bozuk_{bozuk_kip}"
    app = d / "app"
    for m in _KIPLER[kip]:
        p = app / "deploy" / f"{m}.env"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"# {m}\nPEMF_API_PORT={'80O0' if m == bozuk_kip else '8010'}\nPEMF_HEADLESS=1\n", encoding="utf-8"
        )
    betik = BETIK if kip == "install" else SETUP
    cikti = d / "cek.txt"
    govde = (
        _ARAMA_CEK.replace("@@IZIN_PS@@", _IZIN_PS)
        .replace("@@BETIK@@", _ps_lit(betik))
        .replace("@@DEGISKEN@@", _ps_lit(_PROFIL_DEGISKENI[kip]))
        .replace("@@IZINLI@@", _ps_dizi(_ARAMA_IZINLI))
        .replace("@@UYE@@", _ps_dizi(IZINLI_UYE))
        .replace("@@CIKTI@@", _ps_lit(cikti))
    )
    r = _pwsh_file(d, "cek.ps1", govde)
    _izin_disi_denetle(betik, "Y44 profil araması + ön doğrulaması", r.stdout)
    assert r.returncode == 0 and r.stdout.startswith("OK"), (
        f"{betik.name}: Y44 profil araması ({_PROFIL_DEGISKENI[kip]} = Get-PemfProfilEnvDosyasi …) + ön doğrulaması parser ile "
        f"bulunamadı (rc={r.returncode}):\n{r.stdout}\n{r.stderr}"
    )
    olay = d / "olay.txt"
    olay.write_text("", encoding="utf-8")
    # Split-Path (setup: betik dizini) kayıtçı değil SABİT gölge — Get-Command ile İŞLEV kanıtlı; $ScriptDir (install) aynı dizin.
    on = (
        f"function Split-Path {{ param([switch]$Parent, [Parameter(Position = 0)]$Path) {_ps_lit(app / 'scripts')} }}\n"
        "if ((Get-Command Split-Path).CommandType -ne 'Function') { _Olay 'GOLGE-YOK Split-Path'; exit 99 }\n"
        f"$AppDir = {_ps_lit(app)}\n$Mode = {_ps_lit(mode)}\n$ScriptDir = {_ps_lit(app / 'scripts')}\n"
    )
    eap = "'Stop'" if kip == "install" else "'Continue'"
    govde = (
        _SURUCU.replace("@@OLAY@@", _ps_lit(olay))
        .replace("@@EAP@@", eap)
        .replace("@@KOD@@", on + cikti.read_text(encoding="utf-8"))
    )
    r = _pwsh_file(d, "surucu.ps1", govde)
    olaylar = [s for s in olay.read_text(encoding="utf-8-sig").splitlines() if s.strip()]
    assert r.returncode in (0, 1), f"sürücü düştü (rc={r.returncode}; 99 gölge yok):\n{olaylar}\n{r.stdout}\n{r.stderr}"
    assert ("DEVAM" in olaylar) == (r.returncode == 0), f"aparat: çıkış kodu / DEVAM tutarsız:\n{olaylar}"
    return r.returncode, olaylar, app / "deploy" / f"{mode}.env"


@pytest.mark.parametrize(
    ("kip", "mode"), [(k, m) for k, kipler in _KIPLER.items() for m in kipler], ids=lambda v: str(v)
)
def test_KRITIK_Y44_KIPIN_KENDI_profilini_ARAR_her_kipte_DURDURUR_baska_kipin_bozuk_profili_DURDURMAZ(
    tmp_path, kip, mode
):
    rc, olaylar, profil = kos_arama(tmp_path, kip, mode, mode)
    assert rc == 1 and [s for s in _hata(olaylar) if "'80O0'" in s and str(profil) in s], (
        f"[{kip} / -Mode {mode}] kipin profilindeki ({mode}.env) bozuk PEMF_API_PORT kurulumu DURDURMADI ya da HATA o dosyayı söylemiyor — "
        f"Y44 kipe bağlı atlanıyor ya da başka kipin profilini doğruluyor (servis {mode}.env ile kurulur):\n{olaylar}"
    )
    baska = next(m for m in _KIPLER[kip] if m != mode)
    rc2, olaylar2, _p = kos_arama(tmp_path, kip, mode, baska)
    assert rc2 == 0 and not _hata(olaylar2), (
        f"[{kip} / -Mode {mode}] yalnız BAŞKA kipin profili ({baska}.env) bozukken kurulum durdu — Y44 kendi kipinin profilini değil "
        f"başka / bütün profilleri doğruluyor:\n{olaylar2}"
    )


def test_KARSIT_PEMF_API_PORT_satiri_YOKSA_kurulum_surer(tmp_path):
    rc, olaylar, _profil = kos(tmp_path, "install", None)
    assert rc == 0 and not _hata(olaylar), f"profilde PEMF_API_PORT yokken (backend 8000) kurulum durdu:\n{olaylar}"


@pytest.mark.parametrize(
    "satir",
    [
        "PEMF_API_PORT=80O0",
        "PEMF_API_PORT=70000",
        "PEMF_API_PORT=",
        "PEMF_API_PORT = sekiz bin",
        "PEMF_API_PORT=+8001",
        "PEMF_API_PORT=8_0_10",
        None,
    ],
)
def test_KRITIK_ESLIK_setup_services_Y44_ile_AYNI_karar_ve_AYNI_HATA_metni(tmp_path, satir):
    """A-11: destekli ikinci kurulum yolu setup_services ile aynı davranır — karar (dur / sür) ve HATA metni birebir."""
    sonuc = {}
    for kip in ("install", "setup"):
        rc, olaylar, profil = kos(tmp_path, kip, satir)
        sonuc[kip] = (rc, [s.replace(str(profil), "<PROFIL>") for s in _hata(olaylar)])
    assert sonuc["install"] == sonuc["setup"], (
        f"[{satir!r}] install_backend_service ile setup_services Y44 kararında / metninde AYRIŞTI:\ninstall={sonuc['install']}\n"
        f"setup  ={sonuc['setup']}"
    )
    assert sonuc["install"][0] == (0 if satir is None or satir.endswith(("+8001", "8_0_10")) else 1), sonuc


# ── Betik bağlantısı (AST): Y44 D2.73'ten SONRA, port-dolu denetiminden / $ApiPort'tan / servise dokunan HER adımdan ÖNCE ──
_AST = r"""
using namespace System.Management.Automation.Language
$t = $null; $h = $null
$ast = [Parser]::ParseFile(@@BETIK@@, [ref]$t, [ref]$h)
$ust = @($ast.EndBlock.Statements)
function _Ilk([scriptblock]$k) { for ($i = 0; $i -lt $ust.Count; $i++) { if ($ust[$i] -isnot [FunctionDefinitionAst] -and $ust[$i].Find($k, $true)) { return $i } }; -1 }
$y44 = _Ilk { param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'Test-PemfApiPortDegeri' }
$okuma = @($ast.FindAll({ param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'Read-PemfProfilEnv' }, $true) | Where-Object {
    $p = $_.Parent; $ic = $false; while ($p) { if ($p -is [FunctionDefinitionAst]) { $ic = $true; break }; $p = $p.Parent }; -not $ic })
$okumaArg = @($okuma | ForEach-Object { $e = $_.CommandElements | Select-Object -Skip 1 -First 1; if ($e -is [VariableExpressionAst]) { $e.VariablePath.UserPath } else { "$e" } })
$ortamArg = ''
$ortam = $ast.Find({ param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'Get-PemfServisOrtami' }, $true)
if ($ortam) { $e = $ortam.CommandElements | Select-Object -Skip 1 -First 1; if ($e -is [VariableExpressionAst]) { $ortamArg = $e.VariablePath.UserPath } }
$y44Kosul = ''; $y44Okuma = @()
if ($y44 -ge 0 -and $ust[$y44] -is [IfStatementAst]) { $y44Kosul = $ust[$y44].Clauses[0].Item1.Extent.Text }
if ($y44 -ge 0) { $y44Okuma = @($ust[$y44].FindAll({ param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'Read-PemfProfilEnv' }, $true) | ForEach-Object {
    $e = $_.CommandElements | Select-Object -Skip 1 -First 1; if ($e -is [VariableExpressionAst]) { $e.VariablePath.UserPath } else { "$e" } }) }
[pscustomobject]@{
    hata = @($h | ForEach-Object { $_.Message }); y44 = $y44; okuma_arg = @($okumaArg); ortam_arg = $ortamArg
    y44_kosul = $y44Kosul; y44_okuma = @($y44Okuma)
    y44_exit = [bool]($(if ($y44 -ge 0) { $ust[$y44].Find({ param($n) $n -is [ExitStatementAst] }, $true) }))
    profil = (_Ilk { param($n) $n -is [IfStatementAst] -and $n.Clauses[0].Item1.Extent.Text -match '^-not \$AppEnv$' })
    port_dolu = (_Ilk { param($n) $n -is [VariableExpressionAst] -and $n.VariablePath.UserPath -eq 'PortunDisSahibi' })
    port_atama = (_Ilk { param($n) $n -is [AssignmentStatementAst] -and $n.Left.Extent.Text -eq '$ApiPort' })
    nssm = (_Ilk { param($n) $n -is [CommandAst] -and $n.Extent.Text -match '^&\s*\$NssmExe\s+(stop|remove|install)' })
    indirme = (_Ilk { param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'Invoke-WebRequest' })
    gunluk = (_Ilk { param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'New-Item' -and $n.Extent.Text -match '\$LogDir' })
} | ConvertTo-Json -Compress
"""


def test_KRITIK_Y44_D2_73_sonrasi_port_doludan_ve_servise_DOKUNAN_her_adimdan_ONCE(tmp_path):
    r = _pwsh_file(tmp_path, "ast.ps1", _AST.replace("@@BETIK@@", _ps_lit(BETIK)))
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    a = json.loads(r.stdout.strip().splitlines()[-1])
    assert not a["hata"], a
    assert a["y44"] >= 0 and a["y44_exit"], (
        f"Y44 ön doğrulaması (Test-PemfApiPortDegeri + exit'li üst düzey ifade) betikte YOK: {a}"
    )
    assert a["okuma_arg"] == [a["ortam_arg"]] and a["ortam_arg"], (
        f"Y44 servise giden ortamın profilini (${a['ortam_arg'] or '?'}) okumuyor — denetlenen dosya ile servis ortamı ayrışabilir: {a}"
    )
    # TUR 3b (çürütücü 3 q2c / q2d, install kolu): Y44 `if`inin koşulu YALNIZ servis ortamının profil değişkeni (kip / başka koşul
    # eklenmez — kip koşullu koruma) ve Y44'ün okuduğu dosya o değişken.
    y44_okuma = a["y44_okuma"] if isinstance(a["y44_okuma"], list) else [a["y44_okuma"]]
    assert a["y44_kosul"] == f"${a['ortam_arg']}" and y44_okuma == [a["ortam_arg"]], (
        f"Y44 ön doğrulamasının koşulu / okuduğu dosya servis ortamının profil değişkeni (${a['ortam_arg'] or '?'}) değil "
        f"(koşul {a['y44_kosul']!r}, okuma {y44_okuma}) — kipe / başka koşula bağlı atlanabilir ya da başka dosyayı doğrular: {a}"
    )
    assert 0 <= a["profil"] < a["y44"], f"Y44 profil (D2.73) korumasından ÖNCE — profil yokken okunamaz: {a}"
    for adim in ("port_dolu", "port_atama", "nssm", "indirme", "gunluk"):
        assert 0 <= a["y44"] < a[adim], (
            f"Y44 '{adim}' adımından SONRA (ya da adım bulunamadı) — bozuk PEMF_API_PORT asıl nedeni söylenmeden ya da servis "
            f"değiştirildikten sonra durur: {a}"
        )
