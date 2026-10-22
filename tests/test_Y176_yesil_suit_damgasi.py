# -*- coding: utf-8 -*-
"""Y176 (S-YH.7 = S-4BI.9) — yayın dizinine manifest yazımı Y30 YEŞİL-SÜİT DAMGASI ister; tek istisna "acil fren".

ÖLÇÜLEN DURUM (YH D4 #8, 2026-10-22): `scripts/make_manifest.py` yayın dizinine (`pemf-app-packages`) doğrudan çağrıyla da yazabiliyordu
→ Y30 (yayın öncesi ZORUNLU tam süit) yalnız `katmanli_yayin_hazirla.ps1` yolunda koşuyordu; BUILD.md §6'daki "doğrudan çağırmayın"
uyarısı sözdü. Sahip kararı Y176: `yayin_oncesi_suit.ps1` TAM kipte (kancasız) geçince damga yazar, kırmızıda siler; `make_manifest.py`
yayın dizinine yazarken HEAD'i tutan, ≤ 24 sa, TAM damga ister. İSTİSNA: yalnız `--rollout` / `--launcher-rollout` DÜŞÜREN (paket / sha
değişmeyen) "acil fren" damgasız geçer ve bunu yüksek sesle yazar (bozuk yayını durdurmak ~1,5 sa süit beklemez).

ÖLÇÜM (davranış, GERÇEK yayın dizinine DOKUNMADAN): iki betik geçici bir git deposuna KOPYALANIR (`<tmp>/scripts/…`) → kopyanın yayın
dizini `<tmp>/pemf-app-packages`, git dizini `<tmp>/.git`. make_manifest kopyası gerçek git ile HEAD okur; Y30 betiği gerçek pwsh +
gerçek pytest ile (geçici `tests/`) TAM kipte koşar.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
MANIFEST_BETIK = KOK / "scripts" / "make_manifest.py"
SUIT_BETIK = KOK / "scripts" / "yayin_oncesi_suit.ps1"
YAYINDAKI = KOK / "pemf-app-packages" / "manifest.json"
PWSH = shutil.which("pwsh")
GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(GIT is None, reason="git gerekir (damga HEAD'e bağlıdır)")


def _ortam() -> dict:
    """GIT_* SÜZÜLÜR: pre-commit kancası altında `GIT_DIR` / `GIT_INDEX_FILE` miras kalırsa geçici depo yerine GERÇEK depoya gidilirdi."""
    return {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}


def _git(depo: Path, *a: str) -> str:
    r = subprocess.run(
        [
            GIT,
            "-C",
            str(depo),
            "-c",
            "user.name=y176",
            "-c",
            "user.email=y176@ornek.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=",
            *a,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=_ortam(),
    )
    assert r.returncode == 0, f"git {a}: {r.stderr[-400:]}"
    return r.stdout.strip()


@pytest.fixture
def depo(tmp_path: Path) -> Path:
    d = tmp_path / "depo"
    (d / "scripts").mkdir(parents=True)
    (d / "pemf-app-packages").mkdir()
    shutil.copy2(MANIFEST_BETIK, d / "scripts" / "make_manifest.py")
    shutil.copy2(SUIT_BETIK, d / "scripts" / "yayin_oncesi_suit.ps1")
    _git(d, "init", "-q")
    _git(d, "add", "-A")
    _git(d, "commit", "-q", "-m", "y176")
    return d


def _head(d: Path) -> str:
    return _git(d, "rev-parse", "HEAD")


def _damga_yolu(d: Path) -> Path:
    return Path(_git(d, "rev-parse", "--absolute-git-dir")) / "pemf-y30-damga.json"


def _damga_yaz(d: Path, **ek) -> Path:
    veri = {"head": _head(d), "zaman": int(time.time()), "kip": "TAM", "betik": "scripts/yayin_oncesi_suit.ps1", **ek}
    y = _damga_yolu(d)
    y.write_text(json.dumps(veri), encoding="utf-8")
    return y


def _zipler(dizin: Path, isaret: bytes = b"APP") -> None:
    sabit = (1980, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(dizin / "base-app.zip", "w", zipfile.ZIP_STORED) as z:
        z.writestr(zipfile.ZipInfo("PEMF_Backend/PEMF_Backend.exe", date_time=sabit), isaret * 50)
        z.writestr(zipfile.ZipInfo("PEMF_Backend/_app_roots.json", date_time=sabit), b'{"roots": []}')
    with zipfile.ZipFile(dizin / "base-deps.zip", "w", zipfile.ZIP_STORED) as z:
        z.writestr(zipfile.ZipInfo("PEMF_Backend/_internal/deps.bin", date_time=sabit), b"DEPS" * 50)


def _manifest(d: Path, *ek: str, dizin: Path | None = None, surum: str = "1.9.0", etiket: str = "client-app-v1.9.0"):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [
            sys.executable,
            str(d / "scripts" / "make_manifest.py"),
            "--dir",
            str(dizin or (d / "pemf-app-packages")),
            "--version",
            surum,
            "--tag",
            etiket,
            "--repo",
            "mert61-python/pemf-update",
            *ek,
        ],
        cwd=d,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )


ONCEKI = {
    "schema": 2,
    "version": "1.9.0",
    "tag": "client-app-v1.9.0",
    "launcher": {
        "version": "1.9.51",
        "installer_url": "https://x/setup.exe",
        "sha256": "a" * 64,
        "size": 1,
        "rollout": 100,
    },
    "layers": {
        "win-x64": {
            "rollout": 100,
            "app": {"url": "https://x/base-app.zip", "sha256": "c" * 64, "size": 3, "kind": "zip"},
            "deps": {"url": "https://x/base-deps.zip", "sha256": "d" * 64, "size": 4, "kind": "zip"},
        }
    },
    "runtimes": {},
    "models": {},
    "profiles": {},
}


def _onceki_yaz(d: Path, katman_rollout: int = 100, launcher_rollout: int = 100) -> Path:
    m = json.loads(json.dumps(ONCEKI))
    m["layers"]["win-x64"]["rollout"] = katman_rollout
    m["launcher"]["rollout"] = launcher_rollout
    y = d / "pemf-app-packages" / "manifest.json"
    y.write_text(json.dumps(m), encoding="utf-8")
    return y


# ── make_manifest: yayın dizinine yazım damga ister ────────────────────────


def test_KRITIK_yayin_dizinine_DAMGASIZ_yazilmaz(depo):
    once = _onceki_yaz(depo).read_bytes()
    _zipler(depo / "pemf-app-packages")
    r = _manifest(depo)
    assert r.returncode == 1, f"damgasız yayın dizinine YAZDI: rc={r.returncode}\n{r.stderr[-800:]}"
    assert "Y30 yesil-suit damgasi gecersiz" in r.stderr and "damga YOK" in r.stderr, r.stderr[-800:]
    assert (depo / "pemf-app-packages" / "manifest.json").read_bytes() == once, "red YAZDIKTAN SONRA geldi"


def test_KARSIT_gecerli_damga_ile_YAZAR(depo):
    _onceki_yaz(depo)
    _zipler(depo / "pemf-app-packages")
    _damga_yaz(depo)
    r = _manifest(depo)
    assert r.returncode == 0, r.stderr[-800:]
    m = json.loads((depo / "pemf-app-packages" / "manifest.json").read_text(encoding="utf-8"))
    assert m["layers"]["win-x64"]["app"]["sha256"] != ONCEKI["layers"]["win-x64"]["app"]["sha256"], (
        "yeni paket mühürlenmedi"
    )


@pytest.mark.parametrize(
    "ek, neden",
    [
        ({"kip": "DAR"}, "kipi TAM degil"),
        ({"head": "0" * 40}, "baska bir HEAD"),
        ({"zaman": int(time.time()) - 25 * 3600}, "BAYAT"),
        ({"zaman": int(time.time()) + 3600}, "GELECEKTE"),
        ({"zaman": "dun"}, "zamani yok / bozuk"),
    ],
    ids=["kip_dar", "baska_head", "bayat_25sa", "gelecek", "zaman_bozuk"],
)
def test_KRITIK_gecersiz_damga_RED(depo, ek, neden):
    once = _onceki_yaz(depo).read_bytes()
    _zipler(depo / "pemf-app-packages")
    _damga_yaz(depo, **ek)
    r = _manifest(depo)
    assert r.returncode == 1 and neden in r.stderr, f"rc={r.returncode} beklenen neden '{neden}'\n{r.stderr[-800:]}"
    assert (depo / "pemf-app-packages" / "manifest.json").read_bytes() == once, "geçersiz damgayla YAZDI"


def test_KRITIK_bozuk_JSON_damga_RED(depo):
    _onceki_yaz(depo)
    _zipler(depo / "pemf-app-packages")
    _damga_yolu(depo).write_text("{bozuk", encoding="utf-8")
    r = _manifest(depo)
    assert r.returncode == 1 and "bozuk" in r.stderr, r.stderr[-800:]


def test_KRITIK_yeni_commit_damgayi_GECERSIZ_kilar(depo):
    _onceki_yaz(depo)
    _zipler(depo / "pemf-app-packages")
    _damga_yaz(depo)
    (depo / "yeni.txt").write_text("x", encoding="utf-8")
    _git(depo, "add", "yeni.txt")
    _git(depo, "commit", "-q", "-m", "sonra")
    r = _manifest(depo)
    assert r.returncode == 1 and "baska bir HEAD" in r.stderr, r.stderr[-800:]


def test_KARSIT_yayin_dizini_DISINA_damga_istenmez(depo, tmp_path):
    baska = tmp_path / "baska"
    baska.mkdir()
    (baska / "manifest.json").write_text(json.dumps(ONCEKI), encoding="utf-8")
    _zipler(baska)
    r = _manifest(depo, dizin=baska)
    assert r.returncode == 0, r.stderr[-800:]
    assert "damga" not in r.stderr.lower(), r.stderr[-800:]


# ── acil fren istisnası ─────────────────────────────────────────────────────


def test_KRITIK_ACIL_FREN_rollout_dusurme_DAMGASIZ_gecer_ve_YUKSEK_SESLE_yazar(depo):
    _onceki_yaz(depo)
    r = _manifest(depo, "--rollout", "0")
    assert r.returncode == 0, f"acil fren damga beklemeden geçmeliydi: {r.stderr[-800:]}"
    assert "[ACIL FREN]" in r.stderr, r.stderr[-800:]
    m = json.loads((depo / "pemf-app-packages" / "manifest.json").read_text(encoding="utf-8"))
    assert m["layers"]["win-x64"]["rollout"] == 0
    assert m["layers"]["win-x64"]["app"] == ONCEKI["layers"]["win-x64"]["app"], "fren paketi DEĞİŞTİRDİ"


def test_KRITIK_ACIL_FREN_launcher_rollout_dusurme_DAMGASIZ_gecer(depo):
    _onceki_yaz(depo)
    r = _manifest(depo, "--launcher-rollout", "0")
    assert r.returncode == 0 and "[ACIL FREN]" in r.stderr, r.stderr[-800:]
    m = json.loads((depo / "pemf-app-packages" / "manifest.json").read_text(encoding="utf-8"))
    assert m["launcher"]["rollout"] == 0


def test_KRITIK_rollout_YUKSELTME_fren_DEGIL_damga_ister(depo):
    _onceki_yaz(depo, katman_rollout=0)
    r = _manifest(depo, "--rollout", "100")
    assert r.returncode == 1 and "damga YOK" in r.stderr, f"geri çekilmiş yayını damgasız AÇTI: {r.stderr[-800:]}"


def test_KRITIK_biri_DUSER_oteki_YUKSELIRSE_fren_DEGIL_damga_ister(depo):
    # YLI mutant y176_m2: `r > o` denetimi silinince yalnız-yükseltme vakası yine yeşildi (hiçbir rollout düşmediği için); karışık
    # çağrıda (katman 50 → 0, launcher 50 → 100) yükseltme "fren" kılığında damgasız geçerdi.
    once = _onceki_yaz(depo, katman_rollout=50, launcher_rollout=50).read_bytes()
    r = _manifest(depo, "--rollout", "0", "--launcher-rollout", "100")
    assert r.returncode == 1 and "damga YOK" in r.stderr, f"karışık çağrıda yükseltme damgasız geçti: {r.stderr[-800:]}"
    assert (depo / "pemf-app-packages" / "manifest.json").read_bytes() == once


def test_KRITIK_YENI_PAKETLE_rollout_dusurme_fren_DEGIL(depo):
    _onceki_yaz(depo)
    _zipler(depo / "pemf-app-packages", b"YENI")
    r = _manifest(depo, "--rollout", "0")
    assert r.returncode == 1 and "damga YOK" in r.stderr, f"yeni paketi 'fren' diye damgasız yazdı: {r.stderr[-800:]}"


def test_KRITIK_surum_degisirse_fren_DEGIL(depo):
    _onceki_yaz(depo)
    r = _manifest(depo, "--rollout", "0", surum="1.9.1", etiket="client-app-v1.9.1")
    assert r.returncode == 1 and "damga YOK" in r.stderr, r.stderr[-800:]


def test_KRITIK_rollout_VERILMEDEN_fren_DEGIL(depo):
    _onceki_yaz(depo)
    r = _manifest(depo)
    assert r.returncode == 1 and "damga YOK" in r.stderr, r.stderr[-800:]


@pytest.mark.skipif(not YAYINDAKI.exists(), reason="yayındaki manifest kopyası yok")
def test_KARSIT_GERCEK_yayin_manifestiyle_launcher_FRENI_damgasiz_gecer(depo):
    """BUILD.md "Bozuk bir yayını geri çekmek": yayındaki manifestin kopyası + paketsiz dizin + `--launcher-rollout 0` → damgasız
    geçmeli (paket kimliği yayınla AYNI kalmalı — betiğin ürettiği yapı yayındakiyle uyumlu)."""
    hedef = depo / "pemf-app-packages" / "manifest.json"
    shutil.copy2(YAYINDAKI, hedef)
    m = json.loads(hedef.read_text(encoding="utf-8"))
    r = _manifest(depo, "--launcher-rollout", "0", surum=m["version"], etiket=m["tag"])
    assert r.returncode == 0 and "[ACIL FREN]" in r.stderr, f"gerçek manifestle acil fren DÜŞTÜ:\n{r.stderr[-1200:]}"


# ── yayin_oncesi_suit.ps1: TAM kipte yazar / siler; kancalı kip dokunmaz ─────

_GECEN = "def test_gecer():\n    assert True\n"
_DUSEN = "def test_duser():\n    assert False, 'Y176-KIRMIZI'\n"


def _suit(d: Path, kancali: bool = False) -> subprocess.CompletedProcess:
    if PWSH is None or os.name != "nt":
        pytest.skip("pwsh 7 + Windows gerekir (Y30 yayın makinesi)")
    komut = [
        PWSH,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(d / "scripts" / "yayin_oncesi_suit.ps1"),
    ]
    if kancali:
        komut += ["-PytestOnek", f"{sys.executable},-m,pytest"]
    else:
        komut += ["-Python", sys.executable]
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        komut, cwd=d, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=300
    )


def _testler(d: Path, govde: str) -> None:
    (d / "tests").mkdir(exist_ok=True)
    (d / "tests" / "test_y176_ornek.py").write_text(govde, encoding="utf-8")
    (d / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")


def test_KRITIK_suit_TAM_kipte_GECINCE_damga_yazar_HEAD_ile(depo):
    _testler(depo, _GECEN)
    once = int(time.time())
    r = _suit(depo)
    assert r.returncode == 0, (r.stdout + r.stderr)[-1200:]
    y = _damga_yolu(depo)
    assert y.exists(), f"TAM kip yeşilken damga YAZILMADI:\n{r.stdout[-800:]}"
    d = json.loads(y.read_text(encoding="utf-8-sig"))
    assert d["head"] == _head(depo) and d["kip"] == "TAM" and once - 5 <= d["zaman"] <= int(time.time()) + 5, d


def test_KRITIK_suit_KIRMIZIDA_eski_damgayi_SILER(depo):
    _testler(depo, _DUSEN)
    y = _damga_yaz(depo)
    r = _suit(depo)
    assert r.returncode != 0, r.stdout[-800:]
    assert not y.exists(), "kırmızı süitten sonra eski damga DURUYOR — yayın kırmızıyla geçebilirdi"


def test_KRITIK_kancali_kip_damgaya_DOKUNMAZ(depo):
    _testler(depo, _GECEN)
    y = _damga_yaz(depo, zaman=12345)
    once = y.read_bytes()
    r = _suit(depo, kancali=True)
    assert r.returncode == 0, (r.stdout + r.stderr)[-1200:]
    assert y.exists() and y.read_bytes() == once, "kancalı (dar) süit damgayı YAZDI / değiştirdi"


def test_KRITIK_UCTAN_UCA_suit_damgasi_make_manifesti_ACAR(depo):
    _testler(depo, _GECEN)
    _git(depo, "add", "-A")
    _git(depo, "commit", "-q", "-m", "testler")
    _onceki_yaz(depo)
    _zipler(depo / "pemf-app-packages")
    assert _manifest(depo).returncode == 1, "süitten ÖNCE yazdı"
    r = _suit(depo)
    assert r.returncode == 0, (r.stdout + r.stderr)[-1200:]
    m = _manifest(depo)
    assert m.returncode == 0, f"geçen süitin damgası kabul edilmedi:\n{m.stderr[-800:]}"
