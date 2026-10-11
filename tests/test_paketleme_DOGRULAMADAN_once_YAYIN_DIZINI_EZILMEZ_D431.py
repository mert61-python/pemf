# -*- coding: utf-8 -*-
"""D4.31 (B-9.3 · B-9.4) — başarısız paketleme GEÇERLİ yayın zip'ini EZMEZ; EXE'siz app katmanı manifeste MÜHÜRLENMEZ.

ARIZA 1 (B-9.3, ölçüldü): `build_tools/make_base_zip.py` zip'leri önce yayın dizinine (`os.replace`) yazıyor, YAPI DOĞRULAMASINI
SONRA koşuyordu. EXE'siz ya da korumasız (düz .py) bir dist ile koşu çıkış 1 + "VALIDATION: FAIL" verirken önceki GEÇERLİ
`base-app.zip`'i EXE'siz bir zip'le EZMİŞ oluyordu. Doğru düzen: `.tmp`'ye yaz → `.tmp`'yi doğrula → YALNIZ PASS'te yerine koy.

ARIZA 2 (B-9.4, ölçüldü): `scripts/make_manifest.py` yereldeki `base-app.zip`'in İÇERİĞİNE bakmadan sha'sını mühürlüyordu.
guii'deki yerel `base-app.zip` 7 girdilik bir taslak (6 betik + `_app_roots.json`, EXE YOK) — acil `--rollout 0` yolunda bu
klasörle koşulursa çıkış 0 ve canlı URL'ye EXE'siz app katmanı: taze kurulum / "Onar" / geri çağırma fail-closed düşer.

Betikler GERÇEKTEN alt süreçte koşar; çıktı `PEMF_PKG_OUT` / `--dir` ile tmp'ye yönlenir (gerçek `pemf-app-packages/`a dokunulmaz).
Her kolda ÇIKIŞ KODU da ölçülür (`exit 0` ile biten hata yolu = sahte başarı KIRMIZI).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
MAKE_BASE_ZIP = KOK / "build_tools" / "make_base_zip.py"
MAKE_MANIFEST = KOK / "scripts" / "make_manifest.py"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _sahte_dist(kok: Path, exe: bool = True) -> Path:
    """make_base_zip'in yapı kapılarını geçen en küçük frozen-build taklidi (exe=False → EXE'siz)."""
    d = kok / "dist" / "PEMF_Backend"
    for alt in ("ai_hub", "frontend/dist", "bin/mosquitto", "torch", "ai_models/ai_hub/inference_cat_organ/models"):
        (d / "_internal" / alt).mkdir(parents=True, exist_ok=True)
    if exe:
        (d / "PEMF_Backend.exe").write_bytes(b"EXE-yeni-build")
    (d / "_internal" / "ai_hub" / "model.pyd").write_bytes(b"PYD")
    (d / "_internal" / "frontend" / "dist" / "index.html").write_text("<html>", encoding="utf-8")
    (d / "_internal" / "bin" / "mosquitto" / "mosquitto.exe").write_bytes(b"MOSQ")
    (d / "_internal" / "torch" / "lib.dll").write_bytes(b"TORCH" * 100)
    (d / "_internal" / "ai_models" / "ai_hub" / "inference_cat_organ" / "models" / "r.onnx").write_bytes(b"ORGAN")
    return d


def _zip(yol: Path, girdiler: dict[str, bytes]) -> None:
    with zipfile.ZipFile(yol, "w", zipfile.ZIP_STORED) as z:
        for ad, veri in girdiler.items():
            z.writestr(ad, veri)


def _nobetciler(cikti: Path) -> dict[str, str]:
    """Önceki GEÇERLİ yayının zip'leri (EXE'li) — bilinen sha'larıyla."""
    _zip(
        cikti / "base-app.zip", {"PEMF_Backend/PEMF_Backend.exe": b"NOBETCI-EXE", "PEMF_Backend/_app_roots.json": b"{}"}
    )
    _zip(cikti / "base-deps.zip", {"PEMF_Backend/_internal/torch/lib.dll": b"NOBETCI-DEPS"})
    _zip(
        cikti / "base.zip",
        {"PEMF_Backend/PEMF_Backend.exe": b"NOBETCI-EXE", "PEMF_Backend/_internal/torch/lib.dll": b"X"},
    )
    return {ad: _sha(cikti / ad) for ad in ("base-app.zip", "base-deps.zip", "base.zip")}


def _make_base_zip(dist: Path, cikti: Path, *ek: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PEMF_PKG_OUT": str(cikti)}
    return subprocess.run(
        [sys.executable, str(MAKE_BASE_ZIP), str(dist), *ek],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=300,
    )


@pytest.fixture
def kum(tmp_path):
    cikti = tmp_path / "paket_cikti"
    cikti.mkdir()
    return tmp_path, cikti


# ── 1) make_base_zip: doğrulama FAIL → yayın dizini DOKUNULMAZ ─────────────────────────────────


@pytest.mark.parametrize("ek", [(), ("--no-monolith",)], ids=["varsayilan", "no_monolith"])
def test_KRITIK_EXEsiz_dist_GECERLI_zipleri_EZMEZ(kum, ek):
    tmp, cikti = kum
    once = _nobetciler(cikti)
    dist = _sahte_dist(tmp, exe=False)
    r = _make_base_zip(dist, cikti, *ek)
    assert r.returncode == 1, f"EXE'siz dist ile paketleme BASARILI dondu (rc={r.returncode})\n{r.stdout[-1500:]}"
    assert "VALIDATION: FAIL" in r.stdout and "[FAIL] PEMF_Backend/PEMF_Backend.exe" in r.stdout, r.stdout[-1500:]
    sonra = {ad: _sha(cikti / ad) for ad in once if (cikti / ad).exists()}
    assert sonra == once, (
        "dogrulama FAIL oldugu halde yayin dizinindeki GECERLI zip(ler) degisti/silindi: "
        f"{sorted(ad for ad in once if sonra.get(ad) != once[ad])}"
    )
    artik = sorted(p.name for p in cikti.iterdir() if p.suffix == ".tmp")
    assert not artik, f"basarisiz kosu yari yazilmis .tmp birakti: {artik}"


def test_KRITIK_korumasiz_ai_hub_da_GECERLI_zipleri_EZMEZ(kum):
    """İkinci FAIL sınıfı (EXE var, `ai_hub`'da düz .py): kapı EXE'ye özgü değil, HER doğrulama kırmızısında yerine koyma yok."""
    tmp, cikti = kum
    once = _nobetciler(cikti)
    dist = _sahte_dist(tmp, exe=True)
    (dist / "_internal" / "ai_hub" / "gizli.py").write_text("# duz kaynak", encoding="utf-8")
    r = _make_base_zip(dist, cikti)
    assert r.returncode == 1 and "KORUMASIZ" in r.stdout, r.stdout[-1500:]
    assert {ad: _sha(cikti / ad) for ad in once} == once, "korumasiz paket FAIL'inde gecerli zip ezildi"
    assert not [p for p in cikti.iterdir() if p.suffix == ".tmp"], ".tmp artigi kaldi"


def test_KARSIT_gecerli_dist_PASSte_zipleri_YERINE_KOYAR(kum):
    """Ölçücü kör değil: aynı nöbetçilerle GEÇERLİ dist → çıkış 0, zip'ler YENİ içerikle yerinde, .tmp yok.
    (D4.32: tek-parça yalnız `--monolith` ile — bu kolda açık bayrakla; bayraksız koşu onu siler, D4.32 kapısında.)"""
    tmp, cikti = kum
    once = _nobetciler(cikti)
    r = _make_base_zip(_sahte_dist(tmp, exe=True), cikti, "--monolith")
    assert r.returncode == 0 and "VALIDATION: PASS" in r.stdout, r.stdout[-1500:] + r.stderr[-800:]
    for ad in once:
        assert _sha(cikti / ad) != once[ad], f"{ad} PASS'te yerine konmadi"
    with zipfile.ZipFile(cikti / "base-app.zip") as z:
        assert z.read("PEMF_Backend/PEMF_Backend.exe") == b"EXE-yeni-build"
    assert "[OK] yayin dizinine yerlesti: base-app.zip" in r.stdout, r.stdout[-1500:]
    assert not [p for p in cikti.iterdir() if p.suffix == ".tmp"], ".tmp artigi kaldi"


_OTURMAYAN_SARMAL = """import os
import runpy
import sys

betik, dist = sys.argv[1], sys.argv[2]
_gercek = os.replace


def _replace(src, dst, *a, **k):
    if os.path.basename(str(dst)) == "base-app.zip":
        return None  # kilit / antivirus / es zamanli yukleme: dosya yerine OTURMAZ, eski kopya kalir
    return _gercek(src, dst, *a, **k)


os.replace = _replace
sys.argv = [betik, dist]
runpy.run_path(betik, run_name="__main__")
"""


def test_KRITIK_yerine_OTURMAYAN_app_zip_FAIL_verir(kum):
    """PASS'ten sonra yayın dizinine koyma: `base-app.zip` yerine oturmazsa yayın dizininde ESKİ build'in app'i + YENİ deps
    kalır (karışık set). Betik bunu dosyanın sha'sını doğrulananla karşılaştırarak görmeli: çıkış 1 + adlandırılmış FAIL."""
    tmp, cikti = kum
    once = _nobetciler(cikti)
    sarmal = tmp / "oturmayan_sarmal.py"
    sarmal.write_text(_OTURMAYAN_SARMAL, encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PEMF_PKG_OUT": str(cikti)}
    r = subprocess.run(
        [sys.executable, str(sarmal), str(MAKE_BASE_ZIP), str(_sahte_dist(tmp, exe=True))],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=300,
    )
    assert _sha(cikti / "base-app.zip") == once["base-app.zip"], "on-kosul: base-app.zip yerine oturmamaliydi"
    assert r.returncode == 1, (
        f"yerine oturmayan base-app.zip ile betik BASARILI dondu (rc={r.returncode})\n{r.stdout[-1500:]}"
    )
    assert "[FAIL] yayin dizinine yerlesti: base-app.zip" in r.stdout and "VALIDATION: FAIL" in r.stdout, r.stdout[
        -1500:
    ]
    assert not [p for p in cikti.iterdir() if p.suffix == ".tmp"], ".tmp artigi kaldi"


# ── 2) make_manifest: EXE'siz app katmanı mühürlenmez ─────────────────────────────────────────

ONCEKI = {
    "schema": 2,
    "version": "1.9.50",
    "tag": "client-app-v1.9.50",
    "launcher": {"version": "1.9.51", "url": "https://x/setup.exe", "sha256": "a" * 64, "size": 1},
    "layers": {
        "win-x64": {
            "rollout": 100,
            "app": {"url": "https://x/v1.9.50/base-app.zip", "sha256": "c" * 64, "size": 3, "kind": "zip"},
            "deps": {"url": "https://x/v1.9.41/base-deps.zip", "sha256": "d" * 64, "size": 4, "kind": "zip"},
        }
    },
    "runtimes": {},
    "models": {},
    "profiles": {},
}

#: guii'deki yerel taslak base-app.zip'in biçimi (yalnız AD listesi ölçüldü): 6 betik + sınır dosyası, EXE YOK.
_TASLAK_7 = {
    **{
        f"PEMF_Backend/{b}": b"# betik"
        for b in (
            "install_hotspot_task.ps1",
            "pemf_footprint.ps1",
            "pemf_teardown.ps1",
            "pemf_uninstall_all.ps1",
            "setup_services.ps1",
            "start_hotspot.ps1",
        )
    },
    "PEMF_Backend/_app_roots.json": b'{"roots": []}',
}


def _make_manifest(dizin: Path, *ek: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [
            sys.executable,
            str(MAKE_MANIFEST),
            "--dir",
            str(dizin),
            "--version",
            "1.9.52",
            "--tag",
            "client-app-v1.9.52",
            "--repo",
            "mert61-python/pemf-update",
            *ek,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=180,
    )


@pytest.fixture
def paketler(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps(ONCEKI), encoding="utf-8")
    _zip(tmp_path / "base-deps.zip", {"PEMF_Backend/_internal/torch/lib.dll": b"DEPS"})
    return tmp_path


def _manifest_degismedi(d: Path) -> bool:
    return json.loads((d / "manifest.json").read_text(encoding="utf-8")) == ONCEKI


@pytest.mark.parametrize("ek", [(), ("--rollout", "0")], ids=["siradan", "acil_geri_cekme"])
def test_KRITIK_EXEsiz_7_girdilik_app_MUHURLENMEZ(paketler, ek):
    _zip(paketler / "base-app.zip", _TASLAK_7)
    r = _make_manifest(paketler, *ek)
    assert r.returncode == 1, (
        f"EXE'siz base-app.zip manifeste MUHURLENDI (rc={r.returncode})\n{r.stdout[-800:]}{r.stderr[-800:]}"
    )
    assert "PEMF_Backend/PEMF_Backend.exe" in r.stderr and "manifest YAZILMADI" in r.stderr, r.stderr[-1200:]
    assert "kaldirin" in r.stderr, "hata mesaji acil geri cekmenin yolunu SOYLEMIYOR"
    assert _manifest_degismedi(paketler), "hata verdigi halde manifest.json YAZILDI"


@pytest.mark.parametrize(
    "ad,icerik",
    [
        ("bozuk_zip", b"PK\x03\x04 yarim kalmis zip"),
        ("sinir_dosyasi_yok", None),
    ],
)
def test_KRITIK_bozuk_ya_da_sinirsiz_app_MUHURLENMEZ(paketler, ad, icerik):
    if icerik is None:
        _zip(paketler / "base-app.zip", {"PEMF_Backend/PEMF_Backend.exe": b"EXE"})  # _app_roots.json YOK
    else:
        (paketler / "base-app.zip").write_bytes(icerik)
    r = _make_manifest(paketler)
    assert r.returncode == 1, f"{ad}: app katmani muhurlendi (rc={r.returncode})\n{r.stderr[-800:]}"
    assert _manifest_degismedi(paketler), f"{ad}: manifest yazildi"


def test_KRITIK_mac_app_katmaninda_ikili_yoksa_MUHURLENMEZ(paketler):
    """Platformun ikilisi: Windows `PEMF_Backend.exe`, mac/linux `PEMF_Backend` (uzantısız). `.exe` koyan mac paketi de düşer."""
    (paketler / "base-deps.zip").unlink()  # yalnız mac katmanı yerelde: Windows yarım-set hatası karışmasın
    _zip(
        paketler / "base-mac-app.zip",
        {"PEMF_Backend/PEMF_Backend.exe": b"YANLIS", "PEMF_Backend/_app_roots.json": b"{}"},
    )
    _zip(paketler / "base-mac-deps.zip", {"PEMF_Backend/_internal/x": b"D"})
    r = _make_manifest(paketler)
    assert r.returncode == 1, f"mac app katmani ikilisiz muhurlendi (rc={r.returncode})\n{r.stderr[-800:]}"
    assert "base-mac-app.zip" in r.stderr and "PEMF_Backend/PEMF_Backend" in r.stderr, r.stderr[-800:]
    assert _manifest_degismedi(paketler), "mac: manifest yazildi"


def test_KARSIT_EXEli_app_katmani_MUHURLENIR(paketler):
    _zip(paketler / "base-app.zip", {"PEMF_Backend/PEMF_Backend.exe": b"EXE", "PEMF_Backend/_app_roots.json": b"{}"})
    r = _make_manifest(paketler)
    assert r.returncode == 0, r.stderr[-1200:]
    app = json.loads((paketler / "manifest.json").read_text(encoding="utf-8"))["layers"]["win-x64"]["app"]
    assert app["sha256"] == _sha(paketler / "base-app.zip") and app["url"].endswith("client-app-v1.9.52/base-app.zip")


def test_KARSIT_yerel_app_YOKSA_katman_TASINIR_acil_yol_acik(tmp_path):
    """Hata mesajının söylediği acil yol gerçekten çalışıyor: yerelde app/deps yokken `--rollout 0` katmanı taşır, çıkış 0."""
    (tmp_path / "manifest.json").write_text(json.dumps(ONCEKI), encoding="utf-8")
    r = _make_manifest(tmp_path, "--rollout", "0")
    assert r.returncode == 0, r.stderr[-1200:]
    m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert (
        m["layers"]["win-x64"]["app"] == ONCEKI["layers"]["win-x64"]["app"] and m["layers"]["win-x64"]["rollout"] == 0
    )
