# -*- coding: utf-8 -*-
"""Y205 · S-D5.22 (sahip, 2026-10-28) — `install_backend_service.ps1` servisi başlattıktan sonra SAĞLIK SONDASI yapar.

ÖLÇÜLEN (D5): betik `nssm start` + 4 sn bekleme + `nssm status` ile "Running" basıp "kuruldu" diyordu; servis çalışıyor olsa da backend
(açılış, DB / donanım hazırlığı, port çakışması) istek KABUL ETMİYOR olabilirdi — kurulum yapan kişi bunu göremiyordu. Artık betik
`http://127.0.0.1:<servis portu>/api/health`i süreyle yoklar; yanıt yoksa kurulum DURMAZ (servis kendini yeniden dener) ama eylemli uyarı
(günlük yolu) verir ve özet "Sağlık" satırı sonucu söyler. Sonda YALNIZ yerel döngü adresine gider (LAN'a istek yok).

Ölçüm: `Test-PemfServisSagligi` PowerShell ayrıştırıcısıyla çekilir (betik KOŞTURULMAZ — servis / güvenlik duvarına dokunmaz) ve GÖLGE
`Invoke-RestMethod` ile çağrılır (gerçek porta istek YOK — ORTAK §1). Çağrı yeri ve sıra (başlatmadan SONRA, özetten ÖNCE) kaynakta okunur.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import capraz
import pytest

if sys.platform != "win32":
    capraz.atla("PowerShell betik anlamı Windows'ta ölçülür")

from test_install_backend_service_FW_kurali_ICERIKLE_D5H1 import betik_fonksiyonu  # noqa: E402
from test_setup_services_firewall_kaniti import PWSH, _pwsh_file  # noqa: E402

if PWSH is None:
    capraz.atla("pwsh (PowerShell 7) bulunamadı")

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "install_backend_service.ps1"


def _kod() -> str:
    return "\n".join(s for s in BETIK.read_text(encoding="utf-8-sig").splitlines() if not s.lstrip().startswith("#"))


@pytest.mark.parametrize(
    ("kac_denemede", "beklenen"),
    [(1, True), (3, True), (None, False)],
    ids=["hemen_yanit", "ucuncu_denemede", "hic_yanit_yok"],
)
def test_KRITIK_saglik_sondasi_YEREL_health_ucunu_yoklar_YANITSIZSA_false(tmp_path, kac_denemede, beklenen):
    (tmp_path / "f").mkdir()
    islev = betik_fonksiyonu(
        tmp_path / "f",
        "Test-PemfServisSagligi",
        BETIK,
        ("Invoke-RestMethod", "Get-Date", "Start-Sleep"),
        ("AddSeconds",),
    )
    esik = 0 if kac_denemede is None else kac_denemede
    govde = (
        "$script:cagri = @()\n"
        f"function Invoke-RestMethod {{ param($Uri, $TimeoutSec, $ErrorAction, $Method) $script:cagri += $Uri; "
        f"if ({esik} -gt 0 -and $script:cagri.Count -ge {esik}) {{ return @{{ status = 'ok' }} }}; throw 'baglanti reddedildi' }}\n"
        "function Start-Sleep { param($Seconds, $Milliseconds) }\n"
        + islev
        + "\n$sonuc = Test-PemfServisSagligi -Port 8123 -SureSn 1\n"
        "Write-Output (\"SONUC=\" + $sonuc)\n"
        "Write-Output (\"URI=\" + ($script:cagri | Select-Object -Unique) -join ',')\n"
        "Write-Output (\"CAGRI=\" + $script:cagri.Count)\n"
    )
    r = _pwsh_file(tmp_path, "sonda.ps1", govde)
    assert r.returncode == 0 and "SONUC=" in r.stdout, f"sürücü düştü (rc={r.returncode}):\n{r.stdout}\n{r.stderr}"
    assert f"SONUC={beklenen}" in r.stdout, f"beklenen {beklenen}: {r.stdout}"
    assert "URI=http://127.0.0.1:8123/api/health" in r.stdout, f"sonda yerel health ucu dışına gitti: {r.stdout}"
    if kac_denemede is None:
        assert int(r.stdout.split("CAGRI=")[1].split()[0]) >= 2, f"yanıtsızda yeniden DENENMEDİ: {r.stdout}"


def test_KRITIK_sonda_BASLATMADAN_sonra_servis_portuyla_cagrilir_ozet_sonucu_soyler():
    kod = _kod()
    i_baslat = kod.index("& $NssmExe start $ServiceName")
    cagri = re.search(r"^\$Saglik = Test-PemfServisSagligi -Port \$ApiPort -SureSn (\d+)$", kod, re.M)
    assert cagri, "sağlık sondası çağrılmıyor (ya da servis portu $ApiPort ile değil)"
    assert cagri.start() > i_baslat, "sağlık sondası servis BAŞLATILMADAN önce çağrılıyor"
    assert int(cagri.group(1)) >= 30, "sağlık sondası süresi açılış için çok kısa"
    ozet = kod.index('Write-Host "Backend servisi kuruldu."')
    assert cagri.start() < ozet, "sonda özetten SONRA — özet sonucu söyleyemez"
    assert re.search(r'Write-Host "  Sağlık : .*\$\(if \(\$Saglik\)', kod), (
        "özet 'Sağlık' satırı sonda sonucunu söylemiyor"
    )
