# -*- coding: utf-8 -*-
"""Y30 · D4.10 · B-10.3 — yayın öncesi ZORUNLU tam süit yayın betiğine BAĞLI; CI atlamaları nedeniyle listeler.

🔴 ÖLÇÜLEN DURUM (2026-10-10, 4-A): `tests.yml`'in pytest satırlarında `-rs` yoktu (≥193 atlama nedensiz "yeşil"
okunuyordu); `PEMF_CAPRAZ_KAYNAK_ZORUNLU` / `PEMF_GOLDEN_REQUIRED` hiçbir `.ps1`/`.yml`de ayarlanmıyordu — "yayın makinesi
bayrağı ayarlar" güvencesinin karşılığı YOKTU. Sahip kararı Y30: zorunlu tam süit YAYIN BETİĞİNE BAĞLI adımdır, süit
geçmeden betik ilerlemez (Ö.4-Y1: betik bugün koşturulmaz — bu kapı onu GÖLGELİ koşumla ölçer).

KAPI (davranış):
  · `publish_release.ps1` gerçek pwsh'ta, geçici bir kopyada koşulur; `yayin_oncesi_suit.ps1` yerine kayıtçı taslak,
    `git` / `gh` / `Invoke-RestMethod` / `Invoke-WebRequest` kayıtçı GÖLGE fonksiyonlar. ⚠️ Çifte emniyet: alt sürecin
    PATH'i BOŞ bir dizindir — gölge düşse bile gerçek `git` (kimlik deposu) bulunamaz; ağ çağrısı gölgede `throw` eder.
    Süit düşünce: kayıt yalnız `SUIT`, git/ağ YOK, çıkış ≠ 0. KARŞIT: süit geçince betik ilerler (`SUIT` → `GIT …`).
  · Gerçek `yayin_oncesi_suit.ps1` geçici bir test dizinine karşı koşulur: dış ortamda iki bayrak bilerek "0" iken
    (koşucu maskelemesin) süreçte ikisi de "1", `-rs` atlama nedenini basar, kırmızı test çıkış kodunu TAŞIR.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
BETIKLER = KOK / "scripts"
_PWSH = shutil.which("pwsh")


def _pwsh_gerekli() -> str:
    if _PWSH:
        return _PWSH
    if capraz.ZORUNLU:
        pytest.fail("PEMF_CAPRAZ_KAYNAK_ZORUNLU=1 ama pwsh (PowerShell 7) yok — Y30 kapısı koşulamıyor")
    pytest.skip("pwsh (PowerShell 7) bulunamadı")


def _yaz_bom(yol: Path, metin: str) -> None:
    yol.write_bytes(b"\xef\xbb\xbf" + metin.encode("utf-8"))


# ── 1) CI: atlama nedenleri görünür ─────────────────────────────────────────


def test_KRITIK_CI_pytest_satirlari_ATLAMA_NEDENINI_listeler():
    yaml = pytest.importorskip("yaml", reason="pyyaml yok")
    adimlar = yaml.safe_load((KOK / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))["jobs"][
        "backend"
    ]
    pytestli = [str(a.get("run", "")) for a in adimlar["steps"] if "pytest tests" in str(a.get("run", ""))]
    assert len(pytestli) == 2, f"Linux + Windows pytest adımı bekleniyordu: {pytestli}"
    eksik = [r for r in pytestli if not re.search(r"(^|\s)-r[a-zA-Z]*s", r)]
    assert not eksik, f"`-rs` YOK — CI atlamaları nedensiz yeşil okunur: {eksik}"
    ozetsiz = [r for r in pytestli if not _rapor_harfleri_kirmiziyi_da_listeler(r)]
    assert not ozetsiz, (
        f"pytest `-r` harfleri kırmızıları listelemiyor: {ozetsiz} — `-r<harfler>` varsayılan `fE`nin YERİNE geçer; `-rs` tek "
        "başına kısa özetteki FAILED/ERROR satırlarını SİLER (4A-4.1). `-rfEs` (ya da `-ra`) kullanın."
    )


def _rapor_harfleri_kirmiziyi_da_listeler(komut: str) -> bool:
    """4A-4.1 (4-A incelemesi, ölçüldü pytest 9.1.1): `-r` seçeneği varsayılanı (`fE`) EKLEMEZ, DEĞİŞTİRİR. Komuttaki bütün
    `-r<harfler>` birleşimi `a`/`A` içermeli ya da `f`, `E` ve `s`'nin üçünü de içermeli."""
    harfler = "".join(re.findall(r"(?:^|\s)-r([a-zA-Z]+)", komut))
    return bool(set("aA") & set(harfler)) or set("fEs") <= set(harfler)


# ── 2) publish_release.ps1: süit geçmeden İLERLEMEZ ─────────────────────────

_TASLAK_SUIT = "Add-Content -LiteralPath $env:Y30_KAYIT -Value 'SUIT'\nexit [int]$env:Y30_SUIT_RC\n"
_SARMAL = r"""param([string]$Publish, [string]$Asset)
$ErrorActionPreference = 'Stop'
function global:git { Add-Content -LiteralPath $env:Y30_KAYIT -Value ('GIT ' + ($args -join ' ')) }
function global:gh { Add-Content -LiteralPath $env:Y30_KAYIT -Value 'GH'; throw 'golge gh' }
function global:Invoke-RestMethod { Add-Content -LiteralPath $env:Y30_KAYIT -Value 'IRM'; throw 'golge irm' }
function global:Invoke-WebRequest { Add-Content -LiteralPath $env:Y30_KAYIT -Value 'IWR'; throw 'golge iwr' }
try { & $Publish -Branch exe -Version 9.9.9 -AssetPath $Asset; Write-Host 'PUBLISH-BITTI'; exit 0 }
catch { Write-Host ('PUBLISH-HATA: ' + $_.Exception.Message); exit 9 }
"""


def _publish_golge(tmp_path: Path, suit_rc: int) -> tuple[int, list[str], str]:
    pwsh = _pwsh_gerekli()
    d = tmp_path / f"rc{suit_rc}"
    (d / "scripts").mkdir(parents=True)
    (d / "bos_path").mkdir()
    shutil.copy2(BETIKLER / "publish_release.ps1", d / "scripts" / "publish_release.ps1")
    _yaz_bom(d / "scripts" / "yayin_oncesi_suit.ps1", _TASLAK_SUIT)
    _yaz_bom(d / "sarmal.ps1", _SARMAL)
    (d / "asset.bin").write_bytes(b"x")
    kayit = d / "kayit.txt"
    kayit.write_text("", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("PATH", "PEMF_CAPRAZ_KAYNAK_ZORUNLU")}
    env.update({"PATH": str(d / "bos_path"), "Y30_KAYIT": str(kayit), "Y30_SUIT_RC": str(suit_rc)})
    env.update({"HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "GIT_TERMINAL_PROMPT": "0"})
    komut = [pwsh, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(d / "sarmal.ps1")]
    komut += ["-Publish", str(d / "scripts" / "publish_release.ps1"), "-Asset", str(d / "asset.bin")]
    r = subprocess.run(
        komut, cwd=d, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180
    )
    satirlar = [s.strip() for s in kayit.read_text(encoding="utf-8-sig").splitlines() if s.strip()]
    return r.returncode, satirlar, r.stdout + r.stderr


def test_KRITIK_publish_SUIT_GECMEZSE_kimlik_ve_aga_DOKUNMADAN_durur(tmp_path):
    rc, kayit, cikti = _publish_golge(tmp_path, suit_rc=3)
    assert kayit == ["SUIT"], f"süit düştüğü hâlde publish ilerledi ya da süiti hiç çağırmadı: {kayit}\n{cikti[-800:]}"
    assert rc == 9 and "Y30" in cikti and "PUBLISH-BITTI" not in cikti, f"rc={rc}\n{cikti[-800:]}"


def test_KARSIT_KANIT_publish_SUIT_GECERSE_ILERLER(tmp_path):
    """Ölçücü kör değil: süit geçince publish kimlik adımına GEÇER (sıra: SUIT → GIT); gölge git boş döner → token yok."""
    rc, kayit, cikti = _publish_golge(tmp_path, suit_rc=0)
    assert kayit[:1] == ["SUIT"] and any(s.startswith("GIT credential") for s in kayit[1:]), f"{kayit}\n{cikti[-800:]}"
    assert "IRM" not in kayit and rc == 9 and "token bulunamadi" in cikti, f"rc={rc} {kayit}\n{cikti[-800:]}"


# ── 3) yayin_oncesi_suit.ps1: ZORUNLU kip + -rs + çıkış kodu ────────────────

_ORNEK_TEST = """import os
import pytest


def test_bayraklar():
    assert os.environ.get("PEMF_CAPRAZ_KAYNAK_ZORUNLU") == "1"
    assert os.environ.get("PEMF_GOLDEN_REQUIRED") == "1"


def test_atlanan():
    pytest.skip("Y30-ATLAMA-NEDENI")
"""


def _suit_kos(tmp_path: Path, kirmizi: bool) -> tuple[int, str]:
    pwsh = _pwsh_gerekli()
    hedef = tmp_path / ("kirmizi" if kirmizi else "yesil")
    hedef.mkdir()
    (hedef / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    ek = "\n\ndef test_kirmizi():\n    assert False, 'Y30-KIRMIZI'\n" if kirmizi else ""
    (hedef / "test_y30_ornek.py").write_text(_ORNEK_TEST + ek, encoding="utf-8")
    env = dict(os.environ, PEMF_CAPRAZ_KAYNAK_ZORUNLU="0", PEMF_GOLDEN_REQUIRED="0", PYTHONDONTWRITEBYTECODE="1")
    komut = [pwsh, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File"]
    komut += [
        str(BETIKLER / "yayin_oncesi_suit.ps1"),
        "-PytestOnek",
        f"{sys.executable},-m,pytest",
        "-Hedef",
        str(hedef),
    ]
    r = subprocess.run(
        komut, cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300
    )
    return r.returncode, r.stdout + r.stderr


def test_KRITIK_yayin_oncesi_suit_ZORUNLU_kipte_kosar_ve_ATLAMA_nedenini_listeler(tmp_path):
    rc, cikti = _suit_kos(tmp_path, kirmizi=False)
    assert rc == 0, f"bayraklar süreçte '1' değil ya da süit düştü (rc={rc}):\n{cikti[-1500:]}"
    assert "1 passed, 1 skipped" in cikti, cikti[-1500:]
    assert "Y30-ATLAMA-NEDENI" in cikti, f"-rs yok: atlama nedeni listelenmedi\n{cikti[-1500:]}"


def test_KRITIK_yayin_oncesi_suit_KIRMIZIYI_cikis_koduyla_TASIR(tmp_path):
    rc, cikti = _suit_kos(tmp_path, kirmizi=True)
    assert rc == 1, f"kırmızı süit çıkış kodu taşınmadı (rc={rc}) — publish bunu GEÇTİ sanardı\n{cikti[-1500:]}"
    assert "1 failed" in cikti and "YAYIN DURDU" in cikti, cikti[-1500:]
    # 4A-4.1: betiğin "kırmızıları ve atlama nedenlerini okuyun" iletisi kısa özete yönlendirir — kırmızı orada ADIYLA görünmeli
    # (4-A'nın ZORUNLU tam süit çıktısında 22 kırmızıya karşı FAILED/ERROR satırı 0, SKIPPED satırı 116'ydı).
    assert re.search(r"^FAILED \S*test_y30_ornek\.py::test_kirmizi\b", cikti, re.M), (
        f"kırmızı test kısa özette ADIYLA listelenmedi (`-rs` varsayılan `-rfE`yi siler):\n{cikti[-1500:]}"
    )


# ── 4) pwsh 7'nin modül yolu pytest'in açtığı Windows PowerShell 5.1'e SIZMAZ ──
# ⚠️ ÖLÇÜLDÜ (4-A ZORUNLU koşusu, 2026-10-10): betik pwsh 7'de koşar; pwsh kendi modül dizinlerini süreç `PSModulePath`ine
# ekler, pytest → `powershell.exe` (5.1) bunu MİRAS alır ve `Microsoft.PowerShell.Security`nin 7 sürümünü yükleyemez →
# "Get-Acl … module could not be loaded" → 9 ACL testi (D2.79/D2.81/Y96) YALANCI KIRMIZI, Y30 her yayını durdururdu.
# (pwsh `powershell.exe`yi DOĞRUDAN açınca yolu kendisi ayıklar; araya python girince ayıklama YOK.)

_ACL_TEST = """import os
import subprocess


def test_alt_powershell51_get_acl():
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", f"(Get-Acl -LiteralPath '{os.getcwd()}').Sddl"],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0 and "D:" in r.stdout, "Y30-GETACL-DUSTU " + (r.stdout + r.stderr)[-300:]
"""
_ACL_SARMAL = """param([string]$Betik, [string]$Onek, [string]$Hedef)
$once = $env:PSModulePath
& $Betik -PytestOnek $Onek -Hedef $Hedef
$rc = $LASTEXITCODE
if ($env:PSModulePath -ne $once) { Write-Host 'Y30-PSMODULEPATH-GERI-YUKLENMEDI'; exit 97 }
exit $rc
"""


def test_KRITIK_yayin_oncesi_suit_pwsh7_modul_yolunu_alt_PowerShell51e_SIZDIRMAZ_ve_GERI_yukler(tmp_path):
    pwsh = _pwsh_gerekli()
    if os.name != "nt" or not shutil.which("powershell.exe"):
        pytest.skip("Windows PowerShell 5.1 yalnız Windows'ta")
    hedef = tmp_path / "acl"
    hedef.mkdir()
    (hedef / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (hedef / "test_y30_acl.py").write_text(_ACL_TEST, encoding="utf-8")
    _yaz_bom(tmp_path / "sarmal.ps1", _ACL_SARMAL)
    komut = [pwsh, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(tmp_path / "sarmal.ps1")]
    komut += ["-Betik", str(BETIKLER / "yayin_oncesi_suit.ps1"), "-Onek", f"{sys.executable},-m,pytest"]
    komut += ["-Hedef", str(hedef)]
    r = subprocess.run(
        komut, cwd=hedef, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300
    )
    cikti = r.stdout + r.stderr
    assert "Y30-GETACL-DUSTU" not in cikti and r.returncode == 0, f"rc={r.returncode}\n{cikti[-1500:]}"
    assert "1 passed" in cikti, cikti[-1500:]
