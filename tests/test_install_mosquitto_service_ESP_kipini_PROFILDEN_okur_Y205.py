# -*- coding: utf-8 -*-
"""Y205 · S-D5.16 (sahip, 2026-10-28) — `install_mosquitto_service.ps1` ESP kipini yalnız MAKİNE ortamından okuyordu: A-11 yolunda backend
servisi (`install_backend_service.ps1`) `deploy\\<Mode>.env` profilini makine ortamının ÜSTÜNE koyar → profil `PEMF_ESP_ENABLED=1` taşırsa
backend ESP'yi açık, mosquitto betiği KAPALI görür (1883 kuralını daraltır / siler — ESP bobinlerinin STOP yolu kesilir). Artık betik
`-Mode` alır, aynı profili aynı ayrıştırıcıyla okur ve kararı backend'in göreceği değerden verir (profil > makine).

Ölçüm: betiğin KENDİ `Read-PemfProfilEnv` + `Test-PemfEspEtkin` işlevleri PowerShell ayrıştırıcısıyla çekilir (betik KOŞTURULMAZ — servis /
güvenlik duvarına dokunmaz) ve geçici profille çağrılır; çağrı yeri ve `-Mode` sözleşmesi kaynakta okunur.
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
from test_setup_services_firewall_kaniti import PWSH, _ps_lit, _pwsh_file  # noqa: E402

if PWSH is None:
    capraz.atla("pwsh (PowerShell 7) bulunamadı")

KOK = Path(__file__).resolve().parents[1]
MOSQ = KOK / "scripts" / "install_mosquitto_service.ps1"
SERVIS = KOK / "scripts" / "install_backend_service.ps1"


def _kod(yol: Path) -> str:
    return "\n".join(s for s in yol.read_text(encoding="utf-8-sig").splitlines() if not s.lstrip().startswith("#"))


@pytest.mark.parametrize(
    ("profil", "makine", "beklenen"),
    [
        ("PEMF_ESP_ENABLED=1\n", "0", True),  # profil açar, makine kapalı → backend AÇIK görür
        ("PEMF_ESP_ENABLED=0\n", "1", False),  # profil kapatır → backend KAPALI görür
        ("PEMF_API_PORT=8000\n", "1", True),  # profilde anahtar yok → makine ortamı
        (None, "1", True),  # profil dosyası yok → makine ortamı
    ],
    ids=["profil_acar", "profil_kapatir", "profilde_yok", "profil_dosyasi_yok"],
)
def test_KRITIK_ESP_kipi_PROFIL_makine_ortamina_USTUN(tmp_path, profil, makine, beklenen):
    (tmp_path / "r").mkdir()
    (tmp_path / "t").mkdir()
    oku = betik_fonksiyonu(
        tmp_path / "r", "Read-PemfProfilEnv", MOSQ, ("Get-Content",), ("Trim", "StartsWith", "Contains", "Split")
    )
    karar = betik_fonksiyonu(tmp_path / "t", "Test-PemfEspEtkin", MOSQ, (), ("Contains", "Trim"))
    pf = tmp_path / "device.env"
    if profil is not None:
        pf.write_text(profil, encoding="utf-8")
    govde = (
        oku
        + "\n"
        + karar
        + f"\n$p = if (Test-Path {_ps_lit(pf)}) {{ Read-PemfProfilEnv {_ps_lit(pf)} }} else {{ $null }}\n"
        + f"Write-Output (\"SONUC=\" + (Test-PemfEspEtkin $p '{makine}'))\n"
    )
    r = _pwsh_file(tmp_path, "karar.ps1", govde)
    assert r.returncode == 0 and "SONUC=" in r.stdout, f"sürücü düştü (rc={r.returncode}):\n{r.stdout}\n{r.stderr}"
    assert r.stdout.split("SONUC=")[1].strip().startswith(str(beklenen)), (
        f"ESP kipi profil={profil!r} makine={makine!r} → {r.stdout.strip()} (beklenen {beklenen}: backend servisinin göreceği değer)"
    )


def test_KRITIK_cagri_yeri_PROFILI_verir_ve_Mode_sozlesmesi_backend_servisiyle_AYNI():
    kod = _kod(MOSQ)
    assert re.search(
        r"^\$Profil = if \(\$ProfilDosyasi\) \{ Read-PemfProfilEnv \$ProfilDosyasi \} else \{ \$null \}$", kod, re.M
    ), "mosquitto betiği profili okumuyor"
    cagri = re.findall(r"Ensure-PemfMosquittoServisFirewallRule -EspEtkin \(Test-PemfEspEtkin (\S+) ", kod)
    assert cagri == ["$Profil"], f"ESP kararı profili kullanmıyor (çağrı yeri): {cagri}"
    assert re.search(r'deploy\\\$Mode\.env', kod), "profil yolu deploy\\<Mode>.env değil"
    desen = r'\[ValidateSet\("device", "server"\)\]\s*\n\s*\[string\]\$Mode = "device"'
    assert re.search(desen, kod) and re.search(desen, _kod(SERVIS)), (
        "-Mode sözleşmesi backend servis betiğiyle AYNI değil"
    )
