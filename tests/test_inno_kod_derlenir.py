# Author: mertaygn, cglrgrkn
"""`PEMF_Backend_Setup.iss`'in `[Code]` (Pascal Script) bölümü GERÇEKTEN derleniyor mu?

NEDEN AYRI BİR KAPI (2026-08-17). `tests/test_inno_kurulum_bobin_guvenligi.py` sıra değişmezini
METİN olarak denetliyor — ama metin denetimi sözdizimi hatasını göremez. Bu bölüm Pascal Script'tir
ve `.iss` yalnız YAYIN sırasında (`build_installer.ps1` → ISCC) derlenir; bir sözdizimi hatası
denetimden aylar sonra, tam kurulum dosyası üretilirken ortaya çıkar.

`hooks.nsi` için aynı kapı zaten var (`test_kaldirma_yetim_surec_temizligi.py` geçici bir `.nsi`
yazıp `makensis` ile derliyor). Bu dosya onun Inno karşılığıdır.

⚠️ TAM `.iss` DERLENMEZ: `[Files]` bölümü ~1,5 GB'lık frozen ağacı paketlerdi (dakikalar + disk).
Yalnız `[Code]` bölümü, asgari bir `[Setup]` iskeletiyle derlenir — sözdizimi/tip hatalarını ve
tanımsız yordam çağrılarını yakalamak için yeterli.

ISCC kurulu değilse test ATLANIR (CI'da Inno yok; `bootstrap.ps1` onu kuruyor).
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
ISS = KOK / "build_tools" / "PEMF_Backend_Setup.iss"

ISCC_ADAYLARI = [
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"),
]


def _iscc():
    for p in ISCC_ADAYLARI:
        if p.exists():
            return str(p)
    return None


@pytest.mark.skipif(_iscc() is None, reason="ISCC (Inno Setup) kurulu degil")
def test_KOD_bolumu_ISCC_ile_DERLENIR():
    """`[Code]` bölümü sözdizimsel olarak geçerli olmalı — yoksa installer HİÇ üretilmez."""
    kaynak = ISS.read_text(encoding="utf-8")
    # ⚠️ Basit `split("[Code]")` YANLIŞTIR: dosyada satır 114 civarında bir YORUM da `[Code]`
    # geçiriyor ("[UninstallRun]'dan [Code]'a") → bölme orada olur ve `[Setup]`/`[Files]`/
    # `[Registry]` bölümleri de sondaya kopyalanır, ISCC "String error" verir. Bölüm başlığı
    # SATIR BAŞINDA aranır.
    m = re.search(r"^\[Code\]\s*$", kaynak, re.MULTILINE)
    assert m, "[Code] bolum basligi kayboldu"
    kod = kaynak[m.end() :]
    assert "procedure CurStepChanged" in kod, "CurStepChanged [Code] icinde bulunamadi"

    # `[Code]`'un kullandığı preprocessor sabitleri (gerçek dosyadaki değerlerle aynı olması
    # gerekmez; yalnız TANIMLI olmaları yeterli).
    iskelet = (
        '#define MyAppVersion "0.0.0"\n'
        '#define MyAppPublisher "Test"\n'
        "[Setup]\n"
        "AppName=PEMF Code Syntax Probe\n"
        "AppVersion=0.0.0\n"
        "DefaultDirName={commonappdata}\\PEMF_Code_Probe\n"
        "Uninstallable=no\n"
        "CreateAppDir=yes\n"
        "OutputBaseFilename=pemf_code_probe\n"
        "[Code]\n" + kod
    )

    with tempfile.TemporaryDirectory() as gecici:
        g = Path(gecici)
        probe = g / "probe.iss"
        probe.write_text(iskelet, encoding="utf-8")
        r = subprocess.run(
            [_iscc(), f"/O{g}", str(probe)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )

    assert r.returncode == 0, (
        f"[Code] bolumu DERLENMIYOR (ISCC cikis {r.returncode}). Installer uretilemez.\n"
        f"--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
