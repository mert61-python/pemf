# -*- coding: utf-8 -*-
"""4B-3.6 (A3 inceleme, D4.E01 `b084c386`) — AI hazırlığı modülün YANINDAKİ ağırlığı BÜTÜNLÜK sağlamasız "ok" sayar (sahte YEŞİL).

D4.E01 hazırlığı `yan_dosya_coz(resource_path(rel), rel)`'e bağladı. `yan_dosya_coz` modül-yanı dosya VARSA onu bütünlük denetimi
OLMADAN döndürür; model köklerinden gelen dosya ise `find_installed_model` → `_model_integrity_ok` (asgari boyut + `.sha256` yan
dosyası) süzgecinden geçer. Ölçüldü (`kayit/k3_sonda.txt`, katmanlı düzen benzetimi): kesik `ExtraTrees.onnx` modülün yanındayken
hazırlık **ok**, GERÇEK çıkarım (`load_model`) `InvalidProtobuf` ile DÜŞER — profil kökünde SAĞLAM kopya olsa bile (çıkarım modül-yanını
önce alır). Aynı kesik dosya kökteyken hazırlık doğru biçimde `model_yok` (asimetri). Operatör/build AI kapısı "hazır" görür.

Ölçüm: D4.E01 kapısının deseni (`sys.frozen` + `sys._MEIPASS` = tmp `_internal`, `PEMF_AI_MODELS_DIR` = tmp); izlenen `release_assets`
ağırlığı yalnız OKUNUR, kesik kopya tmp'de üretilir. Çıkarım kolu GERÇEK `inference_human_kidney_disease.load_model` (modül dizini donmuş
düzendeki gibi `_MEIPASS/ai_hub/<modül>`).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
KD = "ai_hub/inference_human_kidney_disease"
REL = f"{KD}/ExtraTrees.onnx"
KAYNAK = KOK / "release_assets" / "ai_models" / KD


@pytest.fixture
def duzen(tmp_path, monkeypatch):
    meipass = tmp_path / "runtime" / "PEMF_Backend" / "_internal"
    (meipass / "ai_models").mkdir(parents=True)
    profil = tmp_path / "ai_models"
    profil.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setenv("PEMF_AI_MODELS_DIR", str(profil))
    return meipass, profil


def _koy(kok: Path, kesik: bool) -> None:
    d = kok / KD
    d.mkdir(parents=True, exist_ok=True)
    veri = (KAYNAK / "ExtraTrees.onnx").read_bytes()
    (d / "ExtraTrees.onnx").write_bytes(veri[:50_000] if kesik else veri)
    shutil.copy2(KAYNAK / "preprocessor.pkl", d / "preprocessor.pkl")


def _cikarim_yuklenir(monkeypatch, meipass: Path) -> bool:
    import ai_hub.inference_human_kidney_disease.inference_human_kidney_disease as kd

    monkeypatch.setattr(kd, "THIS_DIR", meipass / KD)  # donmuşta modül dizini
    try:
        kd.load_model("ExtraTrees")
        return True
    except Exception:
        return False


@pytest.mark.parametrize("profilde_saglam", [False, True], ids=["kokte_yok", "kokte_SAGLAM_kopya"])
def test_KRITIK_kesik_modul_yani_agirligi_HAZIR_sayilmaz(duzen, monkeypatch, profilde_saglam):
    meipass, profil = duzen
    _koy(meipass, kesik=True)
    if profilde_saglam:
        _koy(profil, kesik=False)
    from servers.ai_router import _model_hazir_mi

    yuklenir = _cikarim_yuklenir(monkeypatch, meipass)
    assert not yuklenir, "benzetim kurulamadı: kesik ONNX ile çıkarım yüklendi (vakum)"
    durum, ayrinti = _model_hazir_mi(REL)
    assert durum != "ok", (
        f"çıkarım kesik modül-yanı ağırlıkla DÜŞERKEN hazırlık '{durum}' diyor (sahte yeşil; kökteki aynı kesik dosya model_yok olurdu)"
    )


def test_KARSIT_saglam_modul_yani_HAZIR_ve_cikarim_yuklenir(duzen, monkeypatch):
    meipass, _ = duzen
    _koy(meipass, kesik=False)
    from servers.ai_router import _model_hazir_mi

    assert _cikarim_yuklenir(monkeypatch, meipass)
    assert _model_hazir_mi(REL)[0] == "ok"


def test_KARSIT_kesik_KOK_kopyasi_zaten_model_yok(duzen):
    _, profil = duzen
    _koy(profil, kesik=True)
    from servers.ai_router import _model_hazir_mi

    assert _model_hazir_mi(REL)[0] == "model_yok"
