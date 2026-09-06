# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SYSTEM (LocalSystem) KİMLİK KASASI TEARDOWN'DA TEMİZLENİR — denetim 2026-09-06.

Ölçülen durum: backend servisi (PemfBackend, NSSM) LocalSystem olarak koşar;
database/sqlcipher_util.py `keyring.set_password("PEMF_GUI", "sqlcipher_key", ...)` yazar ve
python-keyring'in Windows arka ucu bunu SYSTEM hesabının Credential Manager kasasına
"<ad>@PEMF_GUI" hedefiyle koyar. `pemf_teardown.ps1::Remove-PemfCredentials` yükseltilmiş
YÖNETİCİ olarak cmdkey çalıştırır → yalnız yöneticinin kasasını görür → DB/fernet anahtarları
KVKK "tam temizlik"ten SAĞ ÇIKIYORDU; depoda o kasayı temizleyen başka adım yoktu.

Çözüm: `Remove-PemfSystemCredentials` — tek-seferlik `/RU SYSTEM` zamanlanmış görev SYSTEM
bağlamında `kasa.ps1` koşturur (cmdkey /delete + cmdkey /list doğrulaması → sonuc.txt); ana
betik sonucu okur, loglar, görev + çalışma dizinini HER DURUMDA siler.

Bu dosya DAVRANIŞ ölçer (metin grep'i değil):
  • Fonksiyon AST ile ÇIKARILIR (pemf_teardown.ps1 bütün olarak asla dot-source edilmez);
    schtasks yerine `$script:PemfSchtasksYolu` ile bir STUB (.ps1) konur: argümanları kaydeder,
    /Run'da kasa.ps1'i MEVCUT kullanıcı olarak powershell.exe ile koşturur (kasa.ps1'in gerçek
    cmdkey davranışı böylece gerçek bir geçici kimlik üzerinde ölçülür).
  • Üretim ana bilgisayarı Windows PowerShell 5.1 (Inno powershell.exe çağırır) → sürücü hem
    pwsh (7) hem powershell.exe (5.1) altında koşar; üretilen kasa.ps1 de 5.1 ile parse edilir.
  • Gerçek-SYSTEM entegrasyon testi (i) yalnız YÜKSELTİLMİŞ oturum + PEMF_SYSTEM_KASA_TESTI=1
    ile koşar; aksi hâlde atlanır.

Yalnız Windows (cmdkey / Credential Manager / schtasks Windows'a özgü).
"""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_TEARDOWN = _KOK / "scripts" / "pemf_teardown.ps1"

_PWSH = shutil.which("pwsh")
_PS51 = shutil.which("powershell")  # Windows PowerShell 5.1 — üretim ana bilgisayarı

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="cmdkey / schtasks / Credential Manager yalnız Windows"),
    pytest.mark.skipif(_PWSH is None, reason="pwsh (PowerShell 7) bulunamadı"),
    pytest.mark.skipif(_PS51 is None, reason="powershell.exe (5.1) bulunamadı"),
]

_KABUKLAR = [pytest.param(_PWSH, id="pwsh7"), pytest.param(_PS51, id="ps51")]

_PROGRAMDATA = Path(os.environ.get("ProgramData", r"C:\ProgramData"))


# ── schtasks STUB: argümanları kaydeder; /Run'da kasa.ps1'i mevcut kullanıcı olarak koşturur ──
_STUB = r"""
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$a)
$mod = '__MOD__'
$kayit = '__KAYIT__'
$kasaYoluDosya = '__KASAYOLU__'
$kopya = '__KOPYA__'
$aclDosya = '__ACL__'
$sahte = '__SAHTE__'
if (-not $a) { $a = @() }
Add-Content -LiteralPath $kayit -Value ($a -join ' ') -Encoding UTF8
$ilk = if ($a.Count -gt 0) { $a[0] } else { '' }
if ($ilk -eq '/Create') {
    if ($mod -eq 'create_fail') { 'ERROR: Access is denied.'; exit 1 }
    # GERÇEK schtasks /ST 00:00 ile HER /Create'te bu uyarıyı STDERR'e yazar (ölçüm 2026-09-06, 5.1):
    # EAP=Stop altında `2>&1` 5.1'de fırlatır → fonksiyon EAP'yi yerel Continue yapmalı.
    if ($mod -eq 'stderr_warn') { & cmd.exe /c "echo WARNING: Task may not run because /ST is earlier than current time. 1>&2" }
    $ix = [array]::IndexOf($a, '/TR')
    if ($ix -ge 0 -and ($ix + 1) -lt $a.Count) {
        $tr = $a[$ix + 1]
        if ($tr -match '-File\s+"?(.+?\.ps1)"?\s*$') {
            Set-Content -LiteralPath $kasaYoluDosya -Value $Matches[1] -Encoding UTF8
            Copy-Item -LiteralPath $Matches[1] -Destination $kopya -Force
            # Çalışma dizininin ACL'si — SID'le (adlar yerelleşir): 'ACL=<sid>|<miras>|<haklar>'
            $dizin = [System.IO.Path]::GetDirectoryName($Matches[1])
            foreach ($ace in (Get-Acl -LiteralPath $dizin).Access) {
                $s = try { $ace.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value } catch { "$($ace.IdentityReference)" }
                Add-Content -LiteralPath $aclDosya -Value ('ACL=' + $s + '|' + $ace.IsInherited + '|' + $ace.FileSystemRights) -Encoding UTF8
            }
        }
    }
    'SUCCESS: The scheduled task has successfully been created.'; exit 0
}
if ($ilk -eq '/Run') {
    if ($mod -eq 'run_ignore') { 'SUCCESS: Attempted to run (stub ignored).'; exit 0 }
    $k = (Get-Content -LiteralPath $kasaYoluDosya -Raw).Trim()
    if ($mod -eq 'sahte_sonuc') {
        # kasa.ps1 KOŞMAZ: hazır sonuc.txt konur → ana betiğin AYRIŞTIRMA/KVKK dalları ölçülür
        Copy-Item -LiteralPath $sahte -Destination (Join-Path ([System.IO.Path]::GetDirectoryName($k)) 'sonuc.txt') -Force
        'SUCCESS: Attempted to run the scheduled task.'; exit 0
    }
    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $k | Out-Null
    'SUCCESS: Attempted to run the scheduled task.'; exit 0
}
if ($ilk -eq '/Delete') { 'SUCCESS: The scheduled task was successfully deleted.'; exit 0 }
'stub: bilinmeyen komut'; exit 2
"""

# ── Sürücü: fonksiyonları AST ile çıkarır, stub'ları kurar, fonksiyonu çağırır ──
_SURUCU = r"""
param([string]$Teardown, [string]$Senaryo, [string]$HedefDosya, [string]$LogYolu, [string]$StubYolu, [int]$ZamanAsimi, [string]$Kok = '')
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Teardown, [ref]$tokens, [ref]$errs)
if ($errs) { throw "pemf_teardown.ps1 parse hatası: $($errs | Out-String)" }
foreach ($ad in 'Remove-PemfSystemCredentials', 'Test-PemfYukseltilmis') {
    $fn = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $ad }, $true) | Select-Object -First 1
    if (-not $fn) { throw "$ad fonksiyonu bulunamadı (çıpa kaymış olabilir)" }
    Invoke-Expression $fn.Extent.Text
}
foreach ($deg in 'PemfSystemKasaZamanAsimiSn', 'PemfSchtasksYolu', 'PemfKimlikTemizlikKoku') {
    $atama = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -eq ('$script:' + $deg) }, $true) | Select-Object -First 1
    if (-not $atama) { throw "`$script:$deg bildirimi bulunamadı" }
    "DECL_$deg=$($atama.Right.Extent.Text)"
}
$script:PemfFailed = @()
$script:PemfSystemKasaZamanAsimiSn = $ZamanAsimi
$script:PemfSchtasksYolu = $StubYolu
$script:PemfKimlikTemizlikKoku = $env:ProgramData
if ($Kok) { $script:PemfKimlikTemizlikKoku = $Kok }
function Write-PemfLog($msg, $color = 'Gray') { Add-Content -LiteralPath $LogYolu -Value "$color|$msg" -Encoding UTF8 }
if ($Senaryo -eq 'yukseltilmemis') { function Test-PemfYukseltilmis { return $false } }
else { function Test-PemfYukseltilmis { return $true } }
$hedefler = @(Get-Content -LiteralPath $HedefDosya -Encoding UTF8 | Where-Object { $_ -ne '' })
# stderr_warn: çağıran EAP=Stop bırakır (setup_services.ps1 dışındaki bir çağıranı temsil eder) —
# fonksiyon kendi içinde Continue'ya çekmezse 5.1'de schtasks uyarısı fırlar (THREW=).
if ($Senaryo -ne 'stderr_warn') { $ErrorActionPreference = 'Continue' }
try {
    if ($Senaryo -eq 'dry') { Remove-PemfSystemCredentials -TargetNames $hedefler -DryRun }
    else { Remove-PemfSystemCredentials -TargetNames $hedefler }
} catch { "THREW=$($_.Exception.Message)" }
"FAILED_COUNT=$($script:PemfFailed.Count)"
foreach ($f in $script:PemfFailed) { "FAILED=$f" }
"""


def _ps(kabuk: str, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    r = subprocess.run(
        [kabuk, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", *args],
        capture_output=True,
        timeout=timeout,
    )
    r.stdout = r.stdout.decode("utf-8", "replace")  # type: ignore[assignment]
    r.stderr = r.stderr.decode("utf-8", "replace")  # type: ignore[assignment]
    return r


def _cmdkey(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["cmdkey", *args], capture_output=True, timeout=30)


def _kimlik_var(ad: str) -> bool:
    """cmdkey /list:<ad> → ad VARSA 'Target: <ad>' satırı (+ başlık = 2 kez), YOKSA '* NONE *' (1 kez)."""
    cikti = _cmdkey(f"/list:{ad}").stdout.decode("utf-8", "replace")
    return cikti.count(ad) >= 2


def _kalinti_dizinler() -> set[str]:
    return {p.name for p in _PROGRAMDATA.glob("PEMF_KimlikTemizlik_*")}


def _yukseltilmis() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception:
        return False


class _Sonuc:
    def __init__(
        self,
        stdout: str,
        log: list[str],
        kayit: list[str],
        kasa: str | None,
        calisma: Path | None,
        sure: float,
        acl: list[str],
    ):
        self.stdout = stdout
        self.log = log
        self.kayit = kayit  # stub'a gelen schtasks çağrıları (satır başına bir çağrı)
        self.kasa = kasa  # üretilen kasa.ps1 metni (stub /Create'te kopyalar)
        self.calisma = calisma  # /TR'den çıkarılan çalışma dizini
        self.sure = sure
        self.acl = acl  # çalışma dizininin ACL'si /Create anında: '<sid>|<miras>|<haklar>'

    @property
    def threw(self) -> str | None:
        m = re.search(r"THREW=(.*)", self.stdout)
        return m.group(1) if m else None

    @property
    def failed_count(self) -> int:
        m = re.search(r"FAILED_COUNT=(\d+)", self.stdout)
        assert m, f"sürücü PemfFailed sayacını basmadı: {self.stdout[-800:]}"
        return int(m.group(1))

    @property
    def failed(self) -> list[str]:
        return [ln[len("FAILED=") :] for ln in self.stdout.splitlines() if ln.startswith("FAILED=")]

    def komutlar(self) -> list[str]:
        return [ln.split(" ", 1)[0] for ln in self.kayit if ln.strip()]


def _kos(
    tmp_path: Path,
    kabuk: str,
    senaryo: str,
    hedefler: list[str],
    zaman: int = 2,
    sahte: str | None = None,
    kok: str | None = None,
) -> _Sonuc:
    """Sürücüyü çalıştır. senaryo: mutlu | create_fail | run_ignore | yukseltilmemis | dry |
    sahte_sonuc (sahte=sonuc.txt içeriği; kasa.ps1 koşmaz) | stderr_warn (EAP=Stop + /Create stderr uyarısı).
    kok: $script:PemfKimlikTemizlikKoku (çalışma dizini kökü) gölgesi."""
    kim = uuid.uuid4().hex[:8]
    kayit = tmp_path / f"kayit_{kim}.txt"
    kasa_yolu = tmp_path / f"kasayolu_{kim}.txt"
    kopya = tmp_path / f"kasa_kopya_{kim}.ps1"
    acl_dosya = tmp_path / f"acl_{kim}.txt"
    sahte_dosya = tmp_path / f"sahte_sonuc_{kim}.txt"
    if sahte is not None:
        sahte_dosya.write_text(sahte, encoding="utf-8-sig")  # Set-Content -Encoding UTF8 (5.1) gibi BOM'lu
    stub = tmp_path / f"schtasks_stub_{kim}.ps1"
    stub.write_text(
        _STUB.replace("__MOD__", senaryo)
        .replace("__KAYIT__", str(kayit))
        .replace("__KASAYOLU__", str(kasa_yolu))
        .replace("__KOPYA__", str(kopya))
        .replace("__ACL__", str(acl_dosya))
        .replace("__SAHTE__", str(sahte_dosya)),
        encoding="utf-8-sig",
    )
    surucu = tmp_path / f"surucu_{kim}.ps1"
    surucu.write_text(_SURUCU, encoding="utf-8-sig")
    log = tmp_path / f"log_{kim}.txt"
    # Hedefler DOSYA ile geçer: -File argümanı olarak ';'/'"' içeren metin kabuk tarafından bozulur.
    hedef_dosya = tmp_path / f"hedefler_{kim}.txt"
    hedef_dosya.write_text("\n".join(hedefler) + "\n", encoding="utf-8-sig")
    t0 = time.monotonic()
    args = [
        "-Teardown",
        str(_TEARDOWN),
        "-Senaryo",
        senaryo,
        "-HedefDosya",
        str(hedef_dosya),
        "-LogYolu",
        str(log),
        "-StubYolu",
        str(stub),
        "-ZamanAsimi",
        str(zaman),
    ]
    if kok:
        args += ["-Kok", kok]
    r = _ps(kabuk, "-File", str(surucu), *args)
    sure = time.monotonic() - t0
    assert r.returncode == 0, (
        f"sürücü başarısız (rc={r.returncode}, kabuk={kabuk}):\nSTDOUT:{r.stdout[-2000:]}\nSTDERR:{r.stderr[-2000:]}"
    )
    log_satirlar = log.read_text(encoding="utf-8-sig").splitlines() if log.exists() else []
    kayit_satirlar = kayit.read_text(encoding="utf-8-sig").splitlines() if kayit.exists() else []
    kasa = kopya.read_text(encoding="utf-8-sig") if kopya.exists() else None
    acl = (
        [ln[len("ACL=") :] for ln in acl_dosya.read_text(encoding="utf-8-sig").splitlines() if ln.startswith("ACL=")]
        if acl_dosya.exists()
        else []
    )
    calisma = None
    for ln in kayit_satirlar:
        m = re.search(r"-File\s+\"?(.+?)\\kasa\.ps1", ln)
        if m:
            calisma = Path(m.group(1))
            break
    return _Sonuc(r.stdout, log_satirlar, kayit_satirlar, kasa, calisma, sure, acl)


# ── (a) Mutlu yol: gerçek geçici kimlik silinir, var-olmayan 'yoktu', doğrulama KALAN=0 ──


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_a_mutlu_yol_kimlik_silinir_yoktu_raporlanir_gorev_temizlenir(tmp_path, kabuk):
    """kasa.ps1 (stub /Run ile mevcut kullanıcı olarak koşar) gerçek kaydı SİLER; log 'silindi'/'yoktu';
    PemfFailed 0; /Create → /Run → /Delete sırası; çalışma dizini kalmaz."""
    ad = f"PEMF_GATE_SYS_{uuid.uuid4().hex}@PEMF_GUI"
    yok = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    once = _kalinti_dizinler()
    try:
        # python-keyring de GENERIC kimlik yazar; cmdkey /generic ile aynı tür yaratılır.
        ekle = _cmdkey(f"/generic:{ad}", "/user:x", "/pass:y")
        assert ekle.returncode == 0, f"test ön-koşulu: cmdkey /generic başarısız: {ekle.stdout!r}"
        assert _kimlik_var(ad), "test ön-koşulu: yaratılan kimlik /list'te görünmüyor"
        assert not _kimlik_var(yok), "test ön-koşulu: rastgele ad zaten kasada?!"

        s = _kos(tmp_path, kabuk, "mutlu", [ad, yok])

        assert not _kimlik_var(ad), f"SYSTEM-kasası betiği (kasa.ps1) kimliği SİLMEDİ: {ad} hâlâ kasada\nLOG:{s.log}"
        assert any("SYSTEM kasası: kimlik silindi (KVKK)" in ln and ad in ln for ln in s.log), (
            f"'silindi' satırı yok:\n{s.log}"
        )
        assert any("SYSTEM kasası: kimlik yoktu" in ln and yok in ln for ln in s.log), (
            f"var-olmayan için 'yoktu' yok:\n{s.log}"
        )
        assert not any("silindi" in ln and yok in ln for ln in s.log), (
            "var-olmayan kimlik 'silindi' diye raporlandı (yanlış-güvence)"
        )
        assert not any("hâlâ duruyor" in ln for ln in s.log), f"KALAN>0 raporlandı ama kimlik silinmişti:\n{s.log}"
        ozet = [ln for ln in s.log if re.search(r"SYSTEM kasası: \d+ silindi / \d+ yoktu / \d+ hata \(kimlik: ", ln)]
        assert ozet, f"özet satırı ('<silindi>/<yoktu>/<hata> (kimlik: ...)') yok:\n{s.log}"
        assert "1 silindi / 1 yoktu / 0 hata" in ozet[0], f"özet sayımı yanlış: {ozet[0]}"
        assert any("görev kimliği" in ln and os.environ.get("USERNAME", "").lower() in ln.lower() for ln in s.log), (
            f"KIMLIK= satırı loglanmadı (stub mevcut kullanıcı olarak koşturur):\n{s.log}"
        )
        assert s.failed_count == 0, f"mutlu yol PemfFailed'i büyüttü: {s.failed}\nLOG:{s.log}"
        assert s.komutlar() == ["/Create", "/Run", "/Delete"], f"schtasks çağrı sırası yanlış: {s.kayit}"
        create = s.kayit[0]
        assert "/RU SYSTEM" in create and "/SC ONCE" in create and "/RL HIGHEST" in create and "/F" in create.split(), (
            f"/Create argümanları eksik: {create}"
        )
        assert "-File" in create and "PEMF_KimlikTemizlik_" in create, f"/TR kasa.ps1'i işaret etmiyor: {create}"
        assert re.search(r"System32\\WindowsPowerShell\\v1\.0\\powershell\.exe -NoProfile", create), (
            f"/TR yalın 'powershell.exe' kullanıyor — SYSTEM görevi de TAM YOL (PATH hijyeni) kullanmalı: {create}"
        )
        assert s.threw is None, f"fonksiyon fırlattı: {s.threw}"
        assert re.search(r"/TN PEMF-KimlikTemizle-[0-9a-f]{32}", create), f"görev adı biçimi: {create}"
        assert s.calisma is not None and str(s.calisma).lower().startswith(str(_PROGRAMDATA).lower()), (
            f"çalışma dizini ProgramData altında değil: {s.calisma}"
        )
        assert "PEMF_System" not in str(s.calisma), "çalışma dizini PEMF_System altında — 6. adım onu siler"
        assert not s.calisma.exists(), f"çalışma dizini geride kaldı: {s.calisma}"
        assert _kalinti_dizinler() - once == set(), "ProgramData'da PEMF_KimlikTemizlik_* kalıntısı"
        assert s.kasa and "KIMLIK=" in s.kasa and "cmdkey /list:" in s.kasa and "KALAN=" in s.kasa, (
            "kasa.ps1 doğrulama adımlarını içermiyor"
        )
    finally:
        _cmdkey(f"/delete:{ad}")  # kalıntı bırakma (zaten silinmişse exit 1 — zararsız)


# ── (b) /Create başarısız → PemfFailed + eylem söyleyen kırmızı; /Run YOK; dizin kalmaz ──


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_b_create_basarisiz_PemfFailed_buyur_Run_yapilmaz(tmp_path, kabuk):
    yok = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    s = _kos(tmp_path, kabuk, "create_fail", [yok])
    assert s.failed_count >= 1 and any("SYSTEM" in f for f in s.failed), (
        f"/Create hatası PemfFailed'e yazılmadı: {s.failed}\n{s.log}"
    )
    kirmizi = [ln for ln in s.log if ln.startswith("Red|") and "schtasks /Create" in ln]
    assert kirmizi, f"/Create hatası için kırmızı satır yok:\n{s.log}"
    assert "Access is denied" in kirmizi[0], "hata satırı schtasks çıktısını (NE oldu) taşımıyor"
    assert "yükseltilmiş PowerShell" in kirmizi[0] and "/RU SYSTEM" in kirmizi[0], (
        "hata satırı NE YAPILMALI (elle komut) demiyor"
    )
    assert "/Run" not in s.komutlar(), f"/Create başarısızken /Run çağrıldı: {s.kayit}"
    assert "/Delete" not in s.komutlar(), f"oluşmamış görev için /Delete çağrıldı: {s.kayit}"
    assert s.calisma is not None and not s.calisma.exists(), f"çalışma dizini geride kaldı: {s.calisma}"
    assert not any("silindi" in ln and yok in ln for ln in s.log), "hiçbir şey koşmadan 'silindi' raporlandı"


# ── (c) /Run yutulur → zaman aşımı → PemfFailed; /Delete yine de çağrılır; dizin kalmaz ──


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_c_zaman_asimi_PemfFailed_buyur_Delete_yine_de_yapilir(tmp_path, kabuk):
    """MUTASYON: zaman-aşımı dalı PemfFailed'e dokunmazsa bu test KIRMIZI olur (rapor 'tam temizlik' derdi)."""
    yok = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    s = _kos(tmp_path, kabuk, "run_ignore", [yok], zaman=2)
    assert s.failed_count >= 1, f"zaman aşımı PemfFailed'e yazılmadı → rapor 'tam temizlik' der:\n{s.stdout}\n{s.log}"
    assert any("bitmedi" in f for f in s.failed), f"PemfFailed girdisi zaman aşımını anlatmıyor: {s.failed}"
    kirmizi = [ln for ln in s.log if ln.startswith("Red|") and "sonuç yazmadı" in ln]
    assert kirmizi, f"zaman aşımı için kırmızı satır yok:\n{s.log}"
    assert "yükseltilmiş PowerShell" in kirmizi[0], "zaman-aşımı satırı elle komutu (NE YAPILMALI) söylemiyor"
    assert s.komutlar() == ["/Create", "/Run", "/Delete"], f"zaman aşımında görev SİLİNMEDİ (finally): {s.kayit}"
    assert s.calisma is not None and not s.calisma.exists(), f"çalışma dizini geride kaldı: {s.calisma}"
    assert s.sure >= 2.0, f"zaman aşımı beklenmedi (sure={s.sure:.1f}s < 2s)"
    assert not any(ln.startswith("Green|") for ln in s.log), "zaman aşımında yeşil özet basıldı"


# ── (d) Yükseltilmemiş oturum → PemfFailed; schtasks HİÇ çağrılmaz ──


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_d_yukseltilmemis_oturum_schtasks_cagirmaz_PemfFailed_buyur(tmp_path, kabuk):
    yok = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    once = _kalinti_dizinler()
    s = _kos(tmp_path, kabuk, "yukseltilmemis", [yok])
    assert s.failed_count == 1 and "yükseltilmiş" in s.failed[0], f"PemfFailed 'yükseltilmiş' demiyor: {s.failed}"
    assert s.kayit == [], f"yükseltilmemişken schtasks çağrıldı: {s.kayit}"
    kirmizi = [ln for ln in s.log if ln.startswith("Red|") and "yükseltilmiş" in ln]
    assert kirmizi, f"kırmızı 'yükseltilmiş' satırı yok:\n{s.log}"
    assert "yeniden çalıştırın" in kirmizi[0], "satır NE YAPILMALI demiyor"
    assert _kalinti_dizinler() - once == set(), "yükseltilmemişken çalışma dizini yaratıldı"


# ── (e) -DryRun → schtasks çağrılmaz, '[DRY]' loglanır ──


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_e_dry_run_schtasks_cagirmaz_DRY_loglar(tmp_path, kabuk):
    yok = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    once = _kalinti_dizinler()
    s = _kos(tmp_path, kabuk, "dry", [yok])
    assert s.kayit == [], f"DryRun schtasks çağırdı: {s.kayit}"
    assert any("[DRY] SYSTEM kasası" in ln and yok in ln for ln in s.log), f"'[DRY] SYSTEM kasası' satırı yok:\n{s.log}"
    assert s.failed_count == 0, f"DryRun PemfFailed'i büyüttü: {s.failed}"
    assert not any("silindi" in ln for ln in s.log), "DryRun 'silindi' raporladı"
    assert _kalinti_dizinler() - once == set(), "DryRun çalışma dizini yarattı"


# ── (f) Geçersiz hedef adı → reddedilir, kasa.ps1'e ASLA gömülmez (betik-enjeksiyonu savunması) ──


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_f_gecersiz_hedef_adi_reddedilir_ve_kasa_ps1e_gomulmez(tmp_path, kabuk):
    kotu = 'a"b&c'
    yok = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    s = _kos(tmp_path, kabuk, "mutlu", [kotu, yok])
    assert any("geçersiz ad" in f and kotu in f for f in s.failed), f"geçersiz ad PemfFailed'e yazılmadı: {s.failed}"
    assert any(ln.startswith("Red|") and "GEÇERSİZ hedef adı" in ln for ln in s.log), (
        f"geçersiz ad için kırmızı satır yok:\n{s.log}"
    )
    assert s.kasa is not None, f"geçerli hedef varken kasa.ps1 üretilmedi: {s.kayit}"
    assert kotu not in s.kasa and "b&c" not in s.kasa, "geçersiz hedef adı kasa.ps1'e GÖMÜLDÜ (enjeksiyon)"
    assert yok in s.kasa, "geçerli hedef kasa.ps1'de yok"
    assert any("SYSTEM kasası: kimlik yoktu" in ln and yok in ln for ln in s.log), f"geçerli hedef işlenmedi:\n{s.log}"


# ── (g) 5.1 parse kapıları: pemf_teardown.ps1 ve ÜRETİLEN kasa.ps1 Windows PowerShell 5.1'de parse eder ──


def _ps51_parse_hatalari(dosya: Path) -> list[str]:
    r = _ps(
        _PS51,
        "-Command",
        "$t=$null;$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('"
        + str(dosya).replace("'", "''")
        + "',[ref]$t,[ref]$e); \"ERR_COUNT=$($e.Count)\"; foreach($x in $e){ \"ERR=$($x.Message)\" }",
    )
    assert r.returncode == 0, f"powershell.exe parse çağrısı başarısız: {r.stderr[-800:]}"
    assert "ERR_COUNT=" in r.stdout, f"parse çıktısı beklenmedik: {r.stdout[-800:]}"
    return [ln for ln in r.stdout.splitlines() if ln.startswith("ERR=")]


def test_KRITIK_g_teardown_ps1_Windows_PowerShell_51de_parse_eder():
    """Inno üretimde powershell.exe (5.1) çağırır — pwsh'te geçen ama 5.1'de kırılan sözdizimi kaldırıcıyı öldürür."""
    hatalar = _ps51_parse_hatalari(_TEARDOWN)
    assert hatalar == [], f"pemf_teardown.ps1 Windows PowerShell 5.1'de parse HATASI: {hatalar}"


def test_KRITIK_g_uretilen_kasa_ps1_Windows_PowerShell_51de_parse_eder(tmp_path):
    """SYSTEM görevi kasa.ps1'i powershell.exe (5.1) ile koşturur → üretilen betik 5.1'de parse ETMELİ."""
    yok = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    s = _kos(tmp_path, _PWSH, "mutlu", [yok])
    assert s.kasa is not None, "kasa.ps1 üretilmedi"
    kasa = tmp_path / "kasa_51_parse.ps1"
    kasa.write_text(s.kasa, encoding="utf-8-sig")
    hatalar = _ps51_parse_hatalari(kasa)
    assert hatalar == [], f"üretilen kasa.ps1 5.1'de parse HATASI: {hatalar}\n---\n{s.kasa}"
    # try/catch + HATA= + BITTI: ana betik çökmüş SYSTEM betiğini beklemesin.
    assert "try {" in s.kasa and "} catch {" in s.kasa and "'HATA='" in s.kasa and "'BITTI'" in s.kasa, s.kasa
    assert "-Encoding UTF8" in s.kasa


# ── (h) AST yapısal kapı: orkestratör çağrıyı -IncludePatientData altında, -DryRun geçirerek yapar ──

_AST_KAPI = r"""
param([string]$Teardown)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Teardown, [ref]$tokens, [ref]$errs)
if ($errs) { throw "parse hatası" }
$ork = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Invoke-PemfTeardown' }, $true) | Select-Object -First 1
if (-not $ork) { "ORK=0"; exit 0 }
"ORK=1"
$cmds = $ork.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Remove-PemfSystemCredentials' }, $true)
"CALL_COUNT=$(@($cmds).Count)"
$eski = $ork.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Remove-PemfCredentials' }, $true) | Select-Object -First 1
foreach ($c in $cmds) {
    $p = $c.Parent; $if = $null
    while ($p -and $p -ne $ork) { if ($p -is [System.Management.Automation.Language.IfStatementAst]) { $if = $p; break }; $p = $p.Parent }
    if ($if) { "IF_COND=$($if.Clauses[0].Item1.Extent.Text)" } else { "IF_COND=<yok>" }
    $dry = $c.CommandElements | Where-Object { $_ -is [System.Management.Automation.Language.CommandParameterAst] -and $_.ParameterName -eq 'DryRun' } | Select-Object -First 1
    if ($dry -and $dry.Argument) { "DRY_ARG=$($dry.Argument.Extent.Text)" } elseif ($dry) { "DRY_ARG=<argümansız>" } else { "DRY_ARG=<yok>" }
    # -TargetNames <değer>: değer AYRI CommandElement (yalnız -Param:değer biçiminde .Argument dolar).
    $el = @($c.CommandElements); $tnArg = '<yok>'
    for ($k = 0; $k -lt $el.Count - 1; $k++) {
        if ($el[$k] -is [System.Management.Automation.Language.CommandParameterAst] -and $el[$k].ParameterName -eq 'TargetNames') {
            if ($el[$k].Argument) { $tnArg = $el[$k].Argument.Extent.Text } else { $tnArg = $el[$k + 1].Extent.Text }
        }
    }
    "TN_ARG=$tnArg"
    if ($eski) { "AFTER_STEP7=$([int]($c.Extent.StartOffset -gt $eski.Extent.StartOffset))" } else { "AFTER_STEP7=<step7yok>" }
}
"""


def test_KRITIK_h_orkestrator_SYSTEM_kasasini_IncludePatientData_altinda_DryRun_gecirerek_cagirir(tmp_path):
    """MUTASYON: Invoke-PemfTeardown'daki çağrı silinirse CALL_COUNT=0 → KIRMIZI."""
    kapi = tmp_path / "ast_kapi.ps1"
    kapi.write_text(_AST_KAPI, encoding="utf-8-sig")
    r = _ps(_PWSH, "-File", str(kapi), "-Teardown", str(_TEARDOWN))
    assert r.returncode == 0, f"AST kapısı koşmadı: {r.stderr[-800:]}"
    out = r.stdout
    assert "ORK=1" in out, "Invoke-PemfTeardown bulunamadı (çıpa kaymış)"
    m = re.search(r"CALL_COUNT=(\d+)", out)
    assert m and int(m.group(1)) == 1, (
        "Invoke-PemfTeardown içinde Remove-PemfSystemCredentials çağrısı tam 1 kez beklenirdi — "
        f"fonksiyon var olabilir ama ÇAĞRILMIYORSA SYSTEM kasası yine temizlenmez:\n{out}"
    )
    assert re.search(r"IF_COND=.*IncludePatientData", out), (
        f"çağrı -IncludePatientData koşulu altında değil (KVKK varsayılan-koruma):\n{out}"
    )
    assert "DRY_ARG=$DryRun" in out, f"çağrı -DryRun:$DryRun geçirmiyor → önizleme SYSTEM kasasına dokunur:\n{out}"
    assert "TN_ARG=$fp.Credentials" in out, f"çağrı footprint Credentials listesini geçirmiyor:\n{out}"
    assert "AFTER_STEP7=1" in out, f"çağrı 7. adım (Remove-PemfCredentials) sonrasında değil:\n{out}"


def test_h_bildirimler_zaman_asimi_60_ve_schtasks_tam_yol(tmp_path):
    """$script: bildirimleri: zaman aşımı varsayılanı 60 sn; schtasks SystemRoot altından TAM YOL (PATH hijyeni);
    çalışma dizini kökü varsayılan $env:ProgramData."""
    yok = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    s = _kos(tmp_path, _PWSH, "dry", [yok])
    assert "DECL_PemfSystemKasaZamanAsimiSn=60" in s.stdout, s.stdout
    m = re.search(r"DECL_PemfSchtasksYolu=(.+)", s.stdout)
    assert m and "SystemRoot" in m.group(1) and "schtasks.exe" in m.group(1), s.stdout
    assert "DECL_PemfKimlikTemizlikKoku=$env:ProgramData" in s.stdout, s.stdout


# ── (j) SONUC.TXT AYRIŞTIRMA / KVKK DOĞRULAMA DALLARI — fonksiyonun VAR OLMA nedeni ──
# Stub 'sahte_sonuc' modunda kasa.ps1'i KOŞTURMAZ; hazır sonuc.txt koyar. Böylece cmdkey'in gerçek
# davranışıyla üretilemeyen durumlar (SYSTEM kasasında kimlik DURUYOR, rc≠0, HATA=, KALAN yok) ölçülür.
# Bulgu (2 bağımsız inceleme, 2026-09-06): bu dallar kapısızdı — `-gt 0` → `-gt 999` mutasyonu YEŞİL kalıyordu.


def _sahte(satirlar: list[str]) -> str:
    return "\r\n".join(satirlar) + "\r\n"


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_j_KALAN_buyuk_sifir_ve_rc_sifir_degil_PemfFailed_buyur_yesil_ozet_yok(tmp_path, kabuk):
    """SYSTEM betiği 'KALAN=1' (kimlik hâlâ duruyor) + bir hedefte rc=1 'Access is denied' yazarsa:
    PemfFailed 'hâlâ duruyor' (adla) + 'SYSTEM kimlik: <t1>'; 'yoktu' olan yalnız t2; YEŞİL özet YOK;
    kırmızı satırlar elle komutu taşır ve elle komut YALNIZ duran adı sayar; /Delete yine de kaydedilir.
    MUTASYON: `if ($kalan -gt 0)` → `-gt 999` ⇒ bu test KIRMIZI."""
    t1 = f"PEMF_GATE_DURAN_{uuid.uuid4().hex}@PEMF_GUI"
    t2 = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    sahte = _sahte(
        [
            r"KIMLIK=NT AUTHORITY\SYSTEM",
            f"{t1}=1|Access is denied.",
            f"{t2}=1|Eleman bulunamadı.",
            f"KALANLAR={t1}",
            "KALAN=1",
            "BITTI",
        ]
    )
    s = _kos(tmp_path, kabuk, "sahte_sonuc", [t1, t2], sahte=sahte)
    assert s.threw is None, f"fonksiyon fırlattı: {s.threw}"
    assert any("hâlâ duruyor" in f for f in s.failed), (
        f"KALAN=1 iken PemfFailed 'hâlâ duruyor' içermiyor → rapor 'tam temizlik' der (KVKK sahte kanıt): {s.failed}\nLOG:{s.log}"
    )
    assert any("hâlâ duruyor" in f and t1 in f for f in s.failed), f"KALANLAR adı PemfFailed'e taşınmadı: {s.failed}"
    assert any(f == f"SYSTEM kimlik: {t1}" for f in s.failed), (
        f"rc=1 hedef 'SYSTEM kimlik: <t>' olarak PemfFailed'e yazılmadı: {s.failed}"
    )
    assert any("SYSTEM kasası: kimlik yoktu" in ln and t2 in ln for ln in s.log), (
        f"'bulunamadı' hedef 'yoktu' değil:\n{s.log}"
    )
    assert not any("silindi" in ln and (t1 in ln or t2 in ln) for ln in s.log), (
        f"hiçbir şey silinmemişken 'silindi':\n{s.log}"
    )
    assert not any(ln.startswith("Green|") for ln in s.log), f"KALAN=1 iken YEŞİL özet basıldı:\n{s.log}"
    ozet = [ln for ln in s.log if re.search(r"SYSTEM kasası: \d+ silindi / \d+ yoktu / \d+ hata", ln)]
    assert ozet and ozet[0].startswith("Red|") and "0 silindi / 1 yoktu / 1 hata" in ozet[0], (
        f"özet yanlış/kırmızı değil: {ozet}"
    )
    duran = [ln for ln in s.log if ln.startswith("Red|") and "hâlâ SYSTEM kasasında DURUYOR" in ln]
    assert duran, f"KALAN>0 için kırmızı satır yok:\n{s.log}"
    assert "yükseltilmiş PowerShell" in duran[0] and "/RU SYSTEM" in duran[0], (
        "KALAN satırı elle komutu (NE YAPILMALI) taşımıyor"
    )
    adlar = duran[0].split("adlar:", 1)[1]
    assert t1 in adlar and t2 not in adlar, (
        f"elle komut yalnız DURAN adı saymalı (operatör hangisini koşturacağını bilsin): {duran[0]}"
    )
    assert any("görev kimliği" in ln and "SYSTEM" in ln for ln in s.log), "KIMLIK= satırı loglanmadı"
    assert s.komutlar() == ["/Create", "/Run", "/Delete"], f"görev temizlenmedi (finally): {s.kayit}"
    assert s.calisma is not None and not s.calisma.exists(), f"çalışma dizini geride kaldı: {s.calisma}"


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_j_HATA_satiri_PemfFailed_buyur(tmp_path, kabuk):
    """SYSTEM betiği çöküp 'HATA=boom' yazarsa: PemfFailed 'SYSTEM betiği hatası: boom'; yeşil yok; elle komut var."""
    t = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    s = _kos(tmp_path, kabuk, "sahte_sonuc", [t], sahte=_sahte([r"KIMLIK=NT AUTHORITY\SYSTEM", "HATA=boom", "BITTI"]))
    assert s.threw is None, f"fonksiyon fırlattı: {s.threw}"
    assert any("SYSTEM betiği hatası: boom" in f for f in s.failed), (
        f"HATA= PemfFailed'e yazılmadı: {s.failed}\n{s.log}"
    )
    kirmizi = [ln for ln in s.log if ln.startswith("Red|") and "SYSTEM betiği hata verdi: boom" in ln]
    assert kirmizi and "yükseltilmiş PowerShell" in kirmizi[0], f"HATA= için eylemli kırmızı satır yok:\n{s.log}"
    assert not any(ln.startswith("Green|") for ln in s.log), "HATA= iken yeşil özet"
    assert s.komutlar() == ["/Create", "/Run", "/Delete"], s.kayit


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_j_KALAN_yazilmadi_dogrulama_yok_PemfFailed_buyur(tmp_path, kabuk):
    """KALAN satırı hiç gelmezse (doğrulama koşmadı) 'tam temizlik' DENMEZ: PemfFailed 'doğrulama (KALAN) yazılmadı'."""
    t = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    s = _kos(
        tmp_path,
        kabuk,
        "sahte_sonuc",
        [t],
        sahte=_sahte([r"KIMLIK=NT AUTHORITY\SYSTEM", f"{t}=1|Eleman bulunamadı.", "BITTI"]),
    )
    assert s.threw is None, f"fonksiyon fırlattı: {s.threw}"
    assert any("doğrulama (KALAN) yazılmadı" in f for f in s.failed), (
        f"KALAN yokken PemfFailed büyümedi: {s.failed}\n{s.log}"
    )
    assert not any(ln.startswith("Green|") for ln in s.log), "doğrulama yokken yeşil özet"
    assert any(
        ln.startswith("Red|") and "KALAN satırı yazmadı" in ln and "yükseltilmiş PowerShell" in ln for ln in s.log
    ), s.log


# ── (k) ACL: çalışma dizini SYSTEM + Administrators + çağıran dışında KİMSEYE açık değil ──
# Ölçüm (2026-09-06): ProgramData altında yeni klasör BUILTIN\Users (S-1-5-32-545) '(CI)(WD,AD)' mirası alır →
# standart yerel kullanıcı sonuc.txt'yi SYSTEM görevinden ÖNCE sahte içerikle yaratabilirdi (sahte KVKK kanıtı).
# MUTASYON: icacls satırı silinirse bu test KIRMIZI.


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_k_calisma_dizini_ACL_miras_kesik_yalniz_SYSTEM_Administrators_cagiran(tmp_path, kabuk):
    t = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    s = _kos(tmp_path, kabuk, "mutlu", [t])
    assert s.acl, f"stub /Create'te ACL kaydetmedi: {s.kayit}"
    sidler = {ln.split("|")[0] for ln in s.acl}
    miras = [ln for ln in s.acl if ln.split("|")[1].lower() == "true"]
    assert miras == [], (
        f"çalışma dizini ACL MİRASI kesilmemiş → BUILTIN\\Users sonuc.txt'yi SYSTEM'den önce sahte yaratabilir: {s.acl}"
    )
    assert "S-1-5-32-545" not in sidler and "S-1-5-11" not in sidler and "S-1-1-0" not in sidler, (
        f"Users / Authenticated Users / Everyone çalışma dizininde: {s.acl}"
    )
    assert "S-1-5-18" in sidler and "S-1-5-32-544" in sidler, (
        f"SYSTEM ve Administrators ACE'leri yok (SYSTEM görevi yazamaz): {s.acl}"
    )
    izinli = {"S-1-5-18", "S-1-5-32-544", _mevcut_kullanici_sid()}
    assert sidler <= izinli, f"beklenmeyen ACE: {sidler - izinli} — {s.acl}"
    assert s.failed_count == 0 and any("SYSTEM kasası: kimlik yoktu" in ln for ln in s.log), (
        f"ACL kilidi sonrası akış bozuldu: {s.failed}\n{s.log}"
    )


def _mevcut_kullanici_sid() -> str:
    r = _ps(_PWSH, "-Command", "[Security.Principal.WindowsIdentity]::GetCurrent().User.Value")
    return r.stdout.strip()


# ── (l) Çağıran EAP=Stop + schtasks stderr UYARISI (gerçek /ST 00:00 davranışı) → mutlu yol 5.1'de de biter ──
# Ölçüm (2026-09-06, 5.1): `(& schtasks ... 2>&1)` Stop altında 'WARNING: Task may not run...' ile FIRLATIR.
# MUTASYON: fonksiyon başındaki `$ErrorActionPreference = 'Continue'` silinirse ps51 varyantı KIRMIZI.


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_l_cagiran_EAP_Stop_iken_schtasks_stderr_uyarisi_mutlu_yolu_dusurmez(tmp_path, kabuk):
    t = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    s = _kos(tmp_path, kabuk, "stderr_warn", [t])
    assert s.threw is None, (
        "çağıran $ErrorActionPreference='Stop' iken schtasks'ın stderr UYARISI fonksiyonu fırlattı → kaldırıcı çöker, "
        f"özet rapor yazılmaz. Fonksiyon EAP'yi yerel 'Continue' yapmalı: {s.threw}\nLOG:{s.log}"
    )
    assert s.failed_count == 0, f"stderr uyarısı başarısızlık sayıldı: {s.failed}\n{s.log}"
    assert s.komutlar() == ["/Create", "/Run", "/Delete"], s.kayit
    assert any("SYSTEM kasası: kimlik yoktu" in ln and t in ln for ln in s.log), s.log
    assert s.calisma is not None and not s.calisma.exists(), "çalışma dizini geride kaldı"


# ── (m) Hazırlık başarısız (kök yazılamaz) → /Create'e HİÇ gidilmez; PemfFailed 'hazırlık' + elle komut ──


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_m_calisma_dizini_kurulamazsa_gorev_olusturulmaz_PemfFailed_buyur(tmp_path, kabuk):
    """Kök bir DOSYA'ya işaret ediyorsa (dizin açılamaz) → SYSTEM'e var olmayan betiği işaret eden görev
    yaratılıp 60 sn beklenmez; hata 'Görev Zamanlayıcı kapalı' diye YANLIŞ teşhis edilmez."""
    kok_dosya = tmp_path / "kok_bir_dosya.txt"
    kok_dosya.write_text("dizin degil", encoding="utf-8")
    t = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    s = _kos(tmp_path, kabuk, "mutlu", [t], kok=str(kok_dosya))
    assert s.threw is None, f"fonksiyon fırlattı: {s.threw}"
    assert any("hazırlık" in f for f in s.failed), f"hazırlık hatası PemfFailed'e yazılmadı: {s.failed}\n{s.log}"
    assert s.kayit == [], f"çalışma dizini kurulamadan schtasks çağrıldı (yanlış teşhis + 60 sn): {s.kayit}"
    kirmizi = [ln for ln in s.log if ln.startswith("Red|") and "hazırlanamadı" in ln]
    assert kirmizi and "yükseltilmiş PowerShell" in kirmizi[0], (
        f"hazırlık hatası için eylemli kırmızı satır yok:\n{s.log}"
    )
    assert s.sure < 30, f"hazırlık hatasında zaman aşımı beklendi (sure={s.sure:.1f}s)"


# ── (n) Boşluklu kök: /TR'ye ASLA tırnaklı-boşluklu yol gitmez — ya 8.3 kısa ad ya dürüst başarısızlık ──


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_n_bosluklu_kok_TRde_bosluklu_yol_yok_kisa_ad_veya_durust_basarisizlik(tmp_path, kabuk):
    """5.1 gömülü çift tırnağı bozuk aktarır → boşluklu /TR ile görev 'başarılı' görünür, 60 sn sonra zaman
    aşımı. Kabul edilen iki davranış: (1) 8.3 kısa ad (boşluksuz) ile stub kasa.ps1'i çözer ve mutlu yol biter;
    (2) 8.3 yoksa /Create'e gidilmeden PemfFailed 'boşluklu'. YASAK: boşluk içeren /TR."""
    kok = tmp_path / "pemf bosluklu kok"
    kok.mkdir()
    t = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    s = _kos(tmp_path, kabuk, "mutlu", [t], kok=str(kok))
    assert s.threw is None, f"fonksiyon fırlattı: {s.threw}"
    creates = [ln for ln in s.kayit if ln.startswith("/Create")]
    if creates:
        m = re.search(r"/TR (.+)$", creates[0])
        assert m, creates[0]
        tr = m.group(1)
        assert '"' not in tr, f"/TR tırnaklı yol taşıyor — 5.1'de bozuk aktarılır: {tr}"
        yol = tr.split("-File", 1)[1].strip()
        assert " " not in yol, f"/TR'deki kasa.ps1 yolu boşluklu — 8.3 kısa ad kullanılmalıydı: {tr}"
        assert "~" in yol, f"boşluklu kökte 8.3 kısa ad beklenirdi: {tr}"
        assert s.failed_count == 0 and any("SYSTEM kasası: kimlik yoktu" in ln and t in ln for ln in s.log), (
            f"kısa-ad yolu ile stub kasa.ps1'i koşturamadı: {s.failed}\n{s.log}"
        )
        assert s.komutlar() == ["/Create", "/Run", "/Delete"], s.kayit
    else:
        assert any("boşluklu" in f for f in s.failed), (
            f"/Create yok ama PemfFailed 'boşluklu' demiyor: {s.failed}\n{s.log}"
        )
        assert any(ln.startswith("Red|") and "8.3" in ln and "yükseltilmiş PowerShell" in ln for ln in s.log), s.log
    assert not list(kok.glob("PEMF_KimlikTemizlik_*")), "boşluklu kökte çalışma dizini kalıntısı"


# ── (e2) -DryRun geçersiz adı da gösterir (önizleme = gerçek koşu); boş liste iz bırakır ──


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_e2_dry_run_gecersiz_adi_reddeder_gecerliyi_listeler_schtasks_yok(tmp_path, kabuk):
    kotu = 'a"b&c'
    yok = f"PEMF_GATE_YOK_{uuid.uuid4().hex}@PEMF_GUI"
    s = _kos(tmp_path, kabuk, "dry", [kotu, yok])
    assert s.kayit == [], f"DryRun schtasks çağırdı: {s.kayit}"
    assert any("geçersiz ad" in f and kotu in f for f in s.failed), (
        f"DryRun geçersiz adı göstermedi (önizleme ≠ gerçek koşu): {s.failed}"
    )
    dry = [ln for ln in s.log if "[DRY] SYSTEM kasası" in ln]
    assert dry and yok in dry[0] and kotu not in dry[0], f"[DRY] satırı yalnız GEÇERLİ adları listelemeli: {dry}"


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_e2_bos_hedef_listesi_log_izi_birakir_schtasks_yok(tmp_path, kabuk):
    s = _kos(tmp_path, kabuk, "mutlu", [])
    assert s.kayit == [] and s.failed_count == 0, (s.kayit, s.failed)
    assert any("hedef yok, atlandı" in ln for ln in s.log), f"boş listede 8. adımın koştuğuna dair iz yok:\n{s.log}"


def test_h_Remove_PemfCredentials_NOTu_SYSTEM_kasasinin_sonraki_adimda_temizlendigini_soyler():
    """Sarı NOT artık 'ayrıca/psexec ile elle' DEMEZ; sonraki adımı gösterir (operatör yanlış işe kalkışmasın)."""
    kaynak = _TEARDOWN.read_text(encoding="utf-8-sig")
    i = kaynak.find("function Remove-PemfCredentials")
    assert i != -1, "Remove-PemfCredentials bulunamadı (çıpa kaymış)"
    notlar = [ln for ln in kaynak[i:].splitlines() if "Write-PemfLog" in ln and "NOT: cmdkey yalnız" in ln]
    assert len(notlar) == 1, "Remove-PemfCredentials içindeki Sarı NOT satırı bulunamadı (çıpa kaymış)"
    n = notlar[0]
    assert "Remove-PemfSystemCredentials" in n and "SONRAKİ adımda" in n, f"NOT sonraki adımı göstermiyor: {n}"
    assert "psexec" not in n, f"NOT hâlâ psexec ile elle temizlik istiyor — artık otomatik: {n}"
    assert "cmdkey yalnız '$env:USERNAME' kasasını görür" in n, f"kapsam-sınırı gerçeği NOT'tan düşmüş: {n}"


# ── (i) EKSTRA: GERÇEK SYSTEM entegrasyonu — yalnız yükseltilmiş oturum + PEMF_SYSTEM_KASA_TESTI=1 ──

_GERCEK_SYSTEM = r"""
param([string]$Teardown, [string]$Hedef, [string]$LogYolu)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Teardown, [ref]$tokens, [ref]$errs)
foreach ($ad in 'Remove-PemfSystemCredentials', 'Test-PemfYukseltilmis') {
    $fn = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $ad }, $true) | Select-Object -First 1
    Invoke-Expression $fn.Extent.Text
}
$script:PemfFailed = @()
$script:PemfSystemKasaZamanAsimiSn = 60
$script:PemfSchtasksYolu = Join-Path $env:SystemRoot 'System32\schtasks.exe'
function Write-PemfLog($msg, $color = 'Gray') { Add-Content -LiteralPath $LogYolu -Value "$color|$msg" -Encoding UTF8 }
$ErrorActionPreference = 'Continue'
Remove-PemfSystemCredentials -TargetNames @($Hedef)
"FAILED_COUNT=$($script:PemfFailed.Count)"
foreach ($f in $script:PemfFailed) { "FAILED=$f" }
"""


def _system_gorevi_kos(tn: str, komut: str, bekle_dosya: Path, timeout: float = 30.0) -> str:
    """Tek-seferlik /RU SYSTEM görevi ile <komut> koştur; bekle_dosya oluşana kadar bekle; içeriğini döndür."""
    exe = str(Path(os.environ["SystemRoot"]) / "System32" / "schtasks.exe")
    try:
        r = subprocess.run(
            [
                exe,
                "/Create",
                "/TN",
                tn,
                "/RU",
                "SYSTEM",
                "/SC",
                "ONCE",
                "/ST",
                "00:00",
                "/F",
                "/RL",
                "HIGHEST",
                "/TR",
                komut,
            ],
            capture_output=True,
            timeout=30,
        )
        assert r.returncode == 0, f"SYSTEM görevi oluşturulamadı: {r.stdout!r} {r.stderr!r}"
        r = subprocess.run([exe, "/Run", "/TN", tn], capture_output=True, timeout=30)
        assert r.returncode == 0, f"SYSTEM görevi başlatılamadı: {r.stdout!r}"
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if bekle_dosya.exists():
                time.sleep(0.5)
                return bekle_dosya.read_text(encoding="utf-8", errors="replace")
            time.sleep(0.5)
        raise AssertionError(f"SYSTEM görevi {timeout}s içinde {bekle_dosya} yazmadı")
    finally:
        subprocess.run([exe, "/Delete", "/TN", tn, "/F"], capture_output=True, timeout=30)


@pytest.mark.skipif(
    not (_yukseltilmis() and os.environ.get("PEMF_SYSTEM_KASA_TESTI") == "1"),
    reason="gerçek SYSTEM entegrasyonu: yükseltilmiş oturum + PEMF_SYSTEM_KASA_TESTI=1 gerekir",
)
def test_EKSTRA_i_gercek_SYSTEM_kasasindaki_kimlik_silinir(tmp_path):
    """SYSTEM olarak kimlik yarat → gerçek fonksiyon (gerçek schtasks) → SYSTEM bağlamında /list ile doğrula."""
    ad = f"PEMF_GATE_REALSYS_{uuid.uuid4().hex}@PEMF_GUI"
    calisma = _PROGRAMDATA / f"PEMF_KimlikTemizlik_TEST_{uuid.uuid4().hex}"
    calisma.mkdir(parents=True)
    try:
        ekle_iz = calisma / "ekle.txt"
        cikti = _system_gorevi_kos(
            f"PEMF-Test-Ekle-{uuid.uuid4().hex}",
            f'cmd /c "cmdkey /generic:{ad} /user:x /pass:y > "{ekle_iz}" 2>&1"',
            ekle_iz,
        )
        assert "success" in cikti.lower() or "başarı" in cikti.lower(), f"SYSTEM olarak kimlik eklenemedi: {cikti}"
        assert not _kimlik_var(ad), "kimlik yönetici kasasında görünüyor — test SYSTEM kasasını ölçmüyor"

        surucu = tmp_path / "gercek_system.ps1"
        surucu.write_text(_GERCEK_SYSTEM, encoding="utf-8-sig")
        log = tmp_path / "gercek_system.log"
        r = _ps(_PWSH, "-File", str(surucu), "-Teardown", str(_TEARDOWN), "-Hedef", ad, "-LogYolu", str(log))
        assert r.returncode == 0, r.stderr[-1500:]
        satirlar = log.read_text(encoding="utf-8-sig").splitlines()
        assert "FAILED_COUNT=0" in r.stdout, f"{r.stdout}\n{satirlar}"
        assert any("SYSTEM kasası: kimlik silindi (KVKK)" in ln and ad in ln for ln in satirlar), satirlar
        assert any("görev kimliği" in ln and "SYSTEM" in ln.upper() for ln in satirlar), (
            f"KIMLIK= satırı SYSTEM değil:\n{satirlar}"
        )

        liste_iz = calisma / "liste.txt"
        cikti = _system_gorevi_kos(
            f"PEMF-Test-Liste-{uuid.uuid4().hex}",
            f'cmd /c "cmdkey /list:{ad} > "{liste_iz}" 2>&1"',
            liste_iz,
        )
        assert cikti.count(ad) < 2, f"kimlik SYSTEM kasasında hâlâ duruyor:\n{cikti}"
    finally:
        sil_iz = calisma / "sil.txt"
        try:
            _system_gorevi_kos(
                f"PEMF-Test-Sil-{uuid.uuid4().hex}",
                f'cmd /c "cmdkey /delete:{ad} > "{sil_iz}" 2>&1"',
                sil_iz,
                timeout=15,
            )
        except Exception:
            pass
        shutil.rmtree(calisma, ignore_errors=True)
