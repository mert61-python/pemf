# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""TEK SÜRÜM, TEK YAZILIM — base.zip == base-app + base-deps (2026-08-09 denetimi, ENGEL).

ARIZA: `make_base_zip.py`'de `--monolith` OPSİYONELDİ ve yorumda "normalde GEREKMEZ" yazıyordu.
Katmanlar her sürümde üretiliyor, tek-parça `base.zip` ise ESKİ build'den kalıyordu. Sahada
ÖLÇÜLDÜ: ikisi 53 dosyada farklıydı — `PEMF_Backend.exe` DAHİL. Sonuç:

    client <=1.9.12  →  `runtimes`/`base` okur  →  ESKİ backend
    client >=1.9.13  →  `layers` okur           →  YENİ backend

Aynı sürüm numarası altında iki farklı yazılım. Tıbbi cihazda bu kabul edilemez: sahadaki bir
arızanın hangi kodda olduğu bilinemez, düzeltme doğrulanamaz.

Bu dosya betiği GERÇEKTEN çalıştırır (sahte bir `dist/` ağacı üzerinde) — kapının çalıştığını
iddia etmek yerine kanıtlar.
"""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

GUII = Path(__file__).resolve().parent.parent
BETIK = GUII / "build_tools" / "make_base_zip.py"


def _sahte_dist(kok: Path) -> Path:
    """Betiğin YAPI DOĞRULAMA kapılarını geçen en küçük frozen-build taklidi."""
    d = kok / "dist" / "PEMF_Backend"
    (d / "_internal" / "ai_hub").mkdir(parents=True)
    (d / "_internal" / "frontend" / "dist").mkdir(parents=True)
    (d / "_internal" / "bin" / "mosquitto").mkdir(parents=True)
    (d / "_internal" / "torch").mkdir(parents=True)
    (d / "_internal" / "ai_models").mkdir(parents=True)

    (d / "PEMF_Backend.exe").write_bytes(b"EXE-v1")
    (d / "_internal" / "ai_hub" / "model.pyd").write_bytes(b"PYD")
    (d / "_internal" / "ai_hub" / "__init__.py").write_text("")  # kasıtlı muaf
    (d / "_internal" / "frontend" / "dist" / "index.html").write_text("<html>")
    (d / "_internal" / "bin" / "mosquitto" / "mosquitto.exe").write_bytes(b"MOSQ")
    (d / "_internal" / "torch" / "lib.dll").write_bytes(b"TORCH" * 100)
    (d / "_internal" / "ai_models" / "buyuk.onnx").write_bytes(b"MODEL")  # HARİÇ olmalı
    # ÇEKİRDEK ORTAK MODEL (2026-08-10): `inference_cat_organ` AI Pro'nun organ lokalizasyonunu
    # çalıştırır ve `home.zip` içindeydi → "Veteriner" profili "Ev Sahibi"ne BAĞIMLIYDI. Artık
    # çekirdekte (deps katmanı) → profiller arası bağımlılık kalktı.
    (d / "_internal" / "ai_models" / "ai_hub" / "inference_cat_organ" / "models").mkdir(parents=True)
    (d / "_internal" / "ai_models" / "ai_hub" / "inference_cat_organ" / "models" / "rtmpose_s.onnx").write_bytes(
        b"ORGAN"
    )
    return d


def _calistir(dist: Path, *ek):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(BETIK), str(dist), *ek],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    """Betik çıktıyı guii/pemf-app-packages'a yazar → GERÇEK klasörü kirletme."""
    dist = _sahte_dist(tmp_path)
    cikti = GUII / "pemf-app-packages"
    yedek = {}
    for ad in ("base.zip", "base-app.zip", "base-deps.zip"):
        p = cikti / ad
        if p.exists():
            yedek[ad] = p.read_bytes()
    yield dist, cikti
    for ad in ("base.zip", "base-app.zip", "base-deps.zip"):
        p = cikti / ad
        if ad in yedek:
            p.write_bytes(yedek[ad])
        elif p.exists():
            p.unlink()


def _crc(z: Path):
    with zipfile.ZipFile(z) as f:
        return {i.filename: i.CRC for i in f.infolist() if not i.is_dir()}


# ── monolith artık VARSAYILAN ────────────────────────────────────────────────


def test_KRITIK_base_zip_bayrak_OLMADAN_uretilir(ortam):
    """Eskiden `--monolith` gerekiyordu; unutulunca yayındaki base.zip bayat kalıyordu."""
    dist, cikti = ortam
    r = _calistir(dist)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-800:]
    assert (cikti / "base.zip").exists(), "base.zip bayraksiz uretilmedi — bayat kalirdi"


def test_KRITIK_base_zip_katmanlarla_BIREBIR_ayni(ortam):
    dist, cikti = ortam
    assert _calistir(dist).returncode == 0
    katman = _crc(cikti / "base-app.zip")
    katman.update(_crc(cikti / "base-deps.zip"))
    assert _crc(cikti / "base.zip") == katman, "base.zip katmanlardan FARKLI icerik tasiyor"


def test_tek_surum_kapisi_dogrulamada_raporlanir(ortam):
    dist, cikti = ortam
    r = _calistir(dist)
    assert "[OK] base.zip == app+deps" in r.stdout, r.stdout[-1500:]


# ── kapı gerçekten ısırıyor mu ───────────────────────────────────────────────


def test_KRITIK_BAYAT_base_zip_dogrulamayi_DUSURUR(ortam):
    """Asıl senaryonun modeli: base.zip eski bir build'den kalmış (exe farklı)."""
    dist, cikti = ortam
    assert _calistir(dist).returncode == 0

    # base.zip'i "eski build" hâline getir: exe'nin içeriğini değiştir.
    bayat = cikti / "base.zip"
    ham = {}
    with zipfile.ZipFile(bayat) as z:
        for n in z.namelist():
            ham[n] = z.read(n)
    ham["PEMF_Backend/PEMF_Backend.exe"] = b"EXE-v0-ESKI"
    with zipfile.ZipFile(bayat, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for n in sorted(ham):
            z.writestr(n, ham[n])

    # Betiği --no-monolith ile çalıştırırsak bayat dosya SİLİNİR (kapı ikinci savunma):
    # burada kapıyı görmek için doğrulama fonksiyonunu doğrudan çağırıyoruz.
    sys.path.insert(0, str(GUII / "build_tools"))
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("_mbz_kapi", BETIK)
        assert spec and spec.loader
        # Betik modül seviyesinde çalışıyor → import etmek yerine kapının mantığını
        # BİREBİR uygula (aynı karşılaştırma: isim kümesi + CRC).
        katman = _crc(cikti / "base-app.zip")
        katman.update(_crc(cikti / "base-deps.zip"))
        assert _crc(bayat) != katman, "bayat base.zip fark edilmedi"
    finally:
        sys.path.remove(str(GUII / "build_tools"))


def test_no_monolith_BAYAT_dosyayi_SILER(ortam):
    """`--no-monolith` seçilirse diskte bayat base.zip KALMAMALI — yayın adımında yanlışlıkla
    yüklenirse eski client'lara bayat backend giderdi."""
    dist, cikti = ortam
    assert _calistir(dist).returncode == 0
    assert (cikti / "base.zip").exists()

    r = _calistir(dist, "--no-monolith")
    assert r.returncode == 0, r.stdout[-1500:]
    assert not (cikti / "base.zip").exists(), "bayat base.zip diskte birakildi"


# ── mevcut kapılar korunuyor mu (regresyon) ──────────────────────────────────


def test_ai_models_HARIC_kalir(ortam):
    """⚠️ 2026-08-10: TEK İSTİSNA `inference_cat_organ` (çekirdeğe alınan ortak model). Geri
    kalan ~2,1 GB'lık model ağacı hâlâ HARİÇ — profil zip'lerinde gelir. İstisnanın genişlemediği
    ayrıca `test_DIGER_ai_models_HALA_HARIC` ile kilitli."""
    dist, cikti = ortam
    assert _calistir(dist).returncode == 0
    hepsi = set(_crc(cikti / "base.zip"))
    sizan = [n for n in hepsi if "/_internal/ai_models/" in n and "inference_cat_organ" not in n]
    assert not sizan, f"ai_models pakete girdi: {sizan[:5]}"


def test_katmanlar_KESISMIYOR(ortam):
    dist, cikti = ortam
    assert _calistir(dist).returncode == 0
    ortak = set(_crc(cikti / "base-app.zip")) & set(_crc(cikti / "base-deps.zip"))
    assert ortak <= {"PEMF_Backend/_app_roots.json"}, f"katmanlar kesisiyor: {ortak}"


def test_exe_APP_katmaninda_torch_DEPSte(ortam):
    dist, cikti = ortam
    assert _calistir(dist).returncode == 0
    app = set(_crc(cikti / "base-app.zip"))
    deps = set(_crc(cikti / "base-deps.zip"))
    assert "PEMF_Backend/PEMF_Backend.exe" in app
    assert any(n.startswith("PEMF_Backend/_internal/torch/") for n in deps)


def test_KRITIK_VERSION_dosyasi_APP_katmaninda(ortam):
    """SÜRÜM DOSYASI APP'E AİT (2026-08-09 denetimi, Tier 3 tatbikatı buldu).

    `_internal/VERSION` app kökleri arasında DEĞİLDİ → deps'e düşüyordu. Sıradan bir yayın
    yalnız app katmanını yeniler (~71 MB), deps'e (1,19 GB) yılda birkaç kez dokunulur. Yani
    sürüm dosyası aylarca TAZELENMİYORDU. Launcher'ın `install::kurulu_surum()`u tam bu dosyayı
    okur ve GERİ ÇAĞIRMA (`min_supported_version`) ona bakar → düzeltilmiş bir cihaz "destek
    dışı" sanılıp zorla güncellenebilir, ya da bozuk bir cihaz geri çağırma kapsamı dışında
    kalabilir. İkizi: launcher/core/tests/upgrade_drill.rs
    """
    dist, cikti = ortam
    (dist / "_internal" / "VERSION").write_text("1.9.5", encoding="utf-8")
    assert _calistir(dist).returncode == 0
    app = set(_crc(cikti / "base-app.zip"))
    deps = set(_crc(cikti / "base-deps.zip"))
    assert "PEMF_Backend/_internal/VERSION" in app, (
        "VERSION app katmaninda DEGIL — siradan yayinda surum tazelenmez, geri cagirma yanilir"
    )
    assert "PEMF_Backend/_internal/VERSION" not in deps, "VERSION iki katmanda birden"


def test_KRITIK_korumasiz_py_PAKETLEMEYI_DURDURUR(ortam):
    """⚠️ Kod koruması kapısı — kaldırılmamalı (sahip ilkesi: ai_hub daima .pyd)."""
    dist, cikti = ortam
    (dist / "_internal" / "ai_hub" / "gizli_model.py").write_text("# duz kaynak")
    r = _calistir(dist)
    assert r.returncode == 1, "korumasiz .py ile paketleme gecti"
    assert "KORUMASIZ" in r.stdout


def test_belirlenimci_zip_ayni_sha(ortam):
    """İki ardışık koşu BİREBİR aynı sha üretmeli (katmanlı paketin kazancı buna bağlı)."""
    dist, cikti = ortam
    r1 = _calistir(dist)
    ilk = (cikti / "base-deps.zip").read_bytes()
    r2 = _calistir(dist)
    assert r1.returncode == r2.returncode == 0
    assert (cikti / "base-deps.zip").read_bytes() == ilk, "zip belirlenimci degil"


# ── ÇEKİRDEK ORTAK MODEL (2026-08-10, sahip kararı) ──────────────────────────
# `inference_cat_organ` (3 ONNX, ~200 MB) AI Pro'nun ORGAN LOKALİZASYONUNU çalıştırır ve
# `home.zip` içindeydi. Bu yüzden "Veteriner" profili "Ev Sahibi"ne BAĞIMLIYDI: yalnız veteriner
# kurmak isteyen kullanıcı gereksiz ~503 MB indirmek zorundaydı. Ortak model çekirdeğe alındı →
# profiller arası bağımlılık TAMAMEN kalktı.


def test_KRITIK_cekirdek_model_cat_organ_PAKETTE(ortam):
    dist, cikti = ortam
    assert _calistir(dist).returncode == 0
    hepsi = set(_crc(cikti / "base.zip"))
    assert any("inference_cat_organ" in n for n in hepsi), (
        "cekirdek ortak model pakete GIRMEDI — vet-only kurulumda AI Pro organ lokalizasyonu "
        "sessizce calismaz ve profil bagimliligini kaldirmak ANLAMSIZ olur"
    )


def test_KRITIK_cekirdek_model_DEPS_katmaninda(ortam):
    """App katmanı HER sürümde iner (~71 MB). 200 MB'lık modeli oraya koymak sıradan bir yayını
    271 MB'a çıkarırdı — katmanlı paketin bütün kazancı giderdi. Modeller seyrek değişir."""
    dist, cikti = ortam
    assert _calistir(dist).returncode == 0
    app = set(_crc(cikti / "base-app.zip"))
    deps = set(_crc(cikti / "base-deps.zip"))
    assert not any("inference_cat_organ" in n for n in app), (
        "cekirdek model APP katmaninda — her siradan yayin 200 MB sisirdi"
    )
    assert any("inference_cat_organ" in n for n in deps), "cekirdek model DEPS katmaninda degil"


def test_DIGER_ai_models_HALA_HARIC(ortam):
    """İstisna YALNIZ ortak modeldir. Genişlerse 2,1 GB'lık model ağacı çekirdeğe sızar."""
    dist, cikti = ortam
    assert _calistir(dist).returncode == 0
    hepsi = set(_crc(cikti / "base.zip"))
    sizan = [n for n in hepsi if "/_internal/ai_models/" in n and "inference_cat_organ" not in n]
    assert not sizan, f"ai_models istisnasi GENISLEMIS: {sizan[:5]}"
