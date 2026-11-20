# -*- coding: utf-8 -*-
"""OYZ4 · TA (i) (sahip 19-11 "TA için kalanları yayından önce yapalım") — LİSANS DAĞITIMI: atıf envanteri + kopyleft tam metinleri
kurulu uygulamanın YANINDA.

Önce: `THIRD_PARTY_LICENSES.md` + `licenses/` (GPL-3.0, LGPL-2.1, LGPL-3.0) YALNIZ depodaydı; uygulama paketi (runtime, `base-app.zip`) ve
başlatıcı kurucusu (NSIS) bunları taşımıyordu. LGPL bileşenleri (pi-heif içindeki libheif / libde265 DLL'leri, soxr, zeroconf) ikili
olarak DAĞITILIYOR → lisans metni ikiliyle birlikte verilmeli. Ölçü ürünün kendi çıktısı: `make_base_zip` sahte dist ile GERÇEKTEN
koşturulur ve üretilen `base-app.zip` okunur; kurucu tarafı Tauri'nin kurulum dizinine kopyaladığı `bundle.resources` haritasıdır
(üretilmiş NSIS betiğindeki dosya satırları yerel derlemede ayrıca ölçülür — YAYIN-HAZIRLIK B7).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
MAKE_BASE_ZIP = KOK / "build_tools" / "make_base_zip.py"
TAURI_CONF = KOK / "launcher" / "app" / "tauri.conf.json"
LISANSLAR = ("THIRD_PARTY_LICENSES.md", "licenses/GPL-3.0.txt", "licenses/LGPL-2.1.txt", "licenses/LGPL-3.0.txt")


def _sahte_dist(tmp: Path) -> Path:
    d = tmp / "dist" / "PEMF_Backend"
    for alt in ("ai_hub", "frontend/dist", "bin/mosquitto", "torch", "ai_models/ai_hub/inference_cat_organ/models"):
        (d / "_internal" / alt).mkdir(parents=True, exist_ok=True)
    (d / "PEMF_Backend.exe").write_bytes(b"EXE")
    (d / "_internal" / "ai_hub" / "model.pyd").write_bytes(b"PYD")
    (d / "_internal" / "frontend" / "dist" / "index.html").write_text("<html>", encoding="utf-8")
    (d / "_internal" / "bin" / "mosquitto" / "mosquitto.exe").write_bytes(b"MOSQ")
    (d / "_internal" / "torch" / "lib.dll").write_bytes(b"TORCH")
    (d / "_internal" / "ai_models" / "ai_hub" / "inference_cat_organ" / "models" / "r.onnx").write_bytes(b"ORGAN")
    return d


def _paketle(betik: Path, dist: Path, cikti: Path) -> subprocess.CompletedProcess:
    cikti.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [sys.executable, str(betik), str(dist)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PEMF_PKG_OUT": str(cikti)},
        timeout=300,
    )


@pytest.fixture(scope="module")
def paket(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ta_lisans")
    r = _paketle(MAKE_BASE_ZIP, _sahte_dist(tmp), tmp / "cikti")
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-800:]
    with zipfile.ZipFile(tmp / "cikti" / "base-app.zip") as za, zipfile.ZipFile(tmp / "cikti" / "base-deps.zip") as zd:
        yield {
            "app": {n: za.read(n) for n in za.namelist() if not n.endswith("/")},
            "deps": set(zd.namelist()),
            "roots": set(json.loads(za.read("PEMF_Backend/_app_roots.json"))["roots"]),
            "cikti": r.stdout,
        }


def test_KRITIK_runtime_paketi_lisans_metinlerini_exe_nin_YANINDA_ve_BIREBIR_tasir(paket):
    for rel in LISANSLAR:
        arc = "PEMF_Backend/" + rel
        assert arc in paket["app"], (
            f"{arc} uygulama paketinde (base-app.zip) YOK — LGPL ikilileri lisans metinsiz dağıtılır"
        )
        assert paket["app"][arc] == (KOK / rel).read_bytes(), f"{arc} depodaki metinle AYNI değil"
    # NOTICE'taki göreli bağlantılar (`licenses/LGPL-3.0.txt`) kurulu dizinde de çözülür: metinler NOTICE'la aynı dizinin altında
    assert b"](licenses/LGPL-3.0.txt)" in paket["app"]["PEMF_Backend/THIRD_PARTY_LICENSES.md"]


def test_KRITIK_lisanslar_APP_katmaninda_ve_kok_sinirinda_DEPS_e_kaymaz(paket):
    # NOTICE her bağımlılık / crate değişikliğinde değişir: DEPS'te olsaydı her değişiklik kliniklere ~1,5 GB indirtirdi; kök sınırında
    # (`_app_roots.json`) olmasa başlatıcının app güncellemesi / geri alması onları kapsamazdı.
    assert not {n for n in paket["deps"] if "licenses" in n.lower() or "third_party" in n.lower()}
    assert {"PEMF_Backend/THIRD_PARTY_LICENSES.md", "PEMF_Backend/licenses"} <= paket["roots"]


def test_KRITIK_paketleme_dogrulamasi_lisans_kapisini_RAPORLAR(paket):
    assert "lisans metinleri APP katmaninda" in paket["cikti"], paket["cikti"][-1500:]


def test_KRITIK_KARSIT_lisans_metni_YOKSA_paketleme_DURUR_ve_cikti_YAZILMAZ(tmp_path):
    """Kaynak depoda bir lisans dosyası eksikse (ör. `licenses/` silindi) paket ÜRETİLMEZ — sessizce metinsiz paket yayınlanmasın."""
    sahte_kok = tmp_path / "kok"
    (sahte_kok / "build_tools").mkdir(parents=True)
    for ad in ("make_base_zip.py", "paket_sir_taramasi.py"):
        shutil.copy2(KOK / "build_tools" / ad, sahte_kok / "build_tools" / ad)
    shutil.copy2(KOK / "THIRD_PARTY_LICENSES.md", sahte_kok / "THIRD_PARTY_LICENSES.md")
    (sahte_kok / "licenses").mkdir()
    for ad in ("GPL-3.0.txt", "LGPL-3.0.txt"):  # LGPL-2.1 (soxr, zeroconf) EKSİK
        shutil.copy2(KOK / "licenses" / ad, sahte_kok / "licenses" / ad)
    cikti = tmp_path / "cikti"
    r = _paketle(sahte_kok / "build_tools" / "make_base_zip.py", _sahte_dist(tmp_path), cikti)
    assert r.returncode != 0, "lisans metni eksikken paketleme GEÇTİ"
    cikis = r.stdout + r.stderr
    # Eylem söyleyen ileti (çöküş izi değil): hangi dosya eksik + nasıl üretilir; zip yazımına hiç başlanmaz (geçici dosya da yok).
    assert "lisans dosyasi yok: licenses/LGPL-2.1.txt" in cikis and "lisans_envanteri_uret.py" in cikis, cikis[-1500:]
    assert "Traceback" not in cikis, cikis[-1500:]
    assert sorted(p.name for p in cikti.iterdir()) == [], (
        f"çıktı dizinine dosya yazıldı: {sorted(p.name for p in cikti.iterdir())}"
    )


def test_KRITIK_baslatici_kurucusu_lisans_metinlerini_kurulum_dizinine_koyar():
    """Tauri `bundle.resources` haritası: kaynak (tauri.conf.json'a göreli) → kurulum dizini (NSIS'te `$INSTDIR`). Kurucu başlatıcı
    ikilisinin (Rust crate'leri) yanında aynı NOTICE + metinleri bırakır; NOTICE'ın göreli bağlantıları orada da çözülür."""
    kaynaklar = json.loads(TAURI_CONF.read_text(encoding="utf-8"))["bundle"].get("resources")
    assert isinstance(kaynaklar, dict), "bundle.resources harita değil (ya da yok) — kurucu lisans metni taşımıyor"
    hedefler = {}
    for kaynak, hedef in kaynaklar.items():
        p = (TAURI_CONF.parent / kaynak).resolve()
        assert p.is_file(), f"kaynak yok: {kaynak}"
        hedefler[hedef] = p
    for rel in LISANSLAR:
        assert rel in hedefler, f"kurucu {rel} dosyasını kurulum dizinine KOYMUYOR"
        assert hedefler[rel] == (KOK / rel).resolve(), f"{rel} depodaki dosyadan değil: {hedefler[rel]}"
