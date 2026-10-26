# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D3I-A2.5 (D3.48) — BÜTÜNLÜK ÖZET ÖNBELLEĞİ KÜÇÜK (< 5 MB) DOSYADA YOK: yerinde değişim mtime geri konsa da YAKALANIR.

ÖLÇÜLEN KUSUR: `_dosya_ozeti` SHA-256'yı `(yol, boyut, mtime_ns)` anahtarıyla süreç içinde önbellekliyordu; aynı süreçte dosya YERİNDE aynı
boyutla değiştirilip değişiklik zamanı `os.utime` ile geri konursa ESKİ (geçerli) özet dönüyor, kurcalanmış ölçekleyici "bütün" sayılıyordu.
Windows'ta `st_ctime` oluşturma zamanıdır (3.10) ve dosya kimliği (`st_ino`) yerinde yazımda değişmez → üst veri anahtarı bu sınıfı
yakalayamaz; içerik yeniden özetlenmeli. < 5 MB (donmuş pakette modül yanındaki app katmanı — doz ölçekleyicileri dahil) her denetimde
yeniden özetlenir (ms düzeyi); büyük ağırlıkta önbellek SÜRER (bilinen sınır — yüzlerce MB her yüklemede yeniden okunmaz).
Sahte YOK: gerçek takipli manifest, gerçek `butunluk_sebebi`; kopyalar geçici dizinde. Özetleme sayısı `hashlib` sarmalıyla ölçülür.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture
def md(monkeypatch):
    from utils import model_downloader as _md

    monkeypatch.setattr(_md, "_manifest_onbellegi", {})
    monkeypatch.setattr(_md, "_ozet_onbellegi", {})
    sayac = {"n": 0}

    class _SayanHashlib:
        @staticmethod
        def sha256(*a, **k):
            sayac["n"] += 1
            return hashlib.sha256(*a, **k)

    monkeypatch.setattr(_md, "hashlib", _SayanHashlib)
    _md._sayac = sayac
    yield _md


def _yerinde_degistir(yol: Path) -> None:
    st = os.stat(yol)
    veri = bytearray(yol.read_bytes())
    veri[len(veri) // 2] ^= 0x01  # tek bayt — aynı boyut
    with open(yol, "r+b") as f:
        f.write(veri)
    os.utime(yol, ns=(st.st_atime_ns, st.st_mtime_ns))  # değişiklik zamanı geri
    assert os.stat(yol).st_size == st.st_size and os.stat(yol).st_mtime_ns == st.st_mtime_ns


def test_KRITIK_D3I_A2_5_kucuk_DOZ_olcekleyici_yerinde_degisince_YAKALANIR(md, tmp_path):
    """MUTASYON: küçük dosya da önbelleklenir (= HEAD) → KIRMIZI."""
    goreli = "ai_hub/em_kedi/scaler_X.pkl"
    kopya = tmp_path / goreli
    kopya.parent.mkdir(parents=True)
    shutil.copy2(KOK / goreli, kopya)
    assert md.butunluk_sebebi(kopya, goreli) is None, "ön koşul: sağlam kopya manifestle aynı"
    _yerinde_degistir(kopya)
    assert md.butunluk_sebebi(kopya, goreli) == "ozet", (
        "yerinde değiştirilen (aynı boyut + mtime) ölçekleyici önbellekten GEÇTİ"
    )


def test_KRITIK_D3I_A2_5_esik_ALTI_1MB_ONNX_her_denetimde_ozetlenir(md, tmp_path):
    """kidney_rna ONNX (1,15 MB, manifestte) — eşik altı; MUTASYON: eşik 5 KB'a düşerse KIRMIZI."""
    goreli = "ai_hub/inference_human_kidney_rna/mlp_medium_kirc.onnx"
    kopya = tmp_path / goreli
    kopya.parent.mkdir(parents=True)
    shutil.copy2(KOK / goreli, kopya)
    assert md.butunluk_sebebi(kopya, goreli) is None
    _yerinde_degistir(kopya)
    assert md.butunluk_sebebi(kopya, goreli) == "ozet"


def test_KARSIT_D3I_A2_5_BUYUK_agirlikta_onbellek_SURER(md, tmp_path):
    """≥ 5 MB ağırlık ikinci denetimde YENİDEN ÖZETLENMEZ (yüzlerce MB her yüklemede okunmaz). MUTASYON: hiç önbellek yok → KIRMIZI."""
    buyuk = tmp_path / "buyuk.onnx"
    buyuk.write_bytes(os.urandom(64) * (6 * 1024 * 1024 // 64))
    (tmp_path / "buyuk.onnx.sha256").write_text(hashlib.sha256(buyuk.read_bytes()).hexdigest(), encoding="utf-8")
    assert md.butunluk_sebebi(buyuk) is None
    once = md._sayac["n"]
    assert md.butunluk_sebebi(buyuk) is None
    assert md._sayac["n"] == once, "büyük ağırlık önbelleğe rağmen YENİDEN özetlendi"
