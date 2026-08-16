# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Denetim 2026-08-15: `base-deps.zip` AYNI girdiden AYNI bayta inmeli (belirlenimcilik).

NEDEN ÖNEMLİ — KATMANLI PAKETİN AMACI BUYDU. Paket ikiye bölünmüştü:
    base-app.zip   ~71 MB    → her sürümde değişir (bizim kod)
    base-deps.zip  ~1,4 GB   → yalnız requirements değişince
Böylece sıradan bir sürüm klinik başına 1,4 GB yerine ~71 MB indirecekti.

ARIZA: deps sha'sı requirements HİÇ DEĞİŞMEDEN de her yayında değişiyordu → `layers.deps`
yenileniyor → HER KLİNİK HER SÜRÜMDE ~1,4 GB indiriyordu. Bölmenin kazancı sıfırlanmıştı.

ÖLÇÜM (aynı kaynaktan iki PyInstaller koşusu, 6303 ortak dosya): FARKLI olan yalnızca 2 dosya
  • `PEMF_Backend.exe`            → kod koruması farkı, APP katmanı (beklenen)
  • `_internal/base_library.zip`  → AYNI BOYUT (759.753 B), farklı içerik → DEPS katmanı
Sebep zaman damgası DEĞİL (PyInstaller onları 1980'e sabitliyor): **girdi sırası**. İki koşuda
ilk girdi sırasıyla `abc.pyc` ve `functools.pyc` çıktı — dosya sistemi sıralaması.

Fark İŞLEVSEL DEĞİL (zipimport girdi sırasına bakmaz) → iç zip'i sıralı + sabit-tarihli
yeniden yazmak içeriği bozmadan sha'yı sabitler. Ölçüldü: normalize sonrası iki koşu da
`59f502641f936cd2`, 151 girdinin (ad, CRC) kümesi birebir korunuyor.

Bu dosya betiği GERÇEKTEN çalıştırır — iddia etmek yerine kanıtlar.
"""

import io
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

GUII = Path(__file__).resolve().parent.parent
BETIK = GUII / "build_tools" / "make_base_zip.py"

# `base_library.zip` içeriği — iki koşuda AYNI, yalnız SIRA farklı olacak.
_IC_GIRDILER = {
    "abc.pyc": b"ABC-MODULU",
    "functools.pyc": b"FUNCTOOLS-MODULU",
    "os.pyc": b"OS-MODULU",
    "types.pyc": b"TYPES-MODULU",
}


def _ic_zip_yaz(yol: Path, sira, tarih=(1980, 1, 1, 0, 0, 0)):
    """`base_library.zip` taklidi — girdileri VERİLEN sıra ve tarihle yazar.

    ⚠️ `tarih` parametresi mutasyon turunda eklendi. Önce iki koşu da AYNI tarihi kullanıyordu;
    bu yüzden normalizasyondaki `date_time=SABIT_TARIH` silinse bile test YEŞİL kalıyordu —
    yani sabit-tarih koruması hiç sınanmıyordu. PyInstaller bugün tarihleri 1980'e sabitliyor
    ama bu bir GARANTİ DEĞİL (sürüm değişebilir); iki koşuya FARKLI tarih vererek korumayı
    gerçekten sınıyoruz.
    """
    with zipfile.ZipFile(yol, "w", zipfile.ZIP_DEFLATED) as z:
        for ad in sira:
            zi = zipfile.ZipInfo(ad, date_time=tarih)
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, _IC_GIRDILER[ad])


def _sahte_dist(kok: Path, ic_sira, ic_tarih=(1980, 1, 1, 0, 0, 0)) -> Path:
    """Betiğin yapı-doğrulama kapılarını geçen en küçük frozen-build taklidi."""
    d = kok / "dist" / "PEMF_Backend"
    for alt in ("ai_hub", "frontend/dist", "bin/mosquitto", "torch", "ai_models"):
        (d / "_internal" / alt).mkdir(parents=True, exist_ok=True)
    (d / "PEMF_Backend.exe").write_bytes(b"EXE-v1")
    (d / "_internal" / "ai_hub" / "model.pyd").write_bytes(b"PYD")
    (d / "_internal" / "ai_hub" / "__init__.py").write_text("")
    (d / "_internal" / "frontend" / "dist" / "index.html").write_text("<html>")
    (d / "_internal" / "bin" / "mosquitto" / "mosquitto.exe").write_bytes(b"MOSQ")
    (d / "_internal" / "torch" / "lib.dll").write_bytes(b"TORCH" * 100)
    organ = d / "_internal" / "ai_models" / "ai_hub" / "inference_cat_organ" / "models"
    organ.mkdir(parents=True, exist_ok=True)
    (organ / "rtmpose_s.onnx").write_bytes(b"ORGAN")
    # ASIL KONU: PyInstaller'ın ürettiği iç zip.
    _ic_zip_yaz(d / "_internal" / "base_library.zip", ic_sira, ic_tarih)
    return d


def _calistir(dist: Path, cikti: Path):
    """⚠️ `PEMF_PKG_OUT` ile çıktı tmp'ye yönlendirilir — GERÇEK yayın ziplerine dokunulmaz."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PEMF_PKG_OUT": str(cikti)}
    r = subprocess.run(
        [sys.executable, str(BETIK), str(dist)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=600,
    )
    assert r.returncode == 0, f"paketleme basarisiz:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}"
    return r.stdout


def _sha(cikti_satirlari: str, anahtar: str) -> str:
    for satir in cikti_satirlari.splitlines():
        if satir.startswith(anahtar + "="):
            return satir.split("=", 1)[1].strip()
    raise AssertionError(f"{anahtar} çıktıda yok")


@pytest.fixture
def iki_kosu(tmp_path):
    """Aynı içerikten, iç zip girdi SIRASI ve TARİHİ farklı iki paketleme koşusu.

    İkisi de gerçek dünyada gözlenen belirlenimsizlik kaynağı: sıra (ölçüldü) ve tarih
    (PyInstaller bugün sabitliyor ama garanti değil). Normalizasyon ikisini de eritmeli.
    """
    sira_a = ["abc.pyc", "functools.pyc", "os.pyc", "types.pyc"]
    sira_b = ["functools.pyc", "types.pyc", "abc.pyc", "os.pyc"]  # dosya sistemi başka sırada verdi
    tarih_a = (1980, 1, 1, 0, 0, 0)
    tarih_b = (2026, 8, 15, 22, 24, 0)  # baska bir build makinesi/surumu
    sonuc = []
    for ad, sira, tarih in (("A", sira_a, tarih_a), ("B", sira_b, tarih_b)):
        kok = tmp_path / ad
        dist = _sahte_dist(kok, sira, tarih)
        cikti = tmp_path / f"out_{ad}"
        stdout = _calistir(dist, cikti)
        sonuc.append((cikti, stdout))
    return sonuc


def test_KRITIK_deps_sha_iki_kosuda_AYNI(iki_kosu):
    """🔴 ASIL REGRESYON: iç zip sırası değişince deps sha'sı değişmemeli.

    Değişirse `layers.deps` her yayında yenilenir ve her klinik ~1,4 GB indirir.
    """
    (_, cikti_a), (_, cikti_b) = iki_kosu
    sha_a, sha_b = _sha(cikti_a, "DEPSZIP_SHA"), _sha(cikti_b, "DEPSZIP_SHA")
    assert sha_a == sha_b, (
        f"deps sha'sı iki koşuda FARKLI ({sha_a[:12]} != {sha_b[:12]}). İç zip "
        "(base_library.zip) belirlenimci yazılmıyor → katmanlı paketin kazancı kayboluyor: "
        "requirements değişmese bile her klinik ~1,4 GB indirir."
    )


def test_ic_zip_ICERIGI_bozulmadan_korunur(iki_kosu):
    """Normalize etmek içeriği DEĞİŞTİRMEMELİ — yoksa çalışma zamanında modül kaybolur."""
    (cikti_a, _), _ = iki_kosu[0], iki_kosu[1]
    with zipfile.ZipFile(cikti_a / "base-deps.zip") as deps:
        ham = deps.read("PEMF_Backend/_internal/base_library.zip")
    with zipfile.ZipFile(io.BytesIO(ham)) as ic:
        okunan = {ad: ic.read(ad) for ad in ic.namelist()}
    assert okunan == _IC_GIRDILER, (
        f"iç zip içeriği bozuldu.\n  beklenen: {sorted(_IC_GIRDILER)}\n  gelen: {sorted(okunan)}"
    )


def test_ic_zip_girdileri_SIRALI_yazilir(iki_kosu):
    """Belirlenimciliğin mekanizması: girdiler ada göre sıralı olmalı."""
    (cikti_a, _), _ = iki_kosu[0], iki_kosu[1]
    with zipfile.ZipFile(cikti_a / "base-deps.zip") as deps:
        ham = deps.read("PEMF_Backend/_internal/base_library.zip")
    with zipfile.ZipFile(io.BytesIO(ham)) as ic:
        adlar = ic.namelist()
    assert adlar == sorted(adlar), f"iç zip girdileri sıralı değil: {adlar}"


def test_KRITIK_ic_zip_OLMAYAN_dosyalar_AYNEN_kopyalanir(iki_kosu):
    """🔴 Normalizasyon YALNIZ iç zip'lere uygulanmalı.

    Sıradan bir ikili (torch/lib.dll) yeniden yazılırsa bozulur; bu test yanlışlıkla
    genişletilmiş bir normalizasyonu yakalar.
    """
    (cikti_a, _), _ = iki_kosu[0], iki_kosu[1]
    with zipfile.ZipFile(cikti_a / "base-deps.zip") as deps:
        assert deps.read("PEMF_Backend/_internal/torch/lib.dll") == b"TORCH" * 100


def test_app_katmani_da_iki_kosuda_AYNI(iki_kosu):
    """App katmanı zaten belirlenimciydi; iç-zip değişikliği onu bozmamalı."""
    (_, cikti_a), (_, cikti_b) = iki_kosu
    assert _sha(cikti_a, "APPZIP_SHA") == _sha(cikti_b, "APPZIP_SHA")


def test_monolith_de_iki_kosuda_AYNI(iki_kosu):
    """`base.zip` app+deps'ten üretilir → o da belirlenimci olmalı (tek sürüm, tek yazılım)."""
    (_, cikti_a), (_, cikti_b) = iki_kosu
    assert _sha(cikti_a, "BASEZIP_SHA") == _sha(cikti_b, "BASEZIP_SHA")


def test_cikti_dizini_yonlendirilebilir(tmp_path):
    """⚠️ `PEMF_PKG_OUT` olmadan testler GERÇEK yayın ziplerini eziyordu.

    Bu tur sırasında gerçekten yakalandı: 1,4 GB'lık `base-deps.zip` GitHub'a yüklenirken
    paketleme testi koşsaydı dosyayı ezecek ve BOZUK asset yayınlanacaktı.
    """
    dist = _sahte_dist(tmp_path / "x", ["abc.pyc", "functools.pyc", "os.pyc", "types.pyc"])
    cikti = tmp_path / "ozel_cikti"
    _calistir(dist, cikti)
    for ad in ("base-app.zip", "base-deps.zip", "base.zip"):
        assert (cikti / ad).is_file(), f"{ad} yönlendirilen dizine yazılmadı"
