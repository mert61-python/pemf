# -*- coding: utf-8 -*-
"""AII-3.8 — toplu XAI CLI (`scripts/xai_batch_rapor.py`) kartı araştırmacıya DOĞRU kararı ve eğitim-dışı uyarısını yazar.

AI1.X10 kartlara iki metin ekledi: termal "açıklanan karar: Hasta / Sağlıklı" (modülün `hedef`'inden) ve EM "⚠ eğitim aralığı dışı nokta: N".
ÖLÇÜLDÜ (A3): kartın karar eşlemesini TERSİNE çeviren mutant (X10_MC) ve sayaç = 0 mutantı (X10_MB, uyarı hiç çıkmaz) AI-1 kapısı +
`test_xai_batch_rapor.py` (17 test) üzerinde 16 geçti / 1 atlandı, YEŞİL. Bu kapı kartları ürünün kendi `_kos_gorsel` / `_kos_em`'i ile kurar
(XAI ve EM modülü en alt çağrı sınırında sahte; sözleşme alanları dolu). Ağırlıksız.
"""

from __future__ import annotations

import base64
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def cli():
    spec = importlib.util.spec_from_file_location("xai_batch_rapor_aii38", KOK / "scripts" / "xai_batch_rapor.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["xai_batch_rapor_aii38"] = m
    spec.loader.exec_module(m)
    return m


def _jpg_b64() -> str:
    import cv2

    ok, buf = cv2.imencode(".jpg", np.full((8, 8, 3), 90, np.uint8))
    return base64.b64encode(buf.tobytes()).decode()


@pytest.mark.parametrize(
    "hedef,beklenen,karsit",
    [("Sick", "açıklanan karar: Hasta", "Sağlıklı"), ("Healthy", "açıklanan karar: Sağlıklı", "Hasta")],
)
def test_KRITIK_termal_karti_ACIKLANAN_karari_dogru_yazar(cli, monkeypatch, tmp_path, hedef, beklenen, karsit):
    import ai_hub.cat_thermal.inference_cat_thermal as ict

    monkeypatch.setattr(
        ict,
        "xai_termal_isi_haritasi",
        lambda *a, **k: {"xai_image_base64": _jpg_b64(), "method": "hirescam", "hedef": hedef},
    )
    girdi = tmp_path / "girdi"
    girdi.mkdir()
    (girdi / "kedi.jpg").write_bytes(base64.b64decode(_jpg_b64()))
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    _, kartlar = cli._kos_gorsel("termal", girdi, cikti, SimpleNamespace(limit=None, xai_method=None))
    assert len(kartlar) == 1
    notu = kartlar[0]["not"]
    assert beklenen in notu and f"açıklanan karar: {karsit}" not in notu, f"kart yanlış kararı yazıyor: {notu!r}"


def test_KRITIK_EM_karti_EGITIM_DISI_nokta_sayisini_yazar(cli, monkeypatch, tmp_path):
    import importlib

    def _run_xai_em(pred, X, out_dir, sample_ids=None, run_shap=True):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "sensitivity_ornek.csv").write_text("a\n", encoding="utf-8")
        return {"alan_disi": [["z=150 (egitim -287..142)"], [], ["x=310 (egitim -298..298)"]]}

    sahte = SimpleNamespace(_run_xai_em=_run_xai_em, Sahte=lambda: object())
    gercek_import = importlib.import_module
    monkeypatch.setattr(cli, "_EM_MODULLER", {"em_kedi": ("sahte_em_modulu", "Sahte")})
    monkeypatch.setattr(
        importlib, "import_module", lambda ad, *a, **k: sahte if ad == "sahte_em_modulu" else gercek_import(ad, *a, **k)
    )
    csv = tmp_path / "points.csv"
    csv.write_text(
        "x,y,z,organ_id,achieved_B,duty_sum\n0,0,150,0,0.001,2\n0,0,0,0,0.001,2\n310,0,0,0,0.001,2\n", encoding="utf-8"
    )
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    satirlar, kartlar = cli._kos_em("em_kedi", csv, cikti, SimpleNamespace(limit=None, no_shap=True))
    assert satirlar[0]["egitim_disi_nokta"] == 2, f"özet sayaç yanlış: {satirlar[0]}"
    assert "⚠ eğitim aralığı dışı nokta: 2" in kartlar[0]["not"], (
        f"kart eğitim-dışı uyarısını yazmıyor: {kartlar[0]['not']!r}"
    )
