# Author: mertaygn, cglrgrkn
"""EXE SÜRÜM-METADATA SENKRONU — 2. tur denetimi bulgu [5.4] (2026-08-20).

ÖLÇÜLEN DURUM: PyInstaller spec'i EXE'nin Windows dosya-özellikleri sürümünü
`docs/version_info.txt`'ten gömer; o dosyayı YALNIZ KAPALI Inno kanalının `build_installer.ps1`i
yeniliyordu. Güncel yayın yolu (`build_backend_exe.ps1` → make_base_zip) hiç dokunmadığı için
dosya 1.9.14.0'da DONMUŞTU — 1.9.15/16/17 paketlerindeki `PEMF_Backend.exe` yanlış sürüm
metadata'sı taşıdı (destek/envanter yanlış teşhis; `versions.json._kanallar`ın "backend hedefi:
docs/version_info.txt" iddiası fiilen yerine gelmiyordu) ve HİÇBİR kapı bunu görmüyordu
(test_uretici_kimligi yalnız alan-ayrışmasına bakar, VERSION eşitliğine değil).

SÖZLEŞME: version_info.txt artık `sync_versions.ps1`in hedefidir (otorite dosyanın iddiasıyla
hizalanır) ve `build_backend_exe.ps1` sync'i çağırır (build_installer/build_apk deseniyle aynı).
Buradaki eşitlik kapısı, sürüm bump'ı sync'siz yayınlanırsa CI'ı KIRMIZI yapar — üç yayındır
süren sessiz kayma sınıfı kapanır.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]


def _powershell():
    for aday in ("pwsh", "powershell"):
        if shutil.which(aday):
            return aday
    return None


def test_KRITIK_version_info_versions_json_ile_AYNI():
    """EXE'ye gömülen dosya-sürümü tek kaynakla (versions.json.backend) eşit olmalı."""
    beklenen = json.loads((KOK / "versions.json").read_text(encoding="utf-8"))["backend"]
    vi = (KOK / "docs" / "version_info.txt").read_text(encoding="utf-8", errors="replace")

    m = re.search(r"filevers=\((\d+), (\d+), (\d+), 0\)", vi)
    assert m, "version_info.txt filevers bulunamadı — biçim değişti, kapıyı güncelle"
    assert ".".join(m.groups()) == beklenen, (
        f"EXE dosya-sürümü {'.'.join(m.groups())} ≠ versions.json {beklenen} — sahadaki "
        f"PEMF_Backend.exe yanlış sürüm metadata'sı taşır (bulgu [5.4]; 1.9.14'te donmuştu)"
    )
    for alan in ("FileVersion", "ProductVersion"):
        s = re.search(rf"u'{alan}', u'(\d+\.\d+\.\d+)\.0'", vi)
        assert s and s.group(1) == beklenen, f"{alan} ayrışık: {s and s.group(1)} ≠ {beklenen}"
    p = re.search(r"prodvers=\((\d+), (\d+), (\d+), 0\)", vi)
    assert p and ".".join(p.groups()) == beklenen, "prodvers ayrışık"


def test_KRITIK_build_backend_exe_sync_cagirir():
    """Canlı yayın yolu sync'i atlarsa dosya yine donar — çağrı build betiğinde olmalı
    (build_installer:104 / build_apk:33 deseniyle aynı; yorum satırı sayılmaz)."""
    src = (KOK / "scripts" / "build_backend_exe.ps1").read_text(encoding="utf-8", errors="replace")
    kod = [s for s in src.splitlines() if not s.strip().startswith("#")]
    # ⚠️ İKİ ayrı iddia (mutasyon turu kendi zaafımı yakaladı: Warn-DİZESİNDEKİ
    # "sync_versions.ps1 yok..." geçişi tek-iddialı kapıyı kandırıyordu):
    #   (a) yol GERÇEKTEN sync_versions.ps1'e kuruluyor, (b) o değişken GERÇEKTEN çağrılıyor.
    assert any(re.search(r'Join-Path .*build_tools\\+sync_versions\.ps1', s) for s in kod), (
        "build_backend_exe.ps1 sync_versions yolunu kurmuyor — version_info.txt canlı yayın "
        "yolunda yine donar (bulgu [5.4])"
    )
    assert any(re.search(r"^\s*&\s*\$SyncScript\b", s) for s in kod), (
        "sync_versions atanmış ama ÇAĞRILMIYOR — senkron ölü kod"
    )


@pytest.mark.skipif(_powershell() is None, reason="PowerShell bulunamadi")
def test_KARSIT_KANIT_sync_check_temiz_agacta_yesil():
    """sync_versions -Check senkron ağaçta 0 ile çıkmalı — version_info desenleri dosyayla
    GERÇEKTEN eşleşiyor (desen kayarsa -Check mismatch verir ve bu test kırmızı olur)."""
    r = subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(KOK / "build_tools" / "sync_versions.ps1"),
            "-Check",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        cwd=str(KOK),
    )
    assert r.returncode == 0, f"sync -Check senkron ağaçta kırmızı: {r.stdout}\n{r.stderr}"
    assert "version_info" in r.stdout.lower(), (
        f"-Check çıktısında version_info hedefi görünmüyor — sync kapsamına alınmamış: {r.stdout!r}"
    )
