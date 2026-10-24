# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""T3 · Y191 (sahip, 2026-10-24) — petri YOLO tespit güveni (`yolo_conf`) varsayılanı 0,25 → 0,6.

İSTEK (sahip): "bir de güven skoru var yoloda, onu 0.6 falan set eder misin petride".
ÖLÇÜLEN (önce, HEAD 4c743afc): varsayılan TEK yerde — `PetriCvPipeline.__init__(yolo_conf=0.25)`; uç (`em_petri`), AI Pro petri
sağlayıcısı ve GPU servisi alanı göndermeyince bu varsayılanda kalır; `petri_ayar.varsayilanlar()` (arayüzün gösterdiği "varsayılan")
ayrıca 0,25 YAZIYOR (kopya) ve arayüz "etkin ayarlar" satırı 0,25'i sabit karşılaştırıyor. Kayıtlı karelerde etkisi
`DENETIM\\YAYIN-T3.md` Y191 bölümünde (koşulsuz ham YOLO kipinde düşük güvenli sahte kuyular elenir).
KAPI: boru hattı varsayılanı 0,6; arayüz varsayılanı boru hattınınkini İZLER (kopya değil); alan gönderilmeyen istek 0,6 ile koşar,
açıkça gönderilen değer (ör. 0,25) yine geçer (karşıt); sınırlar değişmedi.
"""

from __future__ import annotations

import inspect

import pytest


def _boru_hatti_varsayilani() -> float:
    from ai_hub.inference_petri_dish.petri_cv_v2.pipeline import PetriCvPipeline

    return inspect.signature(PetriCvPipeline.__init__).parameters["yolo_conf"].default


def test_KRITIK_petri_YOLO_guven_varsayilani_0_6():
    assert _boru_hatti_varsayilani() == pytest.approx(0.6), "sahip kararı Y191: petri yolo_conf varsayılanı 0,6"


def test_KRITIK_arayuz_varsayilani_BORU_HATTINI_izler_kopya_degil(monkeypatch):
    from ai_hub.inference_petri_dish import petri_ayar as pa
    from ai_hub.inference_petri_dish.petri_cv_v2 import pipeline as pp

    assert pa.varsayilanlar()["yolo_conf"] == pytest.approx(_boru_hatti_varsayilani())
    # TAKİP sınaması: boru hattının varsayılanı değişirse arayüzün gösterdiği de değişmeli (sabit kopya bunu yakalar)
    gercek = pp.PetriCvPipeline.__init__

    def _sahte(self, cfg=None, *, yolo_conf: float = 0.42, kuyu_skor_esigi: float = 0.6, **k):  # noqa: ARG001
        return None

    monkeypatch.setattr(pp.PetriCvPipeline, "__init__", _sahte)
    assert pa.varsayilanlar()["yolo_conf"] == pytest.approx(0.42), "varsayılan KOPYALANMIŞ (boru hattını izlemiyor)"
    monkeypatch.setattr(pp.PetriCvPipeline, "__init__", gercek)


def test_KARSIT_acik_gonderilen_guven_YINE_gecer_sinirlar_ayni():
    from ai_hub.inference_petri_dish import petri_ayar as pa

    assert pa.coz() == {}, "alan gönderilmeyen istek varsayılanı EZMEMELİ (boru hattı 0,6'da kalır)"
    assert pa.coz(yolo_conf="0.25") == {"yolo_conf": pytest.approx(0.25)}
    assert pa.SINIRLAR["yolo_conf"] == (0.01, 0.95)


def test_KRITIK_AI_Pro_petri_saglayicisi_guveni_GONDERMEZ_varsayilanda_kalir():
    """AI Pro petri sağlayıcısı boru hattını `yolo_conf` vermeden kurar → sahip kararı (0,6) AI Pro'da da geçerli (ayrı kopya yok)."""
    import ast
    from pathlib import Path

    kaynak = (Path(__file__).resolve().parents[1] / "apps" / "backend" / "servers" / "ai_pro_hedef.py").read_text(
        encoding="utf-8"
    )
    cagrilar = [
        n
        for n in ast.walk(ast.parse(kaynak))
        if isinstance(n, ast.Call) and "yolo_model_path" in {k.arg for k in n.keywords}
    ]
    assert cagrilar, "aparat: AI Pro petri boru hattı kurulumu bulunamadı"
    for n in cagrilar:
        assert "yolo_conf" not in {k.arg for k in n.keywords}, (
            "AI Pro petri kendi güven eşiğini veriyor (sahip kararını ezer)"
        )
