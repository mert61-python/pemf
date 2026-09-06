# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KİMLİK (Credential Manager) SİLME SONUCU DOĞRULANIR — denetim 2026-09-06.

`scripts/pemf_teardown.ps1::Remove-PemfCredentials` şunu yapıyordu:

    & cmdkey /delete:$c *>$null; Write-PemfLog "kimlik silindi (KVKK): $c"

KOŞULSUZ. cmdkey hedef yoksa exit 1 döner ("Eleman bulunamadı" — bu makinede ölçüldü),
`$LASTEXITCODE` hiç okunmuyor, `$script:PemfFailed`e dokunulmuyordu → KVKK "tam temizlik"
raporu, hiçbir şey silinmemişken "kimlik silindi" diyordu. Ağırlaştırıcı: footprint listesi
'fernet_key@PEMF_GUI' derken runtime 'patient_fernet_key' yazar (utils/secrets_manager.py
`_keyring_get("patient_fernet_key")`) — yani o kayıt HİÇBİR koşuda silinemezdi ve her koşu
sahte "silindi" üretiyordu.

Bu dosya iki şeyi ÖLÇER (metin grep'i değil, davranış):
  1. Remove-PemfCredentials gerçek pwsh'te, GERÇEK bir geçici kimlikle: silinen → "silindi";
     var-olmayan → "yoktu" (başarısızlık DEĞİL); cmdkey başka hata → PemfFailed büyür + "SİLİNEMEDİ".
  2. pemf_footprint.ps1 Credentials listesi (pwsh'te değerlendirilir) runtime'ın keyring'e
     yazdığı/okuduğu HER adı "<ad>@PEMF_GUI" biçiminde içerir.

Çalıştırma: yalnız Windows + pwsh (cmdkey Windows'a özgü). Fonksiyon AST ile ÇIKARILIR;
pemf_teardown.ps1 bütün olarak asla dot-source edilmez (footprint'i yükler ama zararsız —
yine de yalnız ihtiyaç duyulan fonksiyon metni Invoke-Expression edilir).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_TEARDOWN = _KOK / "scripts" / "pemf_teardown.ps1"
_FOOTPRINT = _KOK / "scripts" / "pemf_footprint.ps1"
_SECRETS = _KOK / "utils" / "secrets_manager.py"
_SQLCIPHER = _KOK / "database" / "sqlcipher_util.py"
_GUI_CONFIG = _KOK / "pemf_gui" / "config.py"

_PWSH = shutil.which("pwsh")

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="cmdkey / Credential Manager yalnız Windows"),
    pytest.mark.skipif(_PWSH is None, reason="pwsh (PowerShell 7) bulunamadı"),
]

# Sürücü betik: pemf_teardown.ps1'den YALNIZ Remove-PemfCredentials'ı AST ile çıkarır,
# Write-PemfLog'u renk+mesajı dosyaya yazan bir stub'la değiştirir, $script:PemfFailed'i sıfırlar.
_SURUCU = r"""
param([string]$Teardown, [string]$Senaryo, [string]$Ad, [string]$LogYolu)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Teardown, [ref]$tokens, [ref]$errs)
if ($errs) { throw "pemf_teardown.ps1 parse hatası: $($errs | Out-String)" }
$fn = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Remove-PemfCredentials' }, $true) | Select-Object -First 1
if (-not $fn) { throw "Remove-PemfCredentials fonksiyonu bulunamadı (çıpa kaymış olabilir)" }
$script:PemfFailed = @()
function Write-PemfLog($msg, $color = 'Gray') { Add-Content -LiteralPath $LogYolu -Value "$color|$msg" -Encoding UTF8 }
Invoke-Expression $fn.Extent.Text
if ($Senaryo -eq 'stub') {
    # cmdkey'i gölgele: hedef VAR ama silinemiyor (erişim engeli) senaryosu.
    function cmdkey { $global:LASTEXITCODE = 1; 'CMDKEY: Access is denied.' }
}
if ($Senaryo -eq 'dry') { Remove-PemfCredentials -TargetNames @($Ad) -DryRun }
else { Remove-PemfCredentials -TargetNames @($Ad) }
"FAILED_COUNT=$($script:PemfFailed.Count)"
foreach ($f in $script:PemfFailed) { "FAILED=$f" }
"""


def _pwsh(*args: str, timeout: int = 90) -> subprocess.CompletedProcess:
    r = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", *args],
        capture_output=True,
        timeout=timeout,
    )
    r.stdout = r.stdout.decode("utf-8", "replace")  # type: ignore[assignment]
    r.stderr = r.stderr.decode("utf-8", "replace")  # type: ignore[assignment]
    return r


def _cmdkey(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["cmdkey", *args], capture_output=True, timeout=30)


def _kimlik_listede(ad: str) -> bool:
    """`cmdkey /list` çıktısında hedef adı geçiyor mu (dil-bağımsız: 'NONE'/'Hedef:' metnine bakmaz)."""
    cikti = _cmdkey("/list").stdout.decode("utf-8", "replace")
    return ad in cikti


def _kos(tmp_path: Path, senaryo: str, ad: str) -> tuple[str, list[str]]:
    """Sürücüyü çalıştır → (PemfFailed satırları dâhil stdout, log satırları 'renk|mesaj')."""
    surucu = tmp_path / f"surucu_{uuid.uuid4().hex[:8]}.ps1"
    surucu.write_text(_SURUCU, encoding="utf-8-sig")
    log = tmp_path / f"log_{uuid.uuid4().hex[:8]}.txt"
    r = _pwsh("-File", str(surucu), "-Teardown", str(_TEARDOWN), "-Senaryo", senaryo, "-Ad", ad, "-LogYolu", str(log))
    assert r.returncode == 0, (
        f"sürücü başarısız (rc={r.returncode}):\nSTDOUT:{r.stdout[-1500:]}\nSTDERR:{r.stderr[-1500:]}"
    )
    satirlar = log.read_text(encoding="utf-8-sig").splitlines() if log.exists() else []
    return r.stdout, satirlar


def _failed_count(stdout: str) -> int:
    m = re.search(r"FAILED_COUNT=(\d+)", stdout)
    assert m, f"sürücü PemfFailed sayacını basmadı: {stdout[-500:]}"
    return int(m.group(1))


# ── 1) Davranış: gerçek geçici kimlik silinir ve DOĞRU raporlanır ─────────────


def test_KRITIK_gercek_kimlik_silinir_ve_silindi_denir(tmp_path):
    """(a) Gerçek kayıt: cmdkey /add ile yaratılır, fonksiyon siler, /list'ten kaybolur, log 'silindi'."""
    ad = f"PEMF_GATE_{uuid.uuid4().hex}"
    try:
        ekle = _cmdkey(f"/add:{ad}", "/user:x", "/pass:y")
        assert ekle.returncode == 0, f"test ön-koşulu: cmdkey /add başarısız: {ekle.stdout!r}"
        assert _kimlik_listede(ad), "test ön-koşulu: yaratılan kimlik /list'te görünmüyor"

        stdout, log = _kos(tmp_path, "gercek", ad)

        assert not _kimlik_listede(ad), f"Remove-PemfCredentials kimliği SİLMEDİ: {ad} hâlâ /list'te"
        assert any("kimlik silindi (KVKK)" in s and ad in s for s in log), f"silinen kimlik için 'silindi' yok:\n{log}"
        assert _failed_count(stdout) == 0, f"başarılı silme PemfFailed'i büyüttü:\n{stdout}"
    finally:
        _cmdkey(f"/delete:{ad}")  # kalıntı bırakma (zaten silinmişse exit 1 — zararsız)


def test_KRITIK_var_olmayan_kimlik_silindi_DENMEZ_yoktu_denir(tmp_path):
    """(b) Var-olmayan hedef (eski-kurulum adı senaryosu): 'silindi' YASAK, 'yoktu' ŞART, PemfFailed 0.

    MUTASYON: eski koşulsuz `Write-PemfLog "kimlik silindi (KVKK): $c"` satırı geri konursa bu
    test 'silindi' satırında KIRMIZI olur.
    """
    ad = f"PEMF_GATE_YOK_{uuid.uuid4().hex}"
    assert not _kimlik_listede(ad), "test ön-koşulu: rastgele ad zaten kasada?!"

    stdout, log = _kos(tmp_path, "yok", ad)

    silindi = [s for s in log if "silindi" in s and ad in s]
    assert not silindi, (
        f"var-olmayan kimlik için 'silindi' raporlandı → KVKK yanlış-güvence (bulgunun kendisi):\n{silindi}"
    )
    assert any("kimlik yoktu" in s and ad in s for s in log), f"var-olmayan kimlik 'yoktu' diye raporlanmadı:\n{log}"
    assert _failed_count(stdout) == 0, (
        f"var-olmayan (eski-ad) kimlik başarısızlık sayıldı — 'yoktu' normal olmalı:\n{stdout}"
    )
    # Kapsam sınırı notu her çağrıda bir kez, Sarı: LocalSystem kasası bu adımın dışında.
    notlar = [
        s for s in log if s.startswith("Yellow|") and "LocalSystem" in s and "servis kasası ayrıca temizlenmeli" in s
    ]
    assert len(notlar) == 1, f"LocalSystem kasa-kapsamı NOT satırı tam 1 kez beklenirdi:\n{log}"


def test_KRITIK_cmdkey_hatasi_PemfFailed_buyutur_ve_SILINEMEDI_der(tmp_path):
    """(c) cmdkey gölgelenir (exit 1 + 'Access is denied'): PemfFailed 'kimlik: <ad>' alır, log kırmızı 'SİLİNEMEDİ'."""
    ad = f"PEMF_GATE_HATA_{uuid.uuid4().hex}"

    stdout, log = _kos(tmp_path, "stub", ad)

    assert _failed_count(stdout) == 1, f"cmdkey hatası PemfFailed'e yazılmadı → rapor 'tam temizlik' der:\n{stdout}"
    assert f"FAILED=kimlik: {ad}" in stdout, f"PemfFailed girdisi 'kimlik: <ad>' biçiminde değil:\n{stdout}"
    kirmizi = [s for s in log if "SİLİNEMEDİ" in s and ad in s]
    assert kirmizi, f"cmdkey hatasında 'SİLİNEMEDİ' satırı yok:\n{log}"
    assert kirmizi[0].startswith("Red|"), f"SİLİNEMEDİ satırı kırmızı değil: {kirmizi[0]}"
    assert "Access is denied" in kirmizi[0], "hata satırı cmdkey çıktısını (NE oldu) taşımıyor"
    assert "cmdkey /delete:" in kirmizi[0], "hata satırı NE YAPILMALI demiyor (elle silme komutu)"
    assert not any("silindi" in s and ad in s and "SİLİNEMEDİ" not in s for s in log), (
        "hata durumunda 'silindi' raporlandı"
    )


def test_dry_run_cmdkey_cagirmaz_ve_DRY_loglar(tmp_path):
    """-DryRun: gerçek kayıt DOKUNULMAZ, log '[DRY] kimlik'."""
    ad = f"PEMF_GATE_DRY_{uuid.uuid4().hex}"
    try:
        assert _cmdkey(f"/add:{ad}", "/user:x", "/pass:y").returncode == 0
        stdout, log = _kos(tmp_path, "dry", ad)
        assert _kimlik_listede(ad), "DryRun kimliği SİLDİ — önizleme yıkıcı olamaz"
        assert any("[DRY] kimlik" in s and ad in s for s in log), f"DryRun '[DRY]' loglamadı:\n{log}"
        assert not any("kimlik silindi" in s for s in log), "DryRun 'silindi' raporladı"
        assert _failed_count(stdout) == 0
    finally:
        _cmdkey(f"/delete:{ad}")


# ── 2) Footprint: Credentials listesi runtime'ın GERÇEK keyring adlarını kapsar ──


def _runtime_keyring_adlari() -> set[str]:
    """Runtime'ın keyring'de kullandığı adlar (servis 'PEMF_GUI'); kaynaktan regex ile."""
    adlar: set[str] = set()
    sm = _SECRETS.read_text(encoding="utf-8")
    adlar.update(re.findall(r'_keyring_get\("([^"]+)"\)', sm))
    sq = _SQLCIPHER.read_text(encoding="utf-8")
    adlar.update(re.findall(r'_KEY_NAME\s*=\s*"([^"]+)"', sq))
    if _GUI_CONFIG.exists():
        gc = _GUI_CONFIG.read_text(encoding="utf-8")
        adlar.update(re.findall(r'service,\s*name\s*=\s*"PEMF_GUI",\s*"([^"]+)"', gc))
    assert adlar, "runtime keyring adları bulunamadı (regex çıpası kaymış olabilir)"
    return adlar


def _footprint_credentials() -> list[str]:
    """pemf_footprint.ps1 yan etkisizdir → gerçekten dot-source edip listeyi DEĞERLENDİR (grep değil)."""
    r = _pwsh(
        "-Command",
        f"[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); . '{_FOOTPRINT}'; (Get-PemfFootprint).Credentials | ForEach-Object {{ \"CRED=$_\" }}",
    )
    assert r.returncode == 0, f"footprint değerlendirilemedi: {r.stderr[-800:]}"
    return [ln[len("CRED=") :].strip() for ln in r.stdout.splitlines() if ln.startswith("CRED=")]


def test_KRITIK_footprint_runtime_keyring_adlarinin_HEPSINI_icerir():
    """Runtime 'patient_fernet_key' yazar, footprint 'fernet_key' silerdi → kayıt HİÇ silinmiyordu.

    python-keyring Windows arka ucu TargetName'i "<ad>@<servis>" yazar → '<ad>@PEMF_GUI' beklenir.
    """
    beklenen = {f"{ad}@PEMF_GUI" for ad in _runtime_keyring_adlari()}
    assert "patient_fernet_key@PEMF_GUI" in beklenen, "regex patient_fernet_key'i yakalamadı (çıpa kontrolü)"
    liste = _footprint_credentials()
    eksik = sorted(beklenen - set(liste))
    assert not eksik, (
        f"footprint Credentials listesinde runtime keyring adları EKSİK: {eksik} — "
        f"teardown bu kayıtları hiç silmez; scripts/pemf_footprint.ps1 Credentials'a ekleyin. Mevcut: {liste}"
    )


def test_footprint_eski_kurulum_adlari_LISTEDE_KALIR():
    """Eski kurulumlar bu adlarla yazmış olabilir; silinmeleri gerekir (teardown yoksa 'yoktu' der)."""
    liste = set(_footprint_credentials())
    eski = {"PEMF_GUI", "api_token@PEMF_GUI", "fernet_key@PEMF_GUI"}
    assert eski <= liste, f"eski-kurulum kimlik adları listeden düşmüş: {sorted(eski - liste)}"
