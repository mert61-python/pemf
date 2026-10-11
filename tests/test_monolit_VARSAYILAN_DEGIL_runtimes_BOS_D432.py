# -*- coding: utf-8 -*-
"""D4.32 (B-9.5 · B-11.4) — tek-parça monolit (`base.zip`) VARSAYILAN değil; manifest `runtimes` BOŞ; belgeler katmanlı modelde.

1.9.48'de (2026-09-11, sahip kararı) monolit KALICI olarak yayından çıktı: canlı manifestte `runtimes` boş, v1 `base` yok
(ölçüldü: depodaki `pemf-app-packages/manifest.json`). Hat ise tersini öğretiyordu:
  · `build_tools/make_base_zip.py` bayraksız koşuda 1,5 GB `base.zip` ÜRETİYORDU (yalnız `--no-monolith` kapatıyordu);
  · `scripts/make_manifest.py` klasörde `base.zip` görünce `runtimes.win-x64` + v1 `base`'i YAYINLANMAMIŞ bir URL'ye bağlıyor,
    önceki manifestte win-x64 tek-parçası varsa "bayat" diye yayını DURDURUYORDU;
  · README / BUILD / build_tools README / pemf-app-packages README / bootstrap.ps1 `base.zip`i güncel dağıtım birimi diye anlatıyordu
    (BUILD.md'yi harfiyen izleyen operatör 1,5 GB üretir; pemf-app-packages README "ESKİ launcher'lar için DURUR, silme" diyordu).

Kapı üç kollu: (1) bayraksız paketleme `base.zip` bırakmaz; (2) GERÇEK make_manifest canlı manifest kopyasıyla `runtimes == {}`
ve `base` yok — klasörde `base.zip` dursa bile; (3) (2)'nin ürettiği manifestte `runtimes == {}` iken belgelerde `base.zip`i
"yayınlanmaz / tarihsel / `--monolith`" işareti OLMADAN anan satır yok. Betikler GERÇEKTEN alt süreçte koşar (çıktı tmp'de).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
MAKE_BASE_ZIP = KOK / "build_tools" / "make_base_zip.py"
MAKE_MANIFEST = KOK / "scripts" / "make_manifest.py"
CANLI_MANIFEST = KOK / "pemf-app-packages" / "manifest.json"

#: Monoliti GÜNCEL ürün gibi anlatabilecek belgeler (plan D4.32 dosya listesi).
BELGELER = ("README.md", "BUILD.md", "build_tools/README.md", "pemf-app-packages/README.md", "scripts/bootstrap.ps1")
#: `base.zip` belirteci — `base-app.zip` / `base-deps.zip` / `base-mac.zip` / `base-linux.zip` DEĞİL.
_BELIRTEC = re.compile(r"(?<![-\w.])base\.zip")
#: Bu işaretlerden biri satırda yoksa `base.zip` güncel dağıtım birimi gibi okunur.
_ISARET = re.compile(r"YAYINLANMA|yayınlanma|yayinlanma|--monolith|1\.9\.48|TARİHSEL|tarihsel|TARIHSEL|[Ee]skiden")


def _sahte_dist(kok: Path) -> Path:
    d = kok / "dist" / "PEMF_Backend"
    for alt in ("ai_hub", "frontend/dist", "bin/mosquitto", "torch", "ai_models/ai_hub/inference_cat_organ/models"):
        (d / "_internal" / alt).mkdir(parents=True, exist_ok=True)
    (d / "PEMF_Backend.exe").write_bytes(b"EXE")
    (d / "_internal" / "ai_hub" / "model.pyd").write_bytes(b"PYD")
    (d / "_internal" / "frontend" / "dist" / "index.html").write_text("<html>", encoding="utf-8")
    (d / "_internal" / "bin" / "mosquitto" / "mosquitto.exe").write_bytes(b"MOSQ")
    (d / "_internal" / "torch" / "lib.dll").write_bytes(b"TORCH" * 100)
    (d / "_internal" / "ai_models" / "ai_hub" / "inference_cat_organ" / "models" / "r.onnx").write_bytes(b"ORGAN")
    return d


def _kos(argv: list[str], **env_ek: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", **env_ek}
    return subprocess.run(
        [sys.executable, *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=300,
    )


def _paketle(tmp: Path, cikti: Path, *ek: str) -> subprocess.CompletedProcess:
    return _kos([str(MAKE_BASE_ZIP), str(_sahte_dist(tmp)), *ek], PEMF_PKG_OUT=str(cikti))


def _manifest_uret(cikti: Path) -> tuple[subprocess.CompletedProcess, dict]:
    r = _kos(
        [
            str(MAKE_MANIFEST),
            "--dir",
            str(cikti),
            "--version",
            "1.9.52",
            "--tag",
            "client-app-v1.9.52",
            "--repo",
            "mert61-python/pemf-update",
        ]
    )
    return r, json.loads((cikti / "manifest.json").read_text(encoding="utf-8"))


@pytest.fixture
def kum(tmp_path):
    cikti = tmp_path / "paket_cikti"
    cikti.mkdir()
    return tmp_path, cikti


# ── (1) paketleme ────────────────────────────────────────────────────────────────────────────


def test_KRITIK_bayraksiz_paketleme_base_zip_URETMEZ(kum):
    tmp, cikti = kum
    r = _paketle(tmp, cikti)
    assert r.returncode == 0 and "VALIDATION: PASS" in r.stdout, r.stdout[-1500:] + r.stderr[-800:]
    assert (cikti / "base-app.zip").exists() and (cikti / "base-deps.zip").exists()
    assert not (cikti / "base.zip").exists(), (
        "bayraksiz kosu 1,5 GB'lik tek-parca base.zip URETTI (1.9.48'den beri yayinlanmaz)"
    )
    assert "BASEZIP_SHA=" not in r.stdout, "ekranda yayinlanmayacak bir paketin sha'si basildi"


def test_KRITIK_bayraksiz_paketleme_BAYAT_base_zipi_SILER(kum):
    """Diskte kalmış tek-parça (`gh release upload *.zip` jokeri onu da yükler) bayraksız koşuda PASS'ten sonra silinir."""
    tmp, cikti = kum
    (cikti / "base.zip").write_bytes(b"PK eski build monolit")
    r = _paketle(tmp, cikti)
    assert r.returncode == 0, r.stdout[-1500:]
    assert not (cikti / "base.zip").exists(), "bayat base.zip diskte birakildi"


def test_KARSIT_monolith_bayragi_ile_URETILIR_ve_katmanlarla_AYNI(kum):
    tmp, cikti = kum
    r = _paketle(tmp, cikti, "--monolith")
    assert r.returncode == 0 and "[OK] base.zip == app+deps" in r.stdout, r.stdout[-1500:]
    assert (cikti / "base.zip").exists(), "--monolith verildigi halde base.zip uretilmedi"
    with zipfile.ZipFile(cikti / "base.zip") as z:
        assert "PEMF_Backend/PEMF_Backend.exe" in z.namelist()


# ── (2) manifest ─────────────────────────────────────────────────────────────────────────────


def test_KRITIK_canli_manifest_kopyasiyla_runtimes_BOS_base_YOK(kum):
    tmp, cikti = kum
    assert _paketle(tmp, cikti).returncode == 0
    shutil.copyfile(CANLI_MANIFEST, cikti / "manifest.json")
    r, m = _manifest_uret(cikti)
    assert r.returncode == 0, r.stderr[-1500:]
    assert m["runtimes"] == {} and "base" not in m, f"runtimes={m['runtimes']} base={'base' in m}"
    assert m["layers"]["win-x64"]["app"]["url"].endswith("client-app-v1.9.52/base-app.zip")


def test_KRITIK_klasorde_base_zip_DURSA_DA_runtimes_BOS(kum):
    """`--monolith` ile üretilmiş (ya da bayat) bir `base.zip` klasörde dursa bile YAYINLANMAMIŞ bir URL ilan edilmez."""
    tmp, cikti = kum
    assert _paketle(tmp, cikti, "--monolith").returncode == 0
    shutil.copyfile(CANLI_MANIFEST, cikti / "manifest.json")
    r, m = _manifest_uret(cikti)
    assert r.returncode == 0, r.stderr[-1500:]
    assert m["runtimes"] == {} and "base" not in m, "klasordeki base.zip runtimes.win-x64 / v1 base olarak ilan edildi"
    assert "base.zip" in (r.stdout + r.stderr) and "YAYINLANMAZ" in (r.stdout + r.stderr), (
        "klasordeki tek-parca dosya hakkinda yayinci UYARILMADI (joker yuklemede gidebilir)"
    )


def test_KRITIK_onceki_manifestteki_win_tek_parcasi_TASINMAZ(kum):
    """Önceki manifest win-x64 tek-parçası taşıyorsa (≤1.9.47 dönemi) taze katmanlarla birlikte TAŞINMAZ ve yayını DURDURMAZ:
    yayınlanmayan bir paket için 'bayat' hatası operatörü kaldırılmış monoliti geri üretmeye yönlendirirdi."""
    tmp, cikti = kum
    assert _paketle(tmp, cikti).returncode == 0
    onceki = json.loads(CANLI_MANIFEST.read_text(encoding="utf-8"))
    eski = {"url": "https://x/client-app-v1.9.47/base.zip", "sha256": "e" * 64, "size": 5, "kind": "zip"}
    onceki["runtimes"] = {"win-x64": eski}
    onceki["base"] = eski
    (cikti / "manifest.json").write_text(json.dumps(onceki), encoding="utf-8")
    r, m = _manifest_uret(cikti)
    assert r.returncode == 0, f"tek-parca artik yayinlanmazken yayin DURDU:\n{r.stderr[-1500:]}"
    assert m["runtimes"] == {} and "base" not in m, "onceki manifestin win-x64 tek-parcasi TASINDI"
    assert "runtimes.win-x64" in r.stderr, "dusurme yayinciya SOYLENMEDI (sessiz olmamali)"


# ── (3) belgeler ─────────────────────────────────────────────────────────────────────────────


def _guncel_gibi_anan_satirlar(metin: str) -> list[str]:
    return [s.strip() for s in metin.splitlines() if _BELIRTEC.search(s) and not _ISARET.search(s)]


def test_olcucu_KENDI_karsit_vakalariyla_KANITLI():
    assert _guncel_gibi_anan_satirlar(r"| base.zip (client runtime) | x | `pemf-app-packages\base.zip` |")
    assert _guncel_gibi_anan_satirlar("Write-Host 'python make_base_zip.py    # base.zip'")
    assert not _guncel_gibi_anan_satirlar("`base-app.zip` + `base-deps.zip` · `base-mac.zip` · `base-linux.zip`")
    assert not _guncel_gibi_anan_satirlar("tek-parça `base.zip` 1.9.48'den beri YAYINLANMAZ")
    assert not _guncel_gibi_anan_satirlar("yalnız `--monolith` ile `base.zip` üretilir")


def test_KRITIK_belgeler_base_zipi_GUNCEL_urun_diye_ANMAZ(kum):
    tmp, cikti = kum
    assert _paketle(tmp, cikti).returncode == 0
    shutil.copyfile(CANLI_MANIFEST, cikti / "manifest.json")
    r, m = _manifest_uret(cikti)
    assert r.returncode == 0, r.stderr[-1500:]
    if m["runtimes"]:
        pytest.fail("manifest runtimes BOS degil — once (2) kollarina bakin; belge kurali runtimes == {} iken gecerli")
    bulgular = []
    taranan = 0
    for ad in BELGELER:
        yol = KOK / ad
        assert yol.is_file(), f"belge yok: {ad} (tasindiysa BELGELER guncellensin)"
        taranan += 1
        for satir in _guncel_gibi_anan_satirlar(yol.read_text(encoding="utf-8-sig")):
            bulgular.append(f"{ad}: {satir[:140]}")
    assert taranan == len(BELGELER)
    assert not bulgular, (
        "manifest runtimes BOS (tek-parca yayinlanmiyor) ama belgeler base.zip'i GUNCEL urun gibi anlatiyor "
        "(satira 'YAYINLANMAZ' / 'tarihsel' / '--monolith' / '1.9.48' isareti koyun ya da katmanli adlari kullanin):\n"
        + "\n".join(bulgular)
    )
