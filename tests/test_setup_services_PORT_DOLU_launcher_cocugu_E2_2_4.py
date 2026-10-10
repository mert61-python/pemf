# -*- coding: utf-8 -*-
"""E2-2.4 (2-E incelemesi, A2) — S-E.4'ün varsayımı ÇÜRÜK: klinik (device) yeniden kurulumunda portu launcher çocuğu (başka bir PEMF
backend'i) tutuyorsa kurulum "port dolu" diye DURMAZ; sağlık sondası O backend'in `/api/health`'inden 200 alır ve "Kurulum DOĞRULANDI" der.

`setup_services.ps1` sağlık sondası (`Invoke-WebRequest http://localhost:<port>/api/health` → 200) YANITLAYANIN kimliğine bakmaz (launcher'ın
`PEMF_HEALTH_NONCE` / `launcherNonce` doğrulaması burada yok). D2.74 (S-E.4) launcher çocuğunu öldürmemeyi seçti ve "port doluysa sağlık
sondası düşer, kurulum exit 1 + 'port dolu' ipucuyla durur — sessiz değil" dedi: port GERÇEK bir PEMF backend'i tarafından tutulduğunda
sonda düşmez. Yeni servis bind edemeyip NSSM döngüsünde çöker; at-rest doğrulaması da (`atRestEncrypted`) launcher çocuğunu ölçer;
`.install_verified` yazılır (Inno başarı bayrağı).

⛔ Betik GERÇEKTEN koşmaz: D2.74'ün KANITLANMIŞ gölge aparatı (`_APARAT`; yalnız izin listesindeki ifadeler koşar, `exit` → kod + dön) METİN
olarak alınır ve YALNIZ şunlar eklenir: sağlık sondası / at-rest sorgusu / port sahibi sorgusu için KAYITÇI gölge işlevler (ağa çıkmaz) ve
sahte süreç tablosuna launcher çocuğu (303). Koruma katmanları (izin listesi, Saf(), kayıtçılar) GEVŞETİLMEZ; ARAÇ kolu aynı dosyada önce koşar.
Senaryo (portu kim tutuyor) GERÇEK davranışın benzetimidir: dinleyen bir PEMF backend'i `/api/health`'e 200 döner (ölçüldü: TestClient).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from test_setup_services_STAGING_klinige_DOKUNMAZ_D274 import (  # noqa: F401  (pytestmark: win32 + pwsh)
    _APARAT,
    _PWSH,
    FOOTPRINT,
    KOK,
    SETUP,
    pytestmark,
)


def _degistir(metin: str, eski: str, yeni: str) -> str:
    assert metin.count(eski) == 1, f"aparat çapası {metin.count(eski)} kez: {eski!r}"
    return metin.replace(eski, yeni)


_EK_GOLGE = r"""
# ── E2-2.4 ek KAYITÇI gölgeler (ağa ÇIKMAZ): port sahibi = $script:PortPid (303 launcher çocuğu | 202 bu kurulum) ──
$script:PortPid = $(if ($Senaryo -like '*launcher*') { 303 } else { 202 })
function Get-NetTCPConnection { param($LocalPort, $State, $ErrorAction)
    K ("PORT-SORGU " + $LocalPort)
    if ([int]$LocalPort -eq 8000) { [pscustomobject]@{ LocalPort = 8000; State = 'Listen'; OwningProcess = $script:PortPid } } }
function Invoke-WebRequest { param($Uri, [switch]$UseBasicParsing, $TimeoutSec, $ErrorAction)
    K ("HEALTH " + $Uri); [pscustomobject]@{ StatusCode = 200 } }
function Invoke-RestMethod { param($Uri, $Method, $TimeoutSec, $ErrorAction)
    K ("HEALTH-JSON " + $Uri); [pscustomobject]@{ status = 'online'; atRestEncrypted = $true } }
"""

_APARAT_E224 = _degistir(_APARAT, "$script:Canli.Add(202)", "$script:Canli.Add(202); $script:Canli.Add(303)")
_APARAT_E224 = _degistir(
    _APARAT_E224,
    "    if ($script:Canli.Contains(202)) { [pscustomobject]@{ ProcessId = 202; Name = 'PEMF_Backend.exe'; ExecutablePath = (Join-Path $App 'PEMF_Backend.exe') } } }",
    "    if ($script:Canli.Contains(202)) { [pscustomobject]@{ ProcessId = 202; Name = 'PEMF_Backend.exe'; ExecutablePath = (Join-Path $App 'PEMF_Backend.exe') } }\n"
    "    if ($script:Canli.Contains(303)) { [pscustomobject]@{ ProcessId = 303; Name = 'PEMF_Backend.exe'; ExecutablePath = (Join-Path (Split-Path $App -Parent) 'Users\\denetim\\AppData\\Local\\PEMF Vet Client\\runtime\\PEMF_Backend\\PEMF_Backend.exe') } } }",
)
_APARAT_E224 = _degistir(
    _APARAT_E224,
    "$izinli = [System.Collections.Generic.List[string]]@(",
    _EK_GOLGE + "$izinli = [System.Collections.Generic.List[string]]@(",
)
_APARAT_E224 = _degistir(
    _APARAT_E224,
    "'Stop-PemfKurulumBackendi', 'Stop-AppProcs', 'Get-ItemProperty')",
    "'Stop-PemfKurulumBackendi', 'Stop-AppProcs', 'Get-ItemProperty', 'Get-NetTCPConnection', 'Invoke-WebRequest', 'Invoke-RestMethod')",
)
_APARAT_E224 = _degistir(
    _APARAT_E224,
    "$sonuc.kaldirma_dali_kostu = $bitti\n",
    "$sonuc.kaldirma_dali_kostu = $bitti\n"
    "$sonuc.komut_turleri = @(foreach ($n in 'Invoke-WebRequest', 'Invoke-RestMethod', 'Get-NetTCPConnection', 'Stop-Process', 'Get-CimInstance',"
    " 'New-NetFirewallRule', 'Get-ItemProperty', 'Get-Service') { \"$n=$((Get-Command $n | Select-Object -First 1).CommandType)\" })\n"
    "$sonuc.canli = @($script:Canli)\n",
)


def _kos(tmp_path: Path, senaryo: str) -> tuple[dict, Path]:
    app = tmp_path / "PEMF_Backend_App"
    klinik = tmp_path / "Program Files" / "PEMF Backend"
    for yol in (app / "_internal" / "bin" / "nssm", app / "deploy", klinik):
        yol.mkdir(parents=True, exist_ok=True)
    for bos in (app / "_internal" / "bin" / "nssm" / "nssm.exe", app / "PEMF_Backend.exe", app / "pemf_teardown.ps1"):
        bos.write_bytes(b"")
    for profil in ("staging.env", "device.env"):
        shutil.copy2(KOK / "deploy" / profil, app / "deploy" / profil)
    aparat = tmp_path / "aparat.ps1"
    aparat.write_text(_APARAT_E224, encoding="utf-8-sig")
    cikti = tmp_path / "cikti.json"
    p = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(aparat),
         "-Setup", str(SETUP), "-Footprint", str(FOOTPRINT), "-App", str(app), "-Klinik", str(klinik),
         "-Senaryo", senaryo, "-Cikti", str(cikti)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
    )  # fmt: skip
    assert p.returncode == 0 and cikti.exists(), (
        f"aparat düştü (rc={p.returncode}):\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}"
    )
    return json.loads(cikti.read_text(encoding="utf-8-sig")), app


def test_ARAC_ek_golgeler_ISLEV_dosya_yazimi_ATLANIR_E2_2_4(tmp_path):
    """Aparat öz-denetimi: ek gölgeler ve kayıtçılar işlevdir (gerçek cmdlet değil); izin listesi dışı yazım (.install_verified) KOŞMAZ."""
    s, app = _kos(tmp_path, "kurulum_device_kendi")
    assert all(t.endswith("=Function") for t in s["komut_turleri"]), s["komut_turleri"]
    assert not (app / ".install_verified").exists(), "izin listesi DIŞI dosya yazımı koştu (aparat korumasız)"
    assert s["atlanan"] > 0, s


def test_KRITIK_launcher_cocugu_portu_tutarken_kurulum_DOGRULANDI_DEMEZ_port_dolu_der_E2_2_4(tmp_path):
    s, _ = _kos(tmp_path, "kurulum_device_launcher")
    k = s["kayit"]
    assert "Stop-Process 303" not in k, f"S-E.4 karşıtı: launcher çocuğu öldürüldü: {k}"
    dogrulandi = [x for x in k if "Kurulum DOĞRULANDI" in x]
    assert not dogrulandi and s["cikis"] == 1, (
        "port BAŞKA bir PEMF backend'i (launcher çocuğu) tarafından tutulurken kurulum DURMADI; sağlık sondası onun 200'ünü bu servisin "
        f"sandı: cikis={s['cikis']} {dogrulandi}\n" + "\n".join(k)
    )
    neden = [x for x in k if x.startswith("LOG ") and "dolu" in x and "PEMF Vet Client" in x]
    assert neden, "ret nedeni (port dolu + sahibi) günlüğe yazılmadı:\n" + "\n".join(k)
    assert not [x for x in k if x.startswith(("nssm install PemfBackend", "nssm start PemfBackend", "FW-YENI"))], (
        f"port dolu iken servis/kural DEĞİŞTİRİLDİ: {k}"
    )


def test_KARSIT_portu_BU_kurulumun_eski_backendi_tutuyorsa_kurulum_surer_ve_DOGRULANIR_E2_2_4(tmp_path):
    s, _ = _kos(tmp_path, "kurulum_device_kendi")
    k = s["kayit"]
    assert s["cikis"] is None and any("Kurulum DOĞRULANDI" in x for x in k), "\n".join(k)
    assert "Stop-Process 202" in k and "Stop-Process 303" not in k, k
