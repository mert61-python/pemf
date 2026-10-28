# -*- coding: utf-8 -*-
"""Y211 · S-D67.2 (sahip, 2026-10-28) — Ayarlar anonimleştirme metinleri "Tedavi → Seans" kararına (2026-08-08) uyar: "tedavi görmeyen"
→ "seans yapılmayan" (TR DEĞİŞTİ ×4; `_one` / `_other` cümlesinde dilbilgisi gereği "seans yapılmadığı için"), EN "not treated" → "with no
session". Hukuki sorumluluk metni (kararın tek istisnası) bu anahtarlarda değildir. Dört anahtar TR + EN birlikte tutulur.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
ANAHTARLAR = ("anonimBekleyen_one", "anonimBekleyen_other", "anonimOnayli", "kapaliAnonim")


def _saklama(dil: str) -> dict:
    veri = json.loads((KOK / "apps" / "ui" / "src" / "i18n" / dil / "ayarlar.json").read_text(encoding="utf-8"))
    return veri["saklama"]


@pytest.mark.parametrize("anahtar", ANAHTARLAR)
def test_TR_seans_terimi_tedavi_gormeyen_YOK(anahtar):
    metin = _saklama("tr")[anahtar]
    assert "tedavi gör" not in metin, (
        f"ayarlar.saklama.{anahtar} hâlâ 'tedavi gör…' diyor (Y211 · S-D67.2): {metin[:120]}"
    )
    assert "seans yapılma" in metin, f"ayarlar.saklama.{anahtar} 'seans yapılma…' terimini taşımıyor: {metin[:120]}"


@pytest.mark.parametrize("anahtar", ANAHTARLAR)
def test_EN_with_no_session_not_treated_YOK(anahtar):
    metin = _saklama("en")[anahtar]
    assert "treated" not in metin, f"EN ayarlar.saklama.{anahtar} hâlâ 'treated' diyor: {metin[:120]}"
    assert "with no session" in metin, f"EN ayarlar.saklama.{anahtar} 'with no session' taşımıyor: {metin[:120]}"
