# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5 J-3 TUR 3 KAPISI — "İzin ver" / paylaşım kurulumunun YÜKSELTME SARMALAYICISI çıkış kodunu DAVRANIŞLA aktarır.

`launcher/app/src/main.rs` `ps_yukselterek_kos_kodlu` yükseltilmiş betiği `Start-Process powershell -Verb RunAs -Wait -PassThru
-ErrorAction Stop` ile koşan bir PowerShell komutu KURAR (`format!`); Rust tarafı O KOMUTUN çıkış kodunu okur → `izin_ver_sonucu` /
`paylasim::hata_anahtari`. Tur 2 kolları bu komutu yalnız METİN olarak ölçüyordu: çürütücü 2 (j3) `-ErrorAction Stop` silinince
app / çekirdek / pytest kümeleri YEŞİL kaldı — oysa UAC "Hayır" SONLANDIRMAYAN bir hata olursa `catch`e düşülmez, `$p` boş kalır,
`exit $p.ExitCode` = `exit $null` = 0 → arayüz "tamam" deyip uyarıyı KAPATIR (gölge ölçümü).

KAPI (gerçek UAC / yükseltme / `Start-Process` / RunAs YOK):
  1. main.rs'teki `format!` dizgesi Rust kurallarıyla çözülür (`\\`+satır sonu, `{{`/`}}`), adlı argümanlar sabitlerinden okunur
     (`red` = `paylasim::KOD_UAC_REDDEDILDI`, `bos` = `KOD_YUKSELTILMIS_CIKIS_KODU_YOK`), `{b64}` yerine zararsız sahte değer.
  2. Komuttaki TEK `Start-Process` gölge işlev adına (`Golge-BaslatSurec`) çevrilir. KOŞMADAN ÖNCE ayrı bir (yalnız AYRIŞTIRAN)
     PowerShell sürecinde komutun AST'i okunur: komut adları YALNIZ gölge (Start-Process / start / saps / RunAs / Invoke-Expression /
     dinamik ad YOK), .NET yöntem çağrısı (`[Diagnostics.Process]::Start` …) YOK — değilse KOŞMADAN KIRMIZI.
  3. Komut, yükseltmesiz AYRI bir `powershell.exe` (5.1, üretimdeki gibi) sürecinde gizli (`CREATE_NO_WINDOW`), `-NoProfile
     -NonInteractive`, zaman aşımlı koşar. Önsöz: Utility `$PSHOME`'dan tam yolla, `$PSModuleAutoLoadingPreference = 'None'`,
     `PSModulePath` boş → gerçek `Start-Process` ÇÖZÜLEBİLİRSE çıkış 96; gölge `Get-Command` ile İŞLEV olarak kanıtlanmazsa 99.
     `$ErrorActionPreference` üretimdeki varsayılan (`Continue`).
  4. Gölge kipleri → beklenen süreç çıkış kodu (testte SABİT): UAC iptali = SONLANDIRMAYAN `Write-Error` → 1223 (ERROR_CANCELLED,
     MEVCUT "Yönetici izni verilmedi" iletisi) · sahte `ExitCode` 2 → 2 · 0 → 0 (karşıt) · `ExitCode` `$null` ve süreç nesnesi YOK →
     SIFIR DIŞI ve 0 / 3 / 4 / 5 / 1223 DIŞI (TUR 3 ÜRÜN KARARI: fail-closed; MEVCUT "kural eklenemedi (kod 1)" iletisi).
  5. TUR 3b (çürütücü 3 w2): gölge `ArgumentList`i AYNEN `-NoProfile | -NonInteractive | -EncodedCommand | <b64>` alır ve <b64>
     sarmalayıcıya verilen iç betiğin UTF-16LE base64'üdür — `-EncodedCommand` yerine `-Command` (yükseltilmiş PowerShell base64'ü
     KOMUT adı sanar → betik HİÇ koşmaz, "İzin ver" her seferinde "kod 1", kural / grup hiç kurulmaz) app / çekirdek / gölge
     kümesinde YEŞİLDİ (gölge ArgumentList'i kaydetmiyordu).
MUTASYON: `-ErrorAction Stop` silinir (j3) / boş-kod koruması silinir ya da 0 döner / catch `exit 0` / son deyim sabit /
`-EncodedCommand` → `-Command` (w2) → KIRMIZI.
[TEZGÂH] gerçek `Start-Process -Verb RunAs` UAC iptalinin hata türü (sonlandıran / sonlandırmayan) gerçek UAC ile bir kez doğrulanmalı;
gölge EN KÖTÜ durumu (sonlandırmayan) modeller — sonlandıran olsa da 1223 beklenir.
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
MAIN_RS = KOK / "launcher" / "app" / "src" / "main.rs"
CORE_SRC = KOK / "launcher" / "core" / "src"

#: Beklenen kodlar testte SABİT (ürün sabitinden okunmaz): ERROR_CANCELLED.
_UAC_REDDI = 1223
#: Özel anlamlı kodlar (başarı · bozuk kural silinemedi / paylaşım izin · bağ · veri yok · UAC) — "kod okunamadı" bunlarla KARIŞMAZ.
_OZEL_KODLAR = {0, 3, 4, 5, _UAC_REDDI}
_GOLGE = "Golge-BaslatSurec"
#: `{b64}` yerine konan zararsız sahte iç betik — gölge ArgumentList'i KOŞMAZ; yalnız AYNEN taşındığı ölçülür (TUR 3b w2).
_SAHTE_IC_BETIK = "exit 0"
#: Yükseltilmiş sürece giden argüman listesi (sıra + bayraklar testte SABİT): betik `-EncodedCommand` ile, kodlaması UTF-16LE base64.
_BEKLENEN_ARGUMANLAR = ["-NoProfile", "-NonInteractive", "-EncodedCommand"]
_CREATE_NO_WINDOW = 0x08000000


def _ps51() -> str:
    s = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    p = s / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if sys.platform != "win32" or not p.is_file():
        capraz.atla("Windows PowerShell 5.1 yok (yükseltme sarmalayıcısı yalnız Windows'ta koşar)")
    return str(p)


def _islev_govdesi(kaynak: str, imza: str) -> str:
    i = kaynak.index(imza)
    j = kaynak.index("\n}\n", i)
    return kaynak[i:j]


def _rust_dizge(govde: str, bas: int) -> tuple[str, int]:
    """`bas`taki `"` ile açılan Rust dizge sabitinin DEĞERİ (kaçışlar çözülür; `\\`+satır sonu+girinti birleşir) ve sonrası konum."""
    assert govde[bas] == '"'
    o, i = [], bas + 1
    while govde[i] != '"':
        c = govde[i]
        if c == "\\":
            n = govde[i + 1]
            if n == "\n" or (n == "\r" and govde[i + 2] == "\n"):
                i += 2 if n == "\n" else 3
                while govde[i] in " \t\r\n":
                    i += 1
                continue
            o.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'", "0": "\0"}.get(n, "\\" + n))
            i += 2
            continue
        o.append(c)
        i += 1
    return "".join(o), i + 1


def _sabit(ad: str) -> int:
    """`const AD: i32 = N;` — main.rs'te ya da çekirdekte (adlı argümanın yolu ne olursa olsun SON parça)."""
    desen = re.compile(rf"\bconst\s+{re.escape(ad)}\s*:\s*i32\s*=\s*(-?\d+)\s*;")
    for yol in [MAIN_RS, *sorted(CORE_SRC.glob("*.rs"))]:
        m = desen.search(yol.read_text(encoding="utf-8"))
        if m:
            return int(m.group(1))
    raise AssertionError(f"sarmalayıcının adlı argümanı {ad} bir i32 sabitine çözülemedi")


def _sarmalayici() -> str:
    """main.rs `ps_yukselterek_kos_kodlu`nun KURDUĞU PowerShell komutu (adlı argümanlar yerine konmuş, `{b64}` sahte)."""
    kaynak = MAIN_RS.read_text(encoding="utf-8").replace("\r\n", "\n")
    govde = _islev_govdesi(kaynak, "fn ps_yukselterek_kos_kodlu(")
    f = govde.index("format!(")
    sablon, son = _rust_dizge(govde, govde.index('"', f))
    kapanis = govde.index(");", son)
    argumanlar = dict(re.findall(r"(\w+)\s*=\s*([\w:]+)", govde[son:kapanis]))
    degerler = {
        ad: str(int(ifade) if re.fullmatch(r"-?\d+", ifade) else _sabit(ifade.split("::")[-1]))
        for ad, ifade in argumanlar.items()
    }
    degerler["b64"] = base64.b64encode(_SAHTE_IC_BETIK.encode("utf-16-le")).decode()  # gölge ArgumentList'i KOŞMAZ

    def _yer(m: re.Match) -> str:
        t = m.group(0)
        if t in ("{{", "}}"):
            return t[0]
        ad = t[1:-1]
        assert ad in degerler, f"format! yer tutucusu {t} çözülemedi (adlı argüman yok): {sorted(degerler)}"
        return degerler[ad]

    return re.sub(r"\{\{|\}\}|\{\w+\}", _yer, sablon)


def _kos(ps: str, args: list[str], env_ek: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PSModulePath"] = ""  # pwsh 7 modül yolları 5.1'e sızmasın; önsöz Utility'yi $PSHOME'dan TAM yolla yükler
    env.update(env_ek or {})
    return subprocess.run(
        [_ps51(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", *args],
        capture_output=True,
        timeout=90,
        env=env,
        creationflags=_CREATE_NO_WINDOW,
    )


def _kodla(betik: str) -> str:
    return base64.b64encode(betik.encode("utf-16-le")).decode()


_AST_DENETIM = r"""
$m = $env:J3_SARMALAYICI
$t = $null; $h = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($m, [ref]$t, [ref]$h)
foreach ($e in @($h)) { if ($e) { "HATA`t$($e.Message)" } }
foreach ($k in $ast.FindAll({ param($d) $d -is [System.Management.Automation.Language.CommandAst] }, $true)) { "KOMUT`t$($k.GetCommandName())" }
foreach ($u in $ast.FindAll({ param($d) $d -is [System.Management.Automation.Language.InvokeMemberExpressionAst] }, $true)) { "UYE`t$($u.Extent.Text)" }
'AST-BITTI'
"""

_KIPLER = {
    # SONLANDIRMAYAN hata (UAC "Hayır"ın en kötü modeli): -ErrorAction Stop varsa catch'e düşer, yoksa $p boş kalır.
    "uac_iptal": "Write-Error -Message 'PEMF-GOLGE UAC iptali: The operation was canceled by the user.' "
    "-Category OperationStopped -ErrorId 'J3UacIptal'; return",
    "kod2": "[pscustomobject]@{ ExitCode = 2 }",
    "kod0": "[pscustomobject]@{ ExitCode = 0 }",
    "kod_bos": "[pscustomobject]@{ ExitCode = $null }",
    "nesne_yok": "return",
}

_ONSOZ = r"""$ErrorActionPreference = 'Continue'
Import-Module "$PSHOME\Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1"
$PSModuleAutoLoadingPreference = 'None'
foreach ($n in @('Start-Process', 'Invoke-Item')) {
    if (Get-Command $n -ErrorAction SilentlyContinue) { [Console]::Out.WriteLine("GERCEK-SUREC-BASLATICI-ERISILEBILIR`t$n"); exit 96 }
}
function Golge-BaslatSurec {
    # PEMF-GOLGE-J3
    [CmdletBinding()]
    param([string]$FilePath, [string]$Verb, [switch]$Wait, [switch]$PassThru, [string]$WindowStyle, [object[]]$ArgumentList)
    [Console]::Out.WriteLine("GOLGE-ARG`t$($ArgumentList -join '|')")
    [Console]::Out.WriteLine("GOLGE-CAGRI`t$FilePath`t$Verb`t$($Wait.IsPresent)`t$($PassThru.IsPresent)`t$($PSBoundParameters['ErrorAction'])")
    __KIP__
}
$c = Get-Command Golge-BaslatSurec -ErrorAction SilentlyContinue
if (-not $c -or "$($c.CommandType)" -ne 'Function' -or $c.ModuleName -or "$($c.ScriptBlock)" -notmatch 'PEMF-GOLGE-J3') { [Console]::Out.WriteLine('GOLGE-YOK'); exit 99 }
[Console]::Out.WriteLine('GOLGE-HAZIR')
"""


@pytest.fixture(scope="module")
def golge_sarmalayici() -> str:
    _ps51()
    ham = _sarmalayici()
    assert len(re.findall(r"(?i)\bStart-Process\b", ham)) == 1, (
        f"aparat: sarmalayıcıda TEK Start-Process beklenir: {ham}"
    )
    golge = re.sub(r"(?i)\bStart-Process\b", _GOLGE, ham)
    r = _kos(_AST_DENETIM, ["-EncodedCommand", _kodla(_AST_DENETIM)], {"J3_SARMALAYICI": golge})
    cikti = r.stdout.decode("utf-8", errors="replace")
    assert r.returncode == 0 and "AST-BITTI" in cikti, (
        f"aparat: AST denetimi koşmadı ({r.returncode}): {cikti} {r.stderr[-400:]!r}"
    )
    satirlar = [s.split("\t", 1) for s in cikti.splitlines() if "\t" in s]
    hata = [d for t, d in satirlar if t == "HATA"]
    assert not hata, f"sarmalayıcı komutu AYRIŞTIRILAMIYOR (üretimde de koşmaz): {hata} — {golge}"
    komutlar = [d.strip() for t, d in satirlar if t == "KOMUT"]
    uyeler = [d for t, d in satirlar if t == "UYE"]
    # KOŞMADAN ÖNCE: gerçek süreç başlatabilecek HİÇBİR komut / yöntem yok — yalnız gölge.
    assert komutlar == [_GOLGE], (
        f"gölgelenmiş sarmalayıcıda gölge DIŞI komut var (Start-Process / start / saps / RunAs / iex / dinamik ad?) — KOŞULMADI: "
        f"{komutlar}"
    )
    assert not uyeler, f"sarmalayıcıda .NET yöntem çağrısı var (süreç başlatabilir) — KOŞULMADI: {uyeler}"
    return golge


def _golge_kos(golge: str, kip: str) -> tuple[int, str]:
    betik = _ONSOZ.replace("__KIP__", _KIPLER[kip]) + "\n" + golge + "\n"
    r = _kos(betik, ["-EncodedCommand", _kodla(betik)])
    cikti = r.stdout.decode("utf-8", errors="replace") + r.stderr.decode("utf-8", errors="replace")
    assert r.returncode not in (96, 99), (
        f"aparat bekçisi düştü ({r.returncode}; 96 = gerçek Start-Process erişilebilir, 99 = gölge yok): {cikti}"
    )
    assert "GOLGE-HAZIR" in cikti, f"aparat: gölge önsözü tamamlanmadı ({r.returncode}): {cikti}"
    cagri = [s for s in cikti.splitlines() if s.startswith("GOLGE-CAGRI\t")]
    assert len(cagri) == 1, f"aparat: sarmalayıcı gölgeyi TAM BİR kez çağırmadı: {cikti}"
    p = cagri[0].split("\t")
    assert p[1:5] == ["powershell", "RunAs", "True", "True"], (
        f"sarmalayıcı yükseltilmiş süreci `powershell -Verb RunAs -Wait -PassThru` ile istemiyor: {p[1:]}"
    )
    # TUR 3b (w2): iç betik yükseltilmiş sürece `-EncodedCommand <UTF-16LE base64>` ile AYNEN gider (`-Command <b64>` → betik koşmaz).
    arg = [s.split("\t", 1)[1] for s in cikti.splitlines() if s.startswith("GOLGE-ARG\t")]
    beklenen = "|".join([*_BEKLENEN_ARGUMANLAR, _kodla(_SAHTE_IC_BETIK)])
    assert arg == [beklenen], (
        f"yükseltilmiş sürece iç betik `-EncodedCommand <b64>` ile AYNEN gitmiyor (`-Command` / eksik bayrak → betik HİÇ koşmaz, "
        f"'İzin ver' her seferinde 'kod 1'): {arg} ≠ [{beklenen!r}]"
    )
    return r.returncode, cikti


def test_KRITIK_J3_UAC_iptali_SONLANDIRMAYAN_hata_olsa_da_1223(golge_sarmalayici):
    kod, cikti = _golge_kos(golge_sarmalayici, "uac_iptal")
    assert kod == _UAC_REDDI, (
        f"UAC iptali (sonlandırmayan hata) {_UAC_REDDI} değil, {kod} ile çıktı — `-ErrorAction Stop` yoksa catch'e düşülmez, "
        f"'İzin ver' 'tamam' / yanlış ileti der:\n{cikti}"
    )


@pytest.mark.parametrize(("kip", "beklenen"), [("kod2", 2), ("kod0", 0)])
def test_KRITIK_J3_ic_surecin_cikis_kodu_AYNEN_aktarilir(golge_sarmalayici, kip, beklenen):
    kod, cikti = _golge_kos(golge_sarmalayici, kip)
    assert kod == beklenen, f"yükseltilmiş sürecin çıkış kodu {beklenen} sarmalayıcıdan {kod} olarak çıktı:\n{cikti}"


@pytest.mark.parametrize("kip", ["kod_bos", "nesne_yok"])
def test_KRITIK_J3_cikis_kodu_BOSSA_sarmalayici_SIFIR_DISI_cikar_fail_closed(golge_sarmalayici, kip):
    """TUR 3 ÜRÜN KARARI [ÖNERİLEN UYGULANDI]: `$p` / `$p.ExitCode` boşsa `exit $null` = 0 ("tamam") DEĞİL; genel hata kodu."""
    kod, cikti = _golge_kos(golge_sarmalayici, kip)
    assert kod not in _OZEL_KODLAR, (
        f"çıkış kodu OKUNAMADI ({kip}) ama sarmalayıcı {kod} ile çıktı — 0 = arayüz 'tamam' der ve uyarıyı kapatır; 3 / 4 / 5 / 1223 = "
        f"yanlış ÖZEL ileti:\n{cikti}"
    )
