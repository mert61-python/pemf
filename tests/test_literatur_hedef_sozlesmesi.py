# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Arayüzdeki tedavi hedefleri ↔ literatür protokol sözlüğü SÖZLEŞMESİ.

Denetim 2026-08-28 #01 (sessiz ölüm): arayüzün sunduğu 8 hedeften 3'ü yanlış doz alıyordu —
  * 'Enflamasyon Azaltma' → sözlükte 'inflamasyon' (İ- vs E-) → eşleşmiyor → genel wellness dozu,
  * 'Sinir Rejenerasyonu' → hiçbir anahtarla eşleşmiyor → genel wellness dozu,
  * 'Bağ Dokusu Tamiri'   → kısa 'doku' anahtarına takılıp YUMUŞAK-DOKU dozunu döndürüyordu,
    üstelik kaynak etiketi 'literature_exact' — yani arayüz doğru protokolü aldığını sanıyordu.
Üçü de SESSİZDİ: hata yok, uyarı yok, ekranda fark yok. Vet hedefe özel doz aldığını sanıyordu.

Bu kapının işi: arayüze YENİ bir hedef eklendiğinde (ya da bir sözlük anahtarı yeniden
adlandırıldığında) süit KIRMIZI olsun. Hedef listesi buraya KOPYALANMAZ — kopya, aynı sınıftan
yeni bir sessiz ölüm demektir (liste değişir, kopya eskir, test yeşil yalan söyler); tek kaynak
olan ControlScreen.tsx'ten okunur.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ai.hybrid_recommender import (
    CLINICAL_PROTOCOLS,
    clean_treatment_target,
    get_literature_recommendation,
)

_KAYNAK_TSX = Path(__file__).resolve().parents[1] / "pf" / "src" / "screens" / "ControlScreen.tsx"

# Arayüzdeki her hedefin ALMASI GEREKEN doz (freq Hz / duty % / süre dk). Bu üçlüler klinik
# protokol tablosundan gelir; sözlükteki bir değer değişirse burada da bilinçli güncellenmeli.
# Denetim öncesi ölçülen GERÇEK davranış yorumda: sessiz sapmanın büyüklüğü kayıt altında.
BEKLENEN_DOZ = {
    "Doku İyileşmesi": (105, 50.0, 30),
    "Eklem Ağrısı": (70, 50.0, 30),
    "Kas Spazmı": (97, 50.0, 25),
    "Kırık İyileşmesi": (60, 37.0, 52),
    "Enflamasyon Azaltma": (87, 47.0, 27),  # önce: 77/50/30 (wellness)
    "Sinir Rejenerasyonu": (70, 42.0, 37),  # önce: 77/50/30 (wellness)
    "Bağ Dokusu Tamiri": (75, 40.0, 37),  # önce: 105/50/30 ('doku'), kaynak yine 'literature_exact'
    "Ödem Azaltma": (110, 45.0, 25),
}


def _arayuz_hedefleri() -> list[str]:
    """ControlScreen.tsx içindeki AUTO_TARGETS dizisini oku (tek kaynak).

    Çıpa kaybolursa/boş dönerse SESSİZCE geçmek yerine testi düşürür — boş liste ile 'yeşil'
    kalmak, kapının yakalaması gereken hatanın ta kendisidir.
    """
    assert _KAYNAK_TSX.exists(), f"Arayüz kaynağı yok: {_KAYNAK_TSX}"
    metin = _KAYNAK_TSX.read_text(encoding="utf-8")
    m = re.search(r"const\s+AUTO_TARGETS\s*=\s*\[(.*?)\]\s*;", metin, re.DOTALL)
    assert m, "ControlScreen.tsx içinde 'const AUTO_TARGETS = [...]' bulunamadı (çıpa kaydı mı?)"
    hedefler = re.findall(r'"([^"]+)"', m.group(1))
    assert hedefler, "AUTO_TARGETS boş okundu — çıpa eşleşti ama içerik çıkmadı"
    return hedefler


def test_arayuz_hedefleri_okunabiliyor():
    """Kapının kendisi çalışıyor mu: liste okunuyor ve makul boyutta."""
    hedefler = _arayuz_hedefleri()
    assert len(hedefler) >= 5, f"Beklenenden az hedef okundu: {hedefler}"


@pytest.mark.parametrize("hedef", _arayuz_hedefleri())
def test_her_arayuz_hedefi_literaturde_karsilik_buluyor(hedef):
    """Hiçbir hedef sessizce genel wellness dozuna DÜŞMEZ."""
    sonuc = get_literature_recommendation(hedef)
    assert sonuc["source"] == "literature_exact", (
        f"'{hedef}' literatürde karşılık bulamadı → {sonuc['source']} "
        f"({sonuc['freq']}/{sonuc['duty']}/{sonuc['duration']}). "
        f"CLINICAL_PROTOCOLS'a bu hedefi karşılayan bir anahtar ekleyin."
    )


@pytest.mark.parametrize("hedef", _arayuz_hedefleri())
def test_her_arayuz_hedefi_dogru_dozu_aliyor(hedef):
    """Kaynak 'literature_exact' olsa bile YANLIŞ protokole düşme (Bağ Dokusu sınıfı)."""
    assert hedef in BEKLENEN_DOZ, (
        f"Arayüze yeni hedef eklenmiş ama beklenen dozu pinlenmemiş: '{hedef}'. "
        f"BEKLENEN_DOZ sözlüğüne klinik protokol üçlüsünü ekleyin."
    )
    beklenen = BEKLENEN_DOZ[hedef]
    sonuc = get_literature_recommendation(hedef)
    alinan = (sonuc["freq"], sonuc["duty"], sonuc["duration"])
    assert alinan == beklenen, f"'{hedef}' yanlış doz aldı: {alinan} ≠ {beklenen} (kaynak={sonuc['source']})"


@pytest.mark.parametrize("anahtar", sorted(CLINICAL_PROTOCOLS.keys()))
def test_her_sozluk_anahtari_kendisiyle_eslesiyor(anahtar):
    """Türkçe katlama sınıfının genel kapısı: sözlüğe eklenen her anahtar, girdi olarak
    verildiğinde KENDİ protokolünü döndürmeli. 'İ/ı/ğ/ö/ç/ş/ü' içeren yeni bir anahtar
    normalizasyonla uyuşmazsa burada patlar (ölü anahtar = sessiz yanlış doz)."""
    sonuc = get_literature_recommendation(anahtar)
    assert sonuc["source"] == "literature_exact", f"Sözlük anahtarı '{anahtar}' kendisiyle eşleşmiyor (ölü anahtar)"
    beklenen = CLINICAL_PROTOCOLS[anahtar]
    assert sonuc["freq"] == int(beklenen["freq"]), f"'{anahtar}' başka bir protokole eşleşti"
    assert sonuc["duration"] == int(beklenen["duration"]), f"'{anahtar}' başka bir protokole eşleşti"


def test_bilinmeyen_hedef_wellnesse_duser_ve_kaynagi_belli_eder(caplog):
    """Düşüş yolu KORUNUR (hedef bulunmasa da doz döner) ama artık SESSİZ değil:
    kaynak 'default_wellness' ve sunucu günlüğünde uyarı var."""
    import logging

    with caplog.at_level(logging.WARNING, logger="ai.hybrid_recommender"):
        sonuc = get_literature_recommendation("Zzz Olmayan Hedef 12345")
    assert sonuc["source"] == "default_wellness"
    assert sonuc["freq"] == 77, "wellness dozu değişmiş"
    assert any("wellness" in r.message.lower() or "wellness" in r.getMessage().lower() for r in caplog.records), (
        "Wellness'a düşüş SESSİZ kaldı — uyarı günlüğe yazılmalı (denetim #01)"
    )
