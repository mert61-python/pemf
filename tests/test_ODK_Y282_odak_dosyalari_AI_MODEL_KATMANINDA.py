# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODK · Y282 (sahip 12 Kasım 2026 akşam, "b olsun"; Y279 ile tutarlı): ODAK alan tablosu + 5 ONNX modeli (CST'den türetilmiş) AÇIK
DEPOYA GİRMEZ — diğer ağırlıklar gibi AI MODEL KATMANINDA (`release_assets/ai_models/ai_hub/odak/veri/`, git-ignored; kurulu: model dizini).
SÖZLEŞME: depoda izlenmez · eski yerine geri giremez (`.gitignore`) · `.gitignore` ONNX istisnası ve 2 MB kuralı istisnası KALKTI ·
takipli SHA-256 manifestinde (yüklemede fail-closed) · dosya yoksa ODAK SÜRMEZ, engel `modelYok` eylem söyler (TR + EN).
Geçmiş temizliği + CI gizli anahtarlı indirme KP-5'te (DENETIM `47-KAPSAM-KP5.txt`)."""

from __future__ import annotations

import json
import os
import subprocess

import pytest
from test_her_model_agirligi_bir_PAKETE_duser_D427 import (  # noqa: F401 — aparat (spec'in datas listesi)
    _mmz,
    spec_datas,
)

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSYALAR = (
    ("alan_tablosu.npz", "e_tablosu.npz")
    + tuple(f"model_{k}.onnx" for k in ("TUM_PETRI", "KUYUCUK", "FANTOM", "KEDI_TV", "KEDI_ORGAN"))
    # ODK8: frekans modelleri (76 / 107 / 147 Hz)
    + tuple(
        f"model_{k}_{f}Hz.onnx"
        for f in (76, 107, 147)
        for k in ("TUM_PETRI", "KUYUCUK", "FANTOM", "KEDI_TV", "KEDI_ORGAN")
    )
)


def _git(*a):
    r = subprocess.run(["git", "-C", KOK, *a], capture_output=True, text=True, encoding="utf-8")
    if r.returncode not in (0, 1):
        pytest.skip("git yok / depo değil")
    return r


def test_KRITIK_Y282_ODAK_dosyalari_DEPODA_IZLENMEZ_ve_ESKI_YERINE_GIREMEZ():
    # izlenen VE çalışma ağacında duran (commit kapısı silmeyi sahnelemeden önce koşar: silinmiş dosya index'te durur)
    izli = _git("ls-files", "ai_hub/odak", "release_assets/ai_models/ai_hub/odak").stdout.split()
    izli = [f for f in izli if f.endswith((".onnx", ".npz")) and os.path.exists(os.path.join(KOK, f))]
    assert not izli, f"ODAK ağırlığı depoda izleniyor: {izli}"
    for f in DOSYALAR:
        for yol in (f"ai_hub/odak/veri/{f}", f"release_assets/ai_models/ai_hub/odak/veri/{f}"):
            assert _git("check-ignore", "-q", "--no-index", yol).returncode == 0, (
                f"{yol} .gitignore'da değil (açık depoya girebilir)"
            )
    gi = open(os.path.join(KOK, ".gitignore"), encoding="utf-8").read()
    assert "!ai_hub/odak/veri" not in gi, ".gitignore ODAK istisnası kalkmadı"
    pc = open(os.path.join(KOK, ".pre-commit-config.yaml"), encoding="utf-8").read()
    assert "ai_hub/odak" not in pc, "2 MB büyük dosya kuralının ODAK istisnası kalkmadı"


def test_KRITIK_Y282_manifestte_ve_BAYT_BIREBIR_yukleyici_AI_MODEL_KATMANINDAN():
    from utils import model_downloader as md

    from ai_hub.odak.alan import model_katmani_yolu

    man = json.load(open(os.path.join(KOK, "release_assets", "ai_models_sha256.json"), encoding="utf-8"))["dosyalar"]
    for f in DOSYALAR:
        rel = f"ai_hub/odak/veri/{f}"
        assert rel in man, f"{rel} bütünlük manifestinde yok"
        yol = model_katmani_yolu(f)
        assert os.path.getsize(yol) == man[rel]["bayt"] and md._dosya_ozeti(md.Path(yol)) == man[rel]["sha256"], yol
        assert os.sep + os.path.join("ai_hub", "odak", "veri", f) in os.path.abspath(yol)
        assert os.path.join("ai_hub", "odak", "veri") + os.sep + f != os.path.relpath(yol, KOK), (
            "depodaki eski yerden çözüldü"
        )


def test_KRITIK_Y282_dosya_YOKSA_SURMEZ_engel_modelYok_EYLEM_iki_dilde(monkeypatch):
    from servers import ai_pro_hedef
    from utils import ceviri

    from ai_hub.odak import alan, oneri

    def yok(ad):
        raise FileNotFoundError(f"Model bulunamadı: ai_hub/odak/veri/{ad}")

    # alan tablosu yok → `odak_plani` SÜRMEZ (duty 0), kod `modelYok` (istisna yukarı — 500 — sızmaz)
    monkeypatch.setattr(alan, "model_katmani_yolu", yok)
    alan.alan_tablosu.cache_clear()
    oneri._SON.clear()
    monkeypatch.setattr(oneri, "alan_modeli", lambda kok, *_a: alan.AlanModeli(_ornek_kalibrasyon()))

    class _Fantom:
        ad = "fantom"

    plan = ai_pro_hedef.odak_plani(_Fantom(), {"x_mm": 0.0, "y_mm": -150.0, "z_mm": 0.0}, 1, 0.5)
    assert plan["engel"] == "modelYok" and plan["duty"] == [0.0] * 7
    alan.alan_tablosu.cache_clear()
    for dil in ("tr", "en"):
        m = ceviri.t("ai.pro.odak.engel.modelYok", dil=dil)
        assert m and "ai.pro" not in m and ("AI model" in m), (dil, m)


def test_KRITIK_Y282_oneri_ONNX_yoksa_engel_modelYok(monkeypatch):
    """Öneri yolu: alan tablosu VAR, kipin ONNX'i YOK → `oner` engeli `modelYok` (istisna yukarı sızmaz)."""
    import numpy as np

    from ai_hub.odak import alan, model, oneri

    A = alan.AlanModeli(_ornek_kalibrasyon())

    def yok(ad):
        raise FileNotFoundError(ad)

    monkeypatch.setattr(model, "model_katmani_yolu", yok)
    model.model_al.cache_clear()
    plan = oneri.oner(
        "FANTOM", A, 0.5, hedef_P=[20.0, -155.0, 10.0], fantom={"merkez_P": [0.0, -150.0, 0.0], "theta": 0.4}
    )
    model.model_al.cache_clear()
    assert plan["engel"] == "modelYok" and np.allclose(plan["duty"], 0.0)


def _ornek_kalibrasyon() -> dict:
    with open(os.path.join(KOK, "tests", "veri", "odak_kalibrasyon_ornek.json"), encoding="utf-8") as fh:
        return json.load(fh)


def test_KRITIK_Y282_SAHADA_model_PAKETLERINDE_ve_APP_katmanina_GOMULMEZ(spec_datas):
    """Başlatıcı düzeninde `_internal/ai_models` HARİÇ (D4.27) → ODAK dosyaları vet + research MODEL PAKETLERİNDE olmalı (launcher
    `install_root/ai_models`'a açar). Paketsiz kalırsa spec onları APP katmanına (`_internal/ai_hub/odak/veri`) gömer — 14e39763'te ölçüldü."""
    mmz = _mmz()
    for f in DOSYALAR:
        rel = f"ai_hub/odak/veri/{f}"
        assert rel in mmz.PROFILLER["vet"] and rel in mmz.PROFILLER["research"], f"{rel} model paketinde değil"
    app = [d for s, d in spec_datas if os.path.basename(s) in DOSYALAR and d.replace(os.sep, "/").startswith("ai_hub")]
    assert not app, f"ODAK ağırlığı APP katmanına gömülüyor: {app}"


def test_KRITIK_Y282_yukleyici_MODUL_YANI_sonra_MODEL_KOKLERI(monkeypatch, tmp_path):
    """Donmuş pakete modül yanına gömülü kopya varsa o (bütünlük denetimiyle), yoksa model kökleri — ikisi de yoksa FileNotFoundError."""
    import shutil

    from ai_hub.odak import alan

    asil = alan.model_katmani_yolu("model_KEDI_TV.onnx")
    assert os.path.normcase(os.path.dirname(asil)) != os.path.normcase(alan.VERI_DIZINI)
    shutil.copyfile(asil, tmp_path / "model_KEDI_TV.onnx")
    monkeypatch.setattr(alan, "VERI_DIZINI", str(tmp_path))
    assert os.path.samefile(alan.model_katmani_yolu("model_KEDI_TV.onnx"), tmp_path / "model_KEDI_TV.onnx")
    with pytest.raises(FileNotFoundError):
        alan.model_katmani_yolu("model_YOK.onnx")
