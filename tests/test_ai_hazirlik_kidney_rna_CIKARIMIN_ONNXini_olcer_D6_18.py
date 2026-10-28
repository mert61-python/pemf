# -*- coding: utf-8 -*-
"""D6.18 · B-5.13 — `/api/ai/hazirlik` envanteri `kidney_rna` için çıkarımın GERÇEKTEN açtığı ONNX'i ölçer, `.pt`'yi değil.

ÖLÇÜLEN KUSUR (HEAD ebf1c3fe): `_AI_MODUL_ENVANTERI` `kidney_rna` satırı `ai_hub/inference_human_kidney_rna/mlp_medium_kirc.pt`
diyordu. Canlı çıkarım (`KidneyRnaPredictor`, `/api/ai/kidney_rna`) `.pt`'yi HİÇ açmaz: `best_model_meta.json`'daki `onnx_file`
(`mlp_medium_kirc.onnx`) ile `onnxruntime.InferenceSession` kurar (`.pt` yalnız XAI / Integrated Gradients içindir, araştırma
profili). Sonuç: ONNX eksik bir kurulumda hazırlık `kidney_rna: hazir=true` derken ilk analiz `FileNotFoundError` ile düşer —
"yeşil kapı / ölü uç" sınıfı (denetim #03).

Ölçüm iki yöntemle: (1) GERÇEK `KidneyRnaPredictor` çıkarımının açtığı dosyalar — Python açışları `sys.addaudithook('open')`,
ONNX (C++ içinde açılır, kanca görmez) `onnxruntime.InferenceSession`'a verilen yol; envanter satırı bu kümeden olmalı.
(2) katmanlı düzen benzetimi (TEMP, `sys.frozen` + `_MEIPASS`): `.pt` var, ONNX YOK → hazırlık `kidney_rna` HAZIR DEĞİL.
Gerçek ağırlıklar yalnız OKUNUR (tmp'ye kopya).
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
_MODUL = "ai_hub/inference_human_kidney_rna"
_ONNX = f"{_MODUL}/mlp_medium_kirc.onnx"  # testte pinli (envanterden okunmaz)
_PT = f"{_MODUL}/mlp_medium_kirc.pt"

_KANCA = {"acik": False, "acilan": []}


def _kanca(olay, argumanlar):
    if _KANCA["acik"] and olay == "open" and argumanlar and isinstance(argumanlar[0], (str, bytes, Path)):
        _KANCA["acilan"].append(str(argumanlar[0]))


_KANCA_KURULDU = False


def _envanter_yolu() -> str:
    from servers.ai_router import _AI_MODUL_ENVANTERI

    satir = [m for ad, _i, m in _AI_MODUL_ENVANTERI if ad == "kidney_rna"]
    assert len(satir) == 1, f"envanterde tek 'kidney_rna' satırı bekleniyordu: {satir}"
    return satir[0]


def test_KRITIK_envanter_satiri_CIKARIMIN_ACTIGI_dosya(monkeypatch):
    """GERÇEK çıkarım (ONNX + scaler + meta) → açılan dosya kümesi; envanterin stat'ladığı yol bu kümede."""
    global _KANCA_KURULDU
    capraz.paket_yoksa_atla("onnxruntime")
    capraz.paket_yoksa_atla("joblib")
    capraz.atla_yoksa(_ONNX)
    import numpy as np
    import onnxruntime as ort
    import pandas as pd

    from ai_hub.inference_human_kidney_rna import inference_human_kidney_rna as ihr

    onnx_acilan: list[str] = []
    gercek = ort.InferenceSession

    def _izleyen(yol, *a, **k):
        onnx_acilan.append(str(yol))
        return gercek(yol, *a, **k)

    monkeypatch.setattr(ort, "InferenceSession", _izleyen)
    if not _KANCA_KURULDU:
        sys.addaudithook(_kanca)  # kaldırılamaz → yalnız `_KANCA["acik"]` iken kaydeder
        _KANCA_KURULDU = True
    _KANCA["acilan"] = []
    _KANCA["acik"] = True
    try:
        p = ihr.KidneyRnaPredictor()
        df = pd.DataFrame(np.zeros((1, p.expected_cols), dtype=np.float32), index=["H1"])
        sonuc = p.predict(df)
    finally:
        _KANCA["acik"] = False
    assert sonuc and "prediction" in sonuc[0], f"çıkarım sonuç üretmedi: {sonuc!r}"
    _kod = {".py", ".pyc", ".pyd", ".dll", ".so"}  # içe aktarma gürültüsü — veri / ağırlık dosyaları kalır
    acilan = {Path(x).name for x in _KANCA["acilan"] + onnx_acilan if Path(x).suffix.lower() not in _kod}
    assert "mlp_medium_kirc.onnx" in acilan, f"ön koşul: çıkarım ONNX'i açmadı? açılan={sorted(acilan)}"
    assert "mlp_medium_kirc.pt" not in acilan, f"ön koşul: çıkarım .pt'yi de açtı? açılan={sorted(acilan)}"
    env = _envanter_yolu()
    assert env.startswith(_MODUL + "/"), f"envanter yolu modül dizininde değil: {env}"
    assert Path(env).name in acilan, (
        f"/api/ai/hazirlik kidney_rna için {env!r} dosyasını ölçüyor; çıkarım bunu AÇMIYOR (açılan: {sorted(acilan)}) — "
        "ölçülen dosya eksikken hazırlık yalan söylemez ama çıkarımın dosyası eksikken YEŞİL kalır"
    )
    assert env == _ONNX, f"envanter satırı {env!r}; çıkarımın ağırlığı {_ONNX!r}"


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


def _kopyala(kaynak_rel: str, hedef: Path) -> None:
    capraz.atla_yoksa(kaynak_rel)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(KOK / kaynak_rel, hedef)


def _kidney_rna_satiri() -> dict:
    import servers.ai_router as air

    yanit = asyncio.run(air.ai_hazirlik(derin=0))
    satir = [m for m in yanit["moduller"] if m["modul"] == "kidney_rna"]
    assert len(satir) == 1, f"hazırlık yanıtında kidney_rna satırı: {satir}"
    return satir[0]


def test_KRITIK_ONNX_YOKKEN_pt_varken_hazirlik_kidney_rna_HAZIR_DEGIL(duzen):
    meipass, _ = duzen
    _kopyala(_PT, meipass / _PT)  # .pt modülün yanında VAR, ONNX HİÇBİR yerde YOK
    s = _kidney_rna_satiri()
    assert s["hazir"] is False and s["model"] == "model_yok", (
        f"çıkarımın ONNX'i yokken hazırlık kidney_rna={s} diyor (yalnız .pt var — çıkarım FileNotFoundError ile düşer)"
    )


def test_KARSIT_ONNX_varken_hazirlik_kidney_rna_MODEL_OK(duzen):
    meipass, _ = duzen
    _kopyala(_ONNX, meipass / _ONNX)
    s = _kidney_rna_satiri()
    assert s["model"] == "ok", f"çıkarımın ONNX'i modülün yanında varken hazırlık kidney_rna={s}"
