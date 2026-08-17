# Author: mertaygn, cglrgrkn
r"""`build_installer.ps1` kendi web-UI kaynağını SİLMEMELİ.

DENETİM BULGUSU (2026-08-17). 2026-08-15'teki "tek kaynak" değişikliğinden beri
`build_tools/build_installer.ps1` içinde:

    $FrontendDir = Join-Path $ProjectRoot "pf"     # (satır ~252)
    ...
    $PfDir       = Join-Path $ProjectRoot "pf"     # (satır ~263)  ← AYNI DİZİN

ve aşağıdaki aynalama adımı hâlâ "pf\dist → frontend\dist" varsayımıyla yazılmış:

    $FrontendDistDir = Join-Path $FrontendDir "dist"          # = pf\dist
    if (Test-Path $FrontendDistDir) { Remove-Item ... -Recurse -Force }   # ← KAYNAĞI SİLER
    Copy-Item (Join-Path $PfDir "dist") $FrontendDistDir -Recurse -Force  # ← artık YOK

Sonuç: taze export edilen `pf\dist` silinir, kopyalama `ItemNotFoundException` atar ve
`$ErrorActionPreference = "Stop"` yüzünden **offline Inno installer varsayılan yolda hiç
derlenemez**. Yalnız `PEMF_SKIP_FRONTEND=1` ile derlenebiliyor. Ayrıca `pf\dist` silinmiş kaldığı
için sonraki backend build'i de etkilenir.

⚠️ AYNALAMA ARTIK GEREKSİZDİR: `build_tools/PEMF_Backend_onedir.spec` web arayüzünü doğrudan
`pf/dist`'ten paketliyor (yayınlanan `base-app.zip` bununla doğrulandı: `frontend\dist\version.json`
diskte VAR ama zip'te YOK → spec `pf/dist` okuyor). Doğru düzeltme kopyalamayı "kaynak == hedef"
durumunda ATLAMAK.

⚠️ NEDEN GREP DEĞİL: bu test bloğu METİN olarak denetlemiyor, betikten çıkarıp **gerçekten
çalıştırıyor** ve `pf\dist`'in hayatta kaldığını ölçüyor. Kaynak-metin denetimleri bu depoda bir
kez "kâğıttan kaplan" çıktı (`test_treatment_persistence.py:339` `-wal` grep'i, TypeError'lı kodu
geçiriyordu), o yüzden davranışsal ölçüm tercih edildi.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
PS1 = KOK / "build_tools" / "build_installer.ps1"

# Aynalama bloğunun ÇIPALARI — betikte AÇIK işaretçiler.
# ⚠️ Neden açık marker: blok bir `if/else` içeriyor ve "ilk `Write-OK`a kadar" gibi örtük bir son,
# bloğu YARIDA kesip PowerShell ayrıştırma hatası verirdi. Marker taşınırsa test "çıpa bulunamadı"
# ile AÇIKÇA kırılır — sessizce atlayıp yanlış-yeşil vermez.
BAS_CIPA = "=== PEMF-AYNALAMA-BASI ==="
SON_CIPA = "=== PEMF-AYNALAMA-SONU ==="


def _powershell():
    for aday in ("pwsh", "powershell"):
        if shutil.which(aday):
            return shutil.which(aday)
    return None


def _aynalama_blogu() -> str:
    """Betikten aynalama bloğunu çıkarır (iki açık çıpa arası, ikisi dahil)."""
    satirlar = PS1.read_text(encoding="utf-8", errors="replace").splitlines()
    bas = next((i for i, s in enumerate(satirlar) if BAS_CIPA in s), None)
    assert bas is not None, (
        f"aynalama blogunun cipasi bulunamadi ({BAS_CIPA!r}) — build_installer.ps1 yeniden "
        "duzenlenmis olabilir; bu kapinin cipasini guncelleyin."
    )
    son = next((i for i in range(bas, len(satirlar)) if SON_CIPA in satirlar[i]), None)
    assert son is not None, f"aynalama blogunun son cipasi bulunamadi ({SON_CIPA!r})"
    return "\n".join(satirlar[bas : son + 1])


@pytest.mark.skipif(_powershell() is None, reason="PowerShell bulunamadi")
def test_KRITIK_aynalama_pf_dist_i_SILMEZ():
    """Blok gerçekten koşturulur; `pf\\dist` ve içindeki export hayatta kalmalı."""
    blok = _aynalama_blogu()

    with tempfile.TemporaryDirectory() as gecici:
        g = Path(gecici)
        pf_dist = g / "pf" / "dist"
        pf_dist.mkdir(parents=True)
        (pf_dist / "index.html").write_text("<html>EXPORT</html>", encoding="utf-8")

        # Betikteki iki değişken de `pf`e işaret eder (2026-08-15 tek-kaynak değişikliği).
        # `Write-OK`/`Write-Fail` saplanır; gerisi betiğin GERÇEK satırlarıdır.
        surucu = (
            '$ErrorActionPreference = "Stop"\n'
            "function Write-OK($m) { Write-Host \"OK: $m\" }\n"
            "function Write-Fail($m) { Write-Host \"FAIL: $m\"; exit 3 }\n"
            f'$ProjectRoot = "{g.as_posix()}"\n'
            '$FrontendDir = Join-Path $ProjectRoot "pf"\n'
            '$PfDir       = Join-Path $ProjectRoot "pf"\n' + blok + "\n"
        )
        script = g / "surucu.ps1"
        script.write_text(surucu, encoding="utf-8")

        r = subprocess.run(
            [_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )

        hayatta = (pf_dist / "index.html").exists()

    assert hayatta, (
        "aynalama adimi taze export edilen `pf\\dist`'i SILDI → Copy-Item kaynagi bulamaz, "
        f"$ErrorActionPreference='Stop' ile Inno build'i coker.\n"
        f"--- cikis {r.returncode} ---\n{r.stdout}\n{r.stderr}"
    )
    assert r.returncode == 0, (
        f"aynalama blogu hata ile bitti (cikis {r.returncode}) → build durur.\n{r.stdout}\n{r.stderr}"
    )


@pytest.mark.skipif(_powershell() is None, reason="PowerShell bulunamadi")
def test_kaynak_ve_hedef_FARKLIYSA_aynalama_hala_calisir_karsit_kanit():
    """Karşı-kanıt: düzeltme kopyalamayı TAMAMEN kaldırmamalı.

    `$FrontendDir` bir gün yeniden ayrı bir dizine dönerse (ör. başka bir paketleyici kanonik
    `frontend\\dist` beklerse) aynalama yine çalışmalı — düzeltme yalnız "kaynak == hedef"
    durumunu atlar."""
    blok = _aynalama_blogu()

    with tempfile.TemporaryDirectory() as gecici:
        g = Path(gecici)
        (g / "pf" / "dist").mkdir(parents=True)
        (g / "pf" / "dist" / "index.html").write_text("<html>EXPORT</html>", encoding="utf-8")

        surucu = (
            '$ErrorActionPreference = "Stop"\n'
            "function Write-OK($m) { Write-Host \"OK: $m\" }\n"
            "function Write-Fail($m) { Write-Host \"FAIL: $m\"; exit 3 }\n"
            f'$ProjectRoot = "{g.as_posix()}"\n'
            '$FrontendDir = Join-Path $ProjectRoot "frontend"\n'
            '$PfDir       = Join-Path $ProjectRoot "pf"\n' + blok + "\n"
        )
        script = g / "surucu2.ps1"
        script.write_text(surucu, encoding="utf-8")

        r = subprocess.run(
            [_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        kopyalandi = (g / "frontend" / "dist" / "index.html").exists()
        kaynak_duruyor = (g / "pf" / "dist" / "index.html").exists()

    assert r.returncode == 0, f"ayri-dizin yolunda blok patladi:\n{r.stdout}\n{r.stderr}"
    assert kopyalandi, "kaynak != hedef iken aynalama YAPILMADI — duzeltme fazla genis"
    assert kaynak_duruyor, "aynalama kaynagi tuketti"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
