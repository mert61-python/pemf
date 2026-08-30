# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""TÜRKÇE ONDALIK VİRGÜL → DOZ — saha bulgusu 2026-08-30 (sayısal locale denetimi).

⚠️ HASTA GÜVENLİĞİ. `ai/hybrid_recommender` hasta kilosunu/yaşını `float(x)` ile çözüyordu.
Python `float("3,5")` → ValueError → kod SESSİZCE varsayılana düşüyordu (kilo 15 kg, yaş 5):

    3.5 kg (nokta)  → float ok → "small"  kategori → doğru doz süresi
    3,5 kg (virgül) → ValueError → 15 kg VARSAYILAN → "medium" kategori → YANLIŞ doz süresi

Yani virgülle girilmiş kilosu olan küçük bir hayvan, sessizce orta-boy dozu alıyordu. Frontend
nokta-normalize ediyor ama ESKİ kayıt / import / doğrudan-API virgül içerebilir.

DÜZELTME: `utils.turkce_metin.sayiya_cevir` — virgül-toleranslı ("3,5"→3.5). Kilo VE yaş aynı
kaynağı kullanır (iki kardeş bug tek yerde). Geçersiz girdide (harf/boş/None) varsayılan korunur.
"""

from __future__ import annotations

import pytest

from utils.turkce_metin import sayiya_cevir

# ── Util birim ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "giris,beklenen",
    [
        ("3,5", 3.5),  # Türkçe ondalık virgül
        ("3.5", 3.5),  # nokta
        ("15", 15.0),
        (3.5, 3.5),  # zaten sayı
        (7, 7.0),
        ("  4,25  ", 4.25),  # boşluklu
    ],
)
def test_KRITIK_virgul_ondalik_cozulur(giris, beklenen):
    assert sayiya_cevir(giris, None) == pytest.approx(beklenen)


@pytest.mark.parametrize("giris", ["abc", "", None, "1.234,5", "3,5,6"])
def test_gecersiz_girdi_VARSAYILANA_duser(giris):
    """Harf/boş/None/binlik-ayraç → çağıranın verdiği güvenli varsayılan (sessiz 0 DEĞİL)."""
    assert sayiya_cevir(giris, 15.0) == 15.0


def test_bool_sayi_SAYILMAZ():
    """True/False int alt-tipidir ama kiloda anlamsız → varsayılan."""
    assert sayiya_cevir(True, 15.0) == 15.0


# ── Uçtan uca: doz kategorisi ───────────────────────────────────────────────


def test_KRITIK_virgullu_kilo_DOGRU_kategori():
    """⚠️ Bug'ın kalbi: 3,5 kg 'small' olmalı, 'medium' DEĞİL (yanlış doz)."""
    from ai.hybrid_recommender import PatientProfileAdaptor

    a = PatientProfileAdaptor.__new__(PatientProfileAdaptor)
    assert a.categorize_weight(sayiya_cevir("3,5", 15.0)) == "small", (
        "virgüllü kilo hâlâ varsayılana düşüyor → yanlış doz kategorisi"
    )
    assert a.categorize_weight(sayiya_cevir("3.5", 15.0)) == "small", "nokta da small olmalı"
    # Karşıt: gerçekten orta-boy
    assert a.categorize_weight(sayiya_cevir("25", 15.0)) == "medium"


def test_KRITIK_hybrid_recommender_sayiya_cevir_KULLANIYOR():
    """⚠️ ZAYIF-ÇIPA: util doğru olsa da recommender onu ÇAĞIRMIYORSA hiçbir şey değişmez.

    Ham `float(weight)` / `float(age)` kilo/yaş için KALMAMALI."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "ai" / "hybrid_recommender.py").read_text(encoding="utf-8")
    assert "sayiya_cevir(patient_info.get('weight'" in src, "kilo parse'ı sayiya_cevir kullanmıyor"
    assert "sayiya_cevir(patient_info.get('age'" in src, "yaş parse'ı sayiya_cevir kullanmıyor"
    # Eski ham float(weight) / float(age) coerce kalmamalı
    assert "float(weight)" not in src, "ham float(weight) hâlâ var → virgül bug'ı geri gelir"
    assert "float(age)" not in src, "ham float(age) hâlâ var → virgül bug'ı geri gelir"
